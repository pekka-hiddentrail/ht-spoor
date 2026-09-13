"""Step definitions for features/change_detection.feature (ROADMAP.md §2d, Phase 3.5).

Change detection is an HTTP-level concern (conditional requests + a content-hash
fallback), so — like the politeness, retry, and anti-bot scenarios — these drive
an in-memory httpx MockTransport, no browser or network. Each scenario runs the
config **twice** against a fresh transport, with the per-domain validator store
under a per-scenario temp directory (`storage.CACHE_ROOT` monkeypatched) so what
the first run records survives into the second. The dispatcher is pinned to tier
1: an unchanged run has zero records, which would otherwise escalate to a browser
the MockTransport can't drive.
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

scenarios("change_detection.feature")

_TARGET = "http://localhost:8000/product.html"
_TARGET_PATH = "/product.html"
_ETAG = '"v1"'

_ORIGINAL = '<html><body><h1 class="product-title">Gizmo</h1></body></html>'
_CHANGED = '<html><body><h1 class="product-title">Gizmo Mk II</h1></body></html>'


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Per-scenario state, with the validator store under a fresh temp root."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    return {"change_detection": False, "no_validators": False}


def _build_config(context: dict[str, Any]) -> str:
    lines = [
        f"target: {_TARGET}",
        "fields:",
        '  title: { selector: "h1.product-title" }',
    ]
    if context["change_detection"]:
        lines.append("change_detection: true")
    return "\n".join(lines) + "\n"


def _run(context: dict[str, Any], handler: Any) -> tuple[Any, list[httpx.Headers]]:
    """Run the config once against a fresh MockTransport; capture request headers."""
    seen: list[httpx.Headers] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return handler(request)

    cfg = load_config(_build_config(context))
    with httpx.Client(transport=httpx.MockTransport(wrapped)) as client:
        # Pin to tier 1 (see module docstring): an unchanged page has zero records
        # and would otherwise escalate to a browser the MockTransport can't drive.
        result = extract.run_report(
            cfg, client=client, tiers=(extract.Tier1Resolver(),)
        )
    return result, seen


def _serve_original(request: httpx.Request) -> httpx.Response:
    """A 200 with an ETag and the original body; a 304 if the ETag still matches.

    Reused for the seed run (no If-None-Match yet -> full 200) and the unchanged
    second run (client replays If-None-Match -> 304), and for a change-detection-
    off run (no conditional header -> full 200 again).
    """
    if request.url.path != _TARGET_PATH:
        return httpx.Response(404, text="not found")
    if request.headers.get("If-None-Match") == _ETAG:
        return httpx.Response(304, headers={"ETag": _ETAG})
    return httpx.Response(200, headers={"ETag": _ETAG}, text=_ORIGINAL)


def _serve_no_validators(request: httpx.Request) -> httpx.Response:
    """A 200 with the original body and no validator headers, every time.

    Forces the content-hash fallback: the server offers no ETag/Last-Modified, so
    an unchanged page is recognized only by its body hash matching a prior run's.
    """
    if request.url.path != _TARGET_PATH:
        return httpx.Response(404, text="not found")
    return httpx.Response(200, text=_ORIGINAL)


def _serve_changed(request: httpx.Request) -> httpx.Response:
    """A 200 with a new ETag and a changed body — the page genuinely moved."""
    if request.url.path != _TARGET_PATH:
        return httpx.Response(404, text="not found")
    return httpx.Response(200, headers={"ETag": '"v2"'}, text=_CHANGED)


# --- Given ----------------------------------------------------------------


@given(parsers.parse('a config fetching the "{field}" from "{selector}"'))
def _config(context: dict[str, Any], field: str, selector: str) -> None:
    context["field"] = field  # selector is fixed in _build_config for this feature


@given("change detection is enabled")
def enabled(context: dict[str, Any]) -> None:
    context["change_detection"] = True


@given("change detection is not configured")
def not_configured(context: dict[str, Any]) -> None:
    context["change_detection"] = False


@given("the page was fetched and recorded on a previous run")
def previous_run(context: dict[str, Any]) -> None:
    _run(context, _serve_original)


@given("the server sends no validators, and the page was recorded on a previous run")
def previous_run_no_validators(context: dict[str, Any]) -> None:
    context["no_validators"] = True
    _run(context, _serve_no_validators)


# --- When -----------------------------------------------------------------


@when("the page has not changed and I run it again")
def run_unchanged(context: dict[str, Any]) -> None:
    handler = _serve_no_validators if context["no_validators"] else _serve_original
    result, seen = _run(context, handler)
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)
    context["request_headers"] = seen


@when("the page has changed and I run it again")
def run_changed(context: dict[str, Any]) -> None:
    result, seen = _run(context, _serve_changed)
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)
    context["request_headers"] = seen


@when("I run the config against a page never seen before")
def run_first_time(context: dict[str, Any]) -> None:
    result, seen = _run(context, _serve_original)
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)
    context["request_headers"] = seen


# --- Then -----------------------------------------------------------------


@then("no records are extracted on the second run")
def no_records(context: dict[str, Any]) -> None:
    assert context["result"].records == []


@then("the field is extracted on the second run")
def field_extracted(context: dict[str, Any]) -> None:
    records = context["result"].records
    assert len(records) == 1
    assert records[0][context["field"]] is not None


@then("the run reports 1 unchanged page")
def one_unchanged(context: dict[str, Any]) -> None:
    assert context["summary"].unchanged == [_TARGET]


@then("the run reports no unchanged pages")
def no_unchanged(context: dict[str, Any]) -> None:
    assert context["summary"].unchanged == []


@then("the second run sent a conditional request")
def sent_conditional(context: dict[str, Any]) -> None:
    assert any(
        "If-None-Match" in h or "If-Modified-Since" in h
        for h in context["request_headers"]
    )


@then("the second run sent no conditional request")
def sent_no_conditional(context: dict[str, Any]) -> None:
    assert all(
        "If-None-Match" not in h and "If-Modified-Since" not in h
        for h in context["request_headers"]
    )
