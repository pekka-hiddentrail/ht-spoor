"""Step definitions for features/exploration_replay.feature (ROADMAP.md §2e, 7d).

Replay resilience is exercised in-process against a fake app that models the one thing a
real SPA does and the earlier fakes did not: *nondeterminism across resets*. A
step can be told to go missing on replay (present on its first firing, absent
when reset-and-replay returns to it) or to diverge (land on a different state
than it first reached) — either transiently (the first replay only) or
persistently (every replay). The explorer under test drives it through the
`BrowserDriver` protocol exactly as it drives a browser, so the retry-and-verify
loop is proven with no browser.

The counts are what make this deterministic. The driver counts, per action, how many
times it has been probed and performed: visit #1 is the first firing (when the action is
discovered and mapped), and visits #2+ are replays. "Missing on the first replay" is
NOT_LOCATED on probe #2 only; "missing on every replay" is NOT_LOCATED on probe #2 and
after. Divergence works the same way on the perform count, sending the driver to a
sentinel "elsewhere" state so the fidelity check sees a state id that is not the one the
step first mapped.

The final scenario drives the whole real stack against a scripted loopback server
(the `_FlakyServer` pattern from the tier-2 retry tests) whose entry page is served
degraded on exactly one reset — no link to the page behind it — so a plain
reset-and-replay would give up there; retry meets a good render on the next reset
and maps the page behind it.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.actuation import ActuationVerdict, Verdict
from spoor.exploration.capture import StateSignals
from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import explore
from spoor.exploration.state import state_id

scenarios("exploration_replay.feature")

# The state a diverging action lands on instead of the one it first mapped. Its own
# html (and so its state id) differs from every real state, which is exactly what the
# explorer's fidelity check keys off.
_ELSEWHERE = "__elsewhere__"


class _ReplayApp:
    """A deterministic app whose actions can be told to flake on replay (§2e, 7d)."""

    def __init__(self) -> None:
        self.root = ""
        self._actions: dict[str, list[ActionableElement]] = {}
        self._transitions: dict[tuple[str, str, str], str] = {}
        self._miss: dict[str, str] = {}  # label -> "first" | "every"
        self._diverge: dict[str, str] = {}  # label -> "first" | "every"
        self._next_id = 0

    def add(self, from_state: str, label: str, role: str, to_state: str) -> None:
        self._next_id += 1
        action = ActionableElement(role=role, name=label, backend_node_id=self._next_id)
        self._actions.setdefault(from_state, []).append(action)
        self._actions.setdefault(to_state, [])  # ensure sink states exist
        self._transitions[(from_state, role, label)] = to_state

    def set_miss(self, label: str, mode: str) -> None:
        self._miss[label] = mode

    def set_diverge(self, label: str, mode: str) -> None:
        self._diverge[label] = mode

    def html(self, name: str) -> str:
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
        return self._transitions[(name, action.role, action.name)]

    def miss_mode(self, action: ActionableElement) -> str | None:
        return self._miss.get(action.name)

    def diverge_mode(self, action: ActionableElement) -> str | None:
        return self._diverge.get(action.name)

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _ReplayDriver:
    """A BrowserDriver over a _ReplayApp, flaking a marked step on replay (§2e, 7d)."""

    def __init__(self, app: _ReplayApp) -> None:
        self._app = app
        self._current = app.root
        self._probes: dict[str, int] = defaultdict(int)
        self._performs: dict[str, int] = defaultdict(int)

    def reset(self) -> None:
        self._current = self._app.root

    def state_html(self) -> str:
        return self._app.html(self._current)

    def ax_nodes(self) -> Sequence[Mapping[str, object]]:
        return self._app.ax_nodes(self._current)

    def probe(self, action: ActionableElement) -> ActuationVerdict:
        # Count this reach (no layers here, so reach probes exactly once). Visit #1
        # is the first firing; #2+ are replays, which is when a "missing" step goes
        # not-located.
        self._probes[action.name] += 1
        if self._is_flaky(self._app.miss_mode(action), self._probes[action.name]):
            return ActuationVerdict(Verdict.NOT_LOCATED)
        return ActuationVerdict(Verdict.ACTUATE)

    def perform(self, action: ActionableElement) -> None:
        self._performs[action.name] += 1
        if self._is_flaky(self._app.diverge_mode(action), self._performs[action.name]):
            self._current = _ELSEWHERE  # land somewhere other than the mapped state
            return
        self._current = self._app.next_state(self._current, action)

    def capture_signals(self) -> StateSignals:
        return StateSignals()

    @staticmethod
    def _is_flaky(mode: str | None, visit: int) -> bool:
        """Whether a step marked `mode` flakes on this 1-based visit (§2e, 7d).

        `first` flakes on the first replay only (visit #2); `every` flakes on every
        replay (visit #2 and after). The first firing (visit #1) never flakes — that
        is when the step is discovered and mapped.
        """
        if mode == "first":
            return visit == 2
        if mode == "every":
            return visit >= 2
        return False


@pytest.fixture
def context() -> Iterator[dict[str, Any]]:
    ctx: dict[str, Any] = {
        "app": _ReplayApp(),
        "target": "http://localhost:8000/",
        "declared_sandbox": True,
    }
    yield ctx
    # Tear down the live server / driver used only by the final scenario.
    driver = ctx.get("driver")
    if driver is not None:
        driver.close()
    server = ctx.get("server")
    if server is not None:
        server.shutdown()
        server.server_close()
        ctx["thread"].join(timeout=5)


# --- Given ---------------------------------------------------------------


@given("a sandbox target")
def sandbox_target(context: dict[str, Any]) -> None:
    context["target"] = "http://localhost:8000/"


@given("an app whose actions are:")
def an_app(context: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    app: _ReplayApp = context["app"]
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        app.add(fields["from"], fields["label"], fields["role"], fields["to"])


@given(
    parsers.parse(
        'the action "{label}" is missing on the first replay but present afterwards'
    )
)
def missing_first_replay(context: dict[str, Any], label: str) -> None:
    context["app"].set_miss(label, "first")


@given(parsers.parse('the action "{label}" is missing on every replay'))
def missing_every_replay(context: dict[str, Any], label: str) -> None:
    context["app"].set_miss(label, "every")


@given(
    parsers.parse('the action "{label}" always lands on a different state on replay')
)
def diverge_every_replay(context: dict[str, Any], label: str) -> None:
    context["app"].set_diverge(label, "every")


@given(
    parsers.parse(
        'the action "{label}" lands on a different state on the first replay but is '
        "correct afterwards"
    )
)
def diverge_first_replay(context: dict[str, Any], label: str) -> None:
    context["app"].set_diverge(label, "first")


# --- When ----------------------------------------------------------------


@when(parsers.parse('I explore from "{root}"'))
def i_explore(context: dict[str, Any], root: str) -> None:
    app: _ReplayApp = context["app"]
    app.root = root
    context["graph"] = explore(
        _ReplayDriver(app),
        target=context["target"],
        controller=RunController(RunBudget()),
        declared_sandbox=context["declared_sandbox"],
    )


# --- Then ----------------------------------------------------------------


def _named_states(context: dict[str, Any], names: Sequence[str]) -> set[str]:
    app: _ReplayApp = context["app"]
    return {app.state_id_of(name) for name in names}


@then(parsers.parse("the graph has states: {names}"))
def graph_has_states(context: dict[str, Any], names: str) -> None:
    wanted = [n.strip() for n in names.split(",")]
    assert set(context["graph"].states) == _named_states(context, wanted)


@then(parsers.parse('the graph has a transition "{frm} --{label}--> {to}"'))
def graph_has_transition(
    context: dict[str, Any], frm: str, label: str, to: str
) -> None:
    app: _ReplayApp = context["app"]
    from_id = app.state_id_of(frm)
    to_id = app.state_id_of(to)
    found = [
        t
        for t in context["graph"].transitions
        if t.from_state == from_id and t.to_state == to_id and t.action.name == label
    ]
    assert found, f"no transition {frm} --{label}--> {to}"


def _skip_reasons(context: dict[str, Any], label: str, frm: str) -> list[str]:
    app: _ReplayApp = context["app"]
    from_id = app.state_id_of(frm)
    reasons = [
        s.reason
        for s in context["graph"].skipped
        if s.from_state == from_id and s.action.name == label
    ]
    fired = [
        t
        for t in context["graph"].transitions
        if t.from_state == from_id and t.action.name == label
    ]
    assert not fired, f"{label!r} from {frm!r} was flagged but also fired"
    return reasons


@then(
    parsers.parse(
        'the action "{label}" from "{frm}" is flagged as an unreachable replay step'
    )
)
def flagged_unreachable(context: dict[str, Any], label: str, frm: str) -> None:
    reasons = _skip_reasons(context, label, frm)
    assert any(
        "replay could not reach" in r for r in reasons
    ), f"reason did not name an unreachable replay step: {reasons}"


@then(
    parsers.parse(
        'the action "{label}" from "{frm}" is flagged as a replay divergence'
    )
)
def flagged_divergence(context: dict[str, Any], label: str, frm: str) -> None:
    reasons = _skip_reasons(context, label, frm)
    assert any(
        "diverged" in r for r in reasons
    ), f"reason did not name a replay divergence: {reasons}"


# --- Live scenario -------------------------------------------------------
#
# A scripted loopback server whose entry page is served degraded (no onward link) on
# exactly one reset. Reset-and-replay meets the degraded render, its fidelity check
# sees a page that is not the start state, and retry meets a good render on the next
# reset — so the page behind the flaky one is mapped. Short settle timings keep it fast.

_QUIET_WINDOW_S = 0.3
_SETTLE_TIMEOUT_S = 2.0

_COMPLETE = '<html><body><h1>Home</h1><a href="/sub">Go to sub</a></body></html>'
_DEGRADED = "<html><body><h1>Loading</h1></body></html>"
_SUB = "<html><body><h1>Sub page</h1></body></html>"


class _DegradedServer(ThreadingHTTPServer):
    """Serves the entry page degraded on the second GET of "/", complete otherwise."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _DegradedHandler)
        self.entry_gets = 0


class _DegradedHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's required name)
        server: _DegradedServer = self.server  # type: ignore[assignment]
        if self.path == "/sub":
            self._respond(_SUB)
            return
        if self.path in ("/", ""):
            server.entry_gets += 1
            self._respond(_DEGRADED if server.entry_gets == 2 else _COMPLETE)
            return
        self._respond("not found", status=404)

    def _respond(self, body: str, status: int = 200) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:  # silence the per-request stderr log
        pass


@given("a live site whose entry page is degraded on the first replay")
def live_degraded_site(context: dict[str, Any]) -> None:
    server = _DegradedServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    driver = PlaywrightDriver(
        base, quiet_window=_QUIET_WINDOW_S, settle_timeout=_SETTLE_TIMEOUT_S
    )
    driver.__enter__()
    context["server"] = server
    context["thread"] = thread
    context["driver"] = driver
    context["target"] = base


@when("I run spoor explore against it")
def run_explore(context: dict[str, Any]) -> None:
    controller = RunController(RunBudget(max_states=25, max_requests=50))
    context["graph"] = explore(
        context["driver"], target=context["target"], controller=controller
    )


@then(parsers.parse("it reports more than {n:d} state discovered"))
def more_than_n_states(context: dict[str, Any], n: int) -> None:
    assert len(context["graph"].states) > n, context["graph"].states
