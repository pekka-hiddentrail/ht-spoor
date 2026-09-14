"""Step definitions for features/exploration_settling_live.feature (§2e, 7b).

The real PlaywrightDriver's settling and reset fidelity are exercised end to end against
the settling fixtures served over loopback (the `live_server` fixture): a reset clears
cookies and web storage so a returning visitor becomes a first visit again, discovery
waits for content that renders after the load event, and a page that mutates forever is
captured flagged unsettled rather than hanging or crashing the run.

The driver is built with a short settle timeout and quiet window so the never-quiet
scenario finishes in a couple of seconds; production defaults (a longer safety timeout)
are unaffected — these are test timings, not a behaviour change. The driver is opened as
a context manager per scenario and torn down in a finalizer.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.discovery import discover_actions
from spoor.exploration.driver import PlaywrightDriver

scenarios("exploration_settling_live.feature")

# Test timings: quiet window comfortably above the fixtures' render/mutation cadence,
# and a short bounded timeout so the never-quiet fixture reports unsettled quickly.
_QUIET_WINDOW_S = 0.3
_SETTLE_TIMEOUT_S = 2.0


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


@given(parsers.parse('a live browser on the settling fixture "{page}"'))
def live_browser(context: dict[str, Any], live_server: str, page: str) -> None:
    driver = PlaywrightDriver(
        f"{live_server}/{page}",
        quiet_window=_QUIET_WINDOW_S,
        settle_timeout=_SETTLE_TIMEOUT_S,
    )
    driver.__enter__()
    context["driver"] = driver


@pytest.fixture(autouse=True)
def _teardown(context: dict[str, Any]) -> Any:
    yield
    driver = context.get("driver")
    if driver is not None:
        driver.close()


@when("the page has recorded a return visit")
def record_return_visit(context: dict[str, Any]) -> None:
    driver: PlaywrightDriver = context["driver"]
    driver.reset()  # load the page so its script (and __recordReturn) is present
    driver._live_page.evaluate("() => window.__recordReturn()")


@when("the explorer resets the browser")
def reset_browser(context: dict[str, Any]) -> None:
    context["driver"].reset()


@then("the page shows its first-visit content")
def shows_first_visit(context: dict[str, Any]) -> None:
    driver: PlaywrightDriver = context["driver"]
    text = driver._live_page.evaluate(
        "() => document.getElementById('visit').textContent"
    )
    assert text == "Welcome, new visitor", text


@then(parsers.parse('the discovered actions include the "{role}" named "{name}"'))
def discovered_includes(context: dict[str, Any], role: str, name: str) -> None:
    driver: PlaywrightDriver = context["driver"]
    actions = discover_actions(driver.ax_nodes())
    assert any(a.role == role and a.name == name for a in actions), actions


@then("the captured state is flagged as unsettled")
def captured_unsettled(context: dict[str, Any]) -> None:
    driver: PlaywrightDriver = context["driver"]
    assert driver.capture_signals().settled is False
