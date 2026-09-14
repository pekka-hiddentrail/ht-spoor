"""Step definitions for features/exploration_settling.feature (§2e, 7b).

The pure quiescence decision is exercised with no browser: a fake clock advanced only
by the injected `sleep`, and a scripted mutation signal, drive `wait_for_quiescence`.
Times are milliseconds throughout — the function is unit-agnostic, so the fake clock
counts in whatever unit the scenario states. The mutation schedule stands in for what a
real `MutationObserver` would report: a count that rises while the page churns and
holds steady once it goes quiet.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.settling import wait_for_quiescence

scenarios("exploration_settling.feature")

# A fine poll relative to the quiet windows the scenarios use, so settling is detected
# promptly and the fake clock advances in small, realistic steps.
_POLL_INTERVAL_MS = 50.0


@pytest.fixture
def context() -> dict[str, Any]:
    return {"now": 0.0}


@given(
    parsers.parse("a quiet window of {quiet:d} ms and a settle timeout of {to:d} ms")
)
def windows(context: dict[str, Any], quiet: int, to: int) -> None:
    context["quiet_window"] = float(quiet)
    context["timeout"] = float(to)


def _install_schedule(context: dict[str, Any], mutations_until: float | None) -> None:
    """Make `observe` report a cumulative count driven by the fake clock.

    `mutations_until` is the fake time up to which the page keeps mutating; the count
    rises with the clock until then and holds steady after. `None` means it never stops
    mutating (the count tracks the clock forever); a value of 0 means it never mutates.
    """

    def observe() -> int:
        now = context["now"]
        if mutations_until is None:
            return int(now)
        return int(min(now, mutations_until))

    context["observe"] = observe


@given(parsers.parse("a page that mutates for {duration:d} ms and then stops"))
def mutates_then_stops(context: dict[str, Any], duration: int) -> None:
    _install_schedule(context, float(duration))


@given("a page that never mutates")
def never_mutates(context: dict[str, Any]) -> None:
    _install_schedule(context, 0.0)


@given("a page that mutates continuously")
def mutates_continuously(context: dict[str, Any]) -> None:
    _install_schedule(context, None)


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
