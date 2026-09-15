"""Step definitions for features/testgen.feature (ROADMAP.md §2g, sub-slice 2g-i).

The pure generator is exercised against a graph built directly in-process — no browser,
no disk. States are keyed by their friendly name (a real run keys them by the 64-char
`state_id`, which the generator only shortens for a docstring label, so a readable id
changes nothing it does), each carrying a `StateSignals` bundle from the Background
table; a mapped transition carries the real `diff_signals` of its endpoints' bundles,
exactly as the explorer records it. The steps render `build_tests` and assert on the
generated pytest sources — that they are valid Python, replay the path, fire the action,
assert what it changed, and never carry a raw secret.
"""

from __future__ import annotations

import ast
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.capture import StateSignals, diff_signals
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.graph import ExplorationGraph
from spoor.security.redaction import REDACTED, redact
from spoor.testgen import build_tests

scenarios("testgen.feature")


def _semis(raw: str) -> tuple[str, ...]:
    """A semicolon-separated table cell into a tuple (the bundle's list shape)."""
    return tuple(part.strip() for part in raw.split(";") if part.strip())


@pytest.fixture
def context() -> dict[str, Any]:
    # State names double as their state ids here (see the module docstring).
    return {"graph": ExplorationGraph(), "signals": {}}


# --- Given ---------------------------------------------------------------


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


@given(parsers.parse('a mapped transition "{label}" from "{frm}" to "{to}"'))
def a_transition(context: dict[str, Any], label: str, frm: str, to: str) -> None:
    _add_transition(context, label, frm, to)


@given(
    parsers.parse(
        'a mapped transition "{label}" from "{frm}" to "{to}" that changed nothing'
    )
)
def a_no_change_transition(
    context: dict[str, Any], label: str, frm: str, to: str
) -> None:
    # frm and to are the same state, so the before/after diff is empty by construction.
    _add_transition(context, label, frm, to)


def _add_transition(context: dict[str, Any], label: str, frm: str, to: str) -> None:
    graph: ExplorationGraph = context["graph"]
    action = ActionableElement(role="button", name=label, backend_node_id=1)
    graph.node(frm).actions.append(action)
    graph.add_transition(
        frm,
        action,
        to,
        diff_signals(context["signals"][frm], context["signals"][to]),
    )


@given(parsers.parse('a state "{name}" whose console logged "{message}"'))
def a_state_with_console(context: dict[str, Any], name: str, message: str) -> None:
    graph: ExplorationGraph = context["graph"]
    signals = StateSignals(ax_node_count=1, console_messages=(message,))
    context["signals"][name] = signals
    graph.add_state(name, [], signals)


# --- When ----------------------------------------------------------------


@when(parsers.parse('I generate a pytest suite for "{target}"'))
def generate(context: dict[str, Any], target: str) -> None:
    context["suite"] = build_tests(context["graph"], target=target)


# --- helpers -------------------------------------------------------------


def _suite(context: dict[str, Any]) -> dict[str, str]:
    return context["suite"]


def _test_files(context: dict[str, Any]) -> dict[str, str]:
    return {
        name: src
        for name, src in _suite(context).items()
        if name.startswith("test_transition_")
    }


def _test_for(context: dict[str, Any], label: str) -> str:
    """The generated test whose *fired* action (not a replayed path step) is `label`."""
    needle = repr(redact(label))
    for src in _test_files(context).values():
        for line in src.splitlines():
            if line.strip().startswith("fire(page,") and needle in line:
                return src
    raise AssertionError(f"no generated test fires an action named {label!r}")


def _path_block(src: str) -> str:
    """The `_PATH = [...]` region of a test source (the replayed path steps)."""
    start = src.index("_PATH = [")
    return src[start : src.index("]", start)]


# --- Then: structure -----------------------------------------------------


@then("the suite has a pytest conftest")
def has_conftest(context: dict[str, Any]) -> None:
    assert "conftest.py" in _suite(context)


@then("the suite has a shared test helper module")
def has_testkit(context: dict[str, Any]) -> None:
    assert "_spoor_testkit.py" in _suite(context)


@then("the suite has one test file per mapped transition")
def one_test_per_transition(context: dict[str, Any]) -> None:
    assert len(_test_files(context)) == len(context["graph"].transitions)


@then("every generated file is valid Python")
def valid_python(context: dict[str, Any]) -> None:
    for src in _suite(context).values():
        ast.parse(src)  # raises SyntaxError if the generated source is malformed


@then("the suite has no test files")
def no_test_files(context: dict[str, Any]) -> None:
    assert _test_files(context) == {}


# --- Then: replay + assertions -------------------------------------------


@then(parsers.parse('the test for "{label}" fires the action named "{name}"'))
def fires_action(context: dict[str, Any], label: str, name: str) -> None:
    src = _test_for(context, label)
    assert f"fire(page, 'button', {redact(name)!r})" in src


@then(parsers.parse('the test for "{label}" replays the action "{name}" first'))
def replays_first(context: dict[str, Any], label: str, name: str) -> None:
    src = _test_for(context, label)
    assert repr(redact(name)) in _path_block(src)


@then(
    parsers.parse('the test for "{label}" asserts the added console message "{msg}"')
)
def asserts_console(context: dict[str, Any], label: str, msg: str) -> None:
    src = _test_for(context, label)
    assert f"assert {redact(msg)!r} in console" in src


@then(parsers.parse('the test for "{label}" asserts the added storage key "{key}"'))
def asserts_storage(context: dict[str, Any], label: str, key: str) -> None:
    src = _test_for(context, label)
    assert f"assert {redact(key)!r} in storage" in src


@then(
    parsers.parse('the test for "{label}" asserts the added network request "{url}"')
)
def asserts_network(context: dict[str, Any], label: str, url: str) -> None:
    src = _test_for(context, label)
    assert f"assert any({redact(url)!r} in request for request in network)" in src


@then(parsers.parse('the test for "{label}" asserts no signal changes'))
def asserts_nothing(context: dict[str, Any], label: str) -> None:
    src = _test_for(context, label)
    assert "no signal changes were recorded" in src
    assert "\n    assert " not in src


# --- Then: redaction (§2h) -----------------------------------------------


@then(parsers.parse('no generated file contains the raw secret "{secret}"'))
def no_raw_secret(context: dict[str, Any], secret: str) -> None:
    for name, src in _suite(context).items():
        assert secret not in src, f"raw secret leaked into {name}"


@then("some generated file shows the redaction placeholder")
def shows_placeholder(context: dict[str, Any]) -> None:
    assert any(REDACTED in src for src in _suite(context).values())
