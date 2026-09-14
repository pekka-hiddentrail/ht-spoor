"""The exploration state-action graph (ROADMAP.md §2e).

Part of the fifth §2e slice (sub-slice 5a), pure logic. The explorer maps a target
into a directed graph whose **nodes are abstract states** (keyed by the slice-2
`state_id`, each carrying the actionable elements discovered there) and whose
**edges are actions** (`from_state --action--> to_state`). Actions the safety gate
refused to fire are recorded separately as skips, so the map honestly shows both
what was explored and what was deliberately left alone.

This is just the data structure the orchestrator (`explorer.py`) fills; the signal
bundle each node/edge will carry (screenshots, diffs) is a later sub-slice (5c).
Nothing here is site-specific (§0).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spoor.exploration.discovery import ActionableElement


@dataclass
class StateNode:
    """One abstract state: its id and the actions discovered in it (§2e)."""

    state_id: str
    actions: list[ActionableElement] = field(default_factory=list)


@dataclass(frozen=True)
class Transition:
    """A fired action and the state it led to: `from_state --action--> to_state`."""

    from_state: str
    action: ActionableElement
    to_state: str


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

    def add_state(self, state_id: str, actions: list[ActionableElement]) -> StateNode:
        """Add a state and its discovered actions; a no-op if already present."""
        node = self._states.get(state_id)
        if node is None:
            node = StateNode(state_id=state_id, actions=list(actions))
            self._states[state_id] = node
        return node

    def has_state(self, state_id: str) -> bool:
        return state_id in self._states

    def node(self, state_id: str) -> StateNode:
        return self._states[state_id]

    def add_transition(
        self, from_state: str, action: ActionableElement, to_state: str
    ) -> None:
        self._transitions.append(Transition(from_state, action, to_state))

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
