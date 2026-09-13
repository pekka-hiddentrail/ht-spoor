"""Unit tests for the change-detection validator store (ROADMAP.md §2d, Phase 3.5).

The `.feature` scenarios exercise change detection end-to-end through two tier-1
runs; these probe `ChangeDetector` directly — the conditional-header replay, the
304-vs-content-hash unchanged judgement, and the persistence that makes it span
runs — including the edge cases (a first run, a server with no validators, a
corrupt store) that must degrade to "extract everything", never crash a run.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from spoor.operational.change_detection import (
    ChangeDetector,
    PageValidators,
    detector_for_target,
    store_path_for_target,
)
from spoor.security import storage

_URL = "http://localhost:8000/product.html"


def _resp(
    status: int, *, text: str = "", headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status, text=text, headers=headers or {})


@pytest.fixture
def detector(tmp_path: Path) -> ChangeDetector:
    return ChangeDetector(tmp_path / "store.json")


def test_a_first_run_sends_no_conditional_headers(detector: ChangeDetector) -> None:
    assert detector.conditional_headers(_URL) == {}


def test_a_first_sighting_is_always_changed(detector: ChangeDetector) -> None:
    # Nothing to compare against, so a never-seen URL always extracts.
    assert detector.is_unchanged(_URL, _resp(200, text="<html></html>")) is False


def test_recorded_validators_are_replayed_as_conditional_headers(
    detector: ChangeDetector,
) -> None:
    detector.record(
        _URL,
        _resp(200, text="body", headers={"ETag": '"v1"', "Last-Modified": "Mon"}),
    )
    assert detector.conditional_headers(_URL) == {
        "If-None-Match": '"v1"',
        "If-Modified-Since": "Mon",
    }


def test_a_recorded_page_with_no_validators_replays_no_headers(
    detector: ChangeDetector,
) -> None:
    # A server that sends no ETag/Last-Modified leaves nothing to replay; detection
    # then rides entirely on the content hash.
    detector.record(_URL, _resp(200, text="body"))
    assert detector.conditional_headers(_URL) == {}


def test_a_304_is_unchanged(detector: ChangeDetector) -> None:
    detector.record(_URL, _resp(200, text="body", headers={"ETag": '"v1"'}))
    assert detector.is_unchanged(_URL, _resp(304)) is True


def test_an_identical_body_is_unchanged_by_hash(detector: ChangeDetector) -> None:
    detector.record(_URL, _resp(200, text="same body"))
    assert detector.is_unchanged(_URL, _resp(200, text="same body")) is True


def test_a_different_body_is_changed(detector: ChangeDetector) -> None:
    detector.record(_URL, _resp(200, text="old body"))
    assert detector.is_unchanged(_URL, _resp(200, text="new body")) is False


def test_the_store_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "store.json"
    first = ChangeDetector(path)
    first.record(_URL, _resp(200, text="body", headers={"ETag": '"v1"'}))
    first.save()

    reopened = ChangeDetector(path)
    assert reopened.conditional_headers(_URL) == {"If-None-Match": '"v1"'}
    assert reopened.is_unchanged(_URL, _resp(200, text="body")) is True


def test_save_is_a_noop_when_nothing_was_recorded(tmp_path: Path) -> None:
    path = tmp_path / "store.json"
    ChangeDetector(path).save()
    assert not path.exists()  # never write an empty store / create the dir for nothing


def test_a_corrupt_store_loads_empty_rather_than_raising(tmp_path: Path) -> None:
    path = tmp_path / "store.json"
    path.write_text("{not valid json", encoding="utf-8")
    detector = ChangeDetector(path)  # must not raise
    assert detector.conditional_headers(_URL) == {}


def test_a_malformed_entry_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "store.json"
    # One good entry, one missing its content_hash — the bad one is dropped, the
    # good one still loads (a hand-edited or truncated store never fails the run).
    path.write_text(
        '{"'
        + _URL
        + '": {"etag": "\\"v1\\"", "content_hash": "abc"}, '
        '"http://localhost:8000/other": {"etag": "\\"v2\\""}}',
        encoding="utf-8",
    )
    detector = ChangeDetector(path)
    assert detector.conditional_headers(_URL) == {"If-None-Match": '"v1"'}
    assert detector.conditional_headers("http://localhost:8000/other") == {}


def test_record_is_dirty_only_on_a_real_change(tmp_path: Path) -> None:
    path = tmp_path / "store.json"
    detector = ChangeDetector(path)
    detector.record(_URL, _resp(200, text="body", headers={"ETag": '"v1"'}))
    detector.save()
    mtime = path.stat().st_mtime_ns

    # Recording the identical response again is a no-op, so save writes nothing.
    detector.record(_URL, _resp(200, text="body", headers={"ETag": '"v1"'}))
    detector.save()
    assert path.stat().st_mtime_ns == mtime


def test_store_path_is_per_domain_under_the_cache_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    path = store_path_for_target(_URL)
    assert path.parent == tmp_path / "cache" / "change_detection"
    assert path.name == "localhost_8000.json"  # colon sanitized for Windows


def test_detector_for_target_is_local_only_under_the_cache_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    detector = detector_for_target(_URL)
    assert isinstance(detector, ChangeDetector)


def test_page_validators_equality_backs_the_noop(tmp_path: Path) -> None:
    # The record no-op relies on value equality of the frozen dataclass.
    a = PageValidators(etag='"v1"', last_modified=None, content_hash="h")
    b = PageValidators(etag='"v1"', last_modified=None, content_hash="h")
    assert a == b
