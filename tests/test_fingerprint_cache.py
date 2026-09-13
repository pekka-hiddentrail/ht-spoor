"""Unit tests for the persistent per-domain fingerprint cache (ROADMAP.md §2, §0).

Exercises the persistence contract the run-level scenarios rely on: path
derivation from a target, a put/save/reload round-trip, the dirty-tracking that
avoids needless writes, and the never-raise-on-I/O guarantees (a missing or
corrupt file yields an empty cache, a first run for a domain — never an error).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from parsel import Selector

from spoor.core import fingerprint_cache
from spoor.core.fingerprint_cache import (
    FingerprintCache,
    cache_path_for_target,
)
from spoor.core.healing import ElementFingerprint, fingerprint
from spoor.security import storage


def _fp(text: str = "Beta Gadget") -> ElementFingerprint:
    element = Selector(text=f'<h2 class="title" id="x">{text}</h2>').css("h2")[0]
    return fingerprint(element)


def test_cache_path_derives_and_sanitizes_the_netloc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    path = cache_path_for_target("http://localhost:8000/products?page=1")
    # The colon (invalid in a Windows filename) is sanitized to an underscore.
    assert path.name == "localhost_8000.json"
    assert path.parent.name == fingerprint_cache.FINGERPRINT_DIRNAME


def test_cache_path_falls_back_when_target_has_no_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    assert cache_path_for_target("not-a-url").name == "_nohost.json"


def test_put_then_save_and_reload_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    cache = FingerprintCache(path)
    fp = _fp()
    cache.put("name", fp)
    cache.save()
    assert path.exists()
    reloaded = FingerprintCache(path)
    assert reloaded.get("name") == fp


def test_get_is_none_for_an_unknown_field(tmp_path: Path) -> None:
    assert FingerprintCache(tmp_path / "d.json").get("missing") is None


def test_save_is_a_noop_when_nothing_changed(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    FingerprintCache(path).save()  # nothing put -> not dirty
    assert not path.exists()  # no file, and no parent dir created


def test_putting_an_identical_fingerprint_leaves_the_cache_clean(
    tmp_path: Path,
) -> None:
    path = tmp_path / "d.json"
    fp = _fp()
    cache = FingerprintCache(path)
    cache.put("name", fp)
    cache.save()
    mtime = path.stat().st_mtime_ns

    cache.put("name", fp)  # identical -> no-op, not dirty
    cache.save()
    assert path.stat().st_mtime_ns == mtime  # not rewritten


def test_a_missing_file_loads_as_an_empty_cache(tmp_path: Path) -> None:
    cache = FingerprintCache(tmp_path / "nope.json")
    assert cache.get("name") is None


def test_a_corrupt_file_loads_as_an_empty_cache_without_raising(
    tmp_path: Path,
) -> None:
    path = tmp_path / "d.json"
    path.write_text("this is not json{", encoding="utf-8")
    cache = FingerprintCache(path)  # must not raise
    assert cache.get("name") is None


def test_a_malformed_entry_is_skipped_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    fp = _fp()
    good = FingerprintCache(path)
    good.put("name", fp)
    good.save()
    # Inject a malformed sibling entry alongside the good one.
    import json

    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["broken"] = {"tag": "h2"}  # missing required keys
    path.write_text(json.dumps(doc), encoding="utf-8")

    reloaded = FingerprintCache(path)
    assert reloaded.get("name") == fp  # good entry survives
    assert reloaded.get("broken") is None  # malformed one skipped


def test_save_creates_the_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "dir" / "d.json"
    cache = FingerprintCache(path)
    cache.put("name", _fp())
    cache.save()
    assert path.exists()


def test_visual_hash_round_trips_through_the_cache(tmp_path: Path) -> None:
    # A browser-tier print carries a 64-bit visual hash; it must survive a
    # save/reload so a later run can heal on appearance.
    from dataclasses import replace

    path = tmp_path / "d.json"
    cache = FingerprintCache(path)
    fp = replace(_fp(), visual_hash=0xABCD1234ABCD1234)
    cache.put("logo", fp)
    cache.save()
    reloaded = FingerprintCache(path).get("logo")
    assert reloaded == fp
    assert reloaded is not None
    assert reloaded.visual_hash == 0xABCD1234ABCD1234


def test_an_entry_without_a_visual_hash_loads_as_none(tmp_path: Path) -> None:
    # Backward-compatible: a cache written before the visual signal (or a tier-1,
    # DOM-only print) has no/null "visual_hash" and must load as None, scored on
    # its DOM signals alone — never crash.
    path = tmp_path / "d.json"
    path.write_text(
        '{"logo": {"tag": "img", "element_id": "", "classes": [], "attrs": [],'
        ' "text": "", "ancestors": ["html", "body"], "sibling_index": 0}}',
        encoding="utf-8",
    )
    loaded = FingerprintCache(path).get("logo")
    assert loaded is not None
    assert loaded.visual_hash is None
