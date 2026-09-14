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

Layer recovery (§2e sub-slice 7c) is what keeps a site guarded by a welcome or consent
overlay from collapsing to its first screen. When an action can't be actuated because a
layer sits over its click point (`ElementCovered`), the explorer treats the layer as its
own state and interacts *past* it — firing the layer's own on-top actions (discovered
and safety-gated the same generic way as everything else) until the target is uncovered,
then firing it. Because reset restores the overlays a stateful target shows a fresh
visitor, replay clears them again on every visit, so states behind the overlay are
reachable more than once. Recovery is bounded by the finite set of the layer's actions
(so it never loops), honours the §2e non-negotiable (a layer whose only exit is a
destructive action outside a sandbox stays blocked), and flags what it can't clear with
a real reason — a covered element as blocked, a genuinely missing one as not located —
never a mute skip.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from spoor.exploration.actuation import ActuationVerdict, CoveringElement, Verdict
from spoor.exploration.capture import StateSignals, diff_signals
from spoor.exploration.control import RunController
from spoor.exploration.discovery import ActionableElement, discover_actions
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.safety import evaluate_action
from spoor.exploration.state import state_id

# Layer recovery (§2e, 7c) is bounded by the finite set of a covered state's own
# on-top actions — each is tried at most once — so it terminates without this cap. The
# cap is a defensive safety net against a pathological driver that reports an unbounded
# stream of distinct clearing actions, guaranteeing recovery can never spin forever.
_MAX_RECOVERY_STEPS = 50


class ActionError(Exception):
    """A discovered action could not be actuated in the current page (§2e).

    On a live, dynamic target an element found during discovery can be gone, hidden,
    detached, or covered by the time reset-and-replay returns to it, so the click can
    never land. A driver raises this from `perform` to say "this action can't be
    fired here" without aborting the run; the explorer records it as a skip and keeps
    mapping the rest of the site. It is *not* for programming errors or a broken
    driver — those should still propagate.

    Robust actuation (§2e sub-slice 7a) tells two of these cases apart with the
    subclasses below, so recovery (7c) can react to a covered element specifically and
    a user reads why an action was skipped. Both subclass `ActionError`, so the
    explorer's existing `except ActionError` still records a skip for either.
    """


class ElementCovered(ActionError):
    """The element is present but a different element sits over its click point (§2e).

    The precise, generic signal that a layer is in the way: clicking the coordinate
    would hit `role`/`text` instead of the target. Layer recovery (7c) catches this
    specifically to interact past the layer; until then the explorer records it as a
    skip like any other `ActionError`.
    """

    def __init__(self, role: str, text: str) -> None:
        super().__init__(f"covered by {role} {text!r}")
        self.role = role
        self.text = text


class ElementNotLocated(ActionError):
    """No discovered node matches the action in the current page — it is gone (§2e).

    Distinct from `ElementCovered`: nothing is intercepting the click, the element
    simply is not there after reset-and-replay, so recovery cannot help. The explorer
    records it as a skip.
    """

    def __init__(self, role: str, name: str) -> None:
        super().__init__(f"{role} {name!r} could not be located")
        self.role = role
        self.name = name


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
        """Fire an action (e.g. click the element it names).

        Raises `ActionError` if the element can't be actuated in the current page;
        the explorer treats that as a recorded skip rather than a failed run. Robust
        actuation (7a) narrows this to `ElementCovered` when a layer sits over the
        click point and `ElementNotLocated` when the element is gone.
        """
        ...

    def probe(self, action: ActionableElement) -> ActuationVerdict:
        """The actuation verdict for `action` in the current page, *without* firing it.

        Returns ACTUATE (a click would land on it), COVERED (a layer sits over its
        click point, carrying what covers it), or NOT_LOCATED (no matching element).
        Layer recovery (7c) uses this to tell whether the target is reachable and to
        find the layer's own on-top actions, so it can interact past a blocker without
        clicking blind. A driver hiccup still surfaces as `ActionError`, like `perform`.
        """
        ...

    def capture_signals(self) -> StateSignals:
        """The free-signal bundle for the current state (§2e sub-slice 5c)."""
        ...


class _Reach(Enum):
    """Whether an action can be actuated now, or why not (§2e, 7c)."""

    PROCEED = "proceed"  # actuatable now (possibly after a layer was cleared)
    BLOCKED = "blocked"  # covered by a layer nothing available could clear
    NOT_LOCATED = "not located"  # no matching element — gone, not covered


@dataclass(frozen=True)
class _Reachability:
    """The outcome of trying to make an action reachable (recovering past a layer).

    `blocker` describes the layer when BLOCKED (for the flagged skip reason);
    `recovered_via` names the layer that *was* cleared when a covered action became
    reachable, so the transition can record it was reached from behind a blocker.
    """

    status: _Reach
    blocker: str = ""
    recovered_via: str | None = None


def _describe(covering: CoveringElement | None) -> str:
    """A short human-readable description of a covering element, for a flag/label."""
    if covering is None:
        return "a layer"
    if covering.text:
        return f"{covering.role} {covering.text!r}"
    return covering.role or "a layer"


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

    def capture(signals: StateSignals | None = None) -> tuple[str, bool]:
        """Record the driver's current state; return its id and whether it's new.

        A caller that already captured the current signal bundle (a transition's
        after-snapshot) passes it in so the driver isn't snapshotted twice for the
        same state; otherwise the bundle is captured here.
        """
        sid = state_id(driver.state_html())
        if graph.has_state(sid):
            return sid, False
        graph.add_state(
            sid,
            discover_actions(driver.ax_nodes()),
            signals if signals is not None else driver.capture_signals(),
        )
        controller.record_state()
        return sid, True

    def next_layer_action(
        action: ActionableElement, attempted: set[tuple[str, str]]
    ) -> ActionableElement | None:
        """Pick a layer action to fire toward uncovering `action`, or None if none fit.

        The layer's own actions are the ones actually *on top* here — those that
        actuate (probe ACTUATE) — never the covered target, never one already tried,
        and never one the safety gate refuses. That last clause is the §2e
        non-negotiable holding through recovery: a layer whose only exit is a
        destructive action on a non-sandbox target yields no candidate, so the layer is
        never forced open. Returns the first fit in document order, or None when the
        layer can't be cleared from here.
        """
        for candidate in discover_actions(driver.ax_nodes()):
            if (candidate.role, candidate.name) == (action.role, action.name):
                continue
            if (candidate.role, candidate.name) in attempted:
                continue
            if not evaluate_action(
                target, candidate.name, candidate.role, declared_sandbox
            ).allowed:
                continue
            if driver.probe(candidate).verdict is not Verdict.ACTUATE:
                continue  # covered itself, or gone — not part of the layer on top
            return candidate
        return None

    def reach(action: ActionableElement) -> _Reachability:
        """Make `action` actuatable, clearing a recoverable covering layer (§2e, 7c).

        Probes the action: ACTUATE proceeds immediately; NOT_LOCATED means it is gone
        (recovery can't help — a missing element is not a blocker). COVERED hands off to
        recovery, which interacts past the layer with its own gate-permitted, on-top
        actions, each fired at most once, re-probing the target after each. It converges
        by *progress* — a cleared or advanced layer exposes a new action or uncovers the
        target — and is bounded by the finite set of such actions, so it never loops;
        when none remains it flags the blocker rather than forcing it.
        """
        verdict = driver.probe(action)
        if verdict.verdict is Verdict.ACTUATE:
            return _Reachability(_Reach.PROCEED)
        if verdict.verdict is Verdict.NOT_LOCATED:
            return _Reachability(_Reach.NOT_LOCATED)
        covering = verdict.covering
        cleared = _describe(covering)
        attempted: set[tuple[str, str]] = set()
        for _ in range(_MAX_RECOVERY_STEPS):
            candidate = next_layer_action(action, attempted)
            if candidate is None:
                return _Reachability(_Reach.BLOCKED, blocker=_describe(covering))
            attempted.add((candidate.role, candidate.name))
            try:
                driver.perform(candidate)
            except ActionError:
                # That layer action itself couldn't be fired (covered/gone by the time
                # we tried): drop it and look for another way past the layer.
                continue
            verdict = driver.probe(action)
            if verdict.verdict is Verdict.ACTUATE:
                return _Reachability(_Reach.PROCEED, recovered_via=cleared)
            if verdict.verdict is Verdict.NOT_LOCATED:
                return _Reachability(_Reach.NOT_LOCATED)
            covering = verdict.covering or covering
        return _Reachability(_Reach.BLOCKED, blocker=_describe(covering))

    def navigate(path: Sequence[ActionableElement]) -> None:
        """Return to the state reached by `path`, via reset and replay.

        Each replayed action is made reachable first (7c): reset restores the covering
        layers a stateful target shows on a fresh visit, so replay must clear them again
        to fire the same path — otherwise every state behind an overlay would be lost on
        the second visit. A step that can't be reached raises `ActionError`, which the
        caller records as a skip for the action it was replaying toward.
        """
        driver.reset()
        for action in path:
            outcome = reach(action)
            if outcome.status is not _Reach.PROCEED:
                raise ActionError(
                    f"replay could not reach {action.name!r}: "
                    f"{outcome.blocker or outcome.status.value}"
                )
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
            try:
                navigate(path)
            except ActionError as exc:
                # A replay step along the way couldn't be reached (or recovered):
                # record this action honestly and carry on — the next iteration resets
                # and replays afresh, so one dead branch never aborts the whole map.
                graph.record_skip(state, action, f"could not be performed: {exc}")
                continue
            # Make the action reachable, clearing a recoverable layer if one covers it
            # (7c). A covered action nothing can clear is flagged as blocked, and a
            # genuinely missing one as not located — never a mute skip.
            outcome = reach(action)
            if outcome.status is _Reach.NOT_LOCATED:
                graph.record_skip(
                    state,
                    action,
                    f"not located: {action.role} {action.name!r} "
                    "is not present after replay",
                )
                continue
            if outcome.status is _Reach.BLOCKED:
                graph.record_skip(
                    state,
                    action,
                    f"blocked by an unresolved layer: {outcome.blocker}",
                )
                continue
            # Capture the free signals either side of the action so the transition
            # records what it changed (§2e sub-slice 5c). `before` is taken after any
            # layer was cleared, so the diff is the action's effect, not the layer's.
            before = driver.capture_signals()
            try:
                driver.perform(action)
            except ActionError as exc:
                graph.record_skip(state, action, f"could not be performed: {exc}")
                continue
            controller.record_request()
            after = driver.capture_signals()
            to_state, first_seen = capture(after)
            graph.add_transition(
                state,
                action,
                to_state,
                diff_signals(before, after),
                recovered_via=outcome.recovered_via,
            )
            # Only recurse into a genuinely new state; a transition back to a known
            # state is recorded but not re-explored — that is what keeps this finite.
            if first_seen:
                walk(to_state, path + [action])

    navigate([])
    root, _ = capture()
    walk(root, [])
    return graph
