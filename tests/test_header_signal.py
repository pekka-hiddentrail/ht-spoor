"""Unit tests for the response-header signal collector (ROADMAP.md §2c/§2h).

Below response_headers.feature: the scenario proves capture works against a real
browser; these pin the derived summary (distinct-name count, security-header
presence, case-insensitivity) and the §2h contract — raw values go only to the
local file, the shareable signal carries no values — without a browser.
"""

from __future__ import annotations

import json
from pathlib import Path

from spoor.signals.headers import HeaderCollector


def test_counts_distinct_header_names() -> None:
    collector = HeaderCollector()
    collector.capture({"server": "nginx", "content-type": "text/html"})
    assert collector.signal.count == 2


def test_distinct_names_deduped_across_pages() -> None:
    collector = HeaderCollector()
    collector.capture({"server": "nginx", "content-type": "text/html"})
    collector.capture({"server": "nginx", "x-powered-by": "Express"})
    # server/content-type/x-powered-by = 3 distinct names, server not double-counted.
    assert collector.signal.count == 3


def test_detects_security_headers() -> None:
    collector = HeaderCollector()
    collector.capture(
        {
            "content-security-policy": "default-src 'self'",
            "strict-transport-security": "max-age=31536000",
            "x-frame-options": "DENY",
        }
    )
    signal = collector.signal
    assert signal.csp is True
    assert signal.hsts is True
    assert signal.x_frame_options is True


def test_absent_security_headers_report_false() -> None:
    collector = HeaderCollector()
    collector.capture({"server": "nginx"})
    signal = collector.signal
    assert signal.csp is False
    assert signal.hsts is False
    assert signal.x_frame_options is False


def test_security_header_detection_is_case_insensitive() -> None:
    # Real servers vary header-name casing; Playwright lowercases, but be defensive.
    collector = HeaderCollector()
    collector.capture({"Content-Security-Policy": "default-src 'self'"})
    assert collector.signal.csp is True


def test_empty_run_reports_zero_and_no_security_headers() -> None:
    signal = HeaderCollector().signal
    assert signal.count == 0
    assert signal.csp is False
    assert signal.hsts is False
    assert signal.x_frame_options is False


def test_signal_carries_no_header_values() -> None:
    # §2h: the shareable signal is counts + booleans, never values. A secret in
    # set-cookie must not ride out on the summary object.
    collector = HeaderCollector()
    collector.capture({"set-cookie": "session=SECRETTOKEN; HttpOnly"})
    assert "SECRETTOKEN" not in repr(collector.signal)


def test_write_persists_raw_values_including_sensitive_ones(tmp_path: Path) -> None:
    # The raw local-only file keeps everything, set-cookie included (§2h): raw
    # captures live in the local cache, redaction applies only to shared output.
    collector = HeaderCollector()
    collector.capture({"server": "nginx", "set-cookie": "session=SECRETTOKEN"})

    path = tmp_path / "headers.json"
    collector.write(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == [{"server": "nginx", "set-cookie": "session=SECRETTOKEN"}]


def test_write_persists_empty_list_for_no_responses(tmp_path: Path) -> None:
    path = tmp_path / "headers.json"
    HeaderCollector().write(path)
    assert json.loads(path.read_text(encoding="utf-8")) == []
