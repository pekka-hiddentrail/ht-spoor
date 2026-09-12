"""End-to-end extraction against the live archetype bench (ROADMAP.md §5.1).

This is the first time the generic tiers meet a real, uncontrolled app rather
than a checked-in fixture. OWASP Juice Shop is an Angular SPA whose product
listing renders client-side, which makes it a faithful two-sided test of what
Phase 1 built:

- tier 1 (static fetch) sees only the empty app shell -> zero records, which is
  *why* the browser tier exists;
- tier 2 (headless render) resolves the same config against the rendered DOM and
  extracts real products, including `number` coercion of a currency-tagged price,
  matched against a committed golden master (§5.4 dogfooding).

Marked `integration`: it needs the docker bench up
(`docker compose -f fixtures/docker-compose.yml up -d`) and skips cleanly when
the container isn't reachable, so the fast unit gate stays Docker-free.

Note on routing: today the dispatcher escalates to tier 2 only for a browser-only
*capability* (infinite scroll); "tier 1 came up empty, try rendering" is a
separate capability deliberately deferred until tier 2 was real (see the
dispatcher-seam decision in ROADMAP §2). Until it lands, this test exercises the
tier-2 resolver directly rather than pretending the dispatcher auto-selected it.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from spoor.core import extract
from spoor.core.config import ExtractionConfig, load_config

JUICE_SHOP_BASE = "http://127.0.0.1:3000"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "fixtures" / "configs" / "juice-shop-products.yaml"
# Committed baseline for §5.4 dogfooding: the deterministic output of the pinned
# Juice Shop image, so a diff surfaces any silent change in Spoor OR the fixture.
_GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "juice-shop-products.json"
# Where a run's actual output lands — a known, durable directory (not a temp
# folder), so it can be uploaded as a CI artifact and inspected on a mismatch.
_RUN_OUTPUT_PATH = _REPO_ROOT / "test-output" / "juice-shop-products.json"

pytestmark = pytest.mark.integration


def _sorted_by_name(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Stable ordering for comparison — the page's render order isn't a contract."""
    return sorted(records, key=lambda record: str(record["name"]))


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


def test_tier1_cannot_resolve_the_spa(
    juice_shop: str, config: ExtractionConfig
) -> None:
    # The static tier fetches the app shell, which carries no rendered products.
    result = extract.Tier1Resolver().run(config)
    assert result.blocked == []
    assert result.records == []


def test_tier2_matches_golden_master(
    juice_shop: str, config: ExtractionConfig
) -> None:
    result = extract.Tier2Resolver().run(config)
    assert result.blocked == []
    records = _sorted_by_name(result.records)

    # Persist the run to a durable path (uploaded as a CI artifact), then diff
    # against the committed golden master (§5.4). Writing first means a mismatch
    # leaves the actual output on disk to inspect, not just an assertion error.
    _RUN_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RUN_OUTPUT_PATH.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    assert records == golden, (
        "Juice Shop extraction drifted from the golden master; inspect "
        f"{_RUN_OUTPUT_PATH} against {_GOLDEN_PATH}"
    )
