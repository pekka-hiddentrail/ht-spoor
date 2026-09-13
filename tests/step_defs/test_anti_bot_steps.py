"""Step definitions for features/anti_bot.feature (ROADMAP.md §2d, Phase 3.5).

Challenge detection is a scan of the fetched HTML for generic anti-bot-vendor
markers, so most of these drive an in-memory httpx MockTransport, no browser or
network needed. The tier-1 dispatcher is pinned to **tier 1**: a challenge page
extracts zero records, which would otherwise escalate to a real browser the
MockTransport can't drive. A challenge served *behind* an error status (403/503)
is exercised on both transports — tier 1 through the MockTransport (asserting the
`FetchFailure` carries the challenge), and one scenario through a *real* browser
against a loopback server that answers the target with a 403 interstitial, since
the browser-tier scan reads the rendered `page.content()` rather than a
`FetchFailure` body. The pure classification is covered by the unit tests.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
# A plain error body with no challenge markers — a genuine server error, not a wall.
_ORDINARY_ERROR = "<html><body>Service temporarily unavailable</body></html>"


class _ChallengeServer(ThreadingHTTPServer):
    """A loopback server that answers the target path with a fixed (status, body).

    Used by the real-browser scenario: the browser-tier challenge scan reads the
    rendered `page.content()`, so it needs a real navigation to a real response
    (a `MockTransport` can't drive a browser). Any other path is a 404.
    """

    def __init__(self, status: int, body: str) -> None:
        super().__init__(("127.0.0.1", 0), _ChallengeHandler)
        self.status = status
        self.body = body


class _ChallengeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's required name)
        server: _ChallengeServer = self.server  # type: ignore[assignment]
        status, body = (
            (server.status, server.body)
            if self.path == _TARGET_PATH
            else (404, "not found")
        )
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
    """Per-scenario state; tears down the loopback server if one was started."""
    ctx: dict[str, Any] = {"status": 200}
    yield ctx
    server = ctx.get("server")
    if server is not None:
        server.shutdown()
        server.server_close()
        ctx["thread"].join(timeout=5)


# --- Given ----------------------------------------------------------------


@given(parsers.parse('a config fetching the "{field}" from "{selector}"'))
def anti_bot_config(context: dict[str, Any], field: str, selector: str) -> None:
    context["field"] = field
    context["selector"] = selector
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


@given("the target returns a Cloudflare interstitial with status 403")
def target_cloudflare_403(context: dict[str, Any]) -> None:
    context["body"] = _CLOUDFLARE
    context["status"] = 403


@given("the target returns a reCAPTCHA page with status 503")
def target_recaptcha_503(context: dict[str, Any]) -> None:
    context["body"] = _RECAPTCHA
    context["status"] = 503


@given("the target returns an ordinary error page with status 503")
def target_ordinary_error_503(context: dict[str, Any]) -> None:
    context["body"] = _ORDINARY_ERROR
    context["status"] = 503


@given("a browser navigation returning a Cloudflare interstitial with status 403")
def browser_cloudflare_403(context: dict[str, Any]) -> None:
    context["body"] = _CLOUDFLARE
    context["status"] = 403


# --- When -----------------------------------------------------------------


@when("I run the config")
def run_the_config(context: dict[str, Any]) -> None:
    body = context["body"]
    status = context["status"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _TARGET_PATH:
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    cfg = load_config(context["config_text"])
    # Pin to tier 1 (see module docstring): a challenge page has zero records and
    # would otherwise escalate to a browser the MockTransport can't drive. `sleep`
    # is a no-op so a 503's exhausted retries cost no real time.
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract.run_report(
            cfg,
            client=client,
            sleep=lambda _seconds: None,
            tiers=(extract.Tier1Resolver(),),
        )
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


@when("I run the config through a real browser")
def run_through_browser(context: dict[str, Any]) -> None:
    server = _ChallengeServer(context["status"], context["body"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context["server"] = server
    context["thread"] = thread

    target = f"http://127.0.0.1:{server.server_address[1]}{_TARGET_PATH}"
    cfg = load_config(
        f"target: {target}\n"
        "fields:\n"
        f'  {context["field"]}: {{ selector: "{context["selector"]}" }}\n'
    )
    # Pin to tier 2 (the browser path): the challenge scan reads page.content().
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


@then(parsers.parse('the target is dead-lettered with reason "{reason}"'))
def dead_lettered_with_reason(context: dict[str, Any], reason: str) -> None:
    dead_letter = context["summary"].dead_letter
    assert len(dead_letter) == 1
    assert dead_letter[0].reason == reason
