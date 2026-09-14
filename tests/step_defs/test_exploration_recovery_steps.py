"""Step definitions for features/exploration_recovery.feature (ROADMAP.md §2e, 7c).

Layer recovery is exercised in-process against a fake app, the same way the loop
(`exploration_loop.feature`) and settling policy are: no browser, a deterministic state
machine, and the explorer under test driving it through the `BrowserDriver` protocol.

The fake extends the loop's app with *covering layers*. A covered state's own actions
are present in the accessibility tree (so discovery finds them) but sit *behind* a
layer, so actuating one reports `COVERED` — exactly what the live driver's coordinate
hit-test reports when an overlay intercepts the click. The layer has its own action(s),
which are *on top* (they actuate); firing the clearing one dismisses the layer (or, for
a multi-step layer, advances it a step). Crucially the layer is restored on every
`reset`, so reset-and-replay meets it afresh each time it returns to the covered
state — which is what proves recovery re-clears it per visit, not merely once.

A layer that nothing clears (its action does not advance it) stands in for a CAPTCHA;
a layer whose only action is destructive stands in for the non-negotiable gate case;
and an action marked "cannot be located" is present at discovery but gone at actuation
time, standing in for a genuinely missing element that recovery must not mistake for a
blocker.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.actuation import ActuationVerdict, CoveringElement, Verdict
from spoor.exploration.capture import StateSignals
from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import (
    ElementCovered,
    ElementNotLocated,
    explore,
)
from spoor.exploration.state import state_id

scenarios("exploration_recovery.feature")


@dataclass(frozen=True)
class _LayerStep:
    """One step of a covering layer: the on-top action, and whether firing it advances.

    `advances` True means firing the action moves the layer on (clearing it when the
    last step advances); False means the action does nothing to the layer (a CAPTCHA —
    present and clickable, but no click gets past it).
    """

    action: ActionableElement
    advances: bool


class _RecoveryApp:
    """A deterministic app whose states may be covered by a recoverable layer."""

    def __init__(self) -> None:
        self.root = ""
        self._actions: dict[str, list[ActionableElement]] = {}
        self._transitions: dict[tuple[str, str, str], str] = {}
        self._layers: dict[str, list[_LayerStep]] = {}
        self._cannot_locate: set[str] = set()
        self._next_id = 0

    # --- construction ----------------------------------------------------

    def add(self, from_state: str, label: str, role: str, to_state: str) -> None:
        action = self._make(label, role)
        self._actions.setdefault(from_state, []).append(action)
        self._actions.setdefault(to_state, [])  # ensure sink states exist
        self._transitions[(from_state, role, label)] = to_state

    def add_layer(
        self, state: str, steps: Sequence[tuple[str, str, bool]]
    ) -> None:
        self._layers[state] = [
            _LayerStep(self._make(label, role), advances)
            for label, role, advances in steps
        ]
        self._actions.setdefault(state, [])

    def cannot_locate(self, label: str) -> None:
        self._cannot_locate.add(label)

    def _make(self, label: str, role: str) -> ActionableElement:
        self._next_id += 1
        return ActionableElement(role=role, name=label, backend_node_id=self._next_id)

    # --- queries the driver uses ----------------------------------------

    def html(self, name: str) -> str:
        # The abstract state id is computed from this; the overlay is modelled
        # separately (driver state), not baked into the HTML, so a covered state and
        # its cleared self are the one state — which is what the scenarios assert.
        return f"<html><body><h1>{name}</h1></body></html>"

    def underlying(self, name: str) -> list[ActionableElement]:
        return list(self._actions.get(name, []))

    def layer_action(self, name: str, step: int) -> ActionableElement | None:
        steps = self._layers.get(name, [])
        return steps[step].action if 0 <= step < len(steps) else None

    def layer_advances(self, name: str, step: int) -> bool:
        return self._layers[name][step].advances

    def ax_nodes(self, name: str, step: int) -> list[dict[str, object]]:
        # Both the state's own actions and the layer's current action are in the tree:
        # discovery sees everything on screen; only the click's hit-test tells them
        # apart (an underlying action is covered, the layer's own action is on top).
        elements = self.underlying(name)
        layer = self.layer_action(name, step)
        if layer is not None:
            elements = [*elements, layer]
        return [
            {
                "role": {"value": e.role},
                "name": {"value": e.name},
                "ignored": False,
                "backendDOMNodeId": e.backend_node_id,
            }
            for e in elements
        ]

    def is_cannot_locate(self, action: ActionableElement) -> bool:
        return action.name in self._cannot_locate

    def next_state(self, name: str, action: ActionableElement) -> str:
        return self._transitions[(name, action.role, action.name)]

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _RecoveryDriver:
    """A BrowserDriver over a _RecoveryApp, modelling layers and the actuation verdict.

    Tracks the current state and, per state, how far its layer has been advanced. Both
    are restored by `reset`, so every reset-and-replay meets each layer afresh.
    """

    def __init__(self, app: _RecoveryApp) -> None:
        self._app = app
        self._current = app.root
        self._layer_step: dict[str, int] = {}

    def reset(self) -> None:
        self._current = self._app.root
        self._layer_step = {}

    def _step(self, state: str) -> int:
        return self._layer_step.get(state, 0)

    def state_html(self) -> str:
        return self._app.html(self._current)

    def ax_nodes(self) -> Sequence[Mapping[str, object]]:
        return self._app.ax_nodes(self._current, self._step(self._current))

    def probe(self, action: ActionableElement) -> ActuationVerdict:
        state = self._current
        step = self._step(state)
        if self._app.is_cannot_locate(action):
            return ActuationVerdict(Verdict.NOT_LOCATED)
        layer = self._app.layer_action(state, step)
        if layer is not None and (action.role, action.name) == (
            layer.role,
            layer.name,
        ):
            return ActuationVerdict(Verdict.ACTUATE)  # the layer's own action is on top
        if not self._present(state, action):
            return ActuationVerdict(Verdict.NOT_LOCATED)
        if layer is not None:
            return ActuationVerdict(
                Verdict.COVERED, CoveringElement(layer.role, layer.name)
            )
        return ActuationVerdict(Verdict.ACTUATE)

    def perform(self, action: ActionableElement) -> None:
        verdict = self.probe(action)
        if verdict.verdict is Verdict.NOT_LOCATED:
            raise ElementNotLocated(action.role, action.name)
        if verdict.verdict is Verdict.COVERED:
            assert verdict.covering is not None
            raise ElementCovered(verdict.covering.role, verdict.covering.text)
        state = self._current
        step = self._step(state)
        layer = self._app.layer_action(state, step)
        if layer is not None and (action.role, action.name) == (
            layer.role,
            layer.name,
        ):
            # Firing the layer's own action: advance it (clearing it past the last
            # step) if this step advances; otherwise it stays put — a click that gets
            # nowhere. Either way the underlying state is unchanged.
            if self._app.layer_advances(state, step):
                self._layer_step[state] = step + 1
            return
        self._current = self._app.next_state(state, action)

    def capture_signals(self) -> StateSignals:
        return StateSignals()

    def _present(self, state: str, action: ActionableElement) -> bool:
        return any(
            (e.role, e.name) == (action.role, action.name)
            for e in self._app.underlying(state)
        )


@pytest.fixture
def context() -> dict[str, Any]:
    return {
        "app": _RecoveryApp(),
        "target": "http://localhost:8000/",
        "declared_sandbox": False,
        "budget": RunBudget(),
    }


# --- Given ---------------------------------------------------------------


@given("a sandbox target")
def sandbox_target(context: dict[str, Any]) -> None:
    context["target"] = "http://localhost:8000/"


@given("a real target")
def real_target(context: dict[str, Any]) -> None:
    context["target"] = "https://shop.example.com/"


@given("an app whose actions are:")
def an_app(context: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    app: _RecoveryApp = context["app"]
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        app.add(fields["from"], fields["label"], fields["role"], fields["to"])


@given(parsers.parse('the "{state}" state is covered by a layer whose actions are:'))
def covered_by_layer(
    context: dict[str, Any], state: str, datatable: list[list[str]]
) -> None:
    header, *rows = datatable
    app: _RecoveryApp = context["app"]
    # A single-action layer: `clears` yes means firing that action dismisses it.
    steps = [
        (fields["label"], fields["role"], fields["clears"].strip() == "yes")
        for fields in (dict(zip(header, row, strict=True)) for row in rows)
    ]
    app.add_layer(state, steps)


@given(
    parsers.parse('the "{state}" state is covered by a layer cleared only by this '
    "sequence:")
)
def covered_by_sequence(
    context: dict[str, Any], state: str, datatable: list[list[str]]
) -> None:
    header, *rows = datatable
    app: _RecoveryApp = context["app"]
    # Every step advances the layer; only after the last does it clear.
    ordered = sorted(
        (dict(zip(header, row, strict=True)) for row in rows),
        key=lambda f: int(f["step"]),
    )
    app.add_layer(state, [(f["label"], f["role"], True) for f in ordered])


@given(parsers.parse('the "{state}" state is covered by a layer that nothing clears:'))
def covered_by_stuck_layer(
    context: dict[str, Any], state: str, datatable: list[list[str]]
) -> None:
    header, *rows = datatable
    app: _RecoveryApp = context["app"]
    # The layer's action does not advance it: no click gets past (a CAPTCHA).
    steps = [
        (fields["label"], fields["role"], False)
        for fields in (dict(zip(header, row, strict=True)) for row in rows)
    ]
    app.add_layer(state, steps)


@given(parsers.parse('the action "{label}" cannot be located'))
def action_cannot_be_located(context: dict[str, Any], label: str) -> None:
    context["app"].cannot_locate(label)


# --- When ----------------------------------------------------------------


@when(parsers.parse('I explore from "{root}"'))
def i_explore(context: dict[str, Any], root: str) -> None:
    app: _RecoveryApp = context["app"]
    app.root = root
    controller = RunController(context["budget"])
    context["graph"] = explore(
        _RecoveryDriver(app),
        target=context["target"],
        controller=controller,
        declared_sandbox=context["declared_sandbox"],
    )


# --- Then ----------------------------------------------------------------


def _named_states(context: dict[str, Any], names: Sequence[str]) -> set[str]:
    app: _RecoveryApp = context["app"]
    return {app.state_id_of(name) for name in names}


@then(parsers.parse("the graph has states: {names}"))
def graph_has_states(context: dict[str, Any], names: str) -> None:
    wanted = [n.strip() for n in names.split(",")]
    assert set(context["graph"].states) == _named_states(context, wanted)


@then(parsers.parse('the graph has a transition "{frm} --{label}--> {to}"'))
def graph_has_transition(
    context: dict[str, Any], frm: str, label: str, to: str
) -> None:
    app: _RecoveryApp = context["app"]
    from_id = app.state_id_of(frm)
    to_id = app.state_id_of(to)
    found = [
        t
        for t in context["graph"].transitions
        if t.from_state == from_id and t.to_state == to_id and t.action.name == label
    ]
    assert found, f"no transition {frm} --{label}--> {to}"


@then("the graph has no transitions")
def graph_has_no_transitions(context: dict[str, Any]) -> None:
    assert context["graph"].transitions == []


def _skipped_with(context: dict[str, Any], label: str, frm: str) -> list[Any]:
    app: _RecoveryApp = context["app"]
    from_id = app.state_id_of(frm)
    return [
        s
        for s in context["graph"].skipped
        if s.from_state == from_id and s.action.name == label
    ]


def _not_fired(context: dict[str, Any], label: str, frm: str) -> None:
    app: _RecoveryApp = context["app"]
    from_id = app.state_id_of(frm)
    fired = [
        t
        for t in context["graph"].transitions
        if t.from_state == from_id and t.action.name == label
    ]
    assert not fired, f"{label!r} from {frm!r} was flagged skipped/blocked but fired"


@then(parsers.parse('the layer action "{label}" from "{frm}" is skipped'))
def layer_action_is_skipped(context: dict[str, Any], label: str, frm: str) -> None:
    assert _skipped_with(context, label, frm), f"expected {label!r} to be skipped"
    _not_fired(context, label, frm)


@then(
    parsers.parse(
        'the action "{label}" from "{frm}" is flagged as blocked by an unresolved layer'
    )
)
def flagged_blocked(context: dict[str, Any], label: str, frm: str) -> None:
    skipped = _skipped_with(context, label, frm)
    assert skipped, f"expected {label!r} from {frm!r} to be flagged"
    assert any(
        "blocked by an unresolved layer" in s.reason for s in skipped
    ), f"reason did not name an unresolved layer: {[s.reason for s in skipped]}"
    _not_fired(context, label, frm)


@then(parsers.parse('the action "{label}" from "{frm}" is flagged as not located'))
def flagged_not_located(context: dict[str, Any], label: str, frm: str) -> None:
    skipped = _skipped_with(context, label, frm)
    assert skipped, f"expected {label!r} from {frm!r} to be flagged"
    assert any(
        "not located" in s.reason for s in skipped
    ), f"reason did not say not located: {[s.reason for s in skipped]}"
    _not_fired(context, label, frm)


# --- Live scenario -------------------------------------------------------
#
# The final scenario drives the whole real stack: a headless Chromium against a fixture
# whose entry screen is behind a consent overlay that intercepts every click. Short
# settle timings keep it fast; production defaults are unchanged. The driver is torn
# down by the autouse finalizer below (a no-op for the browser-free scenarios above).

_QUIET_WINDOW_S = 0.3
_SETTLE_TIMEOUT_S = 2.0


@pytest.fixture(autouse=True)
def _teardown(context: dict[str, Any]) -> Any:
    yield
    driver = context.get("driver")
    if driver is not None:
        driver.close()


@given(parsers.parse('a live fixture site starting at "{page}"'))
def live_fixture_site(context: dict[str, Any], live_server: str, page: str) -> None:
    url = f"{live_server}/{page}"
    driver = PlaywrightDriver(
        url, quiet_window=_QUIET_WINDOW_S, settle_timeout=_SETTLE_TIMEOUT_S
    )
    driver.__enter__()
    context["driver"] = driver
    context["target"] = url


@when("I run spoor explore against it")
def run_explore(context: dict[str, Any]) -> None:
    controller = RunController(RunBudget(max_states=25, max_requests=50))
    context["graph"] = explore(
        context["driver"], target=context["target"], controller=controller
    )


@then(parsers.parse("it reports more than {n:d} state discovered"))
def more_than_n_states(context: dict[str, Any], n: int) -> None:
    assert len(context["graph"].states) > n, context["graph"].states


@then(parsers.parse("it reports at least {n:d} action recovered from behind a blocker"))
def at_least_n_recovered(context: dict[str, Any], n: int) -> None:
    recovered = [t for t in context["graph"].transitions if t.recovered_via is not None]
    assert len(recovered) >= n, f"only {len(recovered)} recovered: {recovered}"
