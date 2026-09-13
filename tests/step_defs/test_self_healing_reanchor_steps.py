"""Step definitions for features/self_healing_reanchor.feature (§2, §2d).

Drives the dispatcher end to end through an in-memory httpx MockTransport (tier 1,
no browser, no network), with the persistent per-domain fingerprint cache pointed
at a per-scenario temp directory (`storage.CACHE_ROOT` monkeypatched) so each run's
learned/re-anchored fingerprints survive into the next run.

The served body is mutable and swapped between runs to model successive redesigns.
The three shapes are engineered (verified numerically against the scoring weights)
so that: the original heals to the first redesign confidently (which re-anchors),
the re-anchored shape heals to the second redesign confidently, but the *original*
shape would only match the second redesign as a sub-threshold uncertain match. That
gap is exactly what re-anchoring closes; the contrast scenario exercises it.
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

scenarios("self_healing_reanchor.feature")

_TARGET = "http://localhost:8000/product.html"
_PATH = "/product.html"


def _page(eid: str, cls: str, text: str, *, role: str = "heading") -> str:
    return (
        "<html><body><main><section>"
        f'<h2 id="{eid}" class="{cls}" data-role="{role}">{text}</h2>'
        "</section></main></body></html>"
    )


# Original (A): h2.title resolves and is fingerprinted.
_ORIGINAL = _page("anchor-1", "title", "Blue Widget")
# Redesign 1 (B): id and class changed, text unchanged — a confident heal from A
# (~0.65). Confidently healing here re-anchors the stored fingerprint to B.
_REDESIGN_1 = _page("anchor-2", "heading", "Blue Widget")
# Redesign 2 (C): shares B's id but not A's, and the text now differs too. A
# confident heal from B (~0.80), but only a sub-threshold uncertain match from A
# (~0.54) — so it heals only *because* B re-anchored the fingerprint first.
_REDESIGN_2 = _page("anchor-2", "label", "Red Gadget")
# Unrelated markup: nothing resembling the stored heading — an uncertain match,
# which must never overwrite the good anchor.
_UNRELATED = (
    "<html><body>"
    '<div class="banner"><p>Totally different unrelated content here</p></div>'
    "<footer><small>copyright notice</small></footer>"
    "</body></html>"
)


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


@given("a first run has recorded the field's original fingerprint")
def first_run_records(context: dict[str, Any]) -> None:
    context["body"] = _ORIGINAL
    _run(context)
    # Invariant: the original run actually resolved (and fingerprinted) the field.
    assert context["result"].records[0][context["field_name"]] is not None


# --- When ----------------------------------------------------------------


@when(parsers.parse('the markup is redesigned once so "{selector}" matches nothing'))
def redesign_once(context: dict[str, Any], selector: str) -> None:
    context["body"] = _REDESIGN_1


@when("the markup is redesigned a second time, further from the original")
def redesign_twice(context: dict[str, Any]) -> None:
    context["body"] = _REDESIGN_2


@when("the markup is redesigned straight to the second shape")
def redesign_straight(context: dict[str, Any]) -> None:
    context["body"] = _REDESIGN_2


@when("the page is replaced with unrelated markup")
def markup_unrelated(context: dict[str, Any]) -> None:
    context["body"] = _UNRELATED


@when("I run the config again")
def run_config_again(context: dict[str, Any]) -> None:
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
