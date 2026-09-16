"""Step definitions for features/exploration_persisted_map.feature (§2e).

The persisted map is produced by the real projector the serving layer uses
(`shareable_exploration_map`) and loaded back by `load_exploration_map`, so these
steps exercise both ends of the contract at once — the round-trip that validates the
resume machinery across a save/load boundary, not just in memory.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.discovery import ActionableElement
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.persisted_map import load_exploration_map
from spoor.exploration.selector import graph_candidates, parse_selector, resolve_anchor
from spoor.serving.store import shareable_exploration_map

scenarios("exploration_persisted_map.feature")


def _action(step: str) -> ActionableElement:
    role, _, name = step.partition("=")
    return ActionableElement(role=role, name=name, backend_node_id=None)


def _path_steps(cell: str) -> tuple[tuple[str, str], ...]:
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
    from spoor.exploration.capture import StateSignals

    graph: ExplorationGraph = context["graph"]
    header, *rows = datatable
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        title = fields["title"].strip()
        signals = StateSignals(title=title) if title else None
        graph.add_state(fields["id"], actions=[], signals=signals)


@given("explored transitions:")
def explored_transitions(context: dict[str, Any], datatable: list[list[str]]) -> None:
    graph: ExplorationGraph = context["graph"]
    header, *rows = datatable
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        graph.add_transition(fields["from"], _action(fields["action"]), fields["to"])


@given("the graph is persisted to its shareable map")
def persist_graph(context: dict[str, Any]) -> None:
    context["persisted"] = shareable_exploration_map(context["graph"])


@given("an empty persisted map")
def empty_persisted_map(context: dict[str, Any]) -> None:
    context["persisted"] = {"states": [], "transitions": [], "skipped": []}


# --- When ----------------------------------------------------------------


@when("I load the persisted map into a graph")
def load_map(context: dict[str, Any]) -> None:
    context["loaded"] = load_exploration_map(context["persisted"])


@when("I build anchor candidates from the loaded graph")
def build_candidates(context: dict[str, Any]) -> None:
    context["candidates"] = graph_candidates(context["loaded"])


@when(parsers.parse('I resolve the selector "{selector}" against them'))
def resolve_selector_against(context: dict[str, Any], selector: str) -> None:
    context["resolution"] = resolve_anchor(
        [parse_selector(selector)], context["candidates"]
    )


@when(parsers.parse('I resolve the path selector "{path}" against them'))
def resolve_path_against(context: dict[str, Any], path: str) -> None:
    from spoor.exploration.selector import PathIs

    context["resolution"] = resolve_anchor(
        [PathIs(_path_steps(path))], context["candidates"]
    )


@when(parsers.parse('I resolve "{selector}" against the original in-memory graph'))
def resolve_against_original(context: dict[str, Any], selector: str) -> None:
    candidates = graph_candidates(context["graph"])
    context["original_res"] = resolve_anchor([parse_selector(selector)], candidates)


@when(parsers.parse('I resolve "{selector}" against the loaded graph'))
def resolve_against_loaded(context: dict[str, Any], selector: str) -> None:
    candidates = graph_candidates(context["loaded"])
    context["loaded_res"] = resolve_anchor([parse_selector(selector)], candidates)


# --- Then ----------------------------------------------------------------


@then(parsers.parse("the loaded graph has states {id_list}"))
def loaded_has_states(context: dict[str, Any], id_list: str) -> None:
    expected = re.findall(r'"([^"]+)"', id_list)
    assert context["loaded"].states == expected


@then(parsers.parse("the loaded graph has {count:d} transitions"))
def loaded_has_transitions(context: dict[str, Any], count: int) -> None:
    assert len(context["loaded"].transitions) == count


@then("the loaded graph has no states")
def loaded_has_no_states(context: dict[str, Any]) -> None:
    assert context["loaded"].states == []


@then(parsers.parse('it resolves to the state "{state_id}"'))
def resolves_to(context: dict[str, Any], state_id: str) -> None:
    resolution = context["resolution"]
    assert resolution.is_resolved, f"did not resolve: {resolution.matches}"
    assert resolution.state_id == state_id


@then("it reports no matching state")
def reports_unmatched(context: dict[str, Any]) -> None:
    assert context["resolution"].is_unmatched


@then(parsers.parse('both resolve to the same state "{state_id}"'))
def both_resolve_same(context: dict[str, Any], state_id: str) -> None:
    original = context["original_res"]
    loaded = context["loaded_res"]
    assert original.is_resolved and loaded.is_resolved
    assert original.state_id == loaded.state_id == state_id
