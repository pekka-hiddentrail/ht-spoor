"""Unit tests for the live browser driver's action contract (ROADMAP.md §2e).

The full driver is exercised end to end against real pages by the live scenarios
(`exploration_actuation_live.feature` and `exploration_settling_live.feature`), which
need a headless Chromium. These browser-free tests pin the pieces of robust actuation
(7a) and settling/reset fidelity (7b) that must hold without a live page: `perform`
re-locates through the accessibility tree, resolves the node and hit-tests its click
point over CDP, and turns the result into one of three honest outcomes — a coordinate
click (ACTUATE), `ElementCovered`, or `ElementNotLocated` — while a CDP failure becomes
a plain `ActionError` (a recorded skip, not a crash); after a click it waits for DOM
quiescence; and `reset` clears cookies and web storage before navigating so replay is a
true first visit.

A hand-rolled fake page stands in for the Playwright `Page`, injected onto the driver
directly. `perform` touches `ax_nodes()` (a CDP accessibility-tree read), a second CDP
session for `DOM.resolveNode` + `Runtime.callFunctionOn`, `page.mouse.click(...)`, and
`page.evaluate(...)` (the mutation-count read the settle wait polls); `reset` touches
`context.clear_cookies()`, `page.evaluate(...)` (the storage clear), and `page.goto`.
The fake implements exactly those, and the driver is built with a fake clock/sleep so
the settle wait resolves instantly and deterministically.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Error as PlaywrightError

from spoor.exploration.discovery import ActionableElement
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import (
    ActionError,
    ElementCovered,
    ElementNotLocated,
)

_ACTION = ActionableElement(role="button", name="Open menu", backend_node_id=1)

# An accessibility tree in which `find_target` locates _ACTION (same shape discovery
# reads): a non-ignored button named "Open menu" carrying a resolvable backend id.
_MATCHING_NODES: list[dict[str, object]] = [
    {
        "role": {"value": "button"},
        "name": {"value": "Open menu"},
        "ignored": False,
        "backendDOMNodeId": 1,
    }
]

# Probe results: the point lands on the target, or a link covers it.
_HITS_TARGET = {"hitsTarget": True, "covering": None, "cx": 10.0, "cy": 20.0}
_COVERED = {
    "hitsTarget": False,
    "covering": {"role": "link", "text": "Accept and continue"},
    "cx": 10.0,
    "cy": 20.0,
}


class _FakeCDPSession:
    """Answers the CDP calls `ax_nodes` and `_probe_click_point` make."""

    def __init__(
        self,
        *,
        nodes: list[dict[str, object]],
        probe_value: dict[str, Any] | None,
        call_error: Exception | None,
    ) -> None:
        self._nodes = nodes
        self._probe_value = probe_value
        self._call_error = call_error
        self.detached = 0

    def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if method == "Accessibility.getFullAXTree":
            return {"nodes": self._nodes}
        if method == "DOM.resolveNode":
            return {"object": {"objectId": "obj-1"}}
        if method == "Runtime.callFunctionOn":
            if self._call_error is not None:
                raise self._call_error
            return {"result": {"value": self._probe_value}}
        raise AssertionError(f"unexpected CDP call: {method}")

    def detach(self) -> None:
        self.detached += 1


class _FakeContext:
    def __init__(self, session: _FakeCDPSession) -> None:
        self._session = session
        self.cookies_cleared = 0

    def new_cdp_session(self, page: object) -> _FakeCDPSession:
        return self._session

    def clear_cookies(self) -> None:
        self.cookies_cleared += 1


class _FakeMouse:
    def __init__(self) -> None:
        self.clicked_at: tuple[float, float] | None = None

    def click(self, x: float, y: float) -> None:
        self.clicked_at = (x, y)


class _FakePage:
    def __init__(
        self,
        *,
        nodes: list[dict[str, object]] = _MATCHING_NODES,
        probe_value: dict[str, Any] | None = None,
        call_error: Exception | None = None,
    ) -> None:
        self.session = _FakeCDPSession(
            nodes=nodes, probe_value=probe_value, call_error=call_error
        )
        self.context = _FakeContext(self.session)
        self.mouse = _FakeMouse()
        self.goto_urls: list[str] = []
        self.evaluated: list[str] = []

    def evaluate(self, expression: str) -> Any:
        # The settle wait polls the mutation counter (always 0 here — quiet); the reset
        # clears web storage. Record every call so tests can assert what ran.
        self.evaluated.append(expression)
        return 0

    def goto(self, url: str, **kwargs: Any) -> None:
        self.goto_urls.append(url)


def _driver_with_page(page: _FakePage) -> PlaywrightDriver:
    # A fake clock advanced only by the fake sleep, so the settle wait's quiet window
    # elapses in a handful of no-op iterations rather than real wall-clock time.
    clock = {"now": 0.0}

    def fake_sleep(dt: float) -> None:
        clock["now"] += dt

    driver = PlaywrightDriver(
        "http://127.0.0.1:0/",
        clock=lambda: clock["now"],
        sleep=fake_sleep,
    )
    driver._page = page  # type: ignore[assignment]
    driver._context = page.context  # type: ignore[assignment]
    return driver


def test_perform_clicks_verified_point() -> None:
    page = _FakePage(probe_value=_HITS_TARGET)
    driver = _driver_with_page(page)
    driver.perform(_ACTION)
    assert page.mouse.clicked_at == (10.0, 20.0)


def test_perform_waits_for_settle_after_click() -> None:
    # After the click the driver polls the mutation counter to wait for the resulting
    # render to go quiet, so the explorer's next read sees the settled page (7b).
    page = _FakePage(probe_value=_HITS_TARGET)
    driver = _driver_with_page(page)
    driver.perform(_ACTION)
    assert page.mouse.clicked_at == (10.0, 20.0)
    assert page.evaluated, "expected the settle wait to poll the mutation counter"


def test_reset_clears_cookies_and_storage_then_navigates() -> None:
    # Reset fidelity (7b): a reset must clear cookies and web storage before navigating,
    # so replay lands on a true first visit rather than a returning-visitor render.
    page = _FakePage(probe_value=_HITS_TARGET)
    driver = _driver_with_page(page)
    driver.reset()
    assert page.context.cookies_cleared == 1
    assert any("localStorage" in expr for expr in page.evaluated)
    assert page.goto_urls == ["http://127.0.0.1:0/"]


def test_perform_covered_raises_element_covered() -> None:
    # The point resolves to a different element: covered, not clicked. The layer's role
    # and text are carried for recovery (7c) and the user-facing flag.
    page = _FakePage(probe_value=_COVERED)
    driver = _driver_with_page(page)
    with pytest.raises(ElementCovered) as excinfo:
        driver.perform(_ACTION)
    assert excinfo.value.role == "link"
    assert excinfo.value.text == "Accept and continue"
    assert page.mouse.clicked_at is None  # never fired at the covering element


def test_perform_not_located_when_no_matching_node() -> None:
    # Nothing in the current tree matches: the element is gone, not covered.
    page = _FakePage(nodes=[], probe_value=_HITS_TARGET)
    driver = _driver_with_page(page)
    with pytest.raises(ElementNotLocated):
        driver.perform(_ACTION)
    assert page.mouse.clicked_at is None


def test_perform_wraps_cdp_failure_as_action_error() -> None:
    # A CDP hiccup while probing is a driver failure, not a fact about the element: it
    # becomes a plain ActionError (a recorded skip) with the cause chained, never a
    # covered/not-located verdict.
    cdp_error = PlaywrightError("Session closed")
    page = _FakePage(probe_value=_HITS_TARGET, call_error=cdp_error)
    driver = _driver_with_page(page)
    with pytest.raises(ActionError) as excinfo:
        driver.perform(_ACTION)
    assert type(excinfo.value) is ActionError  # base, not a subclass verdict
    assert excinfo.value.__cause__ is cdp_error
