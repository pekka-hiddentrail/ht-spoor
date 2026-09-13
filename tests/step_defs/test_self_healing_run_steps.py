"""Step definitions for features/self_healing_runs.feature (ROADMAP.md §2, §2d).

Drives the dispatcher end to end through an in-memory httpx MockTransport (tier 1,
no browser, no network), with the persistent per-domain fingerprint cache pointed
at a per-scenario temp directory (`storage.CACHE_ROOT` monkeypatched) so a first
run's learned fingerprint survives into a second run — the whole point of tier-3
persistence. Assertions are against the extracted record and the `RunSummary`'s
heal counts, never any matched text (§2h).

The served page body is mutable: a scenario records a fingerprint on the original
markup, then swaps in changed markup before the next run so the field's selector
genuinely breaks and tier 3 has something to heal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary
from spoor.security import storage

scenarios("self_healing_runs.feature")

_TARGET = "http://localhost:8000/product.html"
_PATH = "/product.html"

# Original single-record page: the "name" field's selector (h2.title) resolves the
# unique "Beta Gadget" heading, which is fingerprinted on a successful run.
_ORIGINAL = (
    "<html><body><main>"
    '<section class="card"><h2 class="title" data-pos="1">Beta Gadget</h2></section>'
    "</main></body></html>"
)

# Class renamed: h2.title matches nothing, but the heading's unique text, tag, and
# structure survive — enough for a confident heal.
_CLASS_RENAMED = _ORIGINAL.replace('class="title"', 'class="heading"')

# Unrelated markup: nothing resembles the stored heading, so the best candidate
# scores well below the confidence threshold — an uncertain match, field left null.
_UNRELATED = (
    "<html><body>"
    '<div class="banner"><p>Totally different unrelated content here</p></div>'
    "<footer><small>copyright notice</small></footer>"
    "</body></html>"
)

# A page that simply never matched h2.title and was never fingerprinted.
_NO_MATCH = "<html><body><p>No heading here at all</p></body></html>"


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Per-scenario state, with the fingerprint cache under a fresh temp root."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    return {"body": _ORIGINAL}


def _run(context: dict[str, Any]) -> None:
    body = context["body"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _PATH:
            return httpx.Response(200, text=body)
        return httpx.Response(404, text="not found")

    cfg = load_config(context["config_text"])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract.run_report(cfg, client=client, sleep=lambda _: None)
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


# --- Given ---------------------------------------------------------------


@given(parsers.parse('a config extracting a "{name}" field with selector "{selector}"'))
def config_field(context: dict[str, Any], name: str, selector: str) -> None:
    context["field_name"] = name
    context["config_text"] = (
        f"target: {_TARGET}\nfields:\n  {name}: {{ selector: \"{selector}\" }}\n"
    )


@given("a first run has recorded that field's fingerprint")
def first_run_records(context: dict[str, Any]) -> None:
    context["body"] = _ORIGINAL
    _run(context)
    # Invariant: the original run actually resolved (and so fingerprinted) the field.
    assert context["result"].records[0][context["field_name"]] is not None


@given(parsers.parse('the page markup does not match "{selector}"'))
def page_does_not_match(context: dict[str, Any], selector: str) -> None:
    context["body"] = _NO_MATCH


# --- When ----------------------------------------------------------------


@when(parsers.parse('the page markup changes so "{selector}" matches nothing'))
def markup_changes(context: dict[str, Any], selector: str) -> None:
    context["body"] = _CLASS_RENAMED


@when("the page is replaced with unrelated markup")
def markup_unrelated(context: dict[str, Any]) -> None:
    context["body"] = _UNRELATED


@when("I run the config again")
@when("I run the config")
def run_config(context: dict[str, Any]) -> None:
    _run(context)


# --- Then ----------------------------------------------------------------


@then(parsers.parse('the "{name}" field value is present'))
def field_present(context: dict[str, Any], name: str) -> None:
    assert context["result"].records[0][name] is not None


@then(parsers.parse('the "{name}" field is null'))
def field_null(context: dict[str, Any], name: str) -> None:
    assert context["result"].records[0][name] is None


@then(parsers.parse("the run summary reports {count:d} confident heal"))
def summary_confident(context: dict[str, Any], count: int) -> None:
    assert context["summary"].heal_confident == count


@then(parsers.parse("the run summary reports {count:d} uncertain match"))
def summary_uncertain(context: dict[str, Any], count: int) -> None:
    assert context["summary"].heal_uncertain == count


@then("the run summary reports no heals")
def summary_no_heals(context: dict[str, Any]) -> None:
    summary = context["summary"]
    assert summary.heal_confident == 0
    assert summary.heal_uncertain == 0
