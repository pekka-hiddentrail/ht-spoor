"""Step definitions for features/api_discovery.feature (ROADMAP.md §2b).

Drives the full run through an in-memory httpx MockTransport routing table
(deterministic, no ports) whose target page tier 1 can extract — so the run
resolves at tier 1 without a browser — while the conventional spec paths are
routed per scenario. Asserts against the run's discovered spec and the summary.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary

scenarios("api_discovery.feature")

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


@given(parsers.parse('a robots.txt that disallows "{path}"'))
def robots_disallows(context: dict[str, Any], path: str) -> None:
    context["routes"]["/robots.txt"] = (
        200,
        f"User-agent: *\nDisallow: {path}\n",
        "text/plain",
    )


# --- When ----------------------------------------------------------------


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
