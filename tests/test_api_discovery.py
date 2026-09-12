"""Unit tests for §2b layer-1 spec discovery (below api_discovery.feature).

Pins the discovery contract directly: what counts as a spec, path-ordering
(first valid hit wins), robots-gating, and that no probe failure ever raises.
"""

from __future__ import annotations

import json

import httpx
import pytest

from spoor.api_discovery.discovery import (
    CONVENTIONAL_SPEC_PATHS,
    DiscoveredSpec,
    discover_spec,
)
from spoor.core.config import PolitenessPolicy

_OPENAPI = json.dumps({"openapi": "3.1.0"})
_SWAGGER = json.dumps({"swagger": "2.0"})


def _client(routes: dict[str, tuple[int, str, str]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in routes:
            status, body, ctype = routes[request.url.path]
            return httpx.Response(status, text=body, headers={"content-type": ctype})
        return httpx.Response(404, text="nope")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openapi_document_is_discovered() -> None:
    routes = {"/openapi.json": (200, _OPENAPI, "application/json")}
    with _client(routes) as client:
        spec = discover_spec("http://x/page", client)
    assert spec == DiscoveredSpec("openapi", "3.1.0", "http://x/openapi.json")


def test_swagger_document_is_discovered() -> None:
    routes = {"/swagger.json": (200, _SWAGGER, "application/json")}
    with _client(routes) as client:
        spec = discover_spec("http://x/page", client)
    assert spec is not None
    assert spec.kind == "swagger"
    assert spec.version == "2.0"


def test_no_spec_returns_none() -> None:
    with _client({}) as client:
        assert discover_spec("http://x/page", client) is None


def test_json_without_version_key_is_not_a_spec() -> None:
    # A 200 JSON body that isn't an OpenAPI/Swagger doc must not false-positive.
    body = json.dumps({"hello": "world"})
    routes = {"/openapi.json": (200, body, "application/json")}
    with _client(routes) as client:
        assert discover_spec("http://x/page", client) is None


def test_html_at_conventional_path_is_not_a_spec() -> None:
    routes = {"/api-docs": (200, "<html>docs</html>", "text/html")}
    with _client(routes) as client:
        assert discover_spec("http://x/page", client) is None


def test_first_valid_path_wins() -> None:
    # Both openapi.json and swagger.json are valid; the earlier path is returned.
    routes = {
        "/openapi.json": (200, _OPENAPI, "application/json"),
        "/swagger.json": (200, _SWAGGER, "application/json"),
    }
    with _client(routes) as client:
        spec = discover_spec("http://x/page", client)
    assert spec is not None
    assert spec.url.endswith("/openapi.json")


def test_earlier_invalid_path_does_not_block_a_later_valid_one() -> None:
    # /openapi.json 404s, /swagger.json is a real spec: discovery keeps going.
    routes = {"/swagger.json": (200, _SWAGGER, "application/json")}
    with _client(routes) as client:
        spec = discover_spec("http://x/page", client)
    assert spec is not None
    assert spec.url.endswith("/swagger.json")


def test_robots_disallowed_path_is_not_probed() -> None:
    routes = {
        "/robots.txt": (200, "User-agent: *\nDisallow: /openapi.json\n", "text/plain"),
        "/openapi.json": (200, _OPENAPI, "application/json"),
    }
    with _client(routes) as client:
        spec = discover_spec("http://x/page", client)
    assert spec is None


def test_transport_error_is_swallowed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert discover_spec("http://x/page", client) is None


def test_targetless_url_returns_none() -> None:
    # A target with no scheme/host has no origin to probe.
    with _client({}) as client:
        assert discover_spec("not-a-url", client) is None


def test_probe_is_not_crawl_delay_spaced(monkeypatch: pytest.MonkeyPatch) -> None:
    # The bounded origin probe is exempt from crawl-delay spacing (ROADMAP §2b
    # decision): even a delay policy adds no sleeps, so discovery stays near-free.
    from spoor.operational import politeness

    slept: list[float] = []
    monkeypatch.setattr(politeness.time, "sleep", slept.append)
    routes = {"/swagger.json": (200, _SWAGGER, "application/json")}
    policy = PolitenessPolicy(delay=0.5)
    with _client(routes) as client:
        spec = discover_spec("http://x/page", client, policy=policy)
    assert spec is not None
    assert slept == []


def test_conventional_paths_are_the_documented_four() -> None:
    assert CONVENTIONAL_SPEC_PATHS == (
        "/openapi.json",
        "/swagger.json",
        "/api-docs",
        "/.well-known/openapi.json",
    )
