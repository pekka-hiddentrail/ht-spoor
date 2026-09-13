"""Persisted per-domain map that the read-only serving layer answers from (§2f).

The serving layer (`spoor/serving/api.py`) is a *thin* read-over of what a run
already produced — it holds no capture or analysis logic of its own (§2f). This
module is that data: a run records its extracted records for a URL here, keyed by
domain, with the capture time; the API reads it back and attaches a freshness age
(§2f "always show the age, never auto-recheck" in v1).

Placement (§0/§2h): the map holds the same extracted records the output pipeline
already writes to shared output — not a raw local-only capture (HAR/storage
state), which never enters here. It persists under the git-ignored cache root
(`maps/<domain>.json`), the local-first home the rest of the stack uses; a
missing or corrupt file is simply "nothing mapped yet", never an error.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from spoor.security import storage

# Subdirectory of the cache root holding one JSON file per mapped domain.
MAPS_DIRNAME = "maps"

# Characters not safe in a cross-platform filename (Windows forbids ':' etc.);
# the real domain is preserved inside the file, so this is only for the path.
_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class MapEntry:
    """One mapped URL: its extracted records, resolving tier, and capture time."""

    url: str
    domain: str
    records: list[dict[str, object]]
    tier: int | None
    captured_at: str  # ISO-8601 UTC, e.g. "2026-09-13T12:00:00+00:00"


def _domain_of(url: str) -> str:
    """The network location (host[:port]) a URL maps under."""
    return urlsplit(url).netloc


class MapStore:
    """Read/write access to the persisted map, one JSON file per domain.

    The cache root is read from `spoor.security.storage.CACHE_ROOT` at call time
    (not import), so a test's monkeypatch of it — or a future configurable base —
    takes effect without reconstructing the store.
    """

    @property
    def _root(self) -> Path:
        return storage.CACHE_ROOT / MAPS_DIRNAME

    def _path_for_domain(self, domain: str) -> Path:
        safe = _UNSAFE_IN_FILENAME.sub("_", domain) or "_"
        return self._root / f"{safe}.json"

    def _load_domain(self, domain: str) -> dict[str, dict[str, object]]:
        path = self._path_for_domain(domain)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            # No file yet, or a corrupt one: nothing mapped for this domain.
            return {}
        return data if isinstance(data, dict) else {}

    def record(
        self,
        url: str,
        records: list[dict[str, object]],
        *,
        tier: int | None = None,
        captured_at: datetime | None = None,
    ) -> MapEntry:
        """Remember a run's result for `url` so the API can serve it later.

        Overwrites any prior entry for the same URL — the map holds the latest
        known-good result, and its capture time is what freshness is measured
        against. Defaults the capture time to now (UTC).
        """
        domain = _domain_of(url)
        stamp = (captured_at or datetime.now(UTC)).isoformat()
        entry = MapEntry(
            url=url, domain=domain, records=records, tier=tier, captured_at=stamp
        )
        by_url = self._load_domain(domain)
        by_url[url] = {
            "url": entry.url,
            "domain": entry.domain,
            "records": entry.records,
            "tier": entry.tier,
            "captured_at": entry.captured_at,
        }
        path = self._path_for_domain(domain)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(by_url, indent=2), encoding="utf-8")
        return entry

    def get(self, url: str) -> MapEntry | None:
        """The mapped entry for `url`, or None if it has never been mapped."""
        raw = self._load_domain(_domain_of(url)).get(url)
        if not isinstance(raw, dict):
            return None
        records_raw = raw.get("records")
        records = (
            cast("list[dict[str, object]]", records_raw)
            if isinstance(records_raw, list)
            else []
        )
        tier_raw = raw.get("tier")
        return MapEntry(
            url=str(raw["url"]),
            domain=str(raw["domain"]),
            records=records,
            tier=tier_raw if isinstance(tier_raw, int) else None,
            captured_at=str(raw["captured_at"]),
        )

    def domains(self) -> list[str]:
        """Every domain with at least one mapped URL, sorted."""
        root = self._root
        if not root.is_dir():
            return []
        seen: set[str] = set()
        for path in root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                seen.update(
                    str(entry["domain"])
                    for entry in data.values()
                    if isinstance(entry, dict) and "domain" in entry
                )
        return sorted(seen)
