"""Step definitions for features/serving.feature (ROADMAP.md §2f).

The serving layer is a read-only API over a persisted map. These steps build a
map store backed by a temp cache root, populate it the way a run would, drive the
FastAPI app with an in-process test client, and pin the read-only contract:
mapped URLs come back with freshness, unmapped URLs 404, and every route is GET.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when
from starlette.routing import Route

from spoor.api_discovery.discovery import DiscoveredSpec
from spoor.api_discovery.graphql import DiscoveredGraphQL
from spoor.api_discovery.synthesis import SynthesizedEndpoint, SynthesizedSpec
from spoor.security import storage
from spoor.serving.api import create_app
from spoor.serving.store import MapStore, shareable_api_surface

# Marker segments planted in the local-only parts of the surface; the served
# response must never contain them (§2h counts-only for synthesized paths).
_SECRET_PATH_MARKER = "should-not-leak"
_LOCAL_DOC_MARKER = "local-only-doc"

scenarios("serving.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {}


@pytest.fixture(autouse=True)
def temp_cache_root(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the local cache root so the map store writes under a temp dir."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / ".spoor-cache")


# --- Given ---------------------------------------------------------------


@given("a served map containing:")
def served_map(context: dict[str, Any], datatable: list[list[str]]) -> None:
    store = MapStore()
    header, *rows = datatable
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        store.record(
            fields["url"],
            [{"title": fields["title"]}],
            tier=1,
            captured_at=datetime.fromisoformat(fields["captured_at"]),
        )
    context["client"] = TestClient(create_app(store))
    context["app"] = context["client"].app


@given(
    parsers.parse('the map records an observed API surface for "{url}"')
)
def record_api_surface(context: dict[str, Any], url: str) -> None:
    # Build a run's observed surface with synthesized endpoints whose templated
    # paths and doc path carry the leak markers, then project it through the
    # §2h-safe helper the CLI uses — proving the projection drops the paths.
    synthesized = SynthesizedSpec(
        endpoints=(
            SynthesizedEndpoint("GET", f"/api/{_SECRET_PATH_MARKER}/{{id}}", (200,)),
            SynthesizedEndpoint("POST", f"/api/{_SECRET_PATH_MARKER}/orders", (201,)),
            SynthesizedEndpoint("GET", f"/api/{_SECRET_PATH_MARKER}/status", (200,)),
        ),
        request_count=12,
        doc_path=f"/tmp/{_LOCAL_DOC_MARKER}/openapi.json",
    )
    surface = shareable_api_surface(
        api_spec=DiscoveredSpec("openapi", "3.0.0", "https://shop.example/openapi.json"),
        graphql=DiscoveredGraphQL("https://shop.example/graphql", 42),
        synthesized_spec=synthesized,
        action_correlation=None,
    )
    MapStore().record(
        url,
        [{"title": "API Home"}],
        tier=1,
        api_surface=surface,
        captured_at=datetime.fromisoformat("2020-01-01T00:00:00Z"),
    )


# --- When ----------------------------------------------------------------


@when(parsers.parse('I GET "{path}"'))
def do_get(context: dict[str, Any], path: str) -> None:
    # A scenario without a Background (the read-only route check) needs no map.
    if "client" not in context:
        context["client"] = TestClient(create_app(MapStore()))
        context["app"] = context["client"].app
    context["response"] = context["client"].get(path)


# --- Then ----------------------------------------------------------------


@then(parsers.parse("the response status is {code:d}"))
def response_status_is(context: dict[str, Any], code: int) -> None:
    assert context["response"].status_code == code


@then(parsers.parse('the first record\'s "{field}" equals "{value}"'))
def first_record_field_equals(
    context: dict[str, Any], field: str, value: str
) -> None:
    assert context["response"].json()["records"][0][field] == value


@then("the response carries a capture time and a non-negative age")
def response_has_freshness(context: dict[str, Any]) -> None:
    body = context["response"].json()
    assert isinstance(body["captured_at"], str) and body["captured_at"]
    assert isinstance(body["age_seconds"], (int, float))
    assert body["age_seconds"] >= 0


@then(parsers.parse('the domains list contains "{domain}"'))
def domains_list_contains(context: dict[str, Any], domain: str) -> None:
    assert domain in context["response"].json()["domains"]


@then(parsers.parse('the API surface reports an "{kind}" spec'))
def surface_spec_kind(context: dict[str, Any], kind: str) -> None:
    surface = context["response"].json()["api_surface"]
    assert surface["spec"]["kind"] == kind


@then(parsers.parse("the API surface reports a GraphQL endpoint with {n:d} types"))
def surface_graphql_types(context: dict[str, Any], n: int) -> None:
    surface = context["response"].json()["api_surface"]
    assert surface["graphql"]["types"] == n


@then(parsers.parse("the API surface reports {n:d} synthesized endpoints"))
def surface_synthesized_count(context: dict[str, Any], n: int) -> None:
    surface = context["response"].json()["api_surface"]
    assert surface["synthesized"]["endpoint_count"] == n


@then("the served API surface exposes no templated endpoint path")
def surface_hides_paths(context: dict[str, Any]) -> None:
    # The whole served payload, as text, must contain neither the templated
    # endpoint paths nor the local-only doc path (§2h counts-only).
    body = context["response"].text
    assert _SECRET_PATH_MARKER not in body
    assert _LOCAL_DOC_MARKER not in body


@then("every serving route is read-only")
def every_route_read_only(context: dict[str, Any]) -> None:
    # Structural proof of the §2f non-negotiable: no route offers a
    # state-changing method. Starlette adds HEAD alongside GET automatically.
    if "app" not in context:
        context["app"] = create_app(MapStore())
    app_routes = [r for r in context["app"].routes if isinstance(r, Route)]
    assert app_routes, "expected the serving app to declare routes"
    for route in app_routes:
        methods = set(route.methods or set())
        assert methods <= {"GET", "HEAD"}, f"{route.path} allows {methods}"
