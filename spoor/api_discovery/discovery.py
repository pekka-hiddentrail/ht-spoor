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
*observed*, never "the complete API" (§2b's bounded claim).

Two halves, both here (§2b layer 1). First, conventional-path probing (above).
Second, when that finds nothing, scan for a *reference* to a spec — a Redoc
`spec-url`, a Swagger-UI `url:`, or any link carrying the spec vocabulary
(`openapi`/`swagger`/`api-docs`) — first in the landing page's HTML, then inside
the same-origin JS bundles the page loads (where a SPA usually keeps that
config). Every candidate is validated with the same strict JSON check, so a
false lead is never reported. The reference-finding is deliberately loose (a bad
guess costs one bounded probe); the validation is what keeps false positives out.
YAML specs (validation is JSON-only, matching the conventional paths), GraphQL
introspection, and spec synthesis from captured traffic are later §2b slices (see
the ROADMAP note). This slice fetches the landing page itself to scan it; reusing
the HTML the resolver already fetched — like sharing one robots cache between
resolver and discovery — is a known, deferred optimization, not a correctness gap.
"""

from __future__ import annotations

import itertools
import re
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

# Cap on how many landing-page spec references are probed, keeping the HTML-scan
# half of layer 1 bounded and near-free even on a page full of matching strings.
_MAX_HTML_SPEC_CANDIDATES = 10

# Redoc's explicit spec pointer: `<redoc spec-url="...">`. Caught on its own so a
# reference whose path carries none of the spec vocabulary is still found.
_SPEC_URL_ATTR = re.compile(r"""spec-url\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# Any quoted, whitespace-free token carrying the spec vocabulary — covers a
# Swagger-UI `url: "..."`, a `<link>/<a href>`, or an inline path. Whitespace-free
# so a prose title like "Swagger Petstore" is not mistaken for a reference. The
# vocabulary (openapi/swagger/api-docs) is generic convention, not site knowledge
# (§0).
_SPEC_VOCAB_REF = re.compile(
    r"""["']([^"'\s]*(?:openapi|swagger|api[-_]?docs)[^"'\s]*)["']""",
    re.IGNORECASE,
)

# Cap on how many same-origin JS bundles the landing page loads are fetched and
# scanned for a spec reference — keeps the bundle scan bounded and near-free.
_MAX_SCRIPT_BUNDLES = 10

# `<script src="...">` — the bundles a page loads. Only same-origin ones are
# fetched (see `_script_srcs`); a spec's config usually lives in the app's own
# bundle, and fetching arbitrary third-party origins would be neither bounded
# nor polite. `src` must be whitespace-preceded so it is a real attribute, not
# the tail of another one like `data-src` (a lazy-load decoy).
_SCRIPT_SRC = re.compile(
    r"""<script\b[^>]*?\ssrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE
)


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


def _spec_reference_candidates(html: str, page_url: str) -> list[str]:
    """Absolute candidate spec URLs referenced by a page's HTML (§2b layer 1).

    Finds Redoc `spec-url` attributes and any quoted token carrying the spec
    vocabulary, resolves each against `page_url`, and returns the http(s) ones in
    first-seen order with duplicates removed. Fragment/`data:`/`javascript:` and
    non-http references are dropped. Loose by design: each candidate is validated
    strictly by `_probe`, so a wrong guess is rejected, not reported.
    """
    seen: list[str] = []
    for match in itertools.chain(
        _SPEC_URL_ATTR.finditer(html), _SPEC_VOCAB_REF.finditer(html)
    ):
        ref = match.group(1).strip()
        if not ref or ref.startswith(("#", "data:", "javascript:")):
            continue
        url = urljoin(page_url, ref)
        if not url.startswith(("http://", "https://")):
            continue
        if url not in seen:
            seen.append(url)
    return seen


def _script_srcs(html: str, page_url: str) -> list[str]:
    """Same-host `<script src>` URLs a page loads, absolute and de-duplicated.

    Third-party hosts are dropped: a spec's config usually lives in the app's own
    bundle, and fetching arbitrary external hosts would be neither bounded nor
    polite. The match is host-based (`netloc`), so `http`/`https` variants of the
    same host are currently treated as in-scope here. Resolved against
    `page_url`, first-seen order preserved.
    """
    origin = urlsplit(page_url).netloc
    seen: list[str] = []
    for match in _SCRIPT_SRC.finditer(html):
        url = urljoin(page_url, match.group(1).strip())
        if not url.startswith(("http://", "https://")):
            continue
        if urlsplit(url).netloc != origin:
            continue
        if url not in seen:
            seen.append(url)
    return seen


def _probe_candidates(
    client: httpx.Client, gate: Politeness, candidates: list[str]
) -> DiscoveredSpec | None:
    """Probe candidate spec URLs (robots-honored, capped); first valid wins."""
    for url in candidates[:_MAX_HTML_SPEC_CANDIDATES]:
        if not gate.can_fetch(url):
            continue
        spec = _probe(client, url)
        if spec is not None:
            return spec
    return None


def _fetch(client: httpx.Client, url: str, gate: Politeness) -> httpx.Response | None:
    """GET `url`, or None if robots-denied, errored, or not a 200."""
    if not gate.can_fetch(url):
        return None
    try:
        response = client.get(url, timeout=_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    return response


def _discover_spec_in_html(
    client: httpx.Client, target: str, gate: Politeness
) -> DiscoveredSpec | None:
    """Fetch the landing page and probe any spec it references (§2b layer 1).

    The second half of layer 1, run only when conventional-path probing found
    nothing. Looks for a spec reference first in the landing HTML, then inside
    the same-origin JS bundles the page loads. Both are resolved against the
    landing page's *final* URL (after any redirect), matching how a browser
    resolves a relative reference — including one a bundle makes, which resolves
    against the document, not the script. Honors robots on the landing fetch,
    each bundle fetch, and each probed candidate (§6); is bounded by
    `_MAX_SCRIPT_BUNDLES` and `_MAX_HTML_SPEC_CANDIDATES`; never raises — any
    failed fetch or non-spec candidate is simply "not there".
    """
    response = _fetch(client, target, gate)
    if response is None:
        return None
    html = response.text
    page_url = str(response.url)
    spec = _probe_candidates(client, gate, _spec_reference_candidates(html, page_url))
    if spec is not None:
        return spec
    for src in _script_srcs(html, page_url)[:_MAX_SCRIPT_BUNDLES]:
        bundle = _fetch(client, src, gate)
        if bundle is None:
            continue
        spec = _probe_candidates(
            client, gate, _spec_reference_candidates(bundle.text, page_url)
        )
        if spec is not None:
            return spec
    return None


def discover_spec(
    target: str,
    client: httpx.Client,
    *,
    policy: PolitenessPolicy | None = None,
) -> DiscoveredSpec | None:
    """Discover a published API spec for the target (§2b layer 1, both halves).

    First probes `CONVENTIONAL_SPEC_PATHS` against `target`'s scheme+host, in
    order, returning the first valid OpenAPI/Swagger document. If none is found,
    falls back to scanning the landing page's HTML for a reference to a spec and
    probing that. Returns None if neither half finds one. Honors `robots.txt`
    allow/deny (a disallowed path is skipped, never fetched, §6) but does not
    apply crawl-delay spacing to the bounded probe set (see the module
    docstring). Never raises: a probe that errors is "not there".
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
    return _discover_spec_in_html(client, target, gate)
