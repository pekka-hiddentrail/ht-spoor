"""Step definitions for features/retry.feature (ROADMAP.md §2d, Phase 3.5).

Retry/error classification is about HTTP status and transport outcomes, not page
content, so — like the politeness scenarios — these drive an in-memory httpx
MockTransport whose handler is *scripted* per call: it can return a 503 on the
first request to the target and the real page on the next, letting a bounded
retry be observed without a real flaky server, real ports, or real sleeping (the
backoff wait is asserted through an injected recording `sleep`).

The dispatcher is pinned to **tier 1**: this slice is the tier-1 httpx fetch
path, and a dead-lettered run (zero records) would otherwise escalate to a real
browser — which a MockTransport can't drive. The escalation-suppression that
change relies on is unit-tested separately against `_should_escalate`.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary

scenarios("retry.feature")

_TARGET = "http://localhost:8000/product.html"
_TARGET_PATH = "/product.html"
_PAGE = '<html><body><h1 class="product-title">Gizmo</h1></body></html>'


@pytest.fixture
def context() -> dict[str, Any]:
    """Per-scenario state: the scripted responses, config, and run outputs."""
    # `script` is a list of (status, headers, body); the target's Nth request
    # returns the Nth entry, and the last entry repeats for any further request
    # (so "always 503" is a single-entry script).
    return {"script": []}


# --- Given ----------------------------------------------------------------


@given(parsers.parse('a config fetching the "{field}" from "{selector}"'))
def retry_config(context: dict[str, Any], field: str, selector: str) -> None:
    context["field"] = field
    context["config_text"] = (
        f"target: {_TARGET}\n"
        "fields:\n"
        f'  {field}: {{ selector: "{selector}" }}\n'
    )


@given("the target returns 503 once, then the page")
def transient_then_page(context: dict[str, Any]) -> None:
    context["script"] = [
        (503, {}, "service unavailable"),
        (200, {}, _PAGE),
    ]


@given("the target always returns 503")
def always_503(context: dict[str, Any]) -> None:
    context["script"] = [(503, {}, "service unavailable")]


@given("the target returns 404")
def returns_404(context: dict[str, Any]) -> None:
    context["script"] = [(404, {}, "not found")]


@given(
    parsers.parse(
        "the target returns 503 with a Retry-After of {seconds:d} seconds once, "
        "then the page"
    )
)
def retry_after_then_page(context: dict[str, Any], seconds: int) -> None:
    context["script"] = [
        (503, {"Retry-After": str(seconds)}, "service unavailable"),
        (200, {}, _PAGE),
    ]


# --- When -----------------------------------------------------------------


@when("I run the config")
def run_the_config(context: dict[str, Any]) -> None:
    script = context["script"]
    calls = {"n": 0}
    sleeps: list[float] = []
    context["sleeps"] = sleeps

    def handler(request: httpx.Request) -> httpx.Response:
        # Only the target path is scripted; robots.txt and the API-surface probes
        # fall through to a 404 (nothing to obey / nothing discovered).
        if request.url.path == _TARGET_PATH:
            index = min(calls["n"], len(script) - 1)
            calls["n"] += 1
            status, headers, body = script[index]
            return httpx.Response(status, headers=headers, text=body)
        return httpx.Response(404, text="not found")

    cfg = load_config(context["config_text"])
    # Pin to tier 1 (see module docstring): this is the tier-1 fetch path, and a
    # dead-lettered run must not escalate to a real browser under MockTransport.
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract.run_report(
            cfg,
            client=client,
            sleep=sleeps.append,
            tiers=(extract.Tier1Resolver(),),
        )
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


# --- Then -----------------------------------------------------------------


@then("the field is extracted")
def field_extracted(context: dict[str, Any]) -> None:
    records = context["result"].records
    assert len(records) == 1
    assert records[0][context["field"]] is not None


@then("no records are extracted")
@then("the run does not crash")
def no_records(context: dict[str, Any]) -> None:
    # Reaching here at all proves the run returned instead of raising; assert the
    # empty result too so the step earns its keep.
    assert context["result"].records == []


@then(parsers.parse("the run reports {count:d} transient retry"))
@then(parsers.parse("the run reports {count:d} transient retries"))
def reports_retries(context: dict[str, Any], count: int) -> None:
    assert context["summary"].retries == count


@then("nothing is dead-lettered")
def nothing_dead_lettered(context: dict[str, Any]) -> None:
    assert context["summary"].dead_letter == []


@then(parsers.parse('the target is dead-lettered with reason "{reason}"'))
def dead_lettered_with_reason(context: dict[str, Any], reason: str) -> None:
    dead_letter = context["summary"].dead_letter
    assert len(dead_letter) == 1
    failure = dead_letter[0]
    assert failure.url == _TARGET
    assert failure.reason == reason


@then(parsers.parse("it waited {seconds:d} seconds before retrying"))
def waited_before_retrying(context: dict[str, Any], seconds: int) -> None:
    # The only wait in this scenario is the retry backoff (no crawl-delay is set),
    # and it must equal the server's Retry-After, not the default backoff.
    assert context["sleeps"] == [float(seconds)]
