"""Step definitions for features/exploration_state.feature (ROADMAP.md §2e).

State abstraction is pure logic, so these steps feed HTML straight to `state_id`.
The pages are derived from one base by minimal, single-axis edits so each scenario
isolates exactly one kind of variation (a timestamp, a session token, a counter,
whitespace, attribute order, a script, structure, or a state-bearing attribute).
"""

from __future__ import annotations

import string
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then

from spoor.exploration.state import state_id

scenarios("exploration_state.feature")

# One base "orders" screen; volatile bits live in text, attributes, and a script.
_ORDERS_BASE = (
    "<html><body>"
    "<h1>Orders</h1>"
    '<span class="badge">3</span>'
    '<time datetime="2020-01-01T10:00:00Z">2020-01-01T10:00:00Z</time>'
    '<input type="hidden" name="csrf" value="abc123token">'
    "<table><tr><td>Order 1001</td></tr></table>"
    '<button type="submit">Confirm order</button>'
    "</body></html>"
)

# Each variant is a single-axis edit of the base — see the scenario it feeds.
PAGES: dict[str, str] = {
    "orders_base": _ORDERS_BASE,
    "orders_identical": _ORDERS_BASE,
    # Volatile-only edits: must collapse to the same state id as the base.
    "orders_diff_timestamp": _ORDERS_BASE.replace(
        "2020-01-01T10:00:00Z", "2023-12-31T23:59:59Z"
    ),
    "orders_diff_session": _ORDERS_BASE.replace("abc123token", "zzz999differenttoken"),
    "orders_diff_counter": _ORDERS_BASE.replace(">3<", ">7<"),
    "orders_diff_whitespace": _ORDERS_BASE.replace("><", ">\n    <"),
    "orders_diff_attr_order": _ORDERS_BASE.replace(
        '<input type="hidden" name="csrf" value="abc123token">',
        '<input value="abc123token" name="csrf" type="hidden">',
    ),
    "orders_diff_script": _ORDERS_BASE.replace(
        "</body>", "<script>var t = Date.now();</script></body>"
    ),
    # Genuinely different states: must get a different state id.
    "maintenance_base": _ORDERS_BASE.replace("<h1>Orders</h1>", "<h1>Maintenance</h1>"),
    "orders_extra_row": _ORDERS_BASE.replace(
        "</tr></table>", "</tr><tr><td>Order 1002</td></tr></table>"
    ),
    "button_enabled": "<html><body><button type='button'>Go</button></body></html>",
    "button_disabled": (
        "<html><body><button type='button' disabled>Go</button></body></html>"
    ),
}


@pytest.fixture
def context() -> dict[str, Any]:
    return {"pages": []}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('the page "{name}"'))
def a_page(context: dict[str, Any], name: str) -> None:
    assert name in PAGES, f"unknown fixture page: {name}"
    context["pages"].append(PAGES[name])


# --- Then ----------------------------------------------------------------


@then("the two pages have the same state id")
def same_state_id(context: dict[str, Any]) -> None:
    first, second = context["pages"]
    assert state_id(first) == state_id(second)


@then("the two pages have different state ids")
def different_state_id(context: dict[str, Any]) -> None:
    first, second = context["pages"]
    assert state_id(first) != state_id(second)


@then("its state id is a 64-character hex string")
def id_is_hex(context: dict[str, Any]) -> None:
    context["sid"] = state_id(context["pages"][0])
    assert len(context["sid"]) == 64
    assert set(context["sid"]) <= set(string.hexdigits)


@then("computing its state id again gives the same value")
def id_is_deterministic(context: dict[str, Any]) -> None:
    assert state_id(context["pages"][0]) == context["sid"]
