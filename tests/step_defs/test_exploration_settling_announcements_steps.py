"""Step definitions for features/exploration_settling_announcements.feature (§2e, 7f).

Two halves, mirroring 7e. The pure quiescence decision is exercised with no browser: a
fake clock advanced only by the injected `sleep`, a constant (quiet) mutation signal,
and a scripted `announcing` predicate that reports an urgent announcement on screen for
a bounded time (or forever) drive `wait_for_quiescence`. Times are ms — the function is
unit-agnostic. The live half stands up a loopback server whose entry page renders
instantly, shows an `aria-live="assertive"` toast carrying a button, and removes it on a
timer past the quiet window: the real driver's announcement probe must hold the settle
wait open until the toast clears, so discovery reads the page behind it, not the toast.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.discovery import discover_actions
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.settling import wait_for_quiescence

scenarios("exploration_settling_announcements.feature")

# A fine poll relative to the quiet windows the scenarios use (matches the 7b/7e steps).
_POLL_INTERVAL_MS = 50.0

# Live timings: a quiet window short enough that DOM-quiet alone would fire while the
# toast is still up, a dismissal delay comfortably past it, and a timeout above the sum.
_QUIET_WINDOW_S = 0.3
_DISMISS_DELAY_S = 0.7
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


# --- Pure decision (fake clock + scripted announcement signal) -----------


@given(
    parsers.parse("a quiet window of {quiet:d} ms and a settle timeout of {to:d} ms")
)
def windows(context: dict[str, Any], quiet: int, to: int) -> None:
    context["quiet_window"] = float(quiet)
    context["timeout"] = float(to)
    context["observe"] = lambda: 0  # DOM quiet throughout these scenarios


@given(
    parsers.parse(
        "a page whose DOM is quiet but an assertive announcement is showing "
        "until {until:d} ms"
    )
)
def announcing_until(context: dict[str, Any], until: int) -> None:
    context["announcing"] = lambda: context["now"] < float(until)


@given("a page whose DOM is quiet but an assertive announcement never clears")
def announcing_forever(context: dict[str, Any]) -> None:
    context["announcing"] = lambda: True


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
        announcing=context["announcing"],
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


# --- Live half (a loopback server whose toast auto-dismisses) ------------

# The toast is an assertive live region carrying a button; a timer removes the whole
# toast past the quiet window. If the settle read the page while the toast was up it
# would discover the button; waiting the announcement out means it is gone by the read.
_SHELL = (
    "<html><body><h1>Home</h1>"
    "<div id='toast' role='alert' aria-live='assertive'>"
    "<span>Saved</span><button>Dismiss notification</button></div>"
    "<script>"
    f"setTimeout(() => document.getElementById('toast').remove(), {int(_DISMISS_DELAY_S * 1000)});"  # noqa: E501
    "</script></body></html>"
)


class _AutoDismissServer(ThreadingHTTPServer):
    """Serves an entry page whose assertive toast auto-dismisses on a timer."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _AutoDismissHandler)


class _AutoDismissHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's required name)
        payload = _SHELL.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:  # silence the per-request stderr log
        pass


@given("a live site whose entry page shows a toast that auto-dismisses after a delay")
def live_auto_dismiss(context: dict[str, Any]) -> None:
    server = _AutoDismissServer()
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


@then(
    parsers.parse('the discovered actions do not include the "{role}" named "{name}"')
)
def discovered_excludes(context: dict[str, Any], role: str, name: str) -> None:
    driver: PlaywrightDriver = context["driver"]
    actions = discover_actions(driver.ax_nodes())
    assert not any(a.role == role and a.name == name for a in actions), actions
