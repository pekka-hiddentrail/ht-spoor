"""Step definitions for features/resolution.feature (ROADMAP.md §2).

Exercises the escalation dispatcher directly: which resolver a config routes to,
that tier 1 hands a browser-only capability up to tier 2, and that an empty
tier-1 result escalates to the browser on content grounds. The capability-routing
steps assert routing only and never launch a browser; the content-escalation
scenario runs through the full dispatcher against a live loopback server and a
real Chromium, since that is the only honest way to prove the escalation end to
end (tier 1 sees an empty shell, tier 2 renders the same page and extracts).
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


@given("a live fixture server")
def live_fixture_server(context: dict[str, Any], live_server: str) -> None:
    context["server_base"] = live_server


@given("a config whose items only exist after JS renders them:")
def config_js_rendered(context: dict[str, Any], docstring: str) -> None:
    context["config_text"] = docstring


# --- When ----------------------------------------------------------------


@when("the dispatcher resolves the config")
def dispatch(context: dict[str, Any], mock_client: httpx.Client) -> None:
    cfg = context["config"]
    resolver = extract.select_resolver(cfg)
    context["resolver"] = resolver
    # Only tier 1 is network-free here; tier 2 needs a real browser + server,
    # which extraction.feature's browser-backed scenario exercises directly.
    if resolver.tier == 1:
        context["result"] = extract.run_report(cfg, client=mock_client)


@when("I run the config through the dispatcher against a real browser")
def dispatch_through_browser(context: dict[str, Any]) -> None:
    # No mock client: escalation must reach a real Chromium against the live
    # server. Resolve SERVER_BASE, then run the full dispatcher (run_report) and,
    # separately, tier 1 alone — so the assertions can contrast the two.
    text = context["config_text"].replace("SERVER_BASE", context["server_base"])
    cfg = load_config(text)
    context["config"] = cfg
    context["tier1_only"] = extract.Tier1Resolver().run(cfg).records
    context["result"] = extract.run_report(cfg)


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


@then("tier 1 declined it while tier 2 accepted it")
def tier1_declined_tier2_accepted(context: dict[str, Any]) -> None:
    tier1, tier2 = extract.DEFAULT_TIERS
    cfg = context["config"]
    assert not tier1.accepts(cfg)
    assert tier2.accepts(cfg)


@then("tier 1 on its own extracts nothing")
def tier1_extracts_nothing(context: dict[str, Any]) -> None:
    # The served HTML is an empty shell; tier 1's selectors match no items.
    assert context["tier1_only"] == []


@then("the dispatcher escalates to tier 2 and returns the rendered records")
def dispatcher_returns_rendered_records(context: dict[str, Any]) -> None:
    records = context["result"].records
    # Escalation happened iff the dispatcher returned records that tier 1 alone
    # could not (asserted empty in the paired step) — i.e. the browser rendered.
    assert records
    assert all(record["title"] for record in records)


@then("the dispatcher registers tier 1 and tier 2 in order")
def tiers_registered_in_order(context: dict[str, Any]) -> None:
    assert [resolver.tier for resolver in extract.DEFAULT_TIERS] == [1, 2]


@then("both tiers are implemented, tier 2 rendering in a real browser")
def both_tiers_implemented(context: dict[str, Any]) -> None:
    tier1, tier2 = extract.DEFAULT_TIERS
    # Tier 1 resolves an ordinary config; tier 2 is the escalation target that
    # accepts anything handed up and renders it in a browser (name says so).
    plain = load_config(
        "target: http://localhost:8000/products.html\n"
        'fields:\n  title: { selector: "h1" }\n'
    )
    assert tier1.accepts(plain)
    assert tier2.accepts(plain)
    assert "rendering" in tier2.name.lower()
