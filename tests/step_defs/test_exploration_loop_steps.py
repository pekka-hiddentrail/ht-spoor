"""Step definitions for features/exploration_loop.feature (ROADMAP.md §2e, 5a).

The explorer loop is exercised in-process against a fake deterministic app built from
the scenario's transition table. The fake `_FakeDriver` implements the `BrowserDriver`
protocol; it tracks a friendly state *name* internally (a test convenience), while the
explorer under test only ever sees each state's HTML, accessibility nodes, and the
abstract `state_id` computed from them — never the name. The steps, which built the
app, map names to state ids to assert on the resulting graph.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.actuation import ActuationVerdict, Verdict
from spoor.exploration.capture import StateSignals
from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.explorer import ActionError, explore
from spoor.exploration.state import state_id

scenarios("exploration_loop.feature")


class _FakeApp:
    """A deterministic state machine described by the scenario's transition table."""

    def __init__(self) -> None:
        self.root = ""
        self._actions: dict[str, list[ActionableElement]] = {}
        self._transitions: dict[tuple[str, ActionableElement], str] = {}
        self._unperformable: set[str] = set()
        self._next_id = 0

    def break_action(self, label: str) -> None:
        """Mark an action's element as one that can't be actuated (see driver §2e)."""
        self._unperformable.add(label)

    def is_performable(self, action: ActionableElement) -> bool:
        return action.name not in self._unperformable

    def add(self, from_state: str, label: str, role: str, to_state: str) -> None:
        self._next_id += 1
        action = ActionableElement(role=role, name=label, backend_node_id=self._next_id)
        self._actions.setdefault(from_state, []).append(action)
        self._actions.setdefault(to_state, [])  # ensure sink states exist
        self._transitions[(from_state, action)] = to_state

    def html(self, name: str) -> str:
        # Each state's HTML is unique to its name, so distinct names get distinct
        # state ids and the same name is stable — the explorer distinguishes states
        # by these ids, exactly as it would on a real page.
        return f"<html><body><h1>{name}</h1></body></html>"

    def ax_nodes(self, name: str) -> list[dict[str, object]]:
        return [
            {
                "role": {"value": action.role},
                "name": {"value": action.name},
                "ignored": False,
                "backendDOMNodeId": action.backend_node_id,
            }
            for action in self._actions.get(name, [])
        ]

    def next_state(self, name: str, action: ActionableElement) -> str:
        return self._transitions[(name, action)]

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _FakeDriver:
    """A BrowserDriver over a _FakeApp; tracks the current state name."""

    def __init__(self, app: _FakeApp) -> None:
        self._app = app
        self._current = app.root

    def reset(self) -> None:
        self._current = self._app.root

    def state_html(self) -> str:
        return self._app.html(self._current)

    def ax_nodes(self) -> Sequence[Mapping[str, object]]:
        return self._app.ax_nodes(self._current)

    def probe(self, action: ActionableElement) -> ActuationVerdict:
        # No layers in these scenarios: every discovered action is actuatable. A broken
        # action still probes ACTUATE and fails at `perform` (a plain ActionError, not a
        # covered/not-located verdict), exercising the graceful-degradation skip path.
        return ActuationVerdict(Verdict.ACTUATE)

    def perform(self, action: ActionableElement) -> None:
        # A real driver raises when the element can't be actuated (gone, hidden,
        # covered); the fake mirrors that for the marked action so the explorer's
        # graceful-degradation path is exercised in-process.
        if not self._app.is_performable(action):
            raise ActionError(f"{action.name!r} could not be performed")
        self._current = self._app.next_state(self._current, action)

    def capture_signals(self) -> StateSignals:
        # This slice's scenarios don't assert on signals; the diff model itself is
        # exercised by exploration_signals.feature (5c-i). An empty bundle keeps the
        # loop's own scenarios focused on graph shape.
        return StateSignals()


@pytest.fixture
def context() -> dict[str, Any]:
    return {
        "app": _FakeApp(),
        "target": "http://localhost:8000/",
        "declared_sandbox": False,
        "budget": RunBudget(),
        "kill": False,
    }


# --- Given ---------------------------------------------------------------


@given("a sandbox target")
def sandbox_target(context: dict[str, Any]) -> None:
    context["target"] = "http://localhost:8000/"


@given("a real target")
def real_target(context: dict[str, Any]) -> None:
    context["target"] = "https://shop.example.com/"


@given(parsers.parse("a sandbox target with a budget of max_states {n:d}"))
def sandbox_target_with_budget(context: dict[str, Any], n: int) -> None:
    context["target"] = "http://localhost:8000/"
    context["budget"] = RunBudget(max_states=n)


@given("a sandbox target whose kill switch is already thrown")
def sandbox_target_killed(context: dict[str, Any]) -> None:
    context["target"] = "http://localhost:8000/"
    context["kill"] = True


@given(parsers.parse('the action "{label}" cannot be performed'))
def action_cannot_be_performed(context: dict[str, Any], label: str) -> None:
    context["app"].break_action(label)


@given("an app whose actions are:")
def an_app(context: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    app: _FakeApp = context["app"]
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        app.add(fields["from"], fields["label"], fields["role"], fields["to"])


# --- When ----------------------------------------------------------------


@when(parsers.parse('I explore from "{root}"'))
def i_explore(context: dict[str, Any], root: str) -> None:
    app: _FakeApp = context["app"]
    app.root = root
    controller = RunController(context["budget"])
    if context["kill"]:
        controller.kill()
    context["graph"] = explore(
        _FakeDriver(app),
        target=context["target"],
        controller=controller,
        declared_sandbox=context["declared_sandbox"],
    )


# --- Then ----------------------------------------------------------------


def _named_states(context: dict[str, Any], names: Sequence[str]) -> set[str]:
    app: _FakeApp = context["app"]
    return {app.state_id_of(name) for name in names}


@then(parsers.parse("the graph has states: {names}"))
def graph_has_states(context: dict[str, Any], names: str) -> None:
    wanted = [n.strip() for n in names.split(",")]
    assert set(context["graph"].states) == _named_states(context, wanted)


@then(parsers.parse("the graph has {n:d} states"))
def graph_has_n_states(context: dict[str, Any], n: int) -> None:
    assert len(context["graph"].states) == n


@then(parsers.parse('the graph has a transition "{frm} --{label}--> {to}"'))
def graph_has_transition(
    context: dict[str, Any], frm: str, label: str, to: str
) -> None:
    app: _FakeApp = context["app"]
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


@then(parsers.parse('the action "{label}" from "{frm}" is skipped'))
def action_is_skipped(context: dict[str, Any], label: str, frm: str) -> None:
    app: _FakeApp = context["app"]
    from_id = app.state_id_of(frm)
    skipped = [
        s
        for s in context["graph"].skipped
        if s.from_state == from_id and s.action.name == label
    ]
    assert skipped, f"expected {label!r} from {frm!r} to be skipped"
    # And it was never fired: no transition carries this action out of that state.
    fired = [
        t
        for t in context["graph"].transitions
        if t.from_state == from_id and t.action.name == label
    ]
    assert not fired, f"{label!r} was skipped but also fired"
