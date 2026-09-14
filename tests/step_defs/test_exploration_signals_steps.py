"""Step definitions for features/exploration_signals.feature (ROADMAP.md §2e, 5c-i).

The per-transition signal model is exercised in-process: a fake app gives each state
a `StateSignals` bundle (built from the Background table), the fake driver returns the
current state's bundle from `capture_signals()`, and the explorer diffs the before/
after bundles onto every transition. The steps map friendly state names to the
abstract state ids the graph is keyed by, exactly as the 5a loop steps do.
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
from spoor.exploration.explorer import explore
from spoor.exploration.state import state_id

scenarios("exploration_signals.feature")


def _items(raw: str) -> list[str]:
    """A comma-separated cell into a stripped, empty-dropped list."""
    return [part.strip() for part in raw.split(",") if part.strip()]


def _semis(raw: str) -> tuple[str, ...]:
    """A semicolon-separated table cell into a tuple (the bundle's list shape)."""
    return tuple(part.strip() for part in raw.split(";") if part.strip())


class _FakeApp:
    """A deterministic app whose states each carry a signal bundle (§2e, 5c-i)."""

    def __init__(self) -> None:
        self.root = ""
        self._signals: dict[str, StateSignals] = {}
        self._actions: dict[str, list[ActionableElement]] = {}
        self._transitions: dict[tuple[str, ActionableElement], str] = {}
        self._next_id = 0

    def add_state(self, name: str, signals: StateSignals) -> None:
        self._signals[name] = signals
        self._actions.setdefault(name, [])

    def add_action(self, from_state: str, label: str, role: str, to_state: str) -> None:
        self._next_id += 1
        action = ActionableElement(role=role, name=label, backend_node_id=self._next_id)
        self._actions.setdefault(from_state, []).append(action)
        self._actions.setdefault(to_state, [])
        self._transitions[(from_state, action)] = to_state

    def html(self, name: str) -> str:
        return f"<html><body><h1>{name}</h1></body></html>"

    def ax_nodes(self, name: str) -> list[dict[str, object]]:
        # The actionable elements discovery finds — independent of the bundle's
        # ax_node_count, exactly as a real page's full tree is larger than its
        # interactive subset.
        return [
            {
                "role": {"value": action.role},
                "name": {"value": action.name},
                "ignored": False,
                "backendDOMNodeId": action.backend_node_id,
            }
            for action in self._actions.get(name, [])
        ]

    def signals(self, name: str) -> StateSignals:
        return self._signals[name]

    def next_state(self, name: str, action: ActionableElement) -> str:
        return self._transitions[(name, action)]

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _FakeDriver:
    """A BrowserDriver over a _FakeApp, tracking the current state name."""

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
        # No layers here: every discovered action actuates directly.
        return ActuationVerdict(Verdict.ACTUATE)

    def perform(self, action: ActionableElement) -> None:
        self._current = self._app.next_state(self._current, action)

    def capture_signals(self) -> StateSignals:
        return self._app.signals(self._current)


@pytest.fixture
def context() -> dict[str, Any]:
    return {"app": _FakeApp()}


# --- Given ---------------------------------------------------------------


@given("a sandbox app whose states are:")
def app_states(context: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    app: _FakeApp = context["app"]
    for row in rows:
        f = dict(zip(header, row, strict=True))
        app.add_state(
            f["state"],
            StateSignals(
                ax_node_count=int(f["ax_nodes"]),
                console_messages=_semis(f["console"]),
                storage_keys=_semis(f["storage"]),
                network_requests=_semis(f["network"]),
                screenshot_hash=f["screenshot"] or None,
            ),
        )


@given(parsers.parse('an action "{label}" ({role}) from "{frm}" to "{to}"'))
def an_action(
    context: dict[str, Any], label: str, role: str, frm: str, to: str
) -> None:
    context["app"].add_action(frm, label, role, to)


# --- When ----------------------------------------------------------------


@when(parsers.parse('I explore from "{root}"'))
def i_explore(context: dict[str, Any], root: str) -> None:
    app: _FakeApp = context["app"]
    app.root = root
    context["graph"] = explore(
        _FakeDriver(app),
        target="http://localhost:8000/",
        controller=RunController(RunBudget()),
        declared_sandbox=True,
    )


# --- Then ----------------------------------------------------------------


def _transition(context: dict[str, Any], frm: str, label: str, to: str) -> Any:
    app: _FakeApp = context["app"]
    from_id = app.state_id_of(frm)
    to_id = app.state_id_of(to)
    for t in context["graph"].transitions:
        if t.from_state == from_id and t.to_state == to_id and t.action.name == label:
            return t
    raise AssertionError(f"no transition {frm} --{label}--> {to}")


@then(
    parsers.parse(
        'the transition "{frm} --{label}--> {to}" added console messages: {items}'
    )
)
def added_console(
    context: dict[str, Any], frm: str, label: str, to: str, items: str
) -> None:
    sig = _transition(context, frm, label, to).signals
    assert list(sig.console_added) == _items(items)


@then(
    parsers.parse('the transition "{frm} --{label}--> {to}" added no console messages')
)
def no_console(context: dict[str, Any], frm: str, label: str, to: str) -> None:
    assert _transition(context, frm, label, to).signals.console_added == ()


@then(
    parsers.parse(
        'the transition "{frm} --{label}--> {to}" added storage keys: {items}'
    )
)
def added_storage(
    context: dict[str, Any], frm: str, label: str, to: str, items: str
) -> None:
    sig = _transition(context, frm, label, to).signals
    assert list(sig.storage_added) == _items(items)


@then(parsers.parse('the transition "{frm} --{label}--> {to}" added no storage keys'))
def no_storage_added(context: dict[str, Any], frm: str, label: str, to: str) -> None:
    assert _transition(context, frm, label, to).signals.storage_added == ()


@then(
    parsers.parse(
        'the transition "{frm} --{label}--> {to}" removed storage keys: {items}'
    )
)
def removed_storage(
    context: dict[str, Any], frm: str, label: str, to: str, items: str
) -> None:
    sig = _transition(context, frm, label, to).signals
    assert list(sig.storage_removed) == _items(items)


@then(parsers.parse('the transition "{frm} --{label}--> {to}" removed no storage keys'))
def no_storage_removed(context: dict[str, Any], frm: str, label: str, to: str) -> None:
    assert _transition(context, frm, label, to).signals.storage_removed == ()


@then(
    parsers.parse(
        'the transition "{frm} --{label}--> {to}" added network requests: {items}'
    )
)
def added_network(
    context: dict[str, Any], frm: str, label: str, to: str, items: str
) -> None:
    sig = _transition(context, frm, label, to).signals
    assert list(sig.network_added) == _items(items)


@then(
    parsers.parse(
        'the transition "{frm} --{label}--> {to}" added no network requests'
    )
)
def no_network(context: dict[str, Any], frm: str, label: str, to: str) -> None:
    assert _transition(context, frm, label, to).signals.network_added == ()


@then(
    parsers.parse(
        'the transition "{frm} --{label}--> {to}" has an accessibility node delta'
        " of {delta:d}"
    )
)
def ax_delta(
    context: dict[str, Any], frm: str, label: str, to: str, delta: int
) -> None:
    assert _transition(context, frm, label, to).signals.ax_node_delta == delta


@then(parsers.parse('the transition "{frm} --{label}--> {to}" changed the screenshot'))
def screenshot_changed(context: dict[str, Any], frm: str, label: str, to: str) -> None:
    assert _transition(context, frm, label, to).signals.screenshot_changed is True


@then(
    parsers.parse(
        'the transition "{frm} --{label}--> {to}" did not change the screenshot'
    )
)
def screenshot_unchanged(
    context: dict[str, Any], frm: str, label: str, to: str
) -> None:
    assert _transition(context, frm, label, to).signals.screenshot_changed is False


@then(parsers.parse('the state "{name}" recorded {n:d} accessibility nodes'))
def state_ax_nodes(context: dict[str, Any], name: str, n: int) -> None:
    app: _FakeApp = context["app"]
    node = context["graph"].node(app.state_id_of(name))
    assert node.signals is not None
    assert node.signals.ax_node_count == n
