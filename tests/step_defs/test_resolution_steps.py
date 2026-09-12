"""Step definitions for features/resolution.feature (ROADMAP.md §2).

Exercises the escalation dispatcher directly: which resolver a config selects,
and that escalating to the not-yet-built tier 2 surfaces a clear error rather
than crashing or silently mishandling the request.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config

scenarios("resolution.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('a fixture page at "{url}"'))
def fixture_page(context: dict[str, Any], url: str) -> None:
    context["base_url"] = url


@given("a config that tier 1 can fully satisfy:")
def config_tier1(context: dict[str, Any], docstring: str) -> None:
    context["config"] = load_config(docstring)


@given("a config that needs JS-rendered (infinite-scroll) pagination:")
def config_needs_browser(context: dict[str, Any], docstring: str) -> None:
    context["config"] = load_config(docstring)


# --- When ----------------------------------------------------------------


@when("the dispatcher resolves the config")
def dispatch(context: dict[str, Any], mock_client: httpx.Client) -> None:
    cfg = context["config"]
    context["resolver"] = extract.select_resolver(cfg)
    try:
        context["result"] = extract.run_report(cfg, client=mock_client)
    except extract.TierUnavailableError as exc:
        context["error"] = exc


# --- Then ----------------------------------------------------------------


@then("tier 1 handles the run")
def tier1_handles(context: dict[str, Any]) -> None:
    assert context["resolver"].tier == 1
    assert context.get("error") is None


@then("the run produces records without engaging a higher tier")
def records_no_higher_tier(context: dict[str, Any]) -> None:
    assert context["result"].records
    assert context["resolver"].tier == 1


@then("the run escalates past tier 1 to tier 2")
def escalates_to_tier2(context: dict[str, Any]) -> None:
    assert context["resolver"].tier == 2


@then("it fails with a clear message that tier 2 is not yet available")
def clear_unavailable_message(context: dict[str, Any]) -> None:
    error = context.get("error")
    assert isinstance(error, extract.TierUnavailableError)
    message = str(error).lower()
    assert "tier-2" in message
    assert "not yet available" in message


@then("the dispatcher registers tier 1 and tier 2 in order")
def tiers_registered_in_order(context: dict[str, Any]) -> None:
    assert [resolver.tier for resolver in extract.DEFAULT_TIERS] == [1, 2]


@then("tier 1 is implemented while tier 2 is a declared stub")
def tier2_is_stub(context: dict[str, Any]) -> None:
    tier1, tier2 = extract.DEFAULT_TIERS
    # Tier 1 resolves an ordinary config; tier 2 accepts anything it is handed
    # (it is the escalation target) but its stub refuses to run.
    plain = load_config(
        "target: http://localhost:8000/products.html\n"
        'fields:\n  title: { selector: "h1" }\n'
    )
    assert tier1.accepts(plain)
    assert tier2.accepts(plain)
    with pytest.raises(extract.TierUnavailableError):
        tier2.run(plain, None)
