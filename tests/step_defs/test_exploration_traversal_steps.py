"""Step definitions for features/exploration_traversal.feature (§2e slice 9).

The breadth-first walk, depth bound, and URL-path frontier fork are exercised
in-process against a fake site — the same BrowserDriver-protocol style as
exploration_loop.feature, extended with a per-page URL and an optional shared DOM.

Two fake drivers back the scenarios: `_UrlDriver` reports `current_url` (so the
explorer forks the frontier on the URL path), and `_NoUrlDriver` does not (so the
frontier keys on the DOM state id alone — the pre-slice-9 behaviour). Transitions are
keyed by the action's (role, label), not the discovered element instance, mirroring the
real driver, which re-locates an element by role+name rather than a stale node id — so a
shared-DOM node's action fires correctly whichever URL context replay lands in.
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

scenarios("exploration_traversal.feature")


class _FakeSite:
    """A deterministic site described by the scenario's page table.

    Each page has a name (a test handle), a URL, and a DOM key that decides its abstract
    state id — two pages sharing a DOM key render one screen (one state id, one node),
    which is how the URL-fork scenarios build "different URL, identical DOM".
    """

    def __init__(self) -> None:
        self.root = ""
        self._actions: dict[str, list[ActionableElement]] = {}
        self._transitions: dict[tuple[str, str, str], str] = {}
        self._url: dict[str, str] = {}
        self._dom: dict[str, str] = {}
        self._next_id = 0

    def add(self, frm: str, label: str, role: str, to: str, url: str) -> None:
        self._next_id += 1
        action = ActionableElement(role=role, name=label, backend_node_id=self._next_id)
        self._actions.setdefault(frm, []).append(action)
        self._actions.setdefault(to, [])  # ensure sink pages exist
        self._transitions[(frm, role, label)] = to
        self._url[to] = url
        self._dom.setdefault(frm, frm)
        self._dom.setdefault(to, to)
        self._url.setdefault(frm, "/")  # the start page's URL, unless set as a target

    def alias_dom(self, a: str, b: str) -> None:
        """Make page `b` render page `a`'s screen (same DOM key => same state id)."""
        self._dom[b] = self._dom.get(a, a)

    def html(self, name: str) -> str:
        return f"<html><body><h1>{self._dom.get(name, name)}</h1></body></html>"

    def url_of(self, name: str) -> str:
        return self._url.get(name, "/")

    def ax_nodes(self, name: str) -> list[dict[str, object]]:
        return [
            {
                "role": {"value": action.role},
                "name": {"value": action.name},
                "ignored": False,
                "backendDOMNodeId": action.backend_node_id,
                # The destination hint (§2e slice 9b): the URL of the page this action
                # leads to, the same value the live driver reads from a link's href.
                "destination": self._url.get(
                    self._transitions[(name, action.role, action.name)]
                ),
            }
            for action in self._actions.get(name, [])
        ]

    def next_state(self, name: str, action: ActionableElement) -> str:
        return self._transitions[(name, action.role, action.name)]

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _NoUrlDriver:
    """A BrowserDriver over a _FakeSite that reports no URL (pre-slice-9 frontier)."""

    def __init__(self, app: _FakeSite) -> None:
        self._app = app
        self._current = app.root

    def reset(self) -> None:
        self._current = self._app.root

    def state_html(self) -> str:
        return self._app.html(self._current)

    def ax_nodes(self) -> Sequence[Mapping[str, object]]:
        return self._app.ax_nodes(self._current)

    def probe(self, action: ActionableElement) -> ActuationVerdict:
        return ActuationVerdict(Verdict.ACTUATE)

    def perform(self, action: ActionableElement) -> None:
        self._current = self._app.next_state(self._current, action)

    def capture_signals(self) -> StateSignals:
        return StateSignals()


class _UrlDriver(_NoUrlDriver):
    """A _NoUrlDriver that also reports the current page's URL (forks the frontier)."""

    def current_url(self) -> str:
        return self._app.url_of(self._current)


@pytest.fixture
def context() -> dict[str, Any]:
    return {
        "app": _FakeSite(),
        "target": "http://localhost:8000/",
        "declared_sandbox": False,
        "budget": RunBudget(),
        "driver_cls": _UrlDriver,
    }


# --- Given ---------------------------------------------------------------


@given(parsers.parse("a sandbox target with a budget of max_states {n:d}"))
def budget_states(context: dict[str, Any], n: int) -> None:
    context["target"] = "http://localhost:8000/"
    context["budget"] = RunBudget(max_states=n)


@given(parsers.parse("a sandbox target with a budget of max_depth {n:d}"))
def budget_depth(context: dict[str, Any], n: int) -> None:
    context["target"] = "http://localhost:8000/"
    context["budget"] = RunBudget(max_depth=n)


@given("a sandbox target")
def sandbox_target(context: dict[str, Any]) -> None:
    context["target"] = "http://localhost:8000/"


@given("a site whose pages are:")
def a_site(context: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    app: _FakeSite = context["app"]
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        app.add(
            fields["from"], fields["label"], fields["role"], fields["to"], fields["url"]
        )


@given(parsers.parse('pages "{a}" and "{b}" render an identical screen'))
def identical_screen(context: dict[str, Any], a: str, b: str) -> None:
    context["app"].alias_dom(a, b)


@given("the driver does not report page URLs")
def no_url_driver(context: dict[str, Any]) -> None:
    context["driver_cls"] = _NoUrlDriver


# --- When ----------------------------------------------------------------


@when(parsers.parse('I explore the site from "{root}"'))
def i_explore(context: dict[str, Any], root: str) -> None:
    app: _FakeSite = context["app"]
    app.root = root
    controller = RunController(context["budget"])
    context["graph"] = explore(
        context["driver_cls"](app),
        target=context["target"],
        controller=controller,
        declared_sandbox=context["declared_sandbox"],
    )


# --- Then ----------------------------------------------------------------


@then(parsers.parse("the graph has pages: {names}"))
def graph_has_pages(context: dict[str, Any], names: str) -> None:
    app: _FakeSite = context["app"]
    wanted = {app.state_id_of(n.strip()) for n in names.split(",")}
    assert set(context["graph"].states) == wanted


@then(parsers.parse('the graph does not have page "{name}"'))
def graph_lacks_page(context: dict[str, Any], name: str) -> None:
    app: _FakeSite = context["app"]
    assert app.state_id_of(name) not in set(context["graph"].states)


@then(parsers.parse('the graph has a transition "{frm} --{label}--> {to}"'))
def graph_has_transition(
    context: dict[str, Any], frm: str, label: str, to: str
) -> None:
    app: _FakeSite = context["app"]
    from_id = app.state_id_of(frm)
    to_id = app.state_id_of(to)
    found = [
        t
        for t in context["graph"].transitions
        if t.from_state == from_id and t.to_state == to_id and t.action.name == label
    ]
    assert found, f"no transition {frm} --{label}--> {to}"
