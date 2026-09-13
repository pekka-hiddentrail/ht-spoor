"""Unit tests for action-to-endpoint correlation (ROADMAP.md §2b layer 5).

Below api_discovery.feature: the scenarios prove correlation end to end (synthetic
checkpoints + a captured HAR attributed into per-action endpoints, the doc written,
counts surfaced); these pin the pure pieces — the checkpoint recorder, the HAR
time parsing, and `correlate`'s edges (no checkpoints, unreadable / invalid HAR,
window boundaries, cross-origin exclusion, non-JSON, determinism) — without a run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from spoor.api_discovery.correlation import (
    Checkpoint,
    CheckpointRecorder,
    _parse_time,
    correlate,
)

_TARGET = "http://localhost:8000/index.html"
_ORIGIN = "http://localhost:8000"
_BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


# --- CheckpointRecorder --------------------------------------------------


def test_recorder_starts_empty() -> None:
    assert CheckpointRecorder().checkpoints == []


def test_recorder_records_in_order() -> None:
    recorder = CheckpointRecorder()
    recorder.mark("load")
    recorder.mark("scroll #1")
    labels = [c.label for c in recorder.checkpoints]
    assert labels == ["load", "scroll #1"]


def test_recorder_marks_are_timezone_aware() -> None:
    recorder = CheckpointRecorder()
    recorder.mark("load")
    assert recorder.checkpoints[0].at.tzinfo is not None


def test_recorder_checkpoints_is_a_copy() -> None:
    recorder = CheckpointRecorder()
    recorder.mark("load")
    snapshot = recorder.checkpoints
    recorder.mark("scroll #1")
    # A caller holding an earlier snapshot must not see later marks.
    assert len(snapshot) == 1


# --- _parse_time ---------------------------------------------------------


def test_parse_time_handles_zulu() -> None:
    parsed = _parse_time("2026-01-01T12:00:00Z")
    assert parsed == _BASE


def test_parse_time_handles_offset() -> None:
    # A +02:00 wall time is the same instant as 10:00 UTC.
    parsed = _parse_time("2026-01-01T12:00:00+02:00")
    assert parsed == datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def test_parse_time_assumes_utc_when_naive() -> None:
    parsed = _parse_time("2026-01-01T12:00:00")
    assert parsed == _BASE


def test_parse_time_rejects_garbage() -> None:
    assert _parse_time("not a time") is None


# --- correlate: fixtures + edges -----------------------------------------


def _entry_at(
    method: str, url: str, second: int, mime: str = "application/json"
) -> dict[str, object]:
    return {
        "request": {"method": method, "url": url},
        "response": {"status": 200, "content": {"mimeType": mime}},
        "startedDateTime": (_BASE + timedelta(seconds=second)).isoformat(),
    }


def _write_har(path: Path, entries: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"log": {"version": "1.2", "entries": entries}}), encoding="utf-8"
    )
    return path


def _cp(label: str, second: int) -> Checkpoint:
    return Checkpoint(label=label, at=_BASE + timedelta(seconds=second))


def test_no_checkpoints_yields_none(tmp_path: Path) -> None:
    har = _write_har(tmp_path / "h.har", [_entry_at("GET", _ORIGIN + "/api/me", 1)])
    assert correlate([], har, _TARGET) is None


def test_missing_har_yields_none(tmp_path: Path) -> None:
    assert correlate([_cp("load", 0)], tmp_path / "nope.har", _TARGET) is None


def test_invalid_json_yields_none(tmp_path: Path) -> None:
    path = tmp_path / "bad.har"
    path.write_text("{not json", encoding="utf-8")
    assert correlate([_cp("load", 0)], path, _TARGET) is None


def test_request_attributed_to_enclosing_window(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "h.har",
        [
            _entry_at("GET", _ORIGIN + "/api/feed", 2),
            _entry_at("GET", _ORIGIN + "/api/more", 12),
        ],
    )
    corr = correlate([_cp("load", 0), _cp("scroll #1", 10)], har, _TARGET)
    assert corr is not None
    by_label = {a.label: a.endpoints for a in corr.actions}
    assert by_label["load"] == ("GET /api/feed",)
    assert by_label["scroll #1"] == ("GET /api/more",)
    assert corr.request_count == 2
    assert corr.action_count == 2


def test_request_at_exact_checkpoint_time_belongs_to_that_action(
    tmp_path: Path,
) -> None:
    # A request whose timestamp equals a checkpoint's is attributed to it (the
    # "at or before" boundary is inclusive), not to the previous window.
    har = _write_har(tmp_path / "h.har", [_entry_at("GET", _ORIGIN + "/api/x", 10)])
    corr = correlate([_cp("load", 0), _cp("scroll #1", 10)], har, _TARGET)
    assert corr is not None
    by_label = {a.label: a.endpoints for a in corr.actions}
    assert "load" not in by_label
    assert by_label["scroll #1"] == ("GET /api/x",)


def test_request_before_every_checkpoint_is_dropped(tmp_path: Path) -> None:
    har = _write_har(tmp_path / "h.har", [_entry_at("GET", _ORIGIN + "/api/x", 1)])
    assert correlate([_cp("load", 5)], har, _TARGET) is None


def test_id_paths_are_templated(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "h.har",
        [
            _entry_at("GET", _ORIGIN + "/api/users/1", 1),
            _entry_at("GET", _ORIGIN + "/api/users/2", 2),
        ],
    )
    corr = correlate([_cp("load", 0)], har, _TARGET)
    assert corr is not None
    assert corr.actions[0].endpoints == ("GET /api/users/{id}",)
    assert corr.request_count == 2
    assert corr.action_count == 1


def test_cross_origin_request_is_excluded(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "h.har",
        [
            _entry_at("GET", _ORIGIN + "/api/me", 1),
            _entry_at("GET", "http://cdn.example.com/api/track", 2),
        ],
    )
    corr = correlate([_cp("load", 0)], har, _TARGET)
    assert corr is not None
    assert corr.request_count == 1
    assert corr.actions[0].endpoints == ("GET /api/me",)


def test_non_json_request_is_excluded(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "h.har",
        [_entry_at("GET", _ORIGIN + "/page", 1, mime="text/html")],
    )
    assert correlate([_cp("load", 0)], har, _TARGET) is None


def test_entry_without_started_time_is_excluded(tmp_path: Path) -> None:
    entry = _entry_at("GET", _ORIGIN + "/api/me", 1)
    del entry["startedDateTime"]
    har = _write_har(tmp_path / "h.har", [entry])
    assert correlate([_cp("load", 0)], har, _TARGET) is None


def test_endpoints_are_sorted_and_deduplicated(tmp_path: Path) -> None:
    # Same endpoint hit twice collapses; two distinct ones come out sorted.
    har = _write_har(
        tmp_path / "h.har",
        [
            _entry_at("POST", _ORIGIN + "/api/orders", 3),
            _entry_at("GET", _ORIGIN + "/api/feed", 1),
            _entry_at("GET", _ORIGIN + "/api/feed", 2),
        ],
    )
    corr = correlate([_cp("load", 0)], har, _TARGET)
    assert corr is not None
    assert corr.actions[0].endpoints == ("GET /api/feed", "POST /api/orders")
    assert corr.request_count == 3


def test_action_with_no_requests_is_omitted(tmp_path: Path) -> None:
    har = _write_har(tmp_path / "h.har", [_entry_at("GET", _ORIGIN + "/api/feed", 1)])
    corr = correlate([_cp("load", 0), _cp("scroll #1", 100)], har, _TARGET)
    assert corr is not None
    # Only "load" caught a request; the empty "scroll #1" is dropped.
    assert [a.label for a in corr.actions] == ["load"]


def test_document_written_beside_har(tmp_path: Path) -> None:
    har = _write_har(tmp_path / "h.har", [_entry_at("GET", _ORIGIN + "/api/feed", 1)])
    corr = correlate([_cp("load", 0)], har, _TARGET)
    assert corr is not None
    assert corr.doc_path == str(tmp_path / "action_correlation.json")
    doc = json.loads(Path(corr.doc_path).read_text(encoding="utf-8"))
    assert doc["actions"][0]["label"] == "load"
    assert doc["actions"][0]["endpoints"] == ["GET /api/feed"]
    assert "not proven" in doc["note"]


def test_checkpoints_out_of_order_are_sorted(tmp_path: Path) -> None:
    # Correlation must not assume the caller passes checkpoints in time order.
    har = _write_har(
        tmp_path / "h.har",
        [
            _entry_at("GET", _ORIGIN + "/api/feed", 2),
            _entry_at("GET", _ORIGIN + "/api/more", 12),
        ],
    )
    corr = correlate([_cp("scroll #1", 10), _cp("load", 0)], har, _TARGET)
    assert corr is not None
    by_label = {a.label: a.endpoints for a in corr.actions}
    assert by_label["load"] == ("GET /api/feed",)
    assert by_label["scroll #1"] == ("GET /api/more",)
