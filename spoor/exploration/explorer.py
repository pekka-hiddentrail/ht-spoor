"""The exploration explorer loop (ROADMAP.md §2e).

Sub-slice 5a of the fifth §2e slice — the orchestrator, pure logic. `explore` drives
a target with no config into an `ExplorationGraph`, tying together the four earlier
slices: it discovers the actionable elements in each state (slice 3), asks the safety
gate which may be fired (slice 1), recognises a revisited state by its `state_id`
(slice 2) so the walk terminates instead of looping, and checks the run controller
before every action so a budget or the kill switch always stops it (slice 4).

The browser is behind the `BrowserDriver` protocol, so this whole loop runs in-process
against a fake deterministic app; the real Playwright driver and a live-browser run
are sub-slice 5b. The walk is depth-first with **reset-and-replay** navigation: to
reach a state again, the driver is reset to the start and the path of actions that
first reached it is replayed. That needs no back-button assumption from the target and
works for any driver whose actions are deterministic. Nothing here is site-specific
(§0): the same loop maps every target.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from spoor.exploration.control import RunController
from spoor.exploration.discovery import ActionableElement, discover_actions
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.safety import evaluate_action
from spoor.exploration.state import state_id


class BrowserDriver(Protocol):
    """What the explorer needs from a browser, so the loop stays browser-free (§2e).

    A driver is deterministic: resetting and replaying the same actions returns to
    the same state. The real Playwright implementation is sub-slice 5b.
    """

    def reset(self) -> None:
        """Return to the start state (e.g. re-navigate to the entry URL)."""
        ...

    def state_html(self) -> str:
        """The current DOM, for computing the abstract state id (slice 2)."""
        ...

    def ax_nodes(self) -> Sequence[Mapping[str, object]]:
        """The current accessibility-tree nodes, for discovery (slice 3)."""
        ...

    def perform(self, action: ActionableElement) -> None:
        """Fire an action (e.g. click the element it names)."""
        ...


def explore(
    driver: BrowserDriver,
    *,
    target: str,
    controller: RunController,
    declared_sandbox: bool = False,
) -> ExplorationGraph:
    """Explore `target` through `driver`, returning the state-action graph (§2e).

    Runs until every reachable, gate-permitted action has been fired or the run
    controller stops it (budget reached or kill switch thrown). Destructive actions
    are fired only inside a sandbox; on any other target they are recorded as skips
    and their state is never reached (§2e non-negotiable).
    """
    graph = ExplorationGraph()

    def capture() -> tuple[str, bool]:
        """Record the driver's current state; return its id and whether it's new."""
        sid = state_id(driver.state_html())
        if graph.has_state(sid):
            return sid, False
        graph.add_state(sid, discover_actions(driver.ax_nodes()))
        controller.record_state()
        return sid, True

    def navigate(path: Sequence[ActionableElement]) -> None:
        """Return to the state reached by `path`, via reset and replay."""
        driver.reset()
        for action in path:
            driver.perform(action)

    def walk(state: str, path: list[ActionableElement]) -> None:
        # Snapshot the action list: a deeper call may add states, and we iterate the
        # actions discovered for this state when it was first seen.
        for action in list(graph.node(state).actions):
            if controller.check().should_stop:
                return
            decision = evaluate_action(
                target, action.name, action.role, declared_sandbox
            )
            if not decision.allowed:
                graph.record_skip(state, action, decision.reason)
                continue
            navigate(path)
            driver.perform(action)
            controller.record_request()
            to_state, first_seen = capture()
            graph.add_transition(state, action, to_state)
            # Only recurse into a genuinely new state; a transition back to a known
            # state is recorded but not re-explored — that is what keeps this finite.
            if first_seen:
                walk(to_state, path + [action])

    navigate([])
    root, _ = capture()
    walk(root, [])
    return graph
