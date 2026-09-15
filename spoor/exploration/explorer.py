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

Replay resilience (§2e sub-slice 7d) hardens reset-and-replay against the flaky,
nondeterministic renders a real SPA serves under load. Reset-and-replay assumes the
target is a deterministic function of the action sequence, but a reset can land on a
degraded render where a step found on the first visit is gone, or the replay can drift
onto a different state than the path first mapped. So each reset-and-replay is
*verified* (the post-reset page must be the start state, and every replayed step must
land on the state id it first reached) and *retried* a bounded number of times: a
transient bad render usually clears on the next reset, so coverage that all-or-nothing
replay used to lose is regained. When retries are exhausted the action is flagged with a
reason that tells a step that stayed unreachable apart from a replay that *diverged* to
another state — never a mute skip, and attributed to the replay step that actually
failed, not the leaf. A stable blocker (recovery's concern above) is reported at once,
not retried: there is nothing transient to wait out.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

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

# Replay resilience (§2e, 7d): how many times a reset-and-replay is attempted before an
# action behind it is flagged. A transient degraded render (an SPA reload landing on a
# half-rendered or error fallback) almost always clears within one or two fresh resets,
# so a small bound regains the coverage all-or-nothing replay lost without letting a
# genuinely nondeterministic path spin: after this many attempts the failure is flagged.
_MAX_REPLAY_ATTEMPTS = 3


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


@runtime_checkable
class _ScreenshotCapable(Protocol):
    """A driver that can also hand back a full-page screenshot (§2e slice 8b).

    Kept off the core `BrowserDriver` contract on purpose: capturing pixels is an
    opt-in extra, so a driver (or a test fake) that never produces images stays a
    valid `BrowserDriver`. The explorer only asks for a screenshot when it is both
    given a sink *and* the driver satisfies this capability, so the default run — and
    every existing fake — is untouched.
    """

    def screenshot(self) -> bytes | None:
        """A full-page PNG of the current page, or None if it can't be captured."""
        ...


@dataclass(frozen=True)
class ElementShot:
    """The captured screenshot(s) of one actionable element (§2e slices 8d/8e).

    `clip` is a PNG cropped to the element as it sits on the screen — the "Next"
    button, the closed "Currency" dropdown — or None when the driver could not clip it
    (a zero-size or off-page element). `opened` is a PNG of the content the element
    *reveals* when activated — the option list an opened dropdown shows (§2e slice 8e) —
    or None when the element reveals nothing, the driver can't capture it, or opening it
    was not attempted (a non-disclosure role, or an action the safety gate refuses).
    One `ElementShot` is stored per discovered element, in the same order the state's
    actions are discovered, so the wiki can line each up with its Actions-table row.
    Like every screenshot both exist only behind the opt-in element sink; a default run
    produces none (§2h).
    """

    clip: bytes | None = None
    opened: bytes | None = None


# Roles whose element reveals further content when activated — a dropdown's option
# list — so its *opened* state is worth a screenshot (§2e slice 8e). A maintainable,
# PR-extendable set (§0), never site-specific, and a subset of discovery's
# ACTIONABLE_ROLES (a role never discovered could never be opened). Deliberately
# conservative: a plain button/link is excluded because activating it usually navigates
# rather than revealing an in-place overlay, and we only ever open an element the safety
# gate also permits, so opening never fires a destructive action outside a sandbox.
_DISCLOSURE_ROLES = frozenset({"combobox", "listbox"})


@runtime_checkable
class _ElementScreenshotCapable(Protocol):
    """A driver that can also clip a screenshot of a single element (§2e slice 8d).

    Kept off the core `BrowserDriver` contract for the same reason `_ScreenshotCapable`
    is: per-element capture is an opt-in extra, so a driver or fake that never produces
    element images stays a valid `BrowserDriver`. The explorer only asks when it is both
    given an element sink *and* the driver satisfies this capability.
    """

    def element_screenshot(self, action: ActionableElement) -> bytes | None:
        """A PNG clipped to `action`'s element, or None if it can't be captured."""
        ...


@runtime_checkable
class _OpenedScreenshotCapable(Protocol):
    """A driver that can open a disclosure element and capture what it reveals (8e).

    Separate from `_ElementScreenshotCapable` on purpose: a driver may clip elements
    without being able to open them (and every 8d fake is exactly that), so the explorer
    checks for this capability independently and simply leaves `opened` None when the
    driver lacks it.
    """

    def opened_screenshot(self, action: ActionableElement) -> bytes | None:
        """A PNG of what `action` reveals when opened, restoring after; or None."""
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


@dataclass(frozen=True)
class _PathStep:
    """One replayed step: the action fired and the state id it first reached (§2e, 7d).

    Reset-and-replay carries the path as these steps so replay can be *verified*: after
    firing `action`, the current state must be `to_state` — the id it landed on when the
    path was first walked. A mismatch is a replay divergence, not a step to build on.
    """

    action: ActionableElement
    to_state: str


class _ReplayFailure(Exception):
    """One reset-and-replay attempt failed; `navigate_and_reach` retries, then reports.

    Internal to the explorer: it carries an already-formatted `detail` (a step that
    could not be reached, or a divergence to a different state) so the retry loop can
    turn the last failure into an honest skip reason that records how many attempts
    it made.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail

    def reason(self, attempts: int) -> str:
        """This failure's skip reason, noting the bounded retries that were spent."""
        return f"{self.detail} (after {attempts} replay attempts)"


def explore(
    driver: BrowserDriver,
    *,
    target: str,
    controller: RunController,
    declared_sandbox: bool = False,
    screenshots: MutableMapping[str, bytes] | None = None,
    element_screenshots: MutableMapping[str, list[ElementShot]] | None = None,
) -> ExplorationGraph:
    """Explore `target` through `driver`, returning the state-action graph (§2e).

    Runs until every reachable, gate-permitted action has been fired or the run
    controller stops it (budget reached or kill switch thrown). Destructive actions
    are fired only inside a sandbox; on any other target they are recorded as skips
    and their state is never reached (§2e non-negotiable).

    `screenshots` is an opt-in sink for full-page screenshots (§2e slice 8b): when a
    mapping is passed and the driver can take one, each newly discovered state's image
    is stored under its state id. Left None (the default), no screenshot is taken, so
    a default run captures no pixels — embedding them anywhere shared is always an
    explicit opt-in, because a picture cannot be secret-redacted the way text is (§2h).

    `element_screenshots` is the per-element counterpart (§2e slices 8d/8e): when a
    mapping is passed and the driver can clip an element, each newly discovered state
    stores an `ElementShot` per actionable element, in discovery order, so the wiki's
    Actions table can show each control. When the driver can also *open* a disclosure
    element (a dropdown or list) and the safety gate permits firing it, the
    shot's `opened` image captures what that element reveals — but only after every
    non-mutating clip for the state is taken, and only for gate-permitted disclosure
    roles, so opening never fires a destructive action on a non-sandbox target (§2e) and
    never contaminates the clean-page state id and signals, which are captured first. It
    carries the same opt-in, off-by-default posture and the same §2h reason as the
    full-page sink.
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
        actions = discover_actions(driver.ax_nodes())
        graph.add_state(
            sid,
            actions,
            signals if signals is not None else driver.capture_signals(),
        )
        # Opt-in only, and once per distinct state (this branch runs for new states):
        # store the current page's full-page screenshot under its id if a sink was
        # provided and the driver can produce one (§2e slice 8b).
        if screenshots is not None and isinstance(driver, _ScreenshotCapable):
            png = driver.screenshot()
            if png is not None:
                screenshots[sid] = png
        # The per-element counterpart (§2e slices 8d/8e): a clip of each discovered
        # element, in discovery order so the wiki can line each up with its Actions row.
        # A clip that can't be taken is stored as None rather than dropped, so the list
        # stays aligned with the actions. Same opt-in gate as the full-page sink.
        if element_screenshots is not None and isinstance(
            driver, _ElementScreenshotCapable
        ):
            # Every clip first: element_screenshot is non-mutating, so the page is still
            # the clean state captured above while these are taken.
            clips = [driver.element_screenshot(action) for action in actions]
            # Then, and only then, the opened captures (§2e slice 8e). Opening clicks
            # the element, which mutates the page — safe here because it runs *after*
            # the state id, signals and every clip are recorded, and the next driver
            # call is always a reset-and-replay. It fires only for a disclosure role the
            # gate also permits, so opening never actuates a destructive element on a
            # non-sandbox target (§2e non-negotiable); every other element keeps
            # opened=None. Restore is the driver's job and best-effort.
            opener = driver if isinstance(driver, _OpenedScreenshotCapable) else None
            opened: list[bytes | None] = []
            for action in actions:
                if (
                    opener is not None
                    and action.role in _DISCLOSURE_ROLES
                    and evaluate_action(
                        target, action.name, action.role, declared_sandbox
                    ).allowed
                ):
                    opened.append(opener.opened_screenshot(action))
                else:
                    opened.append(None)
            element_screenshots[sid] = [
                ElementShot(clip=clip, opened=shot)
                for clip, shot in zip(clips, opened, strict=True)
            ]
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

    def replay_once(path: Sequence[_PathStep], root_id: str) -> None:
        """One reset-and-replay attempt, *verified* against the ids the path first hit.

        Resets, checks the fresh page is the start state, then replays each step: makes
        it reachable (7c clears any covering layer that reset restored), fires it, and
        verifies the landed state id matches the one the step first reached. A step
        that can't be reached or a landing that diverges raises `_ReplayFailure`; the
        retry in `navigate_and_reach` decides whether a fresh attempt clears a transient
        bad render or the failure is real. Fidelity matters because firing the target
        on a divergent state would record a false edge attributed to the wrong `from`
        state.
        """
        driver.reset()
        if state_id(driver.state_html()) != root_id:
            raise _ReplayFailure(
                "replay diverged: reset did not return to the start state"
            )
        for step in path:
            outcome = reach(step.action)
            if outcome.status is _Reach.NOT_LOCATED:
                raise _ReplayFailure(
                    f"replay could not reach {step.action.name!r}: not located"
                )
            if outcome.status is _Reach.BLOCKED:
                raise _ReplayFailure(
                    f"replay could not reach {step.action.name!r}: "
                    f"blocked by {outcome.blocker}"
                )
            driver.perform(step.action)
            if state_id(driver.state_html()) != step.to_state:
                raise _ReplayFailure(
                    f"replay diverged: firing {step.action.name!r} reached a "
                    "different state than when the path was first mapped"
                )

    def navigate_and_reach(
        path: Sequence[_PathStep], action: ActionableElement, root_id: str
    ) -> _Reachability:
        """Replay `path` and make `action` reachable, retrying a transient bad render.

        Runs a verified reset-and-replay of `path` then reaches `action`, up to
        `_MAX_REPLAY_ATTEMPTS` times. A step that stayed unreachable, a divergence, or a
        target that could not be located is retried — a degraded reset render usually
        clears on the next attempt (§2e, 7d). PROCEED returns with the driver positioned
        at the path's end and `action` reachable (its covering layer cleared, its
        `recovered_via` carried through). A stable BLOCKED layer is returned at once,
        not retried: there is nothing transient to wait out. When the attempts are
        spent the last failure is raised as an `ActionError`, which the caller records
        as a skip for `action`, naming the replay step that failed, not the leaf.
        """
        last: _ReplayFailure | None = None
        for _ in range(_MAX_REPLAY_ATTEMPTS):
            try:
                replay_once(path, root_id)
            except _ReplayFailure as failure:
                last = failure
                continue
            outcome = reach(action)
            if outcome.status is _Reach.NOT_LOCATED:
                last = _ReplayFailure(
                    f"{action.role} {action.name!r} not located after replay"
                )
                continue
            return outcome  # PROCEED (reachable) or BLOCKED (stable — do not retry)
        assert last is not None  # the loop ran at least once, so a failure was recorded
        raise ActionError(last.reason(_MAX_REPLAY_ATTEMPTS))

    def walk(state: str, path: list[_PathStep], root_id: str) -> None:
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
            # Replay to `state` and make the action reachable, retrying a transient bad
            # render and clearing a recoverable layer (7c/7d). A step that stayed
            # unreachable or a replay that diverged is flagged honestly (naming the step
            # that failed); a covered action nothing can clear is flagged as blocked —
            # never a mute skip.
            try:
                outcome = navigate_and_reach(path, action, root_id)
            except ActionError as exc:
                # Replay could not be made faithful within the retry bound: record this
                # action honestly and carry on — the next iteration resets and replays
                # afresh, so one dead branch never aborts the whole map.
                graph.record_skip(state, action, f"could not be performed: {exc}")
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
                walk(to_state, path + [_PathStep(action, to_state)], root_id)

    driver.reset()
    root, _ = capture()
    walk(root, [], root)
    return graph
