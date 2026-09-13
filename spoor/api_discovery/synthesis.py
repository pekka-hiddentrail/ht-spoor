"""API spec synthesis from a captured HAR — §2b layer 4 (ROADMAP.md §2b).

Layer 4 turns the pile of raw requests a run recorded (the layer-3 HAR capture)
into a readable API spec: it recognizes that `/users/1`, `/users/2`, `/users/3`
are really one endpoint, `/users/{id}`, and writes that out as an OpenAPI
document. Per the §2b layer-4 decision, this is **reimplemented directly over
the HAR** — a bounded piece of URL-clustering — rather than taking a dependency
on `mitmproxy2swagger` and its heavy transitive tree.

It reads only the run's own captured HAR file — no network, so nothing to gate on
robots/politeness here. Nothing is site-specific (§0): entries are kept when the
response is JSON and same-origin with the target, and path templating uses a
fixed, generic ID rule (all-digit segments, UUIDs, long hex). The clustering is
deliberately *conservative*: over-clustering (collapsing two genuinely distinct
paths) misrepresents the surface worse than leaving a borderline segment literal.

Bounded claim (§2b): a synthesized spec is inference from what a run happened to
exercise, reported as *synthesized from observed traffic*, never "the complete
API". Deferred to later slices (see the ROADMAP note): body-schema inference,
query-parameter modelling, cross-host surfaces, YAML output, and accumulation
across runs. Never raises — an unreadable/absent/invalid HAR, or one with no API
entries, yields None ("nothing synthesized"). §2h: the synthesized document is
written to the run's local-only cache (beside the HAR); only counts reach shared
output — a templated path can still embed an un-clustered secret segment, so
promoting paths to shared output is a redaction decision left to a later slice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

# Filename the synthesized OpenAPI document is written under, in the run's
# local-only cache dir (beside the HAR it was synthesized from).
_DOC_NAME = "synthesized_openapi.json"

# A path segment that is really an identifier, to template as `{id}`. Kept
# conservative on purpose (see the module docstring): a pure-digit segment, a
# UUID, or a long (>=24-char, Mongo-ObjectId-shaped) hex string. A shorter
# hex-looking word (`cafe`, `beef`) is left literal rather than risk collapsing a
# real distinct path. Generic convention, no site knowledge (§0).
_UUID_RE = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.IGNORECASE
)
_LONG_HEX_RE = re.compile(r"\A[0-9a-f]{24,}\Z", re.IGNORECASE)


@dataclass(frozen=True)
class SynthesizedEndpoint:
    """One clustered endpoint synthesized from observed traffic (ROADMAP.md §2b).

    `method` is the HTTP method (upper-case); `path` is the templated path
    (`/users/{id}`); `statuses` are the response status codes observed for it,
    sorted and de-duplicated. This records what was *observed*, not a claim of the
    endpoint's complete contract.
    """

    method: str
    path: str
    statuses: tuple[int, ...]


@dataclass(frozen=True)
class SynthesizedSpec:
    """An API spec synthesized from a run's captured HAR (ROADMAP.md §2b layer 4).

    `endpoints` are the clustered endpoints; `request_count` is how many API
    requests were clustered into them (a size signal, and proof of the bounded,
    inference-from-observed-traffic claim); `doc_path` is where the OpenAPI
    document was written in the local-only cache, or None if writing it failed.
    """

    endpoints: tuple[SynthesizedEndpoint, ...]
    request_count: int
    doc_path: str | None

    @property
    def endpoint_count(self) -> int:
        """How many distinct endpoints were synthesized."""
        return len(self.endpoints)


def _looks_like_id(segment: str) -> bool:
    """Whether a path segment is an identifier to template as `{id}` (§0)."""
    return (
        segment.isdigit()
        or bool(_UUID_RE.match(segment))
        or bool(_LONG_HEX_RE.match(segment))
    )


def _template_path(path: str) -> str:
    """Replace ID-like segments of `path` with `{id}`, generically (§0)."""
    return "/".join("{id}" if _looks_like_id(s) else s for s in path.split("/"))


def _is_json_response(response: dict[str, object]) -> bool:
    """Whether a HAR response entry carries a JSON body (the API-entry filter)."""
    content = response.get("content")
    if not isinstance(content, dict):
        return False
    mime = content.get("mimeType")
    return isinstance(mime, str) and "json" in mime.lower()


def _api_request(
    entry: object, origin_netloc: str
) -> tuple[str, str, int | None] | None:
    """A HAR entry as `(method, templated_path, status)`, or None if not an API call.

    Not an API call — skipped, never an error — when the entry is malformed, its
    response is not JSON, or its URL is not same-origin with the target (the
    layer-1 same-origin precedent; cross-host surfaces are deferred).
    """
    if not isinstance(entry, dict):
        return None
    request = entry.get("request")
    response = entry.get("response")
    if not isinstance(request, dict) or not isinstance(response, dict):
        return None
    if not _is_json_response(response):
        return None
    url = request.get("url")
    method = request.get("method")
    if not isinstance(url, str) or not isinstance(method, str):
        return None
    parsed = urlsplit(url)
    if parsed.netloc != origin_netloc:
        return None
    status = response.get("status")
    return (
        method.upper(),
        _template_path(parsed.path),
        status if isinstance(status, int) else None,
    )


def _entries(data: object) -> list[object]:
    """The `log.entries` list of a parsed HAR, or [] if the shape is unexpected."""
    if not isinstance(data, dict):
        return []
    log = data.get("log")
    if not isinstance(log, dict):
        return []
    entries = log.get("entries")
    return entries if isinstance(entries, list) else []


def _cluster(
    entries: list[object], origin_netloc: str
) -> tuple[list[SynthesizedEndpoint], int]:
    """Cluster HAR entries by `(method, templated path)`; return endpoints + count.

    Endpoints are sorted by `(path, method)` so the output is deterministic
    (Spoor's deterministic-by-default stance) regardless of capture order.
    """
    statuses: dict[tuple[str, str], set[int]] = {}
    count = 0
    for entry in entries:
        parsed = _api_request(entry, origin_netloc)
        if parsed is None:
            continue
        method, path, status = parsed
        seen = statuses.setdefault((method, path), set())
        if status is not None:
            seen.add(status)
        count += 1
    endpoints = [
        SynthesizedEndpoint(method=method, path=path, statuses=tuple(sorted(codes)))
        for (method, path), codes in statuses.items()
    ]
    endpoints.sort(key=lambda e: (e.path, e.method))
    return endpoints, count


def _to_openapi(endpoints: list[SynthesizedEndpoint], origin: str) -> dict[str, object]:
    """A minimal OpenAPI 3.0 document for the clustered endpoints.

    Records method + observed response status codes only; body/query schema
    inference is a deferred slice (see the ROADMAP §2b layer-4 note).
    """
    paths: dict[str, dict[str, object]] = {}
    for endpoint in endpoints:
        responses: dict[str, object] = {
            str(status): {"description": ""} for status in endpoint.statuses
        }
        if not responses:
            responses = {"default": {"description": ""}}
        paths.setdefault(endpoint.path, {})[endpoint.method.lower()] = {
            "responses": responses
        }
    return {
        "openapi": "3.0.0",
        "info": {"title": "Synthesized from observed traffic", "version": "0.0.0"},
        "servers": [{"url": origin}],
        "paths": paths,
    }


def synthesize_from_har(har_path: Path, target: str) -> SynthesizedSpec | None:
    """Synthesize an API spec from a captured HAR (§2b layer 4).

    Reads `har_path`, clusters the same-origin JSON requests it recorded into
    templated endpoints, writes an OpenAPI document beside the HAR (local-only,
    §2h), and returns the synthesized spec — or None if the HAR is unreadable /
    invalid or holds no API entries. Reads only the local file: no network,
    nothing to gate. Never raises.
    """
    try:
        data = json.loads(Path(har_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    parts = urlsplit(target)
    endpoints, count = _cluster(_entries(data), parts.netloc)
    if not endpoints:
        return None
    origin = f"{parts.scheme}://{parts.netloc}"
    doc_path: str | None
    try:
        out = Path(har_path).parent / _DOC_NAME
        out.write_text(
            json.dumps(_to_openapi(endpoints, origin), indent=2), encoding="utf-8"
        )
        doc_path = str(out)
    except OSError:
        doc_path = None
    return SynthesizedSpec(
        endpoints=tuple(endpoints), request_count=count, doc_path=doc_path
    )
