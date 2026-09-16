"""Step definitions for features/exploration_state_selector.feature (§2e).

Anchor resolution is pure logic, so these steps build an in-memory candidate set
from the Background table and feed selectors straight to the resolver — no browser,
no disk. The table's `path` column encodes the (role, name) action sequence as
`role=name>role=name` (empty for the root); an empty `title`/`url` cell becomes
`None`, mirroring a persisted state that lacks that field.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.selector import (
    AnchorCandidate,
    PathIs,
    SelectorError,
    parse_selector,
    resolve_anchor,
)

scenarios("exploration_state_selector.feature")


def _parse_path(cell: str) -> tuple[tuple[str, str], ...]:
    """Decode a `role=name>role=name` path cell into (role, name) steps."""
    cell = cell.strip()
    if not cell:
        return ()
    steps = []
    for step in cell.split(">"):
        role, _, name = step.partition("=")
        steps.append((role, name))
    return tuple(steps)


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


# --- Given ---------------------------------------------------------------


@given("a mapped graph with states:")
def a_mapped_graph(context: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    candidates = []
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        candidates.append(
            AnchorCandidate(
                state_id=fields["id"],
                title=fields["title"].strip() or None,
                url=fields["url"].strip() or None,
                path=_parse_path(fields["path"]),
            )
        )
    context["candidates"] = candidates


# --- When ----------------------------------------------------------------


def _run(context: dict[str, Any], *selectors: str, path: str | None = None) -> None:
    """Resolve the given flat selectors (+ optional path), recording error or result."""
    try:
        constraints = [parse_selector(text) for text in selectors]
        if path is not None:
            constraints.append(PathIs(_parse_path(path)))
        context["resolution"] = resolve_anchor(constraints, context["candidates"])
        context["error"] = None
    except SelectorError as exc:
        context["resolution"] = None
        context["error"] = exc


@when(parsers.parse('I resolve the selector "{selector}"'))
def resolve_selector(context: dict[str, Any], selector: str) -> None:
    _run(context, selector)


@when(parsers.parse('I resolve the path selector "{path}"'))
def resolve_path_selector(context: dict[str, Any], path: str) -> None:
    _run(context, path=path)


@when(parsers.parse('I resolve the combined selector "{first}" and "{second}"'))
def resolve_combined_selector(
    context: dict[str, Any], first: str, second: str
) -> None:
    _run(context, first, second)


# --- Then ----------------------------------------------------------------


@then(parsers.parse('it resolves to the state "{state_id}"'))
def resolves_to(context: dict[str, Any], state_id: str) -> None:
    resolution = context["resolution"]
    assert resolution is not None, f"selector was rejected: {context['error']}"
    assert resolution.is_resolved, f"did not resolve to one state: {resolution.matches}"
    assert resolution.state_id == state_id


@then("it reports no matching state")
def reports_unmatched(context: dict[str, Any]) -> None:
    resolution = context["resolution"]
    assert resolution is not None, f"selector was rejected: {context['error']}"
    assert resolution.is_unmatched


@then("it reports the selector is ambiguous")
def reports_ambiguous(context: dict[str, Any]) -> None:
    resolution = context["resolution"]
    assert resolution is not None, f"selector was rejected: {context['error']}"
    assert resolution.is_ambiguous


@then(parsers.parse('the ambiguous candidates are "{first}" and "{second}"'))
def ambiguous_candidates_are(
    context: dict[str, Any], first: str, second: str
) -> None:
    resolution = context["resolution"]
    assert resolution is not None
    matched_ids = [candidate.state_id for candidate in resolution.matches]
    assert matched_ids == [first, second]


@then("the selector is rejected as malformed")
def rejected_as_malformed(context: dict[str, Any]) -> None:
    assert context["resolution"] is None
    assert isinstance(context["error"], SelectorError)
