"""Step definitions for features/exploration_actuation_live.feature (§2e, 7a).

The real PlaywrightDriver is driven against the actuation fixture served over a
loopback socket (the `live_server` fixture), proving robust actuation end to end in a
real headless browser: an icon button named only by an aria-label is clicked, a
below-the-fold button is scrolled into view and clicked, a covered button is reported
covered without activating the overlay, and the viewport is pinned for reproducibility.
The driver is opened as a context manager per scenario and torn down in a finalizer.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.discovery import ActionableElement
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import ElementCovered

scenarios("exploration_actuation_live.feature")

# The fixed viewport the driver pins (spoor/exploration/driver.py).
_EXPECTED_VIEWPORT = {"width": 1280, "height": 800}


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


@given(parsers.parse('a live browser on the actuation fixture "{page}"'))
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


@when(parsers.parse('I actuate the "{role}" named "{name}"'))
def actuate(context: dict[str, Any], role: str, name: str) -> None:
    driver: PlaywrightDriver = context["driver"]
    driver.perform(ActionableElement(role=role, name=name, backend_node_id=None))


@when(parsers.parse('I try to actuate the "{role}" named "{name}"'))
def try_actuate(context: dict[str, Any], role: str, name: str) -> None:
    driver: PlaywrightDriver = context["driver"]
    try:
        driver.perform(ActionableElement(role=role, name=name, backend_node_id=None))
    except Exception as exc:  # noqa: BLE001 — the scenario asserts which type it is
        context["error"] = exc


def _evaluate(context: dict[str, Any], js: str) -> Any:
    return context["driver"]._live_page.evaluate(js)


@then(parsers.parse('the fixture records that "{name}" was clicked'))
def records_clicked(context: dict[str, Any], name: str) -> None:
    assert _evaluate(context, "() => window.__clicked") == name


@then("the driver reports the element as covered")
def reports_covered(context: dict[str, Any]) -> None:
    error = context.get("error")
    assert isinstance(error, ElementCovered), f"expected ElementCovered, got {error!r}"


@then("the fixture records that the overlay was not activated")
def overlay_not_activated(context: dict[str, Any]) -> None:
    assert _evaluate(context, "() => window.__overlayActivated") is False


@then("the live page reports a fixed viewport")
def fixed_viewport(context: dict[str, Any]) -> None:
    assert context["driver"]._live_page.viewport_size == _EXPECTED_VIEWPORT
