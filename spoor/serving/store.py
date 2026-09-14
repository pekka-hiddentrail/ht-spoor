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

from spoor.api_discovery.correlation import ActionCorrelation
from spoor.api_discovery.discovery import DiscoveredSpec
from spoor.api_discovery.graphql import DiscoveredGraphQL
from spoor.api_discovery.synthesis import SynthesizedSpec
from spoor.security import storage

# Subdirectory of the cache root holding one JSON file per mapped domain.
MAPS_DIRNAME = "maps"


def shareable_api_surface(
    *,
    api_spec: DiscoveredSpec | None,
    graphql: DiscoveredGraphQL | None,
    synthesized_spec: SynthesizedSpec | None,
    action_correlation: ActionCorrelation | None,
) -> dict[str, object] | None:
    """Project a run's observed API surface to the §2h-shareable facts only.

    Mirrors the observability layer's §2h split. The published spec and GraphQL
    endpoint are non-sensitive and kept whole (kind/version/url, url/types), but
    the *synthesized* spec and action correlation are reduced to **counts only** —
    their templated paths (and the local-only ``doc_path``) can embed an
    un-clustered secret segment, so they never enter this shared surface at all.
    Returns None when nothing was observed, so a URL with no API surface stores
    nothing rather than an empty shell.
    """
    surface: dict[str, object] = {}
    if api_spec is not None:
        surface["spec"] = {
            "kind": api_spec.kind,
            "version": api_spec.version,
            "url": api_spec.url,
        }
    if graphql is not None:
        surface["graphql"] = {"url": graphql.url, "types": graphql.types}
    if synthesized_spec is not None:
        # Counts only — the templated endpoint paths and doc_path stay local (§2h).
        surface["synthesized"] = {
            "endpoint_count": synthesized_spec.endpoint_count,
            "request_count": synthesized_spec.request_count,
        }
    if action_correlation is not None:
        # Counts only — the per-action templated endpoints stay local (§2h).
        surface["correlation"] = {
            "action_count": action_correlation.action_count,
            "request_count": action_correlation.request_count,
        }
    return surface or None

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
    # The §2h-shareable projection of the run's observed API surface (spec whole,
    # synthesized/correlation as counts only), or None if nothing was observed.
    api_surface: dict[str, object] | None = None
    # The serialized ExtractionConfig this entry was produced from, kept so a
    # caller-forced recheck can re-run the exact same extraction (§2f). LOCAL-ONLY:
    # it is never projected into `map_view`, so it never reaches a served surface.
    config: dict[str, object] | None = None


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
        api_surface: dict[str, object] | None = None,
        config: dict[str, object] | None = None,
    ) -> MapEntry:
        """Remember a run's result for `url` so the API can serve it later.

        Overwrites any prior entry for the same URL — the map holds the latest
        known-good result, and its capture time is what freshness is measured
        against. Defaults the capture time to now (UTC). `api_surface` is the
        already-§2h-projected surface (see `shareable_api_surface`), or None.
        `config` is the serialized ExtractionConfig the result came from, kept
        local-only so a forced recheck can re-run the same extraction (§2f).
        """
        domain = _domain_of(url)
        stamp = (captured_at or datetime.now(UTC)).isoformat()
        entry = MapEntry(
            url=url,
            domain=domain,
            records=records,
            tier=tier,
            captured_at=stamp,
            api_surface=api_surface,
            config=config,
        )
        by_url = self._load_domain(domain)
        by_url[url] = {
            "url": entry.url,
            "domain": entry.domain,
            "records": entry.records,
            "tier": entry.tier,
            "captured_at": entry.captured_at,
            "api_surface": entry.api_surface,
            "config": entry.config,
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
        surface_raw = raw.get("api_surface")
        config_raw = raw.get("config")
        return MapEntry(
            url=str(raw["url"]),
            domain=str(raw["domain"]),
            records=records,
            tier=tier_raw if isinstance(tier_raw, int) else None,
            captured_at=str(raw["captured_at"]),
            api_surface=(
                cast("dict[str, object]", surface_raw)
                if isinstance(surface_raw, dict)
                else None
            ),
            config=(
                cast("dict[str, object]", config_raw)
                if isinstance(config_raw, dict)
                else None
            ),
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
