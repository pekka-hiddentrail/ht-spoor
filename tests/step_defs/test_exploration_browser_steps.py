"""Step definitions for features/exploration_browser.feature (ROADMAP.md §2e, 5b).

The whole exploration stack, end to end, in a real headless browser: these steps
run the actual `spoor explore` CLI command against a small static site served over a
real loopback socket (the `live_server` fixture), then assert on the printed run
summary. A browser can't use the in-process fixture transport, which is why this is
the one exploration slice with a live socket and a real Chromium launch.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from typer.testing import CliRunner

from spoor.cli import app

scenarios("exploration_browser.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


@given(parsers.parse('a live fixture site starting at "{page}"'))
def live_fixture_site(context: dict[str, Any], live_server: str, page: str) -> None:
    context["url"] = f"{live_server}/{page}"


@when("I run spoor explore against it")
def run_spoor_explore(context: dict[str, Any]) -> None:
    result = CliRunner().invoke(
        app, ["explore", context["url"], "--max-states", "10", "--max-requests", "50"]
    )
    assert result.exit_code == 0, result.output
    context["output"] = result.output


@then(parsers.parse("it reports {n:d} states discovered"))
def reports_states(context: dict[str, Any], n: int) -> None:
    assert f"states discovered: {n}" in context["output"], context["output"]


@then(parsers.parse("it reports {n:d} transitions"))
def reports_transitions(context: dict[str, Any], n: int) -> None:
    assert f"transitions:       {n}" in context["output"], context["output"]


@then(parsers.parse("it reports {n:d} actions skipped"))
def reports_skipped(context: dict[str, Any], n: int) -> None:
    assert f"actions skipped:   {n}" in context["output"], context["output"]
