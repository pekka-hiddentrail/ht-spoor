"""Step definitions for features/exploration_wiki.feature (ROADMAP.md §2e, slice 6a).

The pure wiki renderer is exercised against a graph built directly in-process — no
browser, no disk. States are keyed by their friendly name (a real run keys them by the
64-char `state_id`, which the renderer only ever shortens for display, so a readable id
changes nothing it does), each carrying a `StateSignals` bundle from the Background
table; a transition carries the real `diff_signals` of its endpoints' bundles, exactly
as the explorer records it. The steps then render `build_pages` and assert on the HTML.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.capture import StateSignals, diff_signals
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.wiki import REDACTED, build_pages

scenarios("exploration_wiki.feature")


def _semis(raw: str) -> tuple[str, ...]:
    """A semicolon-separated table cell into a tuple (the bundle's list shape)."""
    return tuple(part.strip() for part in raw.split(";") if part.strip())


@pytest.fixture
def context() -> dict[str, Any]:
    # State names double as their state ids here (see the module docstring).
    return {"graph": ExplorationGraph(), "signals": {}}


# --- Given ---------------------------------------------------------------


@given("an explored graph of a small app:")
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


@given(parsers.parse('a transition "{label}" from "{frm}" to "{to}"'))
def a_transition(context: dict[str, Any], label: str, frm: str, to: str) -> None:
    graph: ExplorationGraph = context["graph"]
    action = ActionableElement(role="button", name=label, backend_node_id=1)
    # The action is discovered in the from-state; the transition carries the real
    # before/after diff, as the explorer records it.
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


@when(parsers.parse('I render the wiki for "{target}"'))
def render(context: dict[str, Any], target: str) -> None:
    context["pages"] = build_pages(context["graph"], target=target)


# --- helpers -------------------------------------------------------------


def _pages(context: dict[str, Any]) -> dict[str, str]:
    return context["pages"]


def _state_page(context: dict[str, Any], name: str) -> str:
    """The rendered page for the state named `name` (name == its id here)."""
    index = context["graph"].states.index(name)
    return _pages(context)[f"state-{index}.html"]


def _only_transition_page(context: dict[str, Any]) -> str:
    pages = [html for name, html in _pages(context).items() if name.startswith("trans")]
    assert len(pages) == 1, f"expected exactly one transition page, got {len(pages)}"
    return pages[0]


# --- Then: structure -----------------------------------------------------


@then("the wiki has an index page")
def has_index(context: dict[str, Any]) -> None:
    assert "index.html" in _pages(context)


@then("the wiki has a page for each state")
def page_per_state(context: dict[str, Any]) -> None:
    states = context["graph"].states
    for i in range(len(states)):
        assert f"state-{i}.html" in _pages(context)
    pages = [name for name in _pages(context) if name.startswith("state-")]
    assert len(pages) == len(states)


@then("the wiki has a page for each transition")
def page_per_transition(context: dict[str, Any]) -> None:
    transitions = context["graph"].transitions
    for j in range(len(transitions)):
        assert f"transition-{j}.html" in _pages(context)
    pages = [name for name in _pages(context) if name.startswith("transition-")]
    assert len(pages) == len(transitions)


@then(
    parsers.parse("the index reports {states:d} states and {transitions:d} transition")
)
def index_counts(context: dict[str, Any], states: int, transitions: int) -> None:
    index = _pages(context)["index.html"]
    assert f"<strong>{states}</strong> states discovered" in index
    assert f"<strong>{transitions}</strong> transitions" in index


@then("the index links to every state page")
def index_links_states(context: dict[str, Any]) -> None:
    index = _pages(context)["index.html"]
    for i in range(len(context["graph"].states)):
        assert f'href="state-{i}.html"' in index


@then("the index includes a graph overview")
def index_overview(context: dict[str, Any]) -> None:
    index = _pages(context)["index.html"]
    assert 'class="mermaid"' in index
    assert "graph LR" in index


# --- Then: state page ----------------------------------------------------


@then(parsers.parse('the state page for "{name}" reports {n:d} accessibility nodes'))
def state_ax(context: dict[str, Any], name: str, n: int) -> None:
    assert f"Accessibility nodes: <strong>{n}</strong>" in _state_page(context, name)


@then(parsers.parse('the state page for "{name}" shows the console message "{msg}"'))
def state_console(context: dict[str, Any], name: str, msg: str) -> None:
    assert msg in _state_page(context, name)


@then(parsers.parse('the state page for "{name}" shows the storage key "{key}"'))
def state_storage(context: dict[str, Any], name: str, key: str) -> None:
    assert key in _state_page(context, name)


# --- Then: transition page -----------------------------------------------


@then(parsers.parse("the transition page reports an accessibility node delta of {d:d}"))
def transition_ax_delta(context: dict[str, Any], d: int) -> None:
    assert (
        f"Accessibility node delta: <strong>{d}</strong>"
        in _only_transition_page(context)
    )


@then(parsers.parse('the transition page shows the added console message "{msg}"'))
def transition_console(context: dict[str, Any], msg: str) -> None:
    assert msg in _only_transition_page(context)


@then(parsers.parse('the transition page shows the added storage key "{key}"'))
def transition_storage(context: dict[str, Any], key: str) -> None:
    assert key in _only_transition_page(context)


@then(parsers.parse('the transition page shows the added network request "{url}"'))
def transition_network(context: dict[str, Any], url: str) -> None:
    assert url in _only_transition_page(context)


# --- Then: redaction (§2h) -----------------------------------------------


@then(parsers.parse('no wiki page contains the raw secret "{secret}"'))
def no_raw_secret(context: dict[str, Any], secret: str) -> None:
    for name, html in _pages(context).items():
        assert secret not in html, f"raw secret leaked into {name}"


@then("some wiki page shows the redaction placeholder")
def shows_placeholder(context: dict[str, Any]) -> None:
    assert any(REDACTED in html for html in _pages(context).values())
