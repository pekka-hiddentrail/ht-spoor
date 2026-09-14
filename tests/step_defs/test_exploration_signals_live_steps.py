"""Step definitions for features/exploration_signals_live.feature (§2e, 5c-ii).

The real PlaywrightDriver is driven against a signal-rich static fixture served over
a loopback socket (the `live_server` fixture), so `capture_signals` is exercised
against an actual Chromium page — genuine console output, web storage, network
requests, accessibility nodes, and a screenshot. The driver is opened as a context
manager per scenario and torn down in a fixture finalizer.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.capture import diff_signals
from spoor.exploration.discovery import discover_actions
from spoor.exploration.driver import PlaywrightDriver

scenarios("exploration_signals_live.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


@given(parsers.parse('a live browser on the signals fixture "{page}"'))
def live_browser(context: dict[str, Any], live_server: str, page: str) -> None:
    driver = PlaywrightDriver(f"{live_server}/{page}")
    driver.__enter__()
    context["driver"] = driver
    driver.reset()


@pytest.fixture(autouse=True)
def _teardown(context: dict[str, Any]) -> Any:
    yield
    driver = context.get("driver")
    if driver is not None:
        driver.close()


def _find(driver: PlaywrightDriver, label: str) -> Any:
    for action in discover_actions(driver.ax_nodes()):
        if action.name == label:
            return action
    raise AssertionError(f"no actionable element named {label!r}")


@when("I capture the current signals")
def capture_current(context: dict[str, Any]) -> None:
    context["bundle"] = context["driver"].capture_signals()


@when(parsers.parse('I capture, click "{label}", and capture again'))
def capture_click_capture(context: dict[str, Any], label: str) -> None:
    driver: PlaywrightDriver = context["driver"]
    before = driver.capture_signals()
    driver.perform(_find(driver, label))
    after = driver.capture_signals()
    context["diff"] = diff_signals(before, after)


# --- bundle assertions ---------------------------------------------------


@then("the bundle has a screenshot hash")
def bundle_screenshot(context: dict[str, Any]) -> None:
    assert context["bundle"].screenshot_hash is not None


@then(parsers.parse('the bundle includes the storage key "{key}"'))
def bundle_storage(context: dict[str, Any], key: str) -> None:
    assert key in context["bundle"].storage_keys


@then(parsers.parse('the bundle logged the console message "{msg}"'))
def bundle_console(context: dict[str, Any], msg: str) -> None:
    assert msg in context["bundle"].console_messages


@then("the bundle counts more than zero accessibility nodes")
def bundle_ax(context: dict[str, Any]) -> None:
    assert context["bundle"].ax_node_count > 0


# --- diff assertions -----------------------------------------------------


@then(parsers.parse('the diff added the console message "{msg}"'))
def diff_console(context: dict[str, Any], msg: str) -> None:
    assert msg in context["diff"].console_added


@then(parsers.parse('the diff added the storage key "{key}"'))
def diff_storage(context: dict[str, Any], key: str) -> None:
    assert key in context["diff"].storage_added


@then("the diff recorded at least one network request")
def diff_network(context: dict[str, Any]) -> None:
    assert len(context["diff"].network_added) >= 1


@then("the diff marks the screenshot as changed")
def diff_screenshot(context: dict[str, Any]) -> None:
    assert context["diff"].screenshot_changed is True
