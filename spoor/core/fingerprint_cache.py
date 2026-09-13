"""Per-domain fingerprint cache for tier-3 self-healing (ROADMAP.md §2, §0).

Tier 3's mechanic is "fingerprint capture on first success, scored matching on
failure" (§2) — which only spans runs if the fingerprints *persist*. This module
owns that persistence: a per-domain JSON file, keyed by field name, holding the
`ElementFingerprint` each field last resolved to.

This is explicitly the one cache §0 (and CLAUDE.md's hard rule) sanctions as an
exception to "never site-tailored": it is **runtime-learned** — discovered the
same generic way for every target, never a site fact baked into source. Nothing
here contains a hardcoded host; the domain is derived from the run's target at
call time and only ever appears as a dict key / sanitized filename.

It is local-only, sitting under the same git-ignored cache root as the raw
per-run captures (§2h) — a stored fingerprint can embed page text, so it never
reaches shared output. Unlike the per-run capture dirs, this cache is *persistent
across runs* (that is the whole point), so it lives in its own subdirectory
rather than a run-stamped one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from spoor.core.healing import ElementFingerprint
from spoor.security import storage

# Subdirectory of the cache root holding the persistent per-domain caches. Read
# through `storage.CACHE_ROOT` at call time so a test's monkeypatch takes effect.
FINGERPRINT_DIRNAME = "fingerprints"

# Anything outside this set is replaced in a netloc before it becomes a filename,
# so "localhost:8000" -> "localhost_8000.json" (a colon is invalid on Windows).
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _fingerprint_to_dict(fp: ElementFingerprint) -> dict[str, object]:
    """A JSON-serializable view of a fingerprint (frozensets/tuples -> lists)."""
    return {
        "tag": fp.tag,
        "element_id": fp.element_id,
        "classes": sorted(fp.classes),
        "attrs": sorted([k, v] for k, v in fp.attrs),
        "text": fp.text,
        "ancestors": list(fp.ancestors),
        "sibling_index": fp.sibling_index,
    }


def _fingerprint_from_dict(data: dict[str, object]) -> ElementFingerprint:
    """Rebuild a fingerprint from its JSON view; raises on a malformed entry.

    The list-shaped fields are type-checked here so a hand-edited or truncated
    cache entry raises (caught by the loader and skipped) rather than crashing.
    """
    classes = data["classes"]
    attrs = data["attrs"]
    ancestors = data["ancestors"]
    if not (
        isinstance(classes, list)
        and isinstance(attrs, list)
        and isinstance(ancestors, list)
    ):
        raise TypeError("malformed fingerprint entry: expected list fields")
    return ElementFingerprint(
        tag=str(data["tag"]),
        element_id=str(data["element_id"]),
        classes=frozenset(str(c) for c in classes),
        attrs=frozenset((str(pair[0]), str(pair[1])) for pair in attrs),
        text=str(data["text"]),
        ancestors=tuple(str(a) for a in ancestors),
        sibling_index=int(str(data["sibling_index"])),
    )


def cache_path_for_target(target: str) -> Path:
    """The persistent cache file for `target`'s domain, under the cache root.

    Reads `storage.CACHE_ROOT` at call time (not import) so a monkeypatch in a
    test redirects it. The domain is the URL's netloc; a target with none falls
    back to a fixed name so the cache still works for an odd input.
    """
    netloc = urlsplit(target).netloc or "_nohost"
    safe = _UNSAFE_FILENAME_CHARS.sub("_", netloc)
    return storage.CACHE_ROOT / FINGERPRINT_DIRNAME / f"{safe}.json"


class FingerprintCache:
    """A field-name -> fingerprint map persisted to one per-domain JSON file.

    Loaded on construction (a missing or unreadable file yields an empty cache —
    a first run for a domain, never an error). `put` records a fingerprint;
    `save` writes the file only when something changed, and only creating the
    directory when there is something to write.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._store: dict[str, ElementFingerprint] = {}
        # Snapshot of what was loaded from disk — i.e. what *prior* runs recorded,
        # frozen for this run. `get_persisted` reads it so a fingerprint remembered
        # earlier in the *current* run is never healed against (see `get_persisted`).
        self._persisted: dict[str, ElementFingerprint] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # no cache yet, or a corrupt one — start clean, never raise
        if not isinstance(raw, dict):
            return
        for field_name, entry in raw.items():
            if isinstance(entry, dict):
                try:
                    self._store[field_name] = _fingerprint_from_dict(entry)
                except (KeyError, TypeError, ValueError):
                    continue  # skip a malformed entry rather than fail the run
        # Freeze the prior-run view once loading is done.
        self._persisted = dict(self._store)

    def get(self, field_name: str) -> ElementFingerprint | None:
        """The fingerprint currently remembered for `field_name` (incl. this run)."""
        return self._store.get(field_name)

    def get_persisted(self, field_name: str) -> ElementFingerprint | None:
        """The fingerprint a *prior* run recorded for `field_name`, or None.

        Reads the load-time snapshot, so a fingerprint `put` during the current run
        is deliberately not visible here. Healing uses this (not `get`) so that,
        in a listing, a field present in one row is never used to "heal" a sibling
        row that legitimately lacks it — a fabricated value would break the
        reliability-first contract (§2, §1).
        """
        return self._persisted.get(field_name)

    def put(self, field_name: str, fingerprint: ElementFingerprint) -> None:
        """Remember `fingerprint` for `field_name` (a no-op if unchanged)."""
        if self._store.get(field_name) == fingerprint:
            return
        self._store[field_name] = fingerprint
        self._dirty = True

    def save(self) -> None:
        """Persist the cache to its file if it changed; never raises on I/O."""
        if not self._dirty:
            return
        doc = {
            field_name: _fingerprint_to_dict(fp)
            for field_name, fp in self._store.items()
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            self._dirty = False
        except OSError:
            return


def cache_for_target(target: str) -> FingerprintCache:
    """The persistent fingerprint cache for `target`'s domain (§2, §0)."""
    return FingerprintCache(cache_path_for_target(target))
