"""Step definitions for features/exploration_control.feature (ROADMAP.md §2e).

Run-level controls are pure logic. Wall-clock time is read through a fake clock the
steps advance by hand, so the time bound is deterministic in-process — the same
injectable-clock seam `RunController` exposes for real runs.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.control import RunBudget, RunController

scenarios("exploration_control.feature")


class _FakeClock:
    """A monotonic clock the steps advance explicitly."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def context() -> dict[str, Any]:
    return {"clock": _FakeClock()}


def _controller(context: dict[str, Any], budget: RunBudget) -> RunController:
    controller = RunController(budget, clock=context["clock"])
    context["controller"] = controller
    return controller


# --- Given ---------------------------------------------------------------


@given("a run budget with no limits")
def budget_no_limits(context: dict[str, Any]) -> None:
    _controller(context, RunBudget())


@given(
    parsers.parse(
        "a run budget of max_states {states:d}, max_requests {requests:d},"
        " max_seconds {seconds:d}"
    )
)
def budget_all(
    context: dict[str, Any], states: int, requests: int, seconds: int
) -> None:
    _controller(
        context,
        RunBudget(max_states=states, max_requests=requests, max_seconds=seconds),
    )


@given(parsers.parse("a run budget of max_states {states:d}"))
def budget_states(context: dict[str, Any], states: int) -> None:
    _controller(context, RunBudget(max_states=states))


@given(parsers.parse("a run budget of max_requests {requests:d}"))
def budget_requests(context: dict[str, Any], requests: int) -> None:
    _controller(context, RunBudget(max_requests=requests))


@given(parsers.parse("a run budget of max_seconds {seconds:d}"))
def budget_seconds(context: dict[str, Any], seconds: int) -> None:
    _controller(context, RunBudget(max_seconds=seconds))


# --- When ----------------------------------------------------------------


@when(parsers.parse("{count:d} states are discovered"))
@when(parsers.parse("{count:d} state is discovered"))
def states_discovered(context: dict[str, Any], count: int) -> None:
    context["controller"].record_state(count)


@when(parsers.parse("{count:d} requests are made"))
@when(parsers.parse("{count:d} request is made"))
def requests_made(context: dict[str, Any], count: int) -> None:
    context["controller"].record_request(count)


@when(parsers.parse("{count:d} seconds of wall-clock time pass"))
@when(parsers.parse("{count:d} second of wall-clock time passes"))
def time_passes(context: dict[str, Any], count: int) -> None:
    context["clock"].now += count


@when("the kill switch is thrown")
def throw_kill_switch(context: dict[str, Any]) -> None:
    context["controller"].kill()


# --- Then ----------------------------------------------------------------


@then("the run is still running")
def run_still_running(context: dict[str, Any]) -> None:
    decision = context["controller"].check()
    assert decision.running, f"expected running, got stop: {decision.reason}"


@then(parsers.parse('the run stops with a reason mentioning "{text}"'))
def run_stops_with_reason(context: dict[str, Any], text: str) -> None:
    decision = context["controller"].check()
    assert decision.should_stop, "expected the run to stop"
    assert text in decision.reason, f"{text!r} not in reason {decision.reason!r}"


@then(parsers.parse("building a run budget of max_states {states:d} is rejected"))
def budget_states_rejected(context: dict[str, Any], states: int) -> None:
    with pytest.raises(ValueError):
        RunBudget(max_states=states)


@then(parsers.parse("building a run budget of max_requests {requests:d} is rejected"))
def budget_requests_rejected(context: dict[str, Any], requests: int) -> None:
    with pytest.raises(ValueError):
        RunBudget(max_requests=requests)


@then(parsers.parse("building a run budget of max_depth {depth:d} is rejected"))
def budget_depth_rejected(context: dict[str, Any], depth: int) -> None:
    with pytest.raises(ValueError):
        RunBudget(max_depth=depth)
