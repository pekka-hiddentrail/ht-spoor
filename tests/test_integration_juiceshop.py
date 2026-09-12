"""End-to-end extraction against the live archetype bench (ROADMAP.md §5.1).

This is the first time the generic tiers meet a real, uncontrolled app rather
than a checked-in fixture. OWASP Juice Shop is an Angular SPA whose product
listing renders client-side, which makes it a faithful two-sided test of what
Phase 1 built:

- tier 1 (static fetch) sees only the empty app shell -> zero records, which is
  *why* the browser tier exists;
- tier 2 (headless render) resolves the same config against the rendered DOM and
  extracts real products, including `number` coercion of a currency-tagged price.

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

from pathlib import Path

import httpx
import pytest

from spoor.core import extract
from spoor.core.config import ExtractionConfig, load_config

JUICE_SHOP_BASE = "http://127.0.0.1:3000"
_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "configs"
    / "juice-shop-products.yaml"
)

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


def test_tier1_cannot_resolve_the_spa(
    juice_shop: str, config: ExtractionConfig
) -> None:
    # The static tier fetches the app shell, which carries no rendered products.
    result = extract.Tier1Resolver().run(config)
    assert result.blocked == []
    assert result.records == []


def test_tier2_extracts_real_products(
    juice_shop: str, config: ExtractionConfig
) -> None:
    result = extract.Tier2Resolver().run(config)
    # Juice Shop lists a full page of products; assert a healthy count rather
    # than an exact number so a paginator/page-size tweak upstream isn't brittle.
    assert len(result.records) >= 6
    assert result.blocked == []
    for record in result.records:
        name = record["name"]
        assert isinstance(name, str) and name.strip()
        # `type: number` must coerce the currency-tagged price to a real number.
        assert isinstance(record["price"], float)
