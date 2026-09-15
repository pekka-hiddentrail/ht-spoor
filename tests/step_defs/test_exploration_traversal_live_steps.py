"""Step definitions for features/exploration_traversal_live.feature (§2e slice 9).

The real PlaywrightDriver's `current_url` is exercised end to end against the two-page
traversal fixture served over a loopback socket (the `live_server` fixture): it reports
the URL of the page actually loaded, and — crucially for the frontier fork — reports the
new URL after a real navigation, not the stale entry URL. The driver is opened as a
context manager per scenario and torn down in a finalizer.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.discovery import ActionableElement
from spoor.exploration.driver import PlaywrightDriver

scenarios("exploration_traversal_live.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


@given(parsers.parse('a live browser on the traversal fixture "{page}"'))
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


@then(parsers.parse('the driver reports a current URL ending in "{suffix}"'))
def current_url_ends_with(context: dict[str, Any], suffix: str) -> None:
    url = context["driver"].current_url()
    assert url.endswith(suffix), f"{url!r} does not end with {suffix!r}"
