"""Load a persisted exploration map back into a graph (ROADMAP.md §2e resume).

The third slice of the anchored, depth-relative *resume* capability (§2e v2, see the
resume design note), and the one that lets the earlier slices be validated across a
real save/load boundary. A run persists its graph to `maps/<domain>.json` as the
§2h-shareable projection `spoor/serving/store.py:shareable_exploration_map` produces;
this is that projection's inverse — it reconstructs an `ExplorationGraph` from the
stored dict, so a *later* invocation can build anchor candidates
(`selector.graph_candidates`) and resolve a selector against a crawl it no longer
holds in memory.

The reconstruction is deliberately partial, matching what the projection actually
carries: state ids (in order, so the root stays first), each state's discovered
action inventory (role + name), and the transition topology (from --action--> to).
That is exactly what `id:` and `path` anchoring need. What the projection does *not*
carry cannot come back: per-state signals are stored as counts only and without a
title, so a loaded state has no `signals` — and therefore no title, so `title:` does
not resolve against a saved map (its own slice extends the projection). Transition
signal diffs and skip reasons are likewise not reconstructed into signal objects;
skips are restored as edges the gate refused, for fidelity. Nothing here is
site-specific (§0): every stored map is read the same way.

This module takes a plain mapping (the parsed JSON), so it depends only on the
documented projection shape, never on the serving layer — no import cycle. The
round-trip is covered by a scenario that projects a known graph and loads it back,
which fails loudly if the two ends of the contract ever drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from spoor.exploration.discovery import ActionableElement
from spoor.exploration.graph import ExplorationGraph


def _action(entry: Mapping[str, Any]) -> ActionableElement:
    """Rebuild an ActionableElement from a stored `{role, name}` action label.

    The projection keeps only the shareable role and name (§2h); the live-only
    backend node id and destination are not stored, so they come back as `None`.
    """
    return ActionableElement(
        role=str(entry["role"]),
        name=str(entry["name"]),
        backend_node_id=None,
    )


def load_exploration_map(data: Mapping[str, Any]) -> ExplorationGraph:
    """Reconstruct an `ExplorationGraph` from a persisted exploration-map projection.

    Restores states (in stored order, root first) with their action inventories,
    the transition topology, and the recorded skips. Per-state signals are not
    reconstructed — the projection stores counts without a title — so every loaded
    state has `signals=None`, which is why `title:` cannot resolve against a saved
    map while `id:` and `path` can. An empty or state-less map yields an empty graph.
    """
    graph = ExplorationGraph()
    for state in data.get("states", []):
        actions = [_action(a) for a in state.get("actions", [])]
        graph.add_state(str(state["id"]), actions=actions, signals=None)
    for transition in data.get("transitions", []):
        graph.add_transition(
            str(transition["from"]),
            _action(transition["action"]),
            str(transition["to"]),
        )
    for skip in data.get("skipped", []):
        graph.record_skip(
            str(skip["from"]),
            _action(skip["action"]),
            str(skip["reason"]),
        )
    return graph
