"""Step definitions for features/exploration_opened_screenshots_live.feature (§2e, 8e).

The real PlaywrightDriver is driven against the opened-contents fixture served over a
loopback socket (the `live_server` fixture), proving the live half of slice 8e that the
in-process scenarios can't: that `opened_screenshot` actually opens a disclosure element
in a headless Chromium, captures the revealed in-DOM content, and Escape-restores. The
fixture's "Currency" combobox reveals an option list on click, so a correct capture
differs from the closed page; the driver is opened per scenario and torn down after.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.discovery import ActionableElement
from spoor.exploration.driver import PlaywrightDriver

scenarios("exploration_opened_screenshots_live.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


@pytest.fixture(autouse=True)
def _teardown(context: dict[str, Any]) -> Any:
    yield
    driver = context.get("driver")
    if driver is not None:
        driver.close()


@given(parsers.parse('a live browser on the opened-contents fixture "{page}"'))
def live_browser(context: dict[str, Any], live_server: str, page: str) -> None:
    driver = PlaywrightDriver(f"{live_server}/{page}")
    driver.__enter__()
    driver.reset()
    context["driver"] = driver
    # The closed page, to prove the opened capture differs (the click revealed content).
    context["closed"] = driver.screenshot()


@when(parsers.parse('I capture the opened contents of the "{role}" named "{name}"'))
def capture_opened(context: dict[str, Any], role: str, name: str) -> None:
    driver: PlaywrightDriver = context["driver"]
    action = ActionableElement(role=role, name=name, backend_node_id=None)
    context["opened"] = driver.opened_screenshot(action)


@then("a PNG image of the opened contents is returned")
def opened_is_png(context: dict[str, Any]) -> None:
    opened = context["opened"]
    assert opened is not None, "opened_screenshot returned None"
    assert opened[:8] == b"\x89PNG\r\n\x1a\n", "opened capture is not a PNG"


@then("it differs from the closed page, so the click revealed content")
def opened_differs(context: dict[str, Any]) -> None:
    closed = context["closed"]
    assert closed is not None, "could not capture the closed page for comparison"
    assert context["opened"] != closed, "opened capture matches the closed page"


@then("the page is restored to its closed state afterwards")
def page_restored(context: dict[str, Any]) -> None:
    html = context["driver"].state_html()
    assert 'aria-expanded="false"' in html, "combobox left expanded after capture"
    assert 'aria-expanded="true"' not in html, "combobox still expanded after capture"
