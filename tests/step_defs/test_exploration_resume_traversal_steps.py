"""Step definitions for features/exploration_resume_traversal.feature (§2e resume).

The fast-tier scenarios drive the *real* resume chain — project a crawl to its
§2h-shareable map, load it back, resolve a selector, and continue the walk — in-process
against a fake site (the same BrowserDriver-protocol fake as exploration_traversal),
so the end-to-end merge and depth re-origin are exercised without a browser. The
`@browser` scenario proves the same over the A -> B -> C fixture chain in real Chromium.

The fake site is a small copy of the traversal fixture's: pages keyed by a DOM name
(which decides the abstract state id) with a per-page URL, and transitions keyed by an
action's (role, label) so replay re-locates by role+name — exactly what lets a loaded
skeleton action (no live node id) drive a reset-and-replay.
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
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import explore
from spoor.exploration.resume import ResumeError, resume_exploration
from spoor.exploration.state import state_id
from spoor.serving.store import shareable_exploration_map

scenarios("exploration_resume_traversal.feature")

# A sandbox host; the fixture links are all non-destructive.
_TARGET = "http://localhost:8000/"


class _FakeSite:
    """A deterministic site: pages keyed by DOM name (the state id), each with a URL."""

    def __init__(self) -> None:
        self.root = ""
        self._actions: dict[str, list[ActionableElement]] = {}
        self._transitions: dict[tuple[str, str, str], str] = {}
        self._by_label: dict[tuple[str, str], str] = {}
        self._url: dict[str, str] = {}
        self._next_id = 0

    def add(self, frm: str, label: str, role: str, to: str, url: str) -> None:
        self._next_id += 1
        action = ActionableElement(role=role, name=label, backend_node_id=self._next_id)
        self._actions.setdefault(frm, []).append(action)
        self._actions.setdefault(to, [])  # ensure sink pages exist
        self._transitions[(frm, role, label)] = to
        self._by_label[(frm, label)] = to
        self._url[to] = url
        self._url.setdefault(frm, "/")

    def target_of(self, frm: str, label: str) -> str:
        """The page an action labelled `label` reaches from `frm` (test lookup)."""
        return self._by_label[(frm, label)]

    def html(self, name: str) -> str:
        return f"<html><body><h1>{name}</h1></body></html>"

    def ax_nodes(self, name: str) -> list[dict[str, object]]:
        return [
            {
                "role": {"value": action.role},
                "name": {"value": action.name},
                "ignored": False,
                "backendDOMNodeId": action.backend_node_id,
                "destination": self._url.get(
                    self._transitions[(name, action.role, action.name)]
                ),
            }
            for action in self._actions.get(name, [])
        ]

    def next_state(self, name: str, action: ActionableElement) -> str:
        return self._transitions[(name, action.role, action.name)]

    def url_of(self, name: str) -> str:
        return self._url.get(name, "/")

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _UrlDriver:
    """A BrowserDriver over a _FakeSite that reports the current page's URL."""

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

    def current_url(self) -> str:
        return self._app.url_of(self._current)


@pytest.fixture
def context() -> dict[str, Any]:
    return {"app": _FakeSite()}


@pytest.fixture(autouse=True)
def _teardown(context: dict[str, Any]) -> Any:
    yield
    driver = context.get("driver")
    if driver is not None:
        driver.close()


def _controller(depth: int) -> RunController:
    return RunController(RunBudget(max_depth=depth))


# --- Given ---------------------------------------------------------------


@given("a site whose pages are:")
def a_site(context: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    app: _FakeSite = context["app"]
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        app.add(
            fields["from"], fields["label"], fields["role"], fields["to"], fields["url"]
        )


@given(
    parsers.parse(
        'an earlier crawl from "{root}" with a depth budget of {depth:d} was saved'
    )
)
def earlier_crawl(context: dict[str, Any], root: str, depth: int) -> None:
    app: _FakeSite = context["app"]
    app.root = root
    graph = explore(_UrlDriver(app), target=_TARGET, controller=_controller(depth))
    context["earlier_graph"] = graph
    context["saved_map"] = shareable_exploration_map(graph)


@given("a different site whose start page differs from the saved map")
def a_different_site(context: dict[str, Any]) -> None:
    other = _FakeSite()
    # A start page with a different heading => a different state id than the saved root,
    # which is what the resume drift guard must refuse.
    other.add("elsewhere", "Go", "link", "wherever", "/")
    other.root = "elsewhere"
    context["other_app"] = other


# --- When ----------------------------------------------------------------


def _anchor_selector(app: _FakeSite, root: str, label: str) -> str:
    """An `id:` selector for the state reached from `root` by `label` (root if "")."""
    page = root if label == "" else app.target_of(root, label)
    return f"id:{app.state_id_of(page)}"


@when(parsers.parse("I resume from the start page with a depth budget of {depth:d}"))
def resume_from_root(context: dict[str, Any], depth: int) -> None:
    app: _FakeSite = context["app"]
    context["resumed_graph"] = resume_exploration(
        _UrlDriver(app),
        target=_TARGET,
        controller=_controller(depth),
        saved_map=context["saved_map"],
        selector=_anchor_selector(app, app.root, ""),
    )


@when(
    parsers.parse(
        'I resume from the state reached by "{label}" with a depth budget of {depth:d}'
    )
)
def resume_from_label(context: dict[str, Any], label: str, depth: int) -> None:
    app: _FakeSite = context["app"]
    selector = _anchor_selector(app, app.root, label)
    context["resumed_graph"] = resume_exploration(
        _UrlDriver(app),
        target=_TARGET,
        controller=_controller(depth),
        saved_map=context["saved_map"],
        selector=selector,
    )


@when(
    parsers.parse(
        'I crawl afresh from "{root}" with a depth budget of {depth:d}'
    )
)
def crawl_afresh(context: dict[str, Any], root: str, depth: int) -> None:
    app: _FakeSite = context["app"]
    app.root = root
    context["fresh_graph"] = explore(
        _UrlDriver(app), target=_TARGET, controller=_controller(depth)
    )


@when(
    parsers.parse(
        'I resume from the selector "{selector}" with a depth budget of {depth:d}'
    )
)
def resume_from_selector(context: dict[str, Any], selector: str, depth: int) -> None:
    app: _FakeSite = context["app"]
    try:
        context["resumed_graph"] = resume_exploration(
            _UrlDriver(app),
            target=_TARGET,
            controller=_controller(depth),
            saved_map=context["saved_map"],
            selector=selector,
        )
    except (ResumeError, ValueError) as exc:
        context["resume_error"] = exc


@when(
    parsers.parse(
        'I resume that different site from the state reached by "{label}" '
        "with a depth budget of {depth:d}"
    )
)
def resume_different_site(context: dict[str, Any], label: str, depth: int) -> None:
    app: _FakeSite = context["app"]
    other: _FakeSite = context["other_app"]
    selector = _anchor_selector(app, app.root, label)
    try:
        context["resumed_graph"] = resume_exploration(
            _UrlDriver(other),
            target=_TARGET,
            controller=_controller(depth),
            saved_map=context["saved_map"],
            selector=selector,
        )
    except (ResumeError, ValueError) as exc:
        context["resume_error"] = exc


# --- Then ----------------------------------------------------------------


@then(parsers.parse('the resumed map has page "{name}"'))
def resumed_has_page(context: dict[str, Any], name: str) -> None:
    app: _FakeSite = context["app"]
    assert app.state_id_of(name) in set(context["resumed_graph"].states)


@then(parsers.parse('the earlier crawl had not mapped page "{name}"'))
def earlier_lacks_page(context: dict[str, Any], name: str) -> None:
    app: _FakeSite = context["app"]
    assert app.state_id_of(name) not in set(context["earlier_graph"].states)


@then(parsers.parse("the resumed map still has pages: {names}"))
def resumed_still_has(context: dict[str, Any], names: str) -> None:
    app: _FakeSite = context["app"]
    states = set(context["resumed_graph"].states)
    for name in (n.strip() for n in names.split(",")):
        assert app.state_id_of(name) in states, f"resumed map lost page {name!r}"


@then(parsers.parse('the resumed map has a transition "{frm} --{label}--> {to}"'))
def resumed_has_transition(
    context: dict[str, Any], frm: str, label: str, to: str
) -> None:
    app: _FakeSite = context["app"]
    from_id = app.state_id_of(frm)
    to_id = app.state_id_of(to)
    found = [
        t
        for t in context["resumed_graph"].transitions
        if t.from_state == from_id and t.to_state == to_id and t.action.name == label
    ]
    assert found, f"no transition {frm} --{label}--> {to}"


@then(parsers.parse('the fresh map does not have page "{name}"'))
def fresh_lacks_page(context: dict[str, Any], name: str) -> None:
    app: _FakeSite = context["app"]
    assert app.state_id_of(name) not in set(context["fresh_graph"].states)


@then("resuming is refused because the selector matched no state")
def refused_unmatched(context: dict[str, Any]) -> None:
    error = context["resume_error"]
    assert isinstance(error, ResumeError)
    assert "matched no state" in str(error)


@then("resuming is refused because the start page no longer matches the saved map")
def refused_drift(context: dict[str, Any]) -> None:
    error = context["resume_error"]
    assert isinstance(error, ValueError)
    assert "start page no longer matches" in str(error)


# --- Live (@browser) -----------------------------------------------------


@given(
    parsers.parse('an earlier live crawl of "{page}" at depth {depth:d} was saved')
)
def earlier_live_crawl(
    context: dict[str, Any], live_server: str, page: str, depth: int
) -> None:
    url = f"{live_server}/{page}"
    driver = PlaywrightDriver(url)
    driver.__enter__()
    context["driver"] = driver
    context["live_url"] = url
    graph = explore(driver, target=url, controller=_controller(depth))
    context["earlier_graph"] = graph
    context["saved_map"] = shareable_exploration_map(graph)


def _title_reached(graph: Any, label: str) -> str:
    """The state id the earlier live crawl reached by firing the action `label`."""
    for transition in graph.transitions:
        if transition.action.name == label:
            return transition.to_state
    raise AssertionError(f"the earlier crawl fired no action named {label!r}")


@when(
    parsers.parse(
        'I resume the live crawl from the state reached by "{label}" at depth {depth:d}'
    )
)
def resume_live(context: dict[str, Any], label: str, depth: int) -> None:
    anchor = _title_reached(context["earlier_graph"], label)
    context["resumed_graph"] = resume_exploration(
        context["driver"],
        target=context["live_url"],
        controller=_controller(depth),
        saved_map=context["saved_map"],
        selector=f"id:{anchor}",
    )


def _titles(graph: Any) -> set[str]:
    return {
        graph.node(sid).signals.title
        for sid in graph.states
        if graph.node(sid).signals is not None
    }


@then(parsers.parse('the resumed live map has a page titled "{title}"'))
def resumed_live_titled(context: dict[str, Any], title: str) -> None:
    assert title in _titles(context["resumed_graph"])


@then(parsers.parse('the earlier live crawl had not reached "{title}"'))
def earlier_live_lacked(context: dict[str, Any], title: str) -> None:
    assert title not in _titles(context["earlier_graph"])
