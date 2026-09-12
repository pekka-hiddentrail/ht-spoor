"""GraphQL introspection discovery — §2b layer 2 (ROADMAP.md §2b).

Layer 2 of API surface discovery, in the same shape as layer 1's conventional
spec probing: alongside every run, probe a short fixed list of conventional
GraphQL endpoints with a single standard introspection query. An endpoint that
answers with a schema has introspection enabled — Spoor records where it is and
how many types it reports.

Opportunistic by nature (§2b): many production APIs disable introspection
deliberately, so a "none" means "not observed / not exposed", never "no GraphQL
exists". Nothing here is site-specific (§0): the endpoint list and the query are
identical for every target. Probing honors `robots.txt` allow/deny (a disallowed
endpoint is not probed, §6) but — like layer 1 — is exempt from crawl-delay
spacing (a one-time bounded probe). Every failure is swallowed into "none
observed", never an error that fails the run. What is reported is *observed*,
never a complete-API claim. This slice records the endpoint + type count;
persisting the full schema to the local-only cache is a later slice (see the
ROADMAP §2b note).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from spoor.core.config import PolitenessPolicy
from spoor.operational.politeness import Politeness

# Conventional locations a GraphQL endpoint is served at, tried in order. A
# fixed, generic list — no site knowledge (§0).
CONVENTIONAL_GRAPHQL_PATHS: tuple[str, ...] = ("/graphql", "/api/graphql")

# A minimal but standard introspection query: enough to confirm introspection is
# enabled and read the schema's type list. The full introspection query returns
# every field/arg/directive; this slice only needs "is it on, and how big".
INTROSPECTION_QUERY = "query{__schema{queryType{name} types{name}}}"

# Keep a probe cheap and non-blocking; a slow endpoint is treated as "not there".
_PROBE_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class DiscoveredGraphQL:
    """A GraphQL endpoint with introspection observed enabled (ROADMAP.md §2b).

    `url` is the endpoint; `types` is the number of types its schema reported —
    a cheap size signal and proof introspection answered. This records what was
    *observed*, not a claim of the endpoint's complete surface.
    """

    url: str
    types: int


def _schema_types(body: object) -> int | None:
    """Type count if `body` is a GraphQL introspection response, else None.

    A real introspection reply nests the schema under `data.__schema.types` (a
    list). Anything else — a REST endpoint's JSON, a `{"errors": [...]}` body
    from a server with introspection disabled, a non-dict — is not a schema, so
    it is rejected rather than reported as a false positive.
    """
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    schema = data.get("__schema")
    if not isinstance(schema, dict):
        return None
    types = schema.get("types")
    if not isinstance(types, list):
        return None
    return len(types)


def _introspect(client: httpx.Client, url: str) -> DiscoveredGraphQL | None:
    """POST the introspection query; return a schema only for a valid reply."""
    try:
        response = client.post(
            url, json={"query": INTROSPECTION_QUERY}, timeout=_PROBE_TIMEOUT_S
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    count = _schema_types(body)
    if count is None:
        return None
    return DiscoveredGraphQL(url=url, types=count)


def discover_graphql(
    target: str,
    client: httpx.Client,
    *,
    policy: PolitenessPolicy | None = None,
) -> DiscoveredGraphQL | None:
    """Probe the target's origin for an introspectable GraphQL endpoint (§2b).

    Probes `CONVENTIONAL_GRAPHQL_PATHS` against `target`'s scheme+host, in order,
    returning the first that answers introspection — or None if none does. Honors
    `robots.txt` allow/deny (a disallowed endpoint is skipped, §6) but does not
    apply crawl-delay spacing to the bounded probe set. Never raises.
    """
    parts = urlsplit(target)
    if not parts.scheme or not parts.netloc:
        return None
    origin = f"{parts.scheme}://{parts.netloc}"
    gate = Politeness(policy or PolitenessPolicy(), client)
    for path in CONVENTIONAL_GRAPHQL_PATHS:
        url = urljoin(origin, path)
        if not gate.can_fetch(url):
            continue
        found = _introspect(client, url)
        if found is not None:
            return found
    return None
