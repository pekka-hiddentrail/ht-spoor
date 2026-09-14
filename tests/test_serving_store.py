"""Unit tests for the map store's shareable projections (ROADMAP.md §2f/§2h).

The serving surfaces answer from projections built here, not from live objects, so
the projection is where the §2h split is enforced. `shareable_exploration_map`
mirrors `shareable_api_surface`: a pure structural reduction of an exploration graph
to plain strings/ints/bools that `map_view` can redact wholesale — per-state signals
as counts only (raw values stay local), per-transition the actual before/after diff
(the "what changed" §2f serves). These pin its shape and its empty-graph contract
directly, below the BDD scenarios.
"""

from __future__ import annotations

from typing import Any

from spoor.exploration.capture import StateSignals, TransitionSignals
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.graph import ExplorationGraph
from spoor.serving.store import shareable_exploration_map


def test_empty_graph_projects_to_none() -> None:
    # An unexplored URL stores nothing rather than an empty shell — the same stance
    # shareable_api_surface takes when nothing was observed.
    assert shareable_exploration_map(ExplorationGraph()) is None


def _built_graph() -> ExplorationGraph:
    graph = ExplorationGraph()
    open_menu = ActionableElement(role="button", name="Open menu", backend_node_id=1)
    delete = ActionableElement(role="button", name="Delete", backend_node_id=2)
    graph.add_state(
        "s-home",
        [open_menu, delete],
        StateSignals(
            ax_node_count=7,
            console_messages=("boot", "ready"),
            storage_keys=("cartId",),
            network_requests=("GET /", "GET /app.js", "GET /api/me"),
        ),
    )
    graph.add_state("s-menu", [], StateSignals(ax_node_count=11))
    graph.add_transition(
        "s-home",
        open_menu,
        "s-menu",
        TransitionSignals(
            ax_node_delta=4,
            console_added=("opened",),
            storage_added=("menuOpen",),
            storage_removed=(),
            network_added=("GET /api/menu",),
            screenshot_changed=True,
        ),
    )
    graph.record_skip("s-home", delete, "destructive action skipped outside a sandbox")
    return graph


def test_projection_shape_states_transitions_skips_and_counts() -> None:
    projected: Any = shareable_exploration_map(_built_graph())
    assert projected is not None

    assert projected["counts"] == {"states": 2, "transitions": 1, "skipped": 1}

    states = projected["states"]
    assert [s["id"] for s in states] == ["s-home", "s-menu"]
    assert states[0]["actions"] == [
        {"role": "button", "name": "Open menu"},
        {"role": "button", "name": "Delete"},
    ]
    # Per-state signals are counts only — no raw console/storage/network values.
    assert states[0]["signals"] == {
        "ax_node_count": 7,
        "console_count": 2,
        "storage_count": 1,
        "network_count": 3,
    }

    (transition,) = projected["transitions"]
    assert transition["from"] == "s-home"
    assert transition["to"] == "s-menu"
    assert transition["action"] == {"role": "button", "name": "Open menu"}
    # The transition carries the actual diff — what clicking the action changed.
    assert transition["changed"] == {
        "ax_node_delta": 4,
        "console_added": ["opened"],
        "storage_added": ["menuOpen"],
        "storage_removed": [],
        "network_added": ["GET /api/menu"],
        "screenshot_changed": True,
    }

    (skip,) = projected["skipped"]
    assert skip["from"] == "s-home"
    assert skip["action"] == {"role": "button", "name": "Delete"}
    assert skip["reason"] == "destructive action skipped outside a sandbox"


def test_missing_signals_project_to_none_not_empty() -> None:
    # A graph built before signal capture was wired in (signals=None) must not
    # crash the projection; the per-state and per-transition signal slots are None.
    graph = ExplorationGraph()
    action = ActionableElement(role="link", name="Next", backend_node_id=1)
    graph.add_state("s-1", [action])  # signals default None
    graph.add_state("s-2", [])
    graph.add_transition("s-1", action, "s-2")  # signals default None

    projected: Any = shareable_exploration_map(graph)
    assert projected is not None
    assert projected["states"][0]["signals"] is None
    assert projected["transitions"][0]["changed"] is None
