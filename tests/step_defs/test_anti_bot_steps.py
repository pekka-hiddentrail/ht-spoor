"""Step definitions for features/anti_bot.feature (ROADMAP.md §2d, Phase 3.5).

Challenge detection is a scan of the fetched HTML for generic anti-bot-vendor
markers, so — like the politeness and retry scenarios — these drive an in-memory
httpx MockTransport, no browser or network needed. The dispatcher is pinned to
**tier 1**: a challenge page extracts zero records, which would otherwise
escalate to a real browser the MockTransport can't drive. Detection itself is
tier-agnostic (the same `detect_challenge` runs on tier 2's rendered HTML), and
that cross-tier reuse is covered by the unit tests.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary

scenarios("anti_bot.feature")

_TARGET = "http://localhost:8000/product.html"
_TARGET_PATH = "/product.html"

# A reCAPTCHA widget with no product markup: a challenge, not data.
_RECAPTCHA = (
    "<html><head><title>Verify you are human</title></head>"
    '<body><form><div class="g-recaptcha" data-sitekey="x"></div></form></body></html>'
)
# A Cloudflare interstitial: the classic "just a moment" holding page.
_CLOUDFLARE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>Checking your browser before accessing the site."
    '<div class="cf-turnstile"></div></body></html>'
)
_ORDINARY = '<html><body><h1 class="product-title">Gizmo</h1></body></html>'


@pytest.fixture
def context() -> dict[str, Any]:
    """Per-scenario state: the target's response body, config, and run outputs."""
    return {}


# --- Given ----------------------------------------------------------------


@given(parsers.parse('a config fetching the "{field}" from "{selector}"'))
def anti_bot_config(context: dict[str, Any], field: str, selector: str) -> None:
    context["field"] = field
    context["config_text"] = (
        f"target: {_TARGET}\n"
        "fields:\n"
        f'  {field}: {{ selector: "{selector}" }}\n'
    )


@given("the target returns a page guarded by reCAPTCHA")
def target_recaptcha(context: dict[str, Any]) -> None:
    context["body"] = _RECAPTCHA


@given("the target returns a Cloudflare interstitial")
def target_cloudflare(context: dict[str, Any]) -> None:
    context["body"] = _CLOUDFLARE


@given("the target returns an ordinary product page")
def target_ordinary(context: dict[str, Any]) -> None:
    context["body"] = _ORDINARY


# --- When -----------------------------------------------------------------


@when("I run the config")
def run_the_config(context: dict[str, Any]) -> None:
    body = context["body"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _TARGET_PATH:
            return httpx.Response(200, text=body)
        return httpx.Response(404, text="not found")

    cfg = load_config(context["config_text"])
    # Pin to tier 1 (see module docstring): a challenge page has zero records and
    # would otherwise escalate to a browser the MockTransport can't drive.
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract.run_report(
            cfg, client=client, tiers=(extract.Tier1Resolver(),)
        )
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


# --- Then -----------------------------------------------------------------


@then("the field is extracted")
def field_extracted(context: dict[str, Any]) -> None:
    records = context["result"].records
    assert len(records) == 1
    assert records[0][context["field"]] is not None


@then("no real data is extracted")
def no_real_data(context: dict[str, Any]) -> None:
    # A single-record config always emits one record; on a challenge page the
    # requested field finds nothing and stays null — the challenge markup is
    # never scraped into it as if it were data (the whole point of §2d detection).
    records = context["result"].records
    assert all(value is None for record in records for value in record.values())


@then(parsers.parse('the run reports an anti-bot challenge from "{vendor}"'))
def reports_challenge(context: dict[str, Any], vendor: str) -> None:
    challenge = context["summary"].challenge
    assert challenge is not None
    assert challenge.vendor == vendor


@then("the run reports no anti-bot challenge")
def reports_no_challenge(context: dict[str, Any]) -> None:
    assert context["summary"].challenge is None
