"""Unit tests for HAR-capture wiring below capture.feature (ROADMAP.md §2b/§2h).

The feature scenarios drive the real browser end to end; these pin the pieces
that don't need one — the local-only cache paths, the opt-in config model, and
how the run summary surfaces (or hides) the captured HAR.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from spoor.core.config import load_config
from spoor.core.extract import RunResult
from spoor.operational.observability import RunSummary
from spoor.security import storage

# --- storage: the local-only run cache ------------------------------------


def test_new_run_cache_dir_is_under_cache_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".spoor-cache"
    monkeypatch.setattr(storage, "CACHE_ROOT", root)
    run_dir = storage.new_run_cache_dir()
    assert run_dir.is_dir()
    assert root in run_dir.parents


def test_new_run_cache_dirs_are_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / ".spoor-cache")
    assert storage.new_run_cache_dir() != storage.new_run_cache_dir()


# --- config: opt-in capture ------------------------------------------------


def test_capture_defaults_to_absent() -> None:
    cfg = load_config('target: http://x/\nfields:\n  t: { selector: "h1" }\n')
    assert cfg.capture is None


def test_capture_har_flag_parses() -> None:
    cfg = load_config(
        "target: http://x/\n"
        'fields:\n  t: { selector: "h1" }\n'
        "capture:\n  har: true\n"
    )
    assert cfg.capture is not None
    assert cfg.capture.har is True


def test_capture_har_defaults_false_when_section_present() -> None:
    cfg = load_config(
        "target: http://x/\nfields:\n  t: { selector: \"h1\" }\ncapture: {}\n"
    )
    assert cfg.capture is not None
    assert cfg.capture.har is False


def test_capture_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError):
        load_config(
            "target: http://x/\n"
            'fields:\n  t: { selector: "h1" }\n'
            "capture:\n  hars: true\n"
        )


# --- summary: surfacing the capture ---------------------------------------


def test_summary_projects_har_path_as_string() -> None:
    result = RunResult(records=[{"t": "a"}], tier=2, har_path=Path("/c/run/net.har"))
    summary = RunSummary.from_result(result)
    assert summary.har_path == str(Path("/c/run/net.har"))
    assert str(Path("/c/run/net.har")) in summary.render()
    assert "raw HAR (local-only)" in summary.render()


def test_summary_has_no_capture_line_without_har() -> None:
    summary = RunSummary.from_result(RunResult(records=[{"t": "a"}], tier=1))
    assert summary.har_path is None
    assert "captured" not in summary.render()
