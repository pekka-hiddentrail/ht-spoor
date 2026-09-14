"""Unit tests for the live browser driver's action contract (ROADMAP.md §2e).

The full driver is exercised end to end against real pages by the live scenarios
(`exploration_actuation_live.feature`), which need a headless Chromium. These
browser-free tests pin the pieces of robust actuation (7a) that must hold without a
live page: `perform` re-locates through the accessibility tree, resolves the node and
hit-tests its click point over CDP, and turns the result into one of three honest
outcomes — a coordinate click (ACTUATE), `ElementCovered`, or `ElementNotLocated` —
while a CDP failure becomes a plain `ActionError` (a recorded skip, not a crash) and a
post-click load-state timeout is swallowed (an in-page change leaves the page idle).

A hand-rolled fake page stands in for the Playwright `Page`, injected onto the driver
directly. `perform` touches `ax_nodes()` (a CDP accessibility-tree read), a second CDP
session for `DOM.resolveNode` + `Runtime.callFunctionOn`, `page.mouse.click(...)`, and
`wait_for_load_state(...)`, so the fake implements exactly those.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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

    def new_cdp_session(self, page: object) -> _FakeCDPSession:
        return self._session


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
        load_error: Exception | None = None,
    ) -> None:
        self.session = _FakeCDPSession(
            nodes=nodes, probe_value=probe_value, call_error=call_error
        )
        self.context = _FakeContext(self.session)
        self.mouse = _FakeMouse()
        self._load_error = load_error

    def wait_for_load_state(self, state: str, timeout: float | None = None) -> None:
        if self._load_error is not None:
            raise self._load_error


def _driver_with_page(page: _FakePage) -> PlaywrightDriver:
    driver = PlaywrightDriver("http://127.0.0.1:0/")
    driver._page = page  # type: ignore[assignment]
    return driver


def test_perform_clicks_verified_point() -> None:
    page = _FakePage(probe_value=_HITS_TARGET)
    driver = _driver_with_page(page)
    driver.perform(_ACTION)
    assert page.mouse.clicked_at == (10.0, 20.0)


def test_perform_swallows_post_click_load_timeout() -> None:
    # A click that triggers only an in-page change leaves the page already idle, so a
    # networkidle timeout afterwards must not fail the action.
    page = _FakePage(
        probe_value=_HITS_TARGET,
        load_error=PlaywrightTimeoutError("networkidle timeout"),
    )
    driver = _driver_with_page(page)
    driver.perform(_ACTION)  # does not raise
    assert page.mouse.clicked_at == (10.0, 20.0)


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
