"""Step definitions for features/session.feature (ROADMAP.md §2h, §2c).

Bring-your-own-session is proven against a real loopback server that actually
gates content, because the point is that the *supplied* credentials travel with
the fetch. The static-tier scenarios run the real tier-1 httpx client (no mock
transport) against a page whose members-only row is server-rendered only when the
request carries the session cookie — so a run that loaded the session sees the
row and a run without it does not. The browser-tier scenario gates on a
localStorage token instead: the row is injected by page JS only when
`localStorage.token` matches, which a static fetch can never satisfy, proving the
browser context loaded the supplied storage state. Each scenario is pinned to the
single tier under test (as anti_bot.feature does) so a static case never launches
a browser and a browser case never leans on the static path.

The auth server counts the requests it received, so the missing-session scenario
can assert the run failed *before* fetching anything.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.security.session import SessionError

scenarios("session.feature")

_PATH = "/gated.html"
# The secret shapes the supplied session carries; the server reveals its
# members-only row only to a request that presents the matching one.
_COOKIE_NAME = "session"
_COOKIE_VALUE = "s3ss10n-c00k1e-value"
_TOKEN_NAME = "token"
_TOKEN_VALUE = "l0calStorage-t0ken-value"

# Rows the server exposes. The cookie-gated row is server-rendered into the
# initial HTML (a static fetch sees it); the token-gated row is injected by page
# JS on load (only a browser that carries the localStorage token renders it).
_COOKIE_ROW = '<li class="item"><span class="name">Members-only Alpha</span></li>'


class _AuthServer(ThreadingHTTPServer):
    """A loopback server whose members-only rows are gated by the supplied session.

    Records every requested path so a scenario can assert whether a run fetched
    anything at all. Any path other than the gated one is a 404.
    """

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _AuthHandler)
        self.requests: list[str] = []

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class _AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's required name)
        server: _AuthServer = self.server  # type: ignore[assignment]
        server.requests.append(self.path)
        if self.path != _PATH:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        cookie_ok = f"{_COOKIE_NAME}={_COOKIE_VALUE}" in self.headers.get("Cookie", "")
        server_row = _COOKIE_ROW if cookie_ok else ""
        # The token-gated row is appended by JS only when the browser context
        # carries the matching localStorage entry — unreachable by a static fetch.
        body = (
            "<html><body>"
            f'<ul id="items">{server_row}</ul>'
            "<script>"
            f"if (localStorage.getItem('{_TOKEN_NAME}') === '{_TOKEN_VALUE}') {{"
            "  var li = document.createElement('li');"
            "  li.className = 'item';"
            "  li.innerHTML = '<span class=\"name\">Members-only Beta</span>';"
            "  document.getElementById('items').appendChild(li);"
            "}"
            "</script>"
            "</body></html>"
        )
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:  # silence the per-request stderr log
        pass


def _config(base: str, session_path: str | None) -> str:
    text = (
        f"target: {base}{_PATH}\n"
        'item: ".item"\n'
        "fields:\n"
        '  name: { selector: ".name" }\n'
    )
    if session_path is not None:
        text += f"session: {session_path}\n"
    return text


@pytest.fixture
def context() -> Iterator[dict[str, Any]]:
    """Per-scenario state; tears down the loopback server it started."""
    ctx: dict[str, Any] = {}
    yield ctx
    server = ctx.get("server")
    if server is not None:
        server.shutdown()
        server.server_close()
        ctx["thread"].join(timeout=5)


def _start_server(context: dict[str, Any]) -> _AuthServer:
    server = _AuthServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context["server"] = server
    context["thread"] = thread
    return server


# --- Given ----------------------------------------------------------------


@given(
    "an auth-aware fixture server that reveals items only to an "
    "authenticated session"
)
@given("an auth-aware fixture server whose items render only for a localStorage token")
def auth_server(context: dict[str, Any]) -> None:
    _start_server(context)


@given("a session file carrying the server's session cookie")
def cookie_session_file(context: dict[str, Any], tmp_path: Path) -> None:
    path = tmp_path / "cookie-session.json"
    state = {
        "cookies": [
            {
                "name": _COOKIE_NAME,
                "value": _COOKIE_VALUE,
                "domain": "127.0.0.1",
                "path": "/",
                "sameSite": "Lax",
            }
        ],
        "origins": [],
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    context["session_path"] = str(path)


@given("a session file carrying that localStorage token")
def localstorage_session_file(context: dict[str, Any], tmp_path: Path) -> None:
    path = tmp_path / "token-session.json"
    state = {
        "cookies": [],
        "origins": [
            {
                "origin": context["server"].base,
                "localStorage": [{"name": _TOKEN_NAME, "value": _TOKEN_VALUE}],
            }
        ],
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    context["session_path"] = str(path)


@given("a session path that points to no file")
def missing_session_path(context: dict[str, Any], tmp_path: Path) -> None:
    context["session_path"] = str(tmp_path / "does-not-exist.json")


# --- When -----------------------------------------------------------------


@when("I run a static config with that session")
@when("I run a static config with no session")
def run_static(context: dict[str, Any]) -> None:
    session_path = context.get("session_path")
    cfg = load_config(_config(context["server"].base, session_path))
    context["result"] = extract.run_report(
        cfg, sleep=lambda _s: None, tiers=(extract.Tier1Resolver(),)
    )


@when("I run a browser config with that session")
def run_browser(context: dict[str, Any]) -> None:
    cfg = load_config(_config(context["server"].base, context["session_path"]))
    context["result"] = extract.run_report(
        cfg, sleep=lambda _s: None, tiers=(extract.Tier2Resolver(),)
    )


@when("I run a static config with that session expecting an error")
def run_static_expecting_error(context: dict[str, Any]) -> None:
    cfg = load_config(_config(context["server"].base, context["session_path"]))
    try:
        extract.run_report(cfg, sleep=lambda _s: None, tiers=(extract.Tier1Resolver(),))
    except SessionError as exc:
        context["error"] = exc


# --- Then -----------------------------------------------------------------


@then("the members-only item is extracted")
def members_only_item_extracted(context: dict[str, Any]) -> None:
    records = context["result"].records
    assert len(records) == 1
    assert str(records[0]["name"]).startswith("Members-only")


@then("no item is extracted")
def no_item_extracted(context: dict[str, Any]) -> None:
    assert context["result"].records == []


@then("the run raises a session error and fetches nothing")
def run_raises_and_fetches_nothing(context: dict[str, Any]) -> None:
    assert isinstance(context.get("error"), SessionError)
    # The failure must precede any fetch: the server saw no request at all.
    assert context["server"].requests == []
