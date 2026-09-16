"""Step definitions for features/testgen_writer.feature (§2g, sub-slice 2g-ii).

Two tiers. The fast-tier steps build a graph directly in-process (no browser, keyed by
friendly state names exactly as the 2g-i steps do) and exercise `render_suite` — that
it writes every generated source to disk, creates the directory, and writes nothing for
a graph with no transitions. The `@browser` step proves the whole loop end to end:
crawl a real fixture, write its suite, run pytest on that suite against the same live
fixture in a subprocess, and assert it passes green — the evidence the emitted tests
replay, fire, and assert correctly against a running target, not merely that they are
valid Python (which 2g-i already pins).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.capture import StateSignals, diff_signals
from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import explore
from spoor.exploration.graph import ExplorationGraph
from spoor.testgen import build_tests, render_suite

scenarios("testgen_writer.feature")


def _semis(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(";") if part.strip())


@pytest.fixture
def context() -> dict[str, Any]:
    # State names double as their state ids here (a readable id changes nothing the
    # generator does — see the 2g-i step module docstring).
    return {"graph": ExplorationGraph(), "signals": {}, "transitions": 0}


# --- Given: build a graph directly (fast tier) ---------------------------


@given("an explored graph:")
def graph_states(context: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    graph: ExplorationGraph = context["graph"]
    for row in rows:
        f = dict(zip(header, row, strict=True))
        signals = StateSignals(
            ax_node_count=int(f["ax_nodes"]),
            console_messages=_semis(f["console"]),
            storage_keys=_semis(f["storage"]),
            network_requests=_semis(f["network"]),
        )
        context["signals"][f["state"]] = signals
        graph.add_state(f["state"], [], signals)


@given("an empty explored graph")
def empty_graph(context: dict[str, Any]) -> None:
    context["graph"] = ExplorationGraph()
    context["signals"] = {}
    context["transitions"] = 0


@given(parsers.parse('a mapped transition "{label}" from "{frm}" to "{to}"'))
def a_transition(context: dict[str, Any], label: str, frm: str, to: str) -> None:
    graph: ExplorationGraph = context["graph"]
    action = ActionableElement(role="button", name=label, backend_node_id=1)
    graph.node(frm).actions.append(action)
    graph.add_transition(
        frm,
        action,
        to,
        diff_signals(context["signals"][frm], context["signals"][to]),
    )
    context["transitions"] += 1


# --- When: write the suite (fast tier) -----------------------------------


@when(parsers.parse('I write the suite for "{target}" to a directory'))
def write_suite(context: dict[str, Any], target: str, tmp_path: Path) -> None:
    out_dir = tmp_path / "suite"
    context["out_dir"] = out_dir
    context["target"] = target
    context["written"] = render_suite(context["graph"], out_dir, target=target)


@when(
    parsers.parse(
        'I write the suite for "{target}" to a directory that does not exist yet'
    )
)
def write_suite_missing_dir(
    context: dict[str, Any], target: str, tmp_path: Path
) -> None:
    # A nested path whose parents are absent, so the writer must create them.
    out_dir = tmp_path / "does" / "not" / "exist" / "suite"
    assert not out_dir.exists()
    context["out_dir"] = out_dir
    context["target"] = target
    context["written"] = render_suite(context["graph"], out_dir, target=target)


# --- Then: the writer's output (fast tier) -------------------------------


def _out_dir(context: dict[str, Any]) -> Path:
    return context["out_dir"]


@then("the directory contains a pytest conftest")
def dir_has_conftest(context: dict[str, Any]) -> None:
    assert (_out_dir(context) / "conftest.py").is_file()


@then("the directory contains a shared test helper module")
def dir_has_testkit(context: dict[str, Any]) -> None:
    assert (_out_dir(context) / "_spoor_testkit.py").is_file()


@then("the directory contains one test file per mapped transition")
def dir_has_one_test_per_transition(context: dict[str, Any]) -> None:
    test_files = sorted(_out_dir(context).glob("test_transition_*.py"))
    assert len(test_files) == context["transitions"]


@then("each written file's contents match the generated source")
def contents_match_generated(context: dict[str, Any]) -> None:
    # The writer must persist exactly what the pure generator produced — no rewriting.
    expected = build_tests(context["graph"], target=context["target"])
    assert {p.name for p in context["written"]} == set(expected)
    for path in context["written"]:
        assert path.read_text(encoding="utf-8") == expected[path.name]


@then("the directory now exists")
def dir_now_exists(context: dict[str, Any]) -> None:
    assert _out_dir(context).is_dir()


@then("no files are written to the directory")
def no_files_written(context: dict[str, Any]) -> None:
    assert context["written"] == []
    # The writer may create the (empty) directory, but nothing lands in it.
    assert list(_out_dir(context).iterdir()) == []


# --- Live (@browser) -----------------------------------------------------


@given(parsers.parse('a live crawl of "{page}" was mapped at depth {depth:d}'))
def live_crawl(
    context: dict[str, Any], live_server: str, page: str, depth: int
) -> None:
    url = f"{live_server}/{page}"
    context["target"] = url
    with PlaywrightDriver(url) as driver:
        context["graph"] = explore(
            driver,
            target=url,
            controller=RunController(RunBudget(max_depth=depth)),
        )
    # A crawl of the fixture must actually map something to export.
    assert context["graph"].transitions, "the live crawl mapped no transitions"


@when("I write that crawl's suite to a directory")
def write_live_suite(context: dict[str, Any], tmp_path: Path) -> None:
    out_dir = tmp_path / "live_suite"
    context["out_dir"] = out_dir
    context["written"] = render_suite(
        context["graph"], out_dir, target=context["target"]
    )


@when("I run pytest on that suite against the live fixture")
def run_generated_suite(context: dict[str, Any]) -> None:
    # A subprocess, not an in-process pytest.main: the generated conftest launches its
    # own Playwright browser, so isolating it from the outer test run is cleanest. The
    # live_server fixture is still serving (same process tree), and ht-spoor +
    # playwright are importable here, so the suite's baked-in TARGET is reachable.
    context["pytest_result"] = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(context["out_dir"])],
        capture_output=True,
        text=True,
    )


@then("the generated suite passes")
def generated_suite_passes(context: dict[str, Any]) -> None:
    result = context["pytest_result"]
    assert result.returncode == 0, (
        "the generated suite did not pass:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
