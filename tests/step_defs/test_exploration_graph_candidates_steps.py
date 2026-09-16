"""Step definitions for features/exploration_graph_candidates.feature (§2e).

Building anchor candidates from a graph is pure logic, so these steps assemble an
in-memory `ExplorationGraph` from the Background tables (a state carries captured
`StateSignals` only when it has a title; an empty-title row gets no signals, the
signal-less state the feature pins), feed it to `graph_candidates`, and assert on
the candidates — including resolving a selector through them end to end.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.capture import StateSignals
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.selector import (
    PathIs,
    graph_candidates,
    parse_selector,
    resolve_anchor,
)
from spoor.security.redaction import REDACTED

scenarios("exploration_graph_candidates.feature")


def _action(step: str) -> ActionableElement:
    """Decode a `role=name` table cell into an ActionableElement."""
    role, _, name = step.partition("=")
    return ActionableElement(role=role, name=name, backend_node_id=None)


def _path_steps(cell: str) -> tuple[tuple[str, str], ...]:
    """Decode a `role=name>role=name` path cell into (role, name) steps."""
    cell = cell.strip()
    if not cell:
        return ()
    return tuple((s.partition("=")[0], s.partition("=")[2]) for s in cell.split(">"))


@pytest.fixture
def context() -> dict[str, Any]:
    return {"graph": ExplorationGraph()}


# --- Given ---------------------------------------------------------------


@given("an explored graph with states:")
def a_graph_with_states(context: dict[str, Any], datatable: list[list[str]]) -> None:
    graph: ExplorationGraph = context["graph"]
    header, *rows = datatable
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        title = fields["title"].strip()
        # A state with no captured title stands in for one with no signal bundle.
        signals = StateSignals(title=title) if title else None
        graph.add_state(fields["id"], actions=[], signals=signals)


@given("explored transitions:")
def explored_transitions(context: dict[str, Any], datatable: list[list[str]]) -> None:
    graph: ExplorationGraph = context["graph"]
    header, *rows = datatable
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        graph.add_transition(fields["from"], _action(fields["action"]), fields["to"])


# --- When ----------------------------------------------------------------


@when("I build anchor candidates from the graph")
def build_candidates(context: dict[str, Any]) -> None:
    candidates = graph_candidates(context["graph"])
    context["candidates"] = candidates
    context["by_id"] = {candidate.state_id: candidate for candidate in candidates}


@when(parsers.parse('I resolve the selector "{selector}" against them'))
def resolve_selector_against(context: dict[str, Any], selector: str) -> None:
    context["resolution"] = resolve_anchor(
        [parse_selector(selector)], context["candidates"]
    )


@when(parsers.parse('I resolve the path selector "{path}" against them'))
def resolve_path_against(context: dict[str, Any], path: str) -> None:
    context["resolution"] = resolve_anchor(
        [PathIs(_path_steps(path))], context["candidates"]
    )


# --- Then ----------------------------------------------------------------


@then(parsers.parse("the candidate ids are {id_list}"))
def candidate_ids_are(context: dict[str, Any], id_list: str) -> None:
    expected = re.findall(r'"([^"]+)"', id_list)
    actual = [candidate.state_id for candidate in context["candidates"]]
    assert actual == expected


@then(parsers.parse('the candidate "{sid}" has title "{title}"'))
def candidate_has_title(context: dict[str, Any], sid: str, title: str) -> None:
    assert context["by_id"][sid].title == title


@then(parsers.parse('the candidate "{sid}" title has no secret in it'))
def candidate_title_redacted(context: dict[str, Any], sid: str) -> None:
    title = context["by_id"][sid].title
    assert title is not None
    assert REDACTED in title
    assert "abc123def456ghi789" not in title


@then(parsers.parse('the candidate "{sid}" has no title'))
def candidate_has_no_title(context: dict[str, Any], sid: str) -> None:
    assert context["by_id"][sid].title is None


@then(parsers.parse('the candidate "{sid}" has an empty path'))
def candidate_has_empty_path(context: dict[str, Any], sid: str) -> None:
    assert context["by_id"][sid].path == ()


@then(parsers.parse('the candidate "{sid}" has the path "{path}"'))
def candidate_has_path(context: dict[str, Any], sid: str, path: str) -> None:
    assert context["by_id"][sid].path == _path_steps(path)


@then(parsers.parse('it resolves to the state "{state_id}"'))
def resolves_to(context: dict[str, Any], state_id: str) -> None:
    resolution = context["resolution"]
    assert resolution.is_resolved, f"did not resolve to one state: {resolution.matches}"
    assert resolution.state_id == state_id


@then("it reports no matching state")
def reports_unmatched(context: dict[str, Any]) -> None:
    assert context["resolution"].is_unmatched
