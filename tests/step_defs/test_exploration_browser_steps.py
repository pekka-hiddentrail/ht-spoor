"""Step definitions for features/exploration_browser.feature (ROADMAP.md §2e, 5b).

The whole exploration stack, end to end, in a real headless browser: these steps
run the actual `spoor explore` CLI command against a small static site served over a
real loopback socket (the `live_server` fixture), then assert on the printed run
summary. A browser can't use the in-process fixture transport, which is why this is
the one exploration slice with a live socket and a real Chromium launch.
"""

from __future__ import annotations

from pathlib import Path
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


# --- slice 6b: the --wiki flag -------------------------------------------


@when("I run spoor explore against it writing a wiki")
def run_spoor_explore_with_wiki(context: dict[str, Any], tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    result = CliRunner().invoke(
        app,
        [
            "explore",
            context["url"],
            "--max-states",
            "10",
            "--max-requests",
            "50",
            "--wiki",
            str(wiki_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    context["output"] = result.output
    context["wiki_dir"] = wiki_dir


@then("it reports where the wiki was written")
def reports_wiki_path(context: dict[str, Any]) -> None:
    assert "wiki written to:" in context["output"], context["output"]


@then("the wiki has an index page and a page for each state and transition")
def wiki_is_complete(context: dict[str, Any]) -> None:
    wiki_dir: Path = context["wiki_dir"]
    index = wiki_dir / "index.html"
    assert index.is_file(), f"no index written to {wiki_dir}"
    # A page for every state and every transition the run's summary reported.
    states = _summary_count(context, "states discovered")
    transitions = _summary_count(context, "transitions")
    for i in range(states):
        assert (wiki_dir / f"state-{i}.html").is_file()
    for j in range(transitions):
        assert (wiki_dir / f"transition-{j}.html").is_file()


@then(
    parsers.parse(
        "the wiki index reports {states:d} states and {transitions:d} transitions"
    )
)
def wiki_index_counts(context: dict[str, Any], states: int, transitions: int) -> None:
    index = (context["wiki_dir"] / "index.html").read_text(encoding="utf-8")
    assert f"<strong>{states}</strong> states discovered" in index
    assert f"<strong>{transitions}</strong> transitions" in index


def _summary_count(context: dict[str, Any], label: str) -> int:
    """Pull a count off the printed run summary line ``  <label>: <n>``."""
    for line in context["output"].splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{label}:"):
            return int(stripped.split(":", 1)[1].strip())
    raise AssertionError(f"no {label!r} line in output:\n{context['output']}")
