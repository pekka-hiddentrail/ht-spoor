"""Unit tests for the live browser driver's action contract (ROADMAP.md §2e).

The full driver is exercised end to end against real sites by the integration tests,
which need a headless Chromium and the docker bench. These browser-free tests pin the
one piece of behaviour that must hold without a live page: `perform` translates a
Playwright actuation failure into the explorer's domain `ActionError` (so a single
dead element is a recorded skip, not a crashed run), and a post-click load-state
timeout is swallowed (an in-page state change leaves the page already idle).

A hand-rolled fake page stands in for the Playwright `Page`, injected onto the driver
directly; `perform` only touches `get_by_role(...).first.click(...)` and
`wait_for_load_state(...)`, so the fake implements exactly those.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from spoor.exploration.discovery import ActionableElement
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import ActionError

_ACTION = ActionableElement(role="button", name="Open menu", backend_node_id=1)


class _FakeLocator:
    def __init__(self, click_error: Exception | None) -> None:
        self._click_error = click_error
        self.clicked = False

    @property
    def first(self) -> _FakeLocator:
        return self

    def click(self, timeout: float | None = None) -> None:
        if self._click_error is not None:
            raise self._click_error
        self.clicked = True


class _FakePage:
    def __init__(
        self,
        *,
        click_error: Exception | None = None,
        load_error: Exception | None = None,
    ) -> None:
        self.locator = _FakeLocator(click_error)
        self._load_error = load_error

    def get_by_role(self, role: str, **kwargs: object) -> _FakeLocator:
        return self.locator

    def wait_for_load_state(self, state: str, timeout: float | None = None) -> None:
        if self._load_error is not None:
            raise self._load_error


def _driver_with_page(page: _FakePage) -> PlaywrightDriver:
    driver = PlaywrightDriver("http://127.0.0.1:0/")
    driver._page = page  # type: ignore[assignment]
    return driver


@pytest.mark.parametrize(
    "click_error",
    [
        PlaywrightTimeoutError("Timeout 5000ms exceeded"),
        PlaywrightError("element is not attached to the DOM"),
    ],
)
def test_perform_translates_click_failure_to_action_error(
    click_error: Exception,
) -> None:
    driver = _driver_with_page(_FakePage(click_error=click_error))
    with pytest.raises(ActionError) as excinfo:
        driver.perform(_ACTION)
    # The Playwright detail is preserved as the chained cause for debugging, but the
    # domain error is what the explorer catches.
    assert excinfo.value.__cause__ is click_error


def test_perform_swallows_post_click_load_timeout() -> None:
    # A click that triggers only an in-page change leaves the page already idle, so a
    # networkidle timeout afterwards must not fail the action.
    page = _FakePage(load_error=PlaywrightTimeoutError("networkidle timeout"))
    driver = _driver_with_page(page)
    driver.perform(_ACTION)  # does not raise
    assert page.locator.clicked


def test_perform_succeeds_when_click_and_wait_are_clean() -> None:
    page = _FakePage()
    driver = _driver_with_page(page)
    driver.perform(_ACTION)
    assert page.locator.clicked
