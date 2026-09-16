"""The exploration state-action graph (ROADMAP.md §2e).

Part of the fifth §2e slice (sub-slice 5a), pure logic. The explorer maps a target
into a directed graph whose **nodes are abstract states** (keyed by the slice-2
`state_id`, each carrying the actionable elements discovered there) and whose
**edges are actions** (`from_state --action--> to_state`). Actions the safety gate
refused to fire are recorded separately as skips, so the map honestly shows both
what was explored and what was deliberately left alone.

Each state node carries the free-signal bundle captured there and each transition
carries the before/after diff of what its action changed (§2e sub-slice 5c); both
are optional so the graph is usable before signal capture is wired in. Nothing here
is site-specific (§0).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from spoor.exploration.capture import StateSignals, TransitionSignals
from spoor.exploration.discovery import ActionableElement


@dataclass
class StateNode:
    """One abstract state: its id, the actions discovered in it, and its signals (§2e).

    `signals` is the free-signal bundle captured when the state was first reached
    (§2e sub-slice 5c); `None` if signals weren't captured for this run.
    """

    state_id: str
    actions: list[ActionableElement] = field(default_factory=list)
    signals: StateSignals | None = None


@dataclass(frozen=True)
class Transition:
    """A fired action and the state it led to: `from_state --action--> to_state`.

    `signals` is the before/after diff of what the action changed across the free
    signals (§2e sub-slice 5c); `None` if signals weren't captured for this run.

    `recovered_via` records that the action was only reachable after clearing a covering
    layer (§2e sub-slice 7c): `None` when the action actuated directly, or a short
    human-readable description of the layer that was cleared (e.g. "button 'Accept'")
    when recovery interacted past a blocker to reach it. It lets the map show honestly
    that an edge was behind an overlay, not on the surface.
    """

    from_state: str
    action: ActionableElement
    to_state: str
    signals: TransitionSignals | None = None
    recovered_via: str | None = None


@dataclass(frozen=True)
class SkippedAction:
    """An action the safety gate refused to fire, with the log-ready reason (§2e)."""

    from_state: str
    action: ActionableElement
    reason: str


class ExplorationGraph:
    """The state-action graph the explorer builds (§2e).

    States are deduplicated by `state_id` — adding a state that already exists is a
    no-op — which is what stops an AJAX app from exploding into infinite
    near-duplicate nodes. Transitions and skips are kept in discovery order.
    """

    def __init__(self) -> None:
        self._states: dict[str, StateNode] = {}
        self._transitions: list[Transition] = []
        self._skipped: list[SkippedAction] = []

    def add_state(
        self,
        state_id: str,
        actions: list[ActionableElement],
        signals: StateSignals | None = None,
    ) -> StateNode:
        """Add a state, its discovered actions, and its signals; no-op if present."""
        node = self._states.get(state_id)
        if node is None:
            node = StateNode(state_id=state_id, actions=list(actions), signals=signals)
            self._states[state_id] = node
        return node

    def has_state(self, state_id: str) -> bool:
        return state_id in self._states

    def node(self, state_id: str) -> StateNode:
        return self._states[state_id]

    def add_transition(
        self,
        from_state: str,
        action: ActionableElement,
        to_state: str,
        signals: TransitionSignals | None = None,
        recovered_via: str | None = None,
    ) -> None:
        self._transitions.append(
            Transition(from_state, action, to_state, signals, recovered_via)
        )

    def record_skip(
        self, from_state: str, action: ActionableElement, reason: str
    ) -> None:
        self._skipped.append(SkippedAction(from_state, action, reason))

    @property
    def states(self) -> list[str]:
        return list(self._states)

    @property
    def transitions(self) -> list[Transition]:
        return list(self._transitions)

    @property
    def skipped(self) -> list[SkippedAction]:
        return list(self._skipped)


def path_steps_from_root(
    graph: ExplorationGraph,
) -> dict[str, list[tuple[ActionableElement, str]]]:
    """The reset-and-replay path to every reachable state, as (action, landed) steps.

    The root is the first state added (the state the explorer started from). A
    breadth-first walk over the recorded transitions gives the shortest edge path to
    each state; each step is the action fired and the state it led to — exactly the
    pair reset-and-replay carries so it can *verify* each landing. A state not
    reachable from the root (which should not arise from an explorer run) simply has
    no entry. The root maps to an empty path.

    The richer sibling of `paths_from_root`: it keeps the landed state per step, which
    resume (§2e) needs to seed and verify a replay to an anchor, while `paths_from_root`
    projects away the landings for callers that only need the action sequence.
    """
    states = graph.states
    if not states:
        return {}
    root = states[0]
    predecessor: dict[str, tuple[str, ActionableElement] | None] = {root: None}
    adjacency: dict[str, list[tuple[str, ActionableElement]]] = {}
    for transition in graph.transitions:
        adjacency.setdefault(transition.from_state, []).append(
            (transition.to_state, transition.action)
        )
    queue: deque[str] = deque([root])
    while queue:
        state = queue.popleft()
        for to_state, action in adjacency.get(state, []):
            if to_state not in predecessor:
                predecessor[to_state] = (state, action)
                queue.append(to_state)
    paths: dict[str, list[tuple[ActionableElement, str]]] = {}
    for state in predecessor:
        sequence: list[tuple[ActionableElement, str]] = []
        cursor: str | None = state
        while cursor is not None and predecessor[cursor] is not None:
            previous, action = predecessor[cursor]  # type: ignore[misc]
            sequence.append((action, cursor))
            cursor = previous
        paths[state] = list(reversed(sequence))
    return paths


def paths_from_root(graph: ExplorationGraph) -> dict[str, list[ActionableElement]]:
    """The reset-and-replay action path from the root to every reachable state (§2e).

    The action-only projection of `path_steps_from_root`: the shortest edge path to
    each state, as the actions a run replays to reach it (the root maps to an empty
    path, an unreachable state has no entry).

    This is the graph-level primitive both the test generator (§2g, replaying to a
    transition's from-state) and anchor resolution (§2e resume, the `path` selector
    and the candidate adapter) build on, so the walk lives with the graph rather than
    being duplicated per consumer.
    """
    return {
        state: [action for action, _landed in steps]
        for state, steps in path_steps_from_root(graph).items()
    }
