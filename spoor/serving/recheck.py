"""Caller-forced recheck of a mapped URL (ROADMAP.md §2f).

The serving layer is read-only with respect to the target, but the §2f
non-negotiable explicitly permits triggering a *new read/observation* run. This
module is that seam: given a URL already in the map, re-run the exact same
extraction it was produced from, refresh the local map with the fresh result, and
return the new entry. It is a read of the target (the same read a normal run
performs), never a state-changing action on it.

v1 never *auto*-rechecks (§9 backlog); this only ever runs when a caller asks —
the ``--recheck`` opt-in on ``spoor serve`` / ``serve-mcp`` wires it into the API
and MCP surfaces. A URL that was never mapped, or one mapped before configs were
persisted, returns None so the surface reports "not mapped" rather than guessing.
"""

from __future__ import annotations

from spoor.core import extract
from spoor.core.config import ExtractionConfig
from spoor.serving.store import MapEntry, MapStore, shareable_api_surface


def recheck_url(store: MapStore, url: str) -> MapEntry | None:
    """Re-run a mapped URL's extraction and refresh the local map.

    Returns the fresh entry, or None if `url` was never mapped (or was recorded
    without the config needed to reproduce the run — nothing to re-run).
    """
    entry = store.get(url)
    if entry is None or entry.config is None:
        return None
    config = ExtractionConfig.model_validate(entry.config)
    result = extract.run_report(config)
    surface = shareable_api_surface(
        api_spec=result.api_spec,
        graphql=result.graphql,
        synthesized_spec=result.synthesized_spec,
        action_correlation=result.action_correlation,
    )
    return store.record(
        url,
        result.records,
        tier=result.tier,
        api_surface=surface,
        config=entry.config,
    )
