"""Step definitions for features/exploration_settling_network.feature (§2e, 7e).

Two halves, mirroring 7b. The pure quiescence decision is exercised with no browser: a
fake clock advanced only by the injected `sleep`, a constant (quiet) mutation signal,
and a scripted `busy` predicate that reports a request in flight for a bounded time (or
forever) drive `wait_for_quiescence`. Times are ms — the function is unit-agnostic. The
live half stands up a loopback server whose entry page renders instantly and then
fetches a fragment the server delays past the quiet window, injecting a button: the
real driver's in-flight request counter must hold the settle wait open until the fetch
completes, so discovery finds the fetched button rather than the pre-fetch page.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.discovery import discover_actions
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.settling import wait_for_quiescence

scenarios("exploration_settling_network.feature")

# A fine poll relative to the quiet windows the scenarios use (matches the 7b steps).
_POLL_INTERVAL_MS = 50.0

# Live timings: a quiet window short enough that DOM-quiet alone would fire during the
# fragment delay, a fragment delay comfortably past it, and a timeout above their sum.
_QUIET_WINDOW_S = 0.3
_FRAGMENT_DELAY_S = 0.7
_SETTLE_TIMEOUT_S = 3.0


@pytest.fixture
def context() -> dict[str, Any]:
    return {"now": 0.0}


@pytest.fixture(autouse=True)
def _teardown(context: dict[str, Any]) -> Any:
    yield
    driver = context.get("driver")
    if driver is not None:
        driver.close()
    server = context.get("server")
    if server is not None:
        server.shutdown()
        server.server_close()
        context["thread"].join(timeout=5)


# --- Pure decision (fake clock + scripted network signal) ----------------


@given(
    parsers.parse("a quiet window of {quiet:d} ms and a settle timeout of {to:d} ms")
)
def windows(context: dict[str, Any], quiet: int, to: int) -> None:
    context["quiet_window"] = float(quiet)
    context["timeout"] = float(to)
    context["observe"] = lambda: 0  # DOM quiet throughout these scenarios


@given(
    parsers.parse(
        "a page whose DOM is quiet but a request is in flight until {until:d} ms"
    )
)
def in_flight_until(context: dict[str, Any], until: int) -> None:
    context["busy"] = lambda: context["now"] < float(until)


@given("a page whose DOM is quiet but a request stays in flight forever")
def in_flight_forever(context: dict[str, Any]) -> None:
    context["busy"] = lambda: True


@when("the explorer waits for the page to settle")
def wait_to_settle(context: dict[str, Any]) -> None:
    def clock() -> float:
        return context["now"]

    def sleep(dt: float) -> None:
        context["now"] += dt

    context["result"] = wait_for_quiescence(
        observe=context["observe"],
        clock=clock,
        sleep=sleep,
        quiet_window=context["quiet_window"],
        timeout=context["timeout"],
        poll_interval=_POLL_INTERVAL_MS,
        busy=context["busy"],
    )


@then("it reports the page settled")
def reports_settled(context: dict[str, Any]) -> None:
    assert context["result"].settled is True


@then("it reports the page did not settle")
def reports_unsettled(context: dict[str, Any]) -> None:
    assert context["result"].settled is False


@then("it did not wait the full timeout")
def under_timeout(context: dict[str, Any]) -> None:
    assert context["result"].elapsed < context["timeout"]


@then("the wait ended at the timeout")
def ended_at_timeout(context: dict[str, Any]) -> None:
    assert context["result"].elapsed >= context["timeout"]


@then(parsers.parse("the wait lasted at least {ms:d} ms"))
def lasted_at_least(context: dict[str, Any], ms: int) -> None:
    assert context["result"].elapsed >= float(ms), context["result"].elapsed


# --- Live half (a loopback server that delays a fetched fragment) --------

_SHELL = (
    "<html><body><h1>Home</h1><div id='slot'></div>"
    "<script>"
    "fetch('fragment').then(r => r.text())"
    ".then(t => { document.getElementById('slot').innerHTML = t; });"
    "</script></body></html>"
)
_FRAGMENT = "<button>Loaded over the network</button>"


class _DeferredFetchServer(ThreadingHTTPServer):
    """Serves the entry shell instantly and the fetched fragment after a delay."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _DeferredFetchHandler)


class _DeferredFetchHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's required name)
        if self.path.rstrip("/").endswith("fragment"):
            time.sleep(_FRAGMENT_DELAY_S)  # delay the fragment past the quiet window
            self._respond(_FRAGMENT)
            return
        self._respond(_SHELL)

    def _respond(self, body: str, status: int = 200) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:  # silence the per-request stderr log
        pass


@given("a live site whose entry page fetches deferred content after a network delay")
def live_deferred_fetch(context: dict[str, Any]) -> None:
    server = _DeferredFetchServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    driver = PlaywrightDriver(
        base, quiet_window=_QUIET_WINDOW_S, settle_timeout=_SETTLE_TIMEOUT_S
    )
    driver.__enter__()
    context["server"] = server
    context["thread"] = thread
    context["driver"] = driver


@when("the explorer resets the browser")
def reset_browser(context: dict[str, Any]) -> None:
    context["driver"].reset()


@then(parsers.parse('the discovered actions include the "{role}" named "{name}"'))
def discovered_includes(context: dict[str, Any], role: str, name: str) -> None:
    driver: PlaywrightDriver = context["driver"]
    actions = discover_actions(driver.ax_nodes())
    assert any(a.role == role and a.name == name for a in actions), actions
