"""Official API spec discovery — §2b layer 1 (ROADMAP.md §2b).

The cheapest, most-certain layer of API surface discovery: before any
reverse-engineering, just look for a spec the target already publishes. Probe a
short, fixed list of conventional paths against the target's origin and, for the
first that returns a real OpenAPI/Swagger JSON document, report it.

Nothing here is site-specific (§0): the path list and the version-key check are
conventions identical for every target. Probing honors `robots.txt` allow/deny —
a disallowed path is never fetched (§6) — but is *exempt from crawl-delay
spacing*: this is a bounded, one-time origin probe of a fixed ≤4-path list, not
the repeated crawling a crawl-delay guards against, so applying the delay would
turn a "nearly-free" companion (§2b) into a multi-second per-run tax (recorded as
a decision in the ROADMAP §2b note). Every probe failure is swallowed into "no
spec observed there", never an error that fails the run. What is reported is
*observed*, never "the complete API" (§2b's bounded claim). HTML/JS-bundle
scanning, GraphQL introspection, and spec synthesis from captured traffic are
later §2b slices (see the ROADMAP note).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from spoor.core.config import PolitenessPolicy
from spoor.operational.politeness import Politeness

# Conventional locations an OpenAPI/Swagger document is published at, tried in
# order (first valid hit wins). A fixed, generic list — no site knowledge (§0).
CONVENTIONAL_SPEC_PATHS: tuple[str, ...] = (
    "/openapi.json",
    "/swagger.json",
    "/api-docs",
    "/.well-known/openapi.json",
)

# Keep a probe cheap and non-blocking; a slow path is treated as "not there".
_PROBE_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class DiscoveredSpec:
    """An official API spec observed at a conventional path (ROADMAP.md §2b).

    `kind` is "openapi" (OpenAPI 3.x) or "swagger" (Swagger 2.0); `version` is
    the value of that document's version key; `url` is where it was found. This
    records what was *observed*, not a claim that it describes the whole API.
    """

    kind: str
    version: str
    url: str


def _spec_from_json(body: object, url: str) -> DiscoveredSpec | None:
    """Interpret a parsed JSON body as a spec, or None if it isn't one.

    A real OpenAPI 3.x doc carries a top-level `openapi` version string; a
    Swagger 2.0 doc carries `swagger`. Anything without one of those keys — a
    SPA's HTML-shell-as-JSON, an unrelated JSON endpoint — is not a spec, so it
    is rejected rather than reported as a false positive.
    """
    if not isinstance(body, dict):
        return None
    for key, kind in (("openapi", "openapi"), ("swagger", "swagger")):
        version = body.get(key)
        if isinstance(version, str) and version:
            return DiscoveredSpec(kind=kind, version=version, url=url)
    return None


def _probe(client: httpx.Client, url: str) -> DiscoveredSpec | None:
    """Fetch one candidate path; return a spec only for a valid JSON spec doc."""
    try:
        response = client.get(url, timeout=_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        # 200 but not JSON (e.g. an HTML SPA shell served at /api-docs).
        return None
    return _spec_from_json(body, url)


def discover_spec(
    target: str,
    client: httpx.Client,
    *,
    policy: PolitenessPolicy | None = None,
) -> DiscoveredSpec | None:
    """Probe the target's origin for a published API spec (§2b layer 1).

    Probes `CONVENTIONAL_SPEC_PATHS` against `target`'s scheme+host, in order,
    returning the first valid OpenAPI/Swagger document — or None if none is
    found. Honors `robots.txt` allow/deny (a disallowed path is skipped, never
    fetched, §6) but does not apply crawl-delay spacing to the bounded probe set
    (see the module docstring). Never raises: a probe that errors is "not there".
    """
    parts = urlsplit(target)
    if not parts.scheme or not parts.netloc:
        return None
    origin = f"{parts.scheme}://{parts.netloc}"
    gate = Politeness(policy or PolitenessPolicy(), client)
    for path in CONVENTIONAL_SPEC_PATHS:
        url = urljoin(origin, path)
        if not gate.can_fetch(url):
            continue
        spec = _probe(client, url)
        if spec is not None:
            return spec
    return None
