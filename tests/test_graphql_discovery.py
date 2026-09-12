"""Unit tests for §2b layer-2 GraphQL introspection (below api_discovery.feature).

Pins the discovery contract directly: what counts as an introspectable schema,
endpoint ordering, robots-gating, and that no probe failure ever raises.
"""

from __future__ import annotations

import json

import httpx
import pytest

from spoor.api_discovery.graphql import (
    CONVENTIONAL_GRAPHQL_PATHS,
    DiscoveredGraphQL,
    discover_graphql,
)
from spoor.core.config import PolitenessPolicy

_INTROSPECTION = json.dumps(
    {"data": {"__schema": {"types": [{"name": "Query"}, {"name": "User"}]}}}
)
_DISABLED = json.dumps({"errors": [{"message": "introspection disabled"}]})


def _client(routes: dict[str, tuple[int, str]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in routes:
            status, body = routes[request.url.path]
            return httpx.Response(
                status, text=body, headers={"content-type": "application/json"}
            )
        return httpx.Response(404, text="nope")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_introspectable_endpoint_is_discovered() -> None:
    with _client({"/graphql": (200, _INTROSPECTION)}) as client:
        found = discover_graphql("http://x/page", client)
    assert found == DiscoveredGraphQL("http://x/graphql", 2)


def test_introspection_disabled_is_not_discovered() -> None:
    # A 200 whose body is all errors (introspection off) is not a schema.
    with _client({"/graphql": (200, _DISABLED)}) as client:
        assert discover_graphql("http://x/page", client) is None


def test_no_graphql_endpoint_returns_none() -> None:
    with _client({}) as client:
        assert discover_graphql("http://x/page", client) is None


def test_non_graphql_json_is_not_a_schema() -> None:
    # A REST endpoint that happens to sit at /graphql and returns unrelated JSON.
    with _client({"/graphql": (200, json.dumps({"ok": True}))}) as client:
        assert discover_graphql("http://x/page", client) is None


def test_alternate_endpoint_is_probed() -> None:
    # /graphql 404s; /api/graphql answers — discovery keeps going down the list.
    with _client({"/api/graphql": (200, _INTROSPECTION)}) as client:
        found = discover_graphql("http://x/page", client)
    assert found is not None
    assert found.url.endswith("/api/graphql")


def test_robots_disallowed_endpoint_is_not_probed() -> None:
    routes = {
        "/robots.txt": (200, "User-agent: *\nDisallow: /graphql\n"),
        "/graphql": (200, _INTROSPECTION),
    }
    # /api/graphql is not routed, so with /graphql disallowed the result is none.
    with _client(routes) as client:
        assert discover_graphql("http://x/page", client) is None


def test_transport_error_is_swallowed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert discover_graphql("http://x/page", client) is None


def test_targetless_url_returns_none() -> None:
    with _client({}) as client:
        assert discover_graphql("not-a-url", client) is None


def test_probe_is_not_crawl_delay_spaced(monkeypatch: pytest.MonkeyPatch) -> None:
    # The bounded probe is exempt from crawl-delay spacing (ROADMAP §2b decision).
    from spoor.operational import politeness

    slept: list[float] = []
    monkeypatch.setattr(politeness.time, "sleep", slept.append)
    policy = PolitenessPolicy(delay=0.5)
    with _client({"/graphql": (200, _INTROSPECTION)}) as client:
        found = discover_graphql("http://x/page", client, policy=policy)
    assert found is not None
    assert slept == []


def test_conventional_paths_are_documented() -> None:
    assert CONVENTIONAL_GRAPHQL_PATHS == ("/graphql", "/api/graphql")
