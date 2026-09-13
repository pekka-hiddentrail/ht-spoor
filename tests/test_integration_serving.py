"""End-to-end serving round-trip against the live archetype bench (§5.1, §2f/§2h).

The Juice Shop and Sauce Demo integration tests prove *extraction* holds against
a real, uncontrolled app. This one carries that same run one hop further, through
the read-only serving layer (§2f) — the part built in isolation against synthetic
`MapStore` data and never yet exercised end to end against a real capture.

The full wired path, exactly as `spoor run` does it: run the dispatcher against
live Juice Shop, project the observed API surface to its §2h-shareable form,
record the result into the persisted map, then read it back with a *fresh* store
(so the JSON round-trip through disk is real, not an in-memory shortcut) and serve
it over both surfaces:

- the REST API (`api.py`), driven through Starlette's `TestClient`;
- the MCP server (`mcp_server.py`), driven in-process via `call_tool`.

Both must answer with the same records the run produced (post-redaction, §2h),
carry a non-negative freshness age (§2f), agree with each other, and refuse a URL
that was never mapped rather than fabricate one. Read-only is asserted
structurally on the MCP surface (every exposed tool marked read-only /
non-destructive) — the §2f non-negotiable, now proven against a real capture.

Marked `integration`: it needs the docker bench up
(`docker compose -f fixtures/docker-compose.yml up -d`) and skips cleanly when the
container isn't reachable, so the fast unit gate stays Docker-free.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from starlette.testclient import TestClient

from spoor.core import extract
from spoor.core.config import ExtractionConfig, load_config
from spoor.security import storage
from spoor.security.redaction import redact_records
from spoor.serving.api import create_app
from spoor.serving.mcp_server import create_mcp_server
from spoor.serving.store import MapStore, shareable_api_surface

JUICE_SHOP_BASE = "http://127.0.0.1:3000"
_UNMAPPED_URL = "http://127.0.0.1:3000/#/never-mapped"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "fixtures" / "configs" / "juice-shop-products.yaml"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def juice_shop() -> str:
    """Skip the module unless the Juice Shop bench answers on its port."""
    try:
        response = httpx.get(f"{JUICE_SHOP_BASE}/", timeout=3.0)
        response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        pytest.skip(
            "Juice Shop bench not reachable — start it with "
            "`docker compose -f fixtures/docker-compose.yml up -d` "
            f"({exc})"
        )
    return JUICE_SHOP_BASE


@pytest.fixture(scope="module")
def config() -> ExtractionConfig:
    return load_config(_CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def served_map(
    juice_shop: str,
    config: ExtractionConfig,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch_module: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Run the dispatcher once, record it as `spoor run` does, read it back fresh.

    Module-scoped so the (slow) live browser run happens once; both surfaces then
    read the same persisted map. Returns the run's records (the round-trip oracle)
    alongside the mapped URL and a fresh store the served surfaces are built over.
    """
    cache_root = tmp_path_factory.mktemp("serving-cache") / ".spoor-cache"
    monkeypatch_module.setattr(storage, "CACHE_ROOT", cache_root)

    result = extract.run_report(config)
    # The exact wiring the CLI's `run` command performs (§2f/§2h).
    surface = shareable_api_surface(
        api_spec=result.api_spec,
        graphql=result.graphql,
        synthesized_spec=result.synthesized_spec,
        action_correlation=result.action_correlation,
    )
    MapStore().record(
        config.target, result.records, tier=result.tier, api_surface=surface
    )
    # A *fresh* store: forces the read back through the on-disk JSON, not memory.
    return {
        "store": MapStore(),
        "url": config.target,
        "records": result.records,
        "tier": result.tier,
    }


@pytest.fixture(scope="module")
def monkeypatch_module() -> Any:
    """A module-scoped MonkeyPatch (the built-in `monkeypatch` is function-scoped)."""
    patcher = pytest.MonkeyPatch()
    yield patcher
    patcher.undo()


def _mcp_json(server: Any, name: str, arguments: dict[str, Any]) -> Any:
    """Call an MCP tool and parse its JSON text payload (as the step defs do)."""
    result = asyncio.run(server.call_tool(name, arguments))
    return json.loads(result.content[0].text)


def test_rest_surface_serves_the_real_capture(served_map: dict[str, Any]) -> None:
    client = TestClient(create_app(served_map["store"]))

    assert client.get("/healthz").json() == {"status": "ok"}

    domain = urlsplit(served_map["url"]).netloc
    assert domain in client.get("/domains").json()["domains"]

    body = client.get("/map", params={"url": served_map["url"]}).json()
    # Round-trip integrity: what is served equals what the run captured, after the
    # §2h redaction guard on the way out (identity here — product names hold no
    # secrets — but proves the guarded path carries real data faithfully).
    assert body["records"] == redact_records(served_map["records"])
    assert body["tier"] == served_map["tier"]
    assert body["age_seconds"] >= 0
    assert body["captured_at"]

    # A URL that was never mapped is a 404, never a fabricated answer.
    assert client.get("/map", params={"url": _UNMAPPED_URL}).status_code == 404


def test_mcp_surface_serves_the_real_capture(served_map: dict[str, Any]) -> None:
    server = create_mcp_server(served_map["store"])

    # Read-only, always (§2f non-negotiable) — asserted against a real capture.
    tools = asyncio.run(server.list_tools())
    assert tools, "expected the MCP server to expose tools"
    for tool in tools:
        ann = tool.annotations
        assert ann is not None and ann.read_only_hint is True, tool.name
        assert ann.destructive_hint is False, tool.name

    domain = urlsplit(served_map["url"]).netloc
    assert domain in _mcp_json(server, "list_mapped_domains", {})["domains"]

    body = _mcp_json(server, "get_map", {"url": served_map["url"]})
    assert body["records"] == redact_records(served_map["records"])
    assert body["tier"] == served_map["tier"]
    assert body["age_seconds"] >= 0
    assert body["captured_at"]

    # Both surfaces answer identically for the same URL.
    rest = TestClient(create_app(served_map["store"]))
    rest_body = rest.get("/map", params={"url": served_map["url"]}).json()
    assert body["records"] == rest_body["records"]

    # An unmapped URL is an error, not a fabricated answer.
    with pytest.raises(ToolError):
        _mcp_json(server, "get_map", {"url": _UNMAPPED_URL})
