"""Step definitions for features/serving_mcp.feature (ROADMAP.md §2f).

The MCP serving mode is a read-only server over the same map store as the REST
API. These steps build a store backed by a temp cache root, populate it the way
a run would, build the MCP server over it, and drive its tools in-process
(`list_tools` / `call_tool`, run synchronously via `asyncio.run`) — pinning the
read-only contract and that answers match the REST surface's redaction/freshness.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from _serving_fixtures import EXPLORE_SECRET, explored_graph
from mcp.server.mcpserver.exceptions import ToolError
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.security import storage
from spoor.serving.mcp_server import create_mcp_server
from spoor.serving.store import MapStore, shareable_exploration_map

scenarios("serving_mcp.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {}


@pytest.fixture(autouse=True)
def temp_cache_root(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the local cache root so the map store writes under a temp dir."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / ".spoor-cache")


def _tool_json(context: dict[str, Any], name: str, arguments: dict[str, Any]) -> Any:
    """Call an MCP tool and parse its JSON text payload."""
    result = asyncio.run(context["server"].call_tool(name, arguments))
    return json.loads(result.content[0].text)


# --- Given ---------------------------------------------------------------


@given("an MCP server over a map containing:")
def mcp_server_over_map(context: dict[str, Any], datatable: list[list[str]]) -> None:
    store = MapStore()
    header, *rows = datatable
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        store.record(
            fields["url"],
            [{"title": fields["title"]}],
            tier=1,
            captured_at=datetime.fromisoformat(fields["captured_at"]),
        )
    context["store"] = store
    context["server"] = create_mcp_server(store)


@given("the MCP server allows force-recheck")
def mcp_allows_recheck(context: dict[str, Any]) -> None:
    # Rebuild the server with a recheck seam. The fake stands in for a real
    # read/observation run: re-record the URL (title marked "(rechecked)") with a
    # fresh capture time, or return None for an unmapped URL — which recheck_map
    # turns into a not-mapped error. No real target is touched.
    store: MapStore = context["store"]

    def fake_recheck(url: str) -> Any:
        existing = store.get(url)
        if existing is None:
            return None
        old_title = existing.records[0]["title"]
        return store.record(
            url,
            [{"title": f"{old_title} (rechecked)"}],
            tier=existing.tier,
            captured_at=datetime.now(UTC),
        )

    context["server"] = create_mcp_server(store, recheck=fake_recheck)


@given(parsers.parse('an explored graph is mapped for "{url}"'))
def map_explored_graph(context: dict[str, Any], url: str) -> None:
    # Record the projected exploration graph after the server was built; the store
    # reads from disk per call, so the same server serves the freshly-added entry.
    MapStore().record(
        url,
        [{"title": "App"}],
        tier=2,
        exploration=shareable_exploration_map(explored_graph()),
        captured_at=datetime.fromisoformat("2020-01-01T00:00:00Z"),
    )


# --- When ----------------------------------------------------------------


@when(parsers.parse('I call the MCP tool "{name}" with url "{url}"'))
def call_get_map(context: dict[str, Any], name: str, url: str) -> None:
    try:
        context["result"] = _tool_json(context, name, {"url": url})
        context["error"] = None
    except ToolError as exc:
        context["error"] = exc


@when(parsers.parse('I call the MCP tool "{name}"'))
def call_no_args(context: dict[str, Any], name: str) -> None:
    context["result"] = _tool_json(context, name, {})


# --- Then ----------------------------------------------------------------


@then(parsers.parse('the MCP tools are exactly "{a}" and "{b}"'))
def tools_are_exactly(context: dict[str, Any], a: str, b: str) -> None:
    tools = asyncio.run(context["server"].list_tools())
    assert {t.name for t in tools} == {a, b}


@then(parsers.parse('the MCP tools are exactly "{a}", "{b}" and "{c}"'))
def tools_are_exactly_three(context: dict[str, Any], a: str, b: str, c: str) -> None:
    tools = asyncio.run(context["server"].list_tools())
    assert {t.name for t in tools} == {a, b, c}


@then("every MCP tool is marked non-destructive")
def tools_non_destructive(context: dict[str, Any]) -> None:
    # The reframed §2f guarantee: even the recheck tool, which is honestly not
    # read-only, never advertises a destructive effect on a target.
    tools = asyncio.run(context["server"].list_tools())
    assert tools, "expected the MCP server to expose tools"
    for tool in tools:
        ann = tool.annotations
        assert ann is not None and ann.destructive_hint is False, tool.name


@then(parsers.parse('the "{name}" tool is not marked read-only'))
def tool_not_read_only(context: dict[str, Any], name: str) -> None:
    tools = asyncio.run(context["server"].list_tools())
    tool = next(t for t in tools if t.name == name)
    ann = tool.annotations
    assert ann is not None and ann.read_only_hint is False, name


@then("every MCP tool is marked read-only and non-destructive")
def tools_read_only(context: dict[str, Any]) -> None:
    # Structural proof of the §2f non-negotiable: no exposed tool advertises a
    # state-changing or destructive effect.
    tools = asyncio.run(context["server"].list_tools())
    assert tools, "expected the MCP server to expose tools"
    for tool in tools:
        ann = tool.annotations
        assert ann is not None and ann.read_only_hint is True, tool.name
        assert ann.destructive_hint is False, tool.name


@then(parsers.parse('the MCP result\'s first record "{field}" equals "{value}"'))
def first_record_field(context: dict[str, Any], field: str, value: str) -> None:
    assert context["result"]["records"][0][field] == value


@then("the MCP result carries a capture time and a non-negative age")
def result_freshness(context: dict[str, Any]) -> None:
    result = context["result"]
    assert isinstance(result["captured_at"], str) and result["captured_at"]
    assert isinstance(result["age_seconds"], (int, float))
    assert result["age_seconds"] >= 0


@then("the MCP call fails with a not-mapped error")
def call_failed(context: dict[str, Any]) -> None:
    assert isinstance(context["error"], ToolError)
    assert "not mapped" in str(context["error"]).lower()


@then(parsers.parse('the MCP domains include "{domain}"'))
def domains_include(context: dict[str, Any], domain: str) -> None:
    assert domain in context["result"]["domains"]


@then(
    parsers.parse(
        "the MCP result's exploration graph has {states:d} states "
        "and {transitions:d} transition"
    )
)
def mcp_exploration_counts(
    context: dict[str, Any], states: int, transitions: int
) -> None:
    counts = context["result"]["exploration"]["counts"]
    assert counts["states"] == states
    assert counts["transitions"] == transitions


@then("the MCP result's exploration graph exposes no raw secret")
def mcp_exploration_redacted(context: dict[str, Any]) -> None:
    # The MCP surface shares `map_view`, so the same redaction guard applies; the
    # raw token must not survive into the tool result and the placeholder must.
    body = json.dumps(context["result"])
    assert EXPLORE_SECRET not in body
    assert "[REDACTED]" in body
