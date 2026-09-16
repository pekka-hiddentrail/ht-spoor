"""Resume an exploration from a mapped anchor state (ROADMAP.md §2e resume).

The traversal slice that ties the three pure resume slices to the crawl. Given the
§2h-shareable projection of an earlier run's map and a selector naming where to pick
up, this: loads the map back into a graph (`persisted_map.load_exploration_map`),
turns its states into anchor candidates (`selector.graph_candidates`), resolves the
selector to exactly one of them (`selector.resolve_anchor`), and hands that anchor to
the explorer to continue the breadth-first walk outward from it, merging the new
states and transitions into the loaded map (`explorer.explore`'s resume mode).

Resolution never guesses (the same stance the selector and serving layers take):
a selector matching no saved state, or several, raises `ResumeError` rather than
picking one — the several case lists the ambiguous candidates so the caller can
narrow. The explorer refuses a stale map (a changed start page, an unreachable
anchor) with its own `ValueError`, which propagates unchanged. Nothing here is
site-specific (§0): one resume path continues the walk for every target.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

from spoor.exploration.control import RunController
from spoor.exploration.explorer import (
    BrowserDriver,
    ElementShot,
    explore,
)
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.persisted_map import load_exploration_map
from spoor.exploration.screenshot_store import ImageRef
from spoor.exploration.selector import (
    AnchorCandidate,
    graph_candidates,
    parse_selector,
    resolve_anchor,
)


class ResumeError(ValueError):
    """A resume could not begin: its selector matched no saved state, or several."""


def _describe_candidate(candidate: AnchorCandidate) -> str:
    """A one-line, secret-safe label for an ambiguous candidate (id + short path)."""
    if candidate.path:
        trail = " -> ".join(f"{role}:{name}" for role, name in candidate.path)
        return f"{candidate.state_id} (via {trail})"
    return f"{candidate.state_id} (the start page)"


def resolve_resume_anchor(saved_map: Mapping[str, Any], selector: str) -> str:
    """Resolve `selector` against a saved map to exactly one anchor state id (§2e).

    Loads the map, builds candidates, and resolves — raising `ResumeError` when the
    selector matches no state or several (the several case names the candidates). The
    resolution-only half of `resume_exploration`, split out so a caller can report the
    anchor before committing a browser to the crawl.
    """
    loaded = load_exploration_map(saved_map)
    candidates = graph_candidates(loaded)
    resolution = resolve_anchor([parse_selector(selector)], candidates)
    if resolution.is_unmatched:
        raise ResumeError(
            f"selector {selector!r} matched no state in the saved map — nothing to "
            "resume from (a saved map anchors by id or path; a title does not resolve "
            "against it, as titles are not stored)."
        )
    if resolution.is_ambiguous:
        listed = "\n  ".join(_describe_candidate(c) for c in resolution.matches)
        raise ResumeError(
            f"selector {selector!r} matched {len(resolution.matches)} states; narrow "
            f"it to one of:\n  {listed}"
        )
    return resolution.state_id


def resume_exploration(
    driver: BrowserDriver,
    *,
    target: str,
    controller: RunController,
    saved_map: Mapping[str, Any],
    selector: str,
    declared_sandbox: bool = False,
    screenshots: MutableMapping[str, ImageRef] | None = None,
    element_screenshots: MutableMapping[str, list[ElementShot]] | None = None,
    screenshot_dir: Path | None = None,
) -> ExplorationGraph:
    """Resume exploration of `target` from the anchor `selector` names in `saved_map`.

    Loads `saved_map`, resolves `selector` to one anchor state (`ResumeError` if none
    or several), and continues the walk outward from it via the explorer's resume mode,
    returning the loaded graph with the newly discovered states and transitions merged
    in. The depth budget on `controller` counts clicks from the anchor. The explorer
    refuses a stale map (a changed start page or an unreachable anchor) with a
    `ValueError` that propagates unchanged. The screenshot sinks behave exactly as in
    `explore`.
    """
    loaded = load_exploration_map(saved_map)
    anchor = resolve_resume_anchor(saved_map, selector)
    return explore(
        driver,
        target=target,
        controller=controller,
        declared_sandbox=declared_sandbox,
        screenshots=screenshots,
        element_screenshots=element_screenshots,
        screenshot_dir=screenshot_dir,
        resume_from=loaded,
        resume_anchor=anchor,
    )
