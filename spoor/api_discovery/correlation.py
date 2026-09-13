"""Action-to-endpoint correlation — §2b layer 5 (ROADMAP.md §2b).

The one genuinely custom layer: none of the discovery layers tell you *which UI
action triggered which API call*. This does, with a lightweight checkpoint log —
before each simulated action (page load, each scroll) the browser tier marks a
timestamp; afterward, each request the HAR recorded is attributed to the action
whose time window it fell in. Over many runs this turns a flat list of endpoints
into "here's what this endpoint is *for*".

**Approximation, not proof (§2b).** A time window catches whatever fired in it —
background polling, prefetch, analytics beacons that happen to land in the same
window are attributed to the action too. Read any single correlation as "likely
caused by", never exact causal certainty; the output says so. Nothing is
site-specific (§0): it reuses the layer-3/4 HAR-reading primitives (same-origin
JSON filter, generic ID templating) and attributes purely by timestamp. Reads
only the local HAR + the run's own checkpoints — no network. Never raises: an
unreadable HAR, no checkpoints, or nothing attributable yields None. §2h: the
full correlation (with paths) is written to the run's local-only cache; only
counts reach shared output, since a templated path can embed an un-clustered
secret (same reasoning as layer 4).
"""

from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

# Reuse the layer-3/4 HAR-reading primitives so the same-origin + JSON filter and
# the generic ID-templating stay identical across synthesis and correlation (§0).
from spoor.api_discovery.synthesis import (
    _entries,
    _is_json_response,
    _template_path,
)

# Filename the correlation is written under, in the run's local-only cache dir
# (beside the HAR it was correlated from).
_DOC_NAME = "action_correlation.json"

# Stated on the local-only document so a reader never mistakes a time-window
# attribution for proven causation (§2b's bounded claim for layer 5).
_APPROX_NOTE = (
    "Time-window attribution: each endpoint is *likely* triggered by its action, "
    "not proven. Background polling, prefetch, and analytics that fired in the "
    "same window are attributed too."
)


@dataclass(frozen=True)
class Checkpoint:
    """A timestamped mark for a simulated action (ROADMAP.md §2b layer 5).

    `label` names the action ("load", "scroll #1"); `at` is when it was started,
    a timezone-aware UTC instant so it is comparable to a HAR's `startedDateTime`.
    """

    label: str
    at: datetime


class CheckpointRecorder:
    """Records action checkpoints during a run, in the order they happened.

    The browser tier marks one before navigating and one before each scroll; the
    marks are attributed to captured requests after the run (see `correlate`). A
    plain in-memory list — the raw HAR it correlates against is the local-only
    artifact, this just timestamps the actions that produced it.
    """

    def __init__(self) -> None:
        self._marks: list[Checkpoint] = []

    def mark(self, label: str) -> None:
        """Record `label` as happening now (UTC)."""
        self._marks.append(Checkpoint(label=label, at=datetime.now(UTC)))

    @property
    def checkpoints(self) -> list[Checkpoint]:
        """The marks recorded so far, in call order."""
        return list(self._marks)


@dataclass(frozen=True)
class CorrelatedAction:
    """One action and the endpoints attributed to its time window (§2b layer 5).

    `endpoints` are `"METHOD /templated/path"` strings, sorted and de-duplicated —
    "likely triggered by this action", never proven (see the module docstring).
    """

    label: str
    endpoints: tuple[str, ...]


@dataclass(frozen=True)
class ActionCorrelation:
    """Requests attributed to the actions that likely triggered them (§2b layer 5).

    `actions` are the actions that got at least one endpoint (empty ones are
    omitted); `request_count` is how many requests were attributed; `doc_path` is
    where the full correlation was written in the local-only cache, or None if
    writing failed.
    """

    actions: tuple[CorrelatedAction, ...]
    request_count: int
    doc_path: str | None

    @property
    def action_count(self) -> int:
        """How many actions had at least one endpoint attributed."""
        return len(self.actions)


def _parse_time(value: str) -> datetime | None:
    """Parse a HAR `startedDateTime` into a tz-aware UTC datetime, or None."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _attributable(
    entry: object, origin_netloc: str
) -> tuple[str, str, datetime] | None:
    """A HAR entry as `(method, templated_path, started_at)`, or None if not one.

    Same same-origin + JSON filter as layer 4, plus a parseable `startedDateTime`
    (correlation needs *when* the request fired). Anything else is skipped, never
    an error.
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
    started = entry.get("startedDateTime")
    if (
        not isinstance(url, str)
        or not isinstance(method, str)
        or not isinstance(started, str)
    ):
        return None
    parsed = urlsplit(url)
    if parsed.netloc != origin_netloc:
        return None
    at = _parse_time(started)
    if at is None:
        return None
    return method.upper(), _template_path(parsed.path), at


def _write_doc(actions: tuple[CorrelatedAction, ...], har_path: Path) -> str | None:
    """Write the full correlation to the local-only cache; return its path or None."""
    doc = {
        "note": _APPROX_NOTE,
        "actions": [
            {"label": action.label, "endpoints": list(action.endpoints)}
            for action in actions
        ],
    }
    try:
        out = Path(har_path).parent / _DOC_NAME
        out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return str(out)
    except OSError:
        return None


def correlate(
    checkpoints: list[Checkpoint], har_path: Path, target: str
) -> ActionCorrelation | None:
    """Attribute a captured HAR's requests to the actions that likely fired them.

    Reads `har_path`, and for each same-origin JSON request attributes it to the
    last checkpoint at or before its `startedDateTime`. Returns the actions that
    got at least one endpoint — or None if there are no checkpoints, the HAR is
    unreadable, or nothing was attributable. Reads only local state, never raises.
    """
    if not checkpoints:
        return None
    try:
        data = json.loads(Path(har_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    origin_netloc = urlsplit(target).netloc
    ordered = sorted(checkpoints, key=lambda c: c.at)
    times = [c.at for c in ordered]
    buckets: list[set[str]] = [set() for _ in ordered]
    count = 0
    for entry in _entries(data):
        parsed = _attributable(entry, origin_netloc)
        if parsed is None:
            continue
        method, path, at = parsed
        # Last checkpoint at or before the request; skip requests that predate
        # every checkpoint (nothing recorded can have caused them).
        index = bisect_right(times, at) - 1
        if index < 0:
            continue
        buckets[index].add(f"{method} {path}")
        count += 1
    actions = tuple(
        CorrelatedAction(label=checkpoint.label, endpoints=tuple(sorted(endpoints)))
        for checkpoint, endpoints in zip(ordered, buckets, strict=True)
        if endpoints
    )
    if not actions:
        return None
    return ActionCorrelation(
        actions=actions, request_count=count, doc_path=_write_doc(actions, har_path)
    )
