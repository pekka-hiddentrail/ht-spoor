"""Change detection: skip re-extracting unchanged pages (ROADMAP.md §2d, §0).

Monitoring-style use re-runs the same config on a schedule (§2d): re-scraping a
page that hasn't changed is wasted work and wasted politeness budget. This module
remembers, per URL, the validators the last successful fetch carried — an `ETag`,
a `Last-Modified`, and a content hash — so the next run can ask the server "only
send this if it changed" (a conditional `If-None-Match` / `If-Modified-Since`
request) and, when the server sends no validators, fall back to comparing a hash
of the body it did send. A "304 Not Modified" or a matching hash means unchanged,
so the caller skips extraction rather than producing the same records again.

Like the tier-3 fingerprint cache, this store is the §0-sanctioned "runtime-
learned" exception to *never site-tailored*: it is discovered the same generic
way for every target, never a site fact baked into source — nothing here holds a
hardcoded host, and a URL only ever appears as a dict key at runtime. It is
local-only (§2h), sitting under the same git-ignored cache root as the raw
per-run captures and the fingerprint cache, and persists across runs (that is the
whole point), so it lives in its own subdirectory rather than a run-stamped one.

Scope is the sequential tier-1 httpx fetch path; browser-tier change detection is
a follow-on (see the ROADMAP §2d decision note).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from spoor.security import storage

# Subdirectory of the cache root holding the persistent per-domain validator
# stores. Read through `storage.CACHE_ROOT` at call time so a test's monkeypatch
# takes effect (same pattern as the fingerprint cache).
CHANGE_DIRNAME = "change_detection"

# Anything outside this set is replaced in a netloc before it becomes a filename,
# so "localhost:8000" -> "localhost_8000.json" (a colon is invalid on Windows).
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _hash_body(text: str) -> str:
    """A stable content hash of a response body, for the no-validators fallback."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PageValidators:
    """What a prior successful fetch of one URL carried, to detect a change.

    `etag` and `last_modified` are the server's own validator headers, replayed
    verbatim on the next request (`If-None-Match` / `If-Modified-Since`) so the
    server can answer 304 if nothing changed. `content_hash` is a hash of the body
    that fetch returned — the fallback comparison when a server sends no validators
    at all, so change detection still works against a plain static host. All three
    are generic HTTP facts, never site-specific (§0) or a captured secret (§2h).
    """

    etag: str | None
    last_modified: str | None
    content_hash: str


class ChangeDetector:
    """Per-domain, persistent record of page validators for change detection.

    Loaded on construction (a missing or corrupt file yields an empty store — a
    first run for the domain, never an error). `conditional_headers` supplies the
    validators for a request; `is_unchanged` judges a response against what was
    remembered; `record` remembers a freshly-extracted page for next time; `save`
    writes the file only when something changed.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._store: dict[str, PageValidators] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # no store yet, or a corrupt one — start clean, never raise
        if not isinstance(raw, dict):
            return
        for url, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            content_hash = entry.get("content_hash")
            if not isinstance(content_hash, str):
                continue  # skip a malformed entry rather than fail the run
            etag = entry.get("etag")
            last_modified = entry.get("last_modified")
            self._store[url] = PageValidators(
                etag=etag if isinstance(etag, str) else None,
                last_modified=(
                    last_modified if isinstance(last_modified, str) else None
                ),
                content_hash=content_hash,
            )

    def conditional_headers(self, url: str) -> dict[str, str]:
        """Validator headers to attach to `url`'s request, or empty on a first run.

        Replays the remembered `ETag` / `Last-Modified` as `If-None-Match` /
        `If-Modified-Since` so the server can answer 304. Empty when nothing was
        remembered (a first run) or when the prior fetch carried no validators —
        in which case detection falls back to the content hash in `is_unchanged`.
        """
        prior = self._store.get(url)
        if prior is None:
            return {}
        headers: dict[str, str] = {}
        if prior.etag is not None:
            headers["If-None-Match"] = prior.etag
        if prior.last_modified is not None:
            headers["If-Modified-Since"] = prior.last_modified
        return headers

    def is_unchanged(self, url: str, response: httpx.Response) -> bool:
        """Whether `response` shows `url` is unchanged since the last recorded run.

        A 304 is the definitive "not modified". Otherwise, if a prior run recorded
        this URL, its body hash is compared — so a server that ignores conditional
        headers (or never sends validators) is still handled. A URL never seen
        before is always "changed" (there is nothing to compare), so a first run
        always extracts.
        """
        if response.status_code == httpx.codes.NOT_MODIFIED:
            return True
        prior = self._store.get(url)
        if prior is None:
            return False
        return prior.content_hash == _hash_body(response.text)

    def record(self, url: str, response: httpx.Response) -> None:
        """Remember `response`'s validators + body hash for `url`, for next time.

        Called only for a page that was actually fetched with a body and extracted
        (not for an unchanged 304, which carries no fresh body). A no-op when the
        recorded validators and hash are identical to what is already stored.
        """
        entry = PageValidators(
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            content_hash=_hash_body(response.text),
        )
        if self._store.get(url) == entry:
            return
        self._store[url] = entry
        self._dirty = True

    def save(self) -> None:
        """Persist the store to its file if it changed; never raises on I/O."""
        if not self._dirty:
            return
        doc = {
            url: {
                "etag": v.etag,
                "last_modified": v.last_modified,
                "content_hash": v.content_hash,
            }
            for url, v in self._store.items()
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            self._dirty = False
        except OSError:
            return


def store_path_for_target(target: str) -> Path:
    """The persistent validator-store file for `target`'s domain, under the cache.

    Reads `storage.CACHE_ROOT` at call time (not import) so a test monkeypatch
    redirects it. The domain is the URL's netloc; a target with none falls back to
    a fixed name so the store still works for an odd input.
    """
    netloc = urlsplit(target).netloc or "_nohost"
    safe = _UNSAFE_FILENAME_CHARS.sub("_", netloc)
    return storage.CACHE_ROOT / CHANGE_DIRNAME / f"{safe}.json"


def detector_for_target(target: str) -> ChangeDetector:
    """The persistent change-detection store for `target`'s domain (§2d, §0)."""
    return ChangeDetector(store_path_for_target(target))
