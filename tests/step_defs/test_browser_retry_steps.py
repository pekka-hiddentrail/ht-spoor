"""Step definitions for features/browser_retry.feature (ROADMAP.md §2d, Phase 3.5).

Browser-tier navigation retry is the end-to-end companion of the tier-1 retry
scenarios: it must be exercised through a *real* browser navigating a *real*
flaky server, because the whole point is that an uncaught Playwright navigation
error no longer crashes the run. A `MockTransport` can't drive a browser, so
these bind a real loopback `HTTPServer` whose handler is *scripted* per call —
it can return a 503 on the first navigation and the real page on the next — and
run the dispatcher pinned to **tier 2**. The backoff wait is short-circuited
with an injected no-op `sleep`, so a retry costs no real time.

The pure classification/backoff logic (including the transient-*exception* path,
which a live browser can't be made to raise deterministically) is unit-tested
against `RetryingNavigator` in tests/test_retry_navigator.py; these scenarios
prove the wiring: that a scripted transient status is actually retried, and an
unrecoverable one is dead-lettered rather than crashing the crawl.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary

scenarios("browser_retry.feature")

_TARGET_PATH = "/product.html"
_PAGE = '<html><body><h1 class="product-title">Gizmo</h1></body></html>'


class _FlakyServer(ThreadingHTTPServer):
    """A loopback server whose target path replays a per-scenario response script.

    `script` is a list of (status, body); the target's Nth request returns the
    Nth entry, and the last entry repeats for any further request (so "always
    503" is a single-entry script and "503 once then the page" is two). Any other
    path is a 404 — robots.txt and the API-surface probes have nothing to serve.
    """

    def __init__(self, script: list[tuple[int, str]]) -> None:
        super().__init__(("127.0.0.1", 0), _FlakyHandler)
        self.script = script
        self.calls = 0


class _FlakyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's required name)
        server: _FlakyServer = self.server  # type: ignore[assignment]
        if self.path != _TARGET_PATH:
            self._respond(404, "not found")
            return
        index = min(server.calls, len(server.script) - 1)
        server.calls += 1
        status, body = server.script[index]
        self._respond(status, body)

    def _respond(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:  # silence the per-request stderr log
        pass


@pytest.fixture
def context() -> Iterator[dict[str, Any]]:
    """Per-scenario state; tears the flaky server down after the scenario."""
    ctx: dict[str, Any] = {"script": [(200, _PAGE)]}
    yield ctx
    server = ctx.get("server")
    if server is not None:
        server.shutdown()
        server.server_close()
        ctx["thread"].join(timeout=5)


# --- Given ----------------------------------------------------------------


@given(parsers.parse('a browser config fetching the "{field}" from "{selector}"'))
def browser_config(context: dict[str, Any], field: str, selector: str) -> None:
    context["field"] = field
    context["selector"] = selector


@given("the navigation returns 503 once, then the page")
def transient_then_page(context: dict[str, Any]) -> None:
    context["script"] = [(503, "service unavailable"), (200, _PAGE)]


@given("the navigation always returns 503")
def always_503(context: dict[str, Any]) -> None:
    context["script"] = [(503, "service unavailable")]


@given("the navigation returns 404")
def returns_404(context: dict[str, Any]) -> None:
    context["script"] = [(404, "not found")]


# --- When -----------------------------------------------------------------


@when("I run the config through a real browser")
def run_through_browser(context: dict[str, Any]) -> None:
    server = _FlakyServer(context["script"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context["server"] = server
    context["thread"] = thread

    base = f"http://127.0.0.1:{server.server_address[1]}"
    context["target"] = f"{base}{_TARGET_PATH}"
    cfg = load_config(
        f"target: {context['target']}\n"
        "fields:\n"
        f'  {context["field"]}: {{ selector: "{context["selector"]}" }}\n'
    )
    # Pin to tier 2 (see module docstring): this is the browser navigation path.
    # `sleep` is a no-op so the retry backoff costs no real time.
    result = extract.run_report(
        cfg,
        sleep=lambda _seconds: None,
        tiers=(extract.Tier2Resolver(),),
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
    assert failure.url == context["target"]
    assert failure.reason == reason
