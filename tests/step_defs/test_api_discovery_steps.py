"""Step definitions for features/api_discovery.feature (ROADMAP.md §2b).

Drives the full run through an in-memory httpx MockTransport routing table
(deterministic, no ports) whose target page tier 1 can extract — so the run
resolves at tier 1 without a browser — while the conventional spec paths are
routed per scenario. Asserts against the run's discovered spec and the summary.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.api_discovery.correlation import Checkpoint, correlate
from spoor.api_discovery.synthesis import synthesize_from_har
from spoor.core import extract
from spoor.core.config import load_config
from spoor.core.extract import RunResult
from spoor.operational.observability import RunSummary

scenarios("api_discovery.feature")

# The target the run is pointed at (see `_CONFIG`); layer-4 synthesis and layer-5
# correlation cluster only requests same-origin with this, so HAR fixtures below
# use its origin.
_TARGET = "http://localhost:8000/index.html"
_ORIGIN = "http://localhost:8000"

# A fixed base instant for layer-5 correlation fixtures; checkpoints and requests
# are placed at whole-second offsets from it, so the time-window attribution is
# deterministic (no wall-clock, no ports).
_BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

# A target page tier 1 can extract a record from, so the run stays on tier 1
# (no escalation to a browser) and discovery is what the scenarios exercise.
_TARGET_PATH = "/index.html"
_TARGET_HTML = '<html><body><h1 class="t">Hello</h1></body></html>'
_CONFIG = (
    "target: http://localhost:8000/index.html\n"
    'fields:\n  title: { selector: "h1.t" }\n'
)

_OPENAPI_DOC = json.dumps({"openapi": "3.0.1", "info": {"title": "X", "version": "1"}})
_SWAGGER_DOC = json.dumps({"swagger": "2.0", "info": {"title": "X", "version": "1"}})
_INTROSPECTION = json.dumps(
    {"data": {"__schema": {"queryType": {"name": "Query"},
                           "types": [{"name": "Query"}, {"name": "User"}]}}}
)
_INTROSPECTION_DISABLED = json.dumps(
    {"errors": [{"message": "GraphQL introspection is not allowed"}]}
)


@pytest.fixture
def context() -> dict[str, Any]:
    """Per-scenario state: the routing table, then the run summary."""
    return {"routes": {_TARGET_PATH: (200, _TARGET_HTML, "text/html")}}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('a target that serves an OpenAPI 3 document at "{path}"'))
def serves_openapi(context: dict[str, Any], path: str) -> None:
    context["routes"][path] = (200, _OPENAPI_DOC, "application/json")


@given(parsers.parse('a target that serves a Swagger 2.0 document at "{path}"'))
def serves_swagger(context: dict[str, Any], path: str) -> None:
    context["routes"][path] = (200, _SWAGGER_DOC, "application/json")


@given("a target that serves no spec at any conventional path")
def serves_no_spec(context: dict[str, Any]) -> None:
    # Only the target page is routed; every spec path 404s (handler default).
    pass


@given(parsers.parse('a target whose "{path}" returns an HTML page, not a spec'))
def serves_html_at_path(context: dict[str, Any], path: str) -> None:
    context["routes"][path] = (200, "<html><body>docs</body></html>", "text/html")


@given(parsers.parse('a target whose landing page references a spec at "{path}"'))
def landing_references_spec(context: dict[str, Any], path: str) -> None:
    # The landing page stays tier-1 extractable (the h1.t record) and also links
    # the spec — so the run resolves at tier 1 and the HTML scan has a reference.
    html = (
        f'<html><body><h1 class="t">Hello</h1>'
        f'<a href="{path}">API documentation</a></body></html>'
    )
    context["routes"][_TARGET_PATH] = (200, html, "text/html")


@given(parsers.parse('a target whose landing page loads the script "{path}"'))
def landing_loads_script(context: dict[str, Any], path: str) -> None:
    # The landing HTML has no direct spec reference — only a <script src>, so the
    # spec is found (or not) purely by scanning the referenced bundle.
    html = (
        f'<html><body><h1 class="t">Hello</h1>'
        f'<script src="{path}"></script></body></html>'
    )
    context["routes"][_TARGET_PATH] = (200, html, "text/html")


@given(parsers.parse('the script "{path}" references a spec at "{spec_path}"'))
def script_references_spec(context: dict[str, Any], path: str, spec_path: str) -> None:
    js = f'const ui = SwaggerUIBundle({{ url: "{spec_path}", dom_id: "#s" }});'
    context["routes"][path] = (200, js, "application/javascript")


@given(parsers.parse('a target whose landing page has a Redoc spec-url of "{path}"'))
def landing_redoc_spec_url(context: dict[str, Any], path: str) -> None:
    # A path with none of the spec vocabulary: only the explicit spec-url
    # attribute pattern can find it, so this exercises that branch specifically.
    html = (
        f'<html><body><h1 class="t">Hello</h1>'
        f'<redoc spec-url="{path}"></redoc></body></html>'
    )
    context["routes"][_TARGET_PATH] = (200, html, "text/html")


@given(
    parsers.parse(
        'a target with a GraphQL endpoint at "{path}" answering introspection'
    )
)
def serves_graphql(context: dict[str, Any], path: str) -> None:
    context["routes"][path] = (200, _INTROSPECTION, "application/json")


@given(parsers.parse('a target with a "{path}" endpoint that refuses introspection'))
def serves_graphql_disabled(context: dict[str, Any], path: str) -> None:
    context["routes"][path] = (200, _INTROSPECTION_DISABLED, "application/json")


@given(parsers.parse('a robots.txt that disallows "{path}"'))
def robots_disallows(context: dict[str, Any], path: str) -> None:
    context["routes"]["/robots.txt"] = (
        200,
        f"User-agent: *\nDisallow: {path}\n",
        "text/plain",
    )


# --- Given: layer-4 captured-HAR fixtures --------------------------------


def _har_entry(method: str, url: str, mime: str = "application/json") -> dict[str, Any]:
    return {
        "request": {"method": method, "url": url},
        "response": {"status": 200, "content": {"mimeType": mime}},
    }


def _add_har_entry(
    context: dict[str, Any], tmp_path: Path, entry: dict[str, Any]
) -> None:
    entries = context.setdefault("har_entries", [])
    entries.append(entry)
    har = {
        "log": {
            "version": "1.2",
            "creator": {"name": "Playwright", "version": "1.62.0"},
            "entries": entries,
        }
    }
    path = tmp_path / "net.har"
    path.write_text(json.dumps(har), encoding="utf-8")
    context["har_path"] = path


@given(
    parsers.parse(
        'a captured HAR with GET JSON requests to "{p1}", "{p2}", "{p3}"'
    )
)
def har_three_get(
    context: dict[str, Any], tmp_path: Path, p1: str, p2: str, p3: str
) -> None:
    for path in (p1, p2, p3):
        _add_har_entry(context, tmp_path, _har_entry("GET", _ORIGIN + path))


@given(parsers.parse('a captured HAR with a "{method}" JSON request to "{path}"'))
@given(parsers.parse('the captured HAR also has a "{method}" JSON request to "{path}"'))
def har_add_request(
    context: dict[str, Any], tmp_path: Path, method: str, path: str
) -> None:
    _add_har_entry(context, tmp_path, _har_entry(method, _ORIGIN + path))


@given(parsers.parse('a captured HAR with a same-origin JSON request to "{path}"'))
def har_same_origin(context: dict[str, Any], tmp_path: Path, path: str) -> None:
    _add_har_entry(context, tmp_path, _har_entry("GET", _ORIGIN + path))


@given("the captured HAR also has a cross-origin JSON request")
def har_cross_origin(context: dict[str, Any], tmp_path: Path) -> None:
    _add_har_entry(
        context, tmp_path, _har_entry("GET", "http://cdn.example.com/api/track")
    )


@given("a captured HAR whose only requests return HTML, not JSON")
def har_html_only(context: dict[str, Any], tmp_path: Path) -> None:
    _add_har_entry(
        context, tmp_path, _har_entry("GET", _ORIGIN + "/page", mime="text/html")
    )


@given("a run that captured no HAR")
def no_har(context: dict[str, Any]) -> None:
    context["har_path"] = None


# --- When ----------------------------------------------------------------


@when("I synthesize an API spec from the captured HAR")
def run_synthesis(context: dict[str, Any]) -> None:
    har = context.get("har_path")
    spec = synthesize_from_har(har, _TARGET) if har is not None else None
    context["synth"] = spec
    context["summary"] = RunSummary.from_result(
        RunResult(records=[], har_path=har, synthesized_spec=spec)
    )


@when("I run the config and capture the summary")
def run_and_summarize(context: dict[str, Any]) -> None:
    routes = context["routes"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in routes:
            status, body, content_type = routes[request.url.path]
            return httpx.Response(
                status, text=body, headers={"content-type": content_type}
            )
        return httpx.Response(404, text="not found")

    cfg = load_config(_CONFIG)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract.run_report(cfg, client=client, sleep=lambda _: None)
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


# --- Then ----------------------------------------------------------------


@then(parsers.parse('the run reports a discovered "{kind}" spec at "{path}"'))
def reports_spec(context: dict[str, Any], kind: str, path: str) -> None:
    spec = context["result"].api_spec
    assert spec is not None
    assert spec.kind == kind
    assert spec.url.endswith(path)


@then(parsers.parse('the discovered spec version is "{version}"'))
def spec_version(context: dict[str, Any], version: str) -> None:
    assert context["result"].api_spec.version == version


@then("the run reports no discovered API spec")
def reports_no_spec(context: dict[str, Any]) -> None:
    assert context["result"].api_spec is None


@then("the summary describes the API spec as observed, not complete")
def summary_observed(context: dict[str, Any]) -> None:
    rendered = context["summary"].render()
    assert "observed" in rendered
    assert "complete" not in rendered


@then("the summary says no API spec was discovered")
def summary_none(context: dict[str, Any]) -> None:
    assert "none discovered" in context["summary"].render()


@then(parsers.parse('the run reports a discovered GraphQL schema at "{path}"'))
def reports_graphql(context: dict[str, Any], path: str) -> None:
    gql = context["result"].graphql
    assert gql is not None
    assert gql.url.endswith(path)


@then("the discovered GraphQL schema reports at least one type")
def graphql_has_types(context: dict[str, Any]) -> None:
    assert context["result"].graphql.types >= 1


@then("the summary describes the GraphQL schema as observed")
def summary_graphql_observed(context: dict[str, Any]) -> None:
    assert "introspection observed at" in context["summary"].render()


@then("the run reports no discovered GraphQL schema")
def reports_no_graphql(context: dict[str, Any]) -> None:
    assert context["result"].graphql is None


# --- Then: layer-4 synthesis ---------------------------------------------


@then(parsers.parse('the synthesized spec has a "{method}" endpoint for "{path}"'))
def synth_has_endpoint(context: dict[str, Any], method: str, path: str) -> None:
    spec = context["synth"]
    assert spec is not None
    assert any(e.method == method and e.path == path for e in spec.endpoints), (
        f"{method} {path} not in {[(e.method, e.path) for e in spec.endpoints]}"
    )


@then(
    parsers.re(
        r"the synthesized spec clustered (?P<reqs>\d+) requests? "
        r"into (?P<eps>\d+) endpoints?"
    )
)
def synth_counts(context: dict[str, Any], reqs: str, eps: str) -> None:
    spec = context["synth"]
    assert spec is not None
    assert spec.request_count == int(reqs)
    assert spec.endpoint_count == int(eps)


@then("the run summary reports the synthesized endpoint count, not the paths")
def synth_summary_counts_only(context: dict[str, Any]) -> None:
    spec = context["synth"]
    rendered = context["summary"].render()
    assert f"{spec.endpoint_count} endpoints synthesized" in rendered
    # §2h: counts only — no templated path leaks into the shared summary.
    for endpoint in spec.endpoints:
        assert endpoint.path not in rendered


@then("a synthesized OpenAPI document is written to the local-only cache")
def synth_doc_written(context: dict[str, Any]) -> None:
    spec = context["synth"]
    assert spec.doc_path is not None
    doc = Path(spec.doc_path)
    assert doc.is_file()
    data = json.loads(doc.read_text(encoding="utf-8"))
    assert str(data["openapi"]).startswith("3.")
    assert data["paths"]


@then("no API spec is synthesized")
def synth_none(context: dict[str, Any]) -> None:
    assert context["synth"] is None


# --- Given: layer-5 correlation fixtures ---------------------------------


def _har_entry_at(
    method: str, url: str, second: int, mime: str = "application/json"
) -> dict[str, Any]:
    started = (_BASE + timedelta(seconds=second)).isoformat()
    entry = _har_entry(method, url, mime)
    entry["startedDateTime"] = started
    return entry


@given(parsers.parse('a checkpoint "{label}" at second {second:d}'))
def checkpoint_at(context: dict[str, Any], label: str, second: int) -> None:
    checkpoints = context.setdefault("checkpoints", [])
    checkpoints.append(Checkpoint(label=label, at=_BASE + timedelta(seconds=second)))


@given(
    parsers.parse(
        'a captured HAR with a "{method}" JSON request to "{path}" at second {sec:d}'
    )
)
@given(
    parsers.parse(
        'the captured HAR also has a "{method}" JSON request to "{path}" '
        "at second {sec:d}"
    )
)
def har_request_at(
    context: dict[str, Any], tmp_path: Path, method: str, path: str, sec: int
) -> None:
    _add_har_entry(context, tmp_path, _har_entry_at(method, _ORIGIN + path, sec))


@given(
    parsers.parse(
        'a captured HAR with a same-origin JSON request to "{path}" at second {sec:d}'
    )
)
def har_same_origin_at(
    context: dict[str, Any], tmp_path: Path, path: str, sec: int
) -> None:
    _add_har_entry(context, tmp_path, _har_entry_at("GET", _ORIGIN + path, sec))


@given(parsers.parse("the captured HAR also has a cross-origin JSON request "
                     "at second {sec:d}"))
def har_cross_origin_at(context: dict[str, Any], tmp_path: Path, sec: int) -> None:
    _add_har_entry(
        context, tmp_path, _har_entry_at("GET", "http://cdn.example.com/api/track", sec)
    )


@given("no action checkpoints were recorded")
def no_checkpoints(context: dict[str, Any]) -> None:
    context["checkpoints"] = []


# --- When: layer-5 correlation -------------------------------------------


@when("I correlate the captured requests with the actions")
def run_correlation(context: dict[str, Any]) -> None:
    har = context["har_path"]
    checkpoints = context.get("checkpoints", [])
    corr = correlate(checkpoints, har, _TARGET)
    context["correlation"] = corr
    context["summary"] = RunSummary.from_result(
        RunResult(
            records=[], har_path=har, checkpoints=checkpoints, action_correlation=corr
        )
    )


# --- Then: layer-5 correlation -------------------------------------------


@then(parsers.parse('the action "{label}" is credited with a "{method}" '
                    'endpoint for "{path}"'))
def action_credited(
    context: dict[str, Any], label: str, method: str, path: str
) -> None:
    corr = context["correlation"]
    assert corr is not None
    actions = {a.label: a for a in corr.actions}
    assert label in actions, f"{label} not in {list(actions)}"
    assert f"{method} {path}" in actions[label].endpoints, (
        f"{method} {path} not in {actions[label].endpoints}"
    )


@then(
    parsers.re(
        r"the correlation credits (?P<reqs>\d+) requests? "
        r"across (?P<acts>\d+) actions?"
    )
)
def correlation_counts(context: dict[str, Any], reqs: str, acts: str) -> None:
    corr = context["correlation"]
    assert corr is not None
    assert corr.request_count == int(reqs)
    assert corr.action_count == int(acts)


@then("a correlation document is written to the local-only cache")
def correlation_doc_written(context: dict[str, Any]) -> None:
    corr = context["correlation"]
    assert corr.doc_path is not None
    doc = Path(corr.doc_path)
    assert doc.is_file()
    data = json.loads(doc.read_text(encoding="utf-8"))
    assert data["actions"]
    # The bounded-claim caveat travels with the local-only document (§2b).
    assert "not proven" in data["note"]


@then("the run summary reports the correlated counts, not the paths")
def correlation_summary_counts_only(context: dict[str, Any]) -> None:
    corr = context["correlation"]
    rendered = context["summary"].render()
    assert f"{corr.request_count} requests likely triggered" in rendered
    assert f"by {corr.action_count} actions" in rendered
    # §2h: counts only — no templated path leaks into the shared summary.
    for action in corr.actions:
        for endpoint in action.endpoints:
            assert endpoint not in rendered


@then("nothing is correlated")
def correlation_none(context: dict[str, Any]) -> None:
    assert context["correlation"] is None
