"""Unit tests for the client-side storage-state collector (ROADMAP.md §2c/§2h).

Below storage_state.feature: the scenario proves capture works against a real
browser; these pin the derived summary (counts, per-origin localStorage) and the
§2h contract — the shareable signal carries entries with secret shapes redacted
while the raw file keeps every value — from fabricated `storage_state()` dicts,
without a browser.
"""

from __future__ import annotations

import json
from pathlib import Path

from spoor.signals.storage_state import StorageStateCollector

# A storage-state dict shaped like Playwright's context.storage_state() output.
_STATE = {
    "cookies": [
        {"name": "sessionid", "value": "8f9a1b2c3d4e5f60718293a4", "domain": "x"},
        {"name": "theme", "value": "dark", "domain": "x"},
    ],
    "origins": [
        {
            "origin": "http://localhost:8000",
            "localStorage": [
                {"name": "access_token", "value": "eyJab.eyJcd.sig123"},
                {"name": "cart_size", "value": "3"},
            ],
        }
    ],
}


def _collector(state: dict[str, object]) -> StorageStateCollector:
    collector = StorageStateCollector()
    collector.capture(state)
    return collector


def test_counts_cookies_origins_and_local_storage() -> None:
    signal = _collector(_STATE).signal
    assert signal.cookie_count == 2
    assert signal.origin_count == 1
    assert signal.local_storage_count == 2


def test_recognized_session_cookie_value_is_redacted() -> None:
    signal = _collector(_STATE).signal
    assert "sessionid=[REDACTED]" in signal.cookies


def test_non_secret_cookie_is_kept_intact() -> None:
    signal = _collector(_STATE).signal
    assert "theme=dark" in signal.cookies


def test_auth_keyed_local_storage_value_is_redacted() -> None:
    # access_token is a recognized auth-key name; its value must be scrubbed.
    signal = _collector(_STATE).signal
    assert "access_token=[REDACTED]" in signal.local_storage


def test_non_secret_local_storage_is_kept_intact() -> None:
    signal = _collector(_STATE).signal
    assert "cart_size=3" in signal.local_storage


def test_token_shaped_value_is_redacted_regardless_of_key() -> None:
    # A JWT stored under an unremarkable key is still caught by the token-shape
    # rule — redaction keys off value shape too, not only recognized names.
    collector = _collector(
        {
            "origins": [
                {
                    "origin": "http://x",
                    "localStorage": [
                        {"name": "blob", "value": "eyJhbGc.eyJzdWI.sigABC"}
                    ],
                }
            ]
        }
    )
    assert "blob=[REDACTED]" in collector.signal.local_storage


def test_signal_carries_no_raw_secret_values() -> None:
    # §2h: neither the raw cookie value nor the raw token may ride out on the
    # shareable signal object.
    signal = _collector(_STATE).signal
    text = repr(signal)
    assert "8f9a1b2c3d4e5f60718293a4" not in text
    assert "eyJab.eyJcd.sig123" not in text


def test_empty_state_reports_zeros_and_no_entries() -> None:
    signal = StorageStateCollector().signal
    assert signal.cookie_count == 0
    assert signal.origin_count == 0
    assert signal.local_storage_count == 0
    assert signal.cookies == ()
    assert signal.local_storage == ()


def test_write_persists_raw_unredacted_state(tmp_path: Path) -> None:
    # The raw local-only file keeps everything, secret values included (§2h).
    path = tmp_path / "storage_state.json"
    _collector(_STATE).write(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == _STATE
    assert "8f9a1b2c3d4e5f60718293a4" in path.read_text(encoding="utf-8")


def test_write_persists_empty_dict_for_no_capture(tmp_path: Path) -> None:
    path = tmp_path / "storage_state.json"
    StorageStateCollector().write(path)
    assert json.loads(path.read_text(encoding="utf-8")) == {}
