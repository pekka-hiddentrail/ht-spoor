"""Step definitions for features/exploration_discovery.feature (ROADMAP.md §2e).

Discovery is pure logic over an accessibility-node list, so these steps build CDP
`getFullAXTree`-shaped nodes from a datatable (the same shape `AccessibilityCollector`
captures) and run `discover_actions` on them.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.discovery import discover_actions

scenarios("exploration_discovery.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


def _rows(datatable: list[list[str]]) -> list[dict[str, str]]:
    header, *rows = datatable
    return [dict(zip(header, row, strict=True)) for row in rows]


def _ax_node(fields: dict[str, str]) -> dict[str, object]:
    """A CDP accessibility node built from a datatable row."""
    node: dict[str, object] = {
        "role": {"type": "role", "value": fields["role"]},
        "name": {"type": "computedString", "value": fields.get("name", "")},
        "ignored": fields.get("ignored", "false") == "true",
    }
    backend = fields.get("backend_node_id")
    if backend:
        node["backendDOMNodeId"] = int(backend)
    return node


# --- Given ---------------------------------------------------------------


@given("an accessibility tree:")
def an_accessibility_tree(
    context: dict[str, Any], datatable: list[list[str]]
) -> None:
    context["ax_nodes"] = [_ax_node(fields) for fields in _rows(datatable)]


# --- When ----------------------------------------------------------------


@when("I discover the actionable elements")
def discover(context: dict[str, Any]) -> None:
    context["discovered"] = discover_actions(context["ax_nodes"])


# --- Then ----------------------------------------------------------------


@then("the discovered elements are:")
def discovered_elements_are(
    context: dict[str, Any], datatable: list[list[str]]
) -> None:
    expected = [(f["role"], f["name"]) for f in _rows(datatable)]
    actual = [(e.role, e.name) for e in context["discovered"]]
    assert actual == expected


@then(
    parsers.re(
        r'the first discovered element has role "(?P<role>[^"]*)"'
        r' and name "(?P<name>[^"]*)"'
    )
)
def first_element_role_name(context: dict[str, Any], role: str, name: str) -> None:
    first = context["discovered"][0]
    assert first.role == role
    assert first.name == name


@then(parsers.parse("the first discovered element keeps backend node id {node_id:d}"))
def first_element_backend_id(context: dict[str, Any], node_id: int) -> None:
    assert context["discovered"][0].backend_node_id == node_id


@then("no actionable elements are discovered")
def no_elements(context: dict[str, Any]) -> None:
    assert context["discovered"] == []
