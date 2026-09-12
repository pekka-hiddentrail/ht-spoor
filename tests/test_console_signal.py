"""Unit tests for the console signal collector (ROADMAP.md §2c/§2h).

Below signals.feature: the scenario proves capture works against a real browser;
these pin the collector's counting and its §2h contract (raw text goes only to
the local file, never into the shareable `signal`) without a browser, using tiny
stand-ins for Playwright's ConsoleMessage / Error objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from spoor.signals.console import ConsoleCollector


@dataclass
class _FakeMessage:
    type: str
    text: str


@dataclass
class _FakeError:
    name: str
    message: str


def test_counts_messages_errors_and_page_errors() -> None:
    collector = ConsoleCollector()
    collector._on_console(_FakeMessage("log", "boot"))  # type: ignore[arg-type]
    collector._on_console(_FakeMessage("warning", "careful"))  # type: ignore[arg-type]
    collector._on_console(_FakeMessage("error", "broke"))  # type: ignore[arg-type]
    collector._on_pageerror(_FakeError("Error", "boom"))  # type: ignore[arg-type]

    signal = collector.signal
    assert signal.messages == 3  # all console.* calls, every level
    assert signal.errors == 1  # only the error-level console message
    assert signal.page_errors == 1  # the uncaught exception, counted separately


def test_empty_run_reports_zeroes_and_writes_empty_file(tmp_path: Path) -> None:
    collector = ConsoleCollector()
    assert collector.signal.messages == 0
    assert collector.signal.errors == 0
    assert collector.signal.page_errors == 0

    path = tmp_path / "console.jsonl"
    collector.write(path)
    # The file is written even for a silent run, so its presence means "captured".
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == ""


def test_write_persists_raw_text_as_json_lines(tmp_path: Path) -> None:
    collector = ConsoleCollector()
    collector._on_console(_FakeMessage("error", "token=SECRET leaked here"))  # type: ignore[arg-type]
    collector._on_pageerror(_FakeError("TypeError", "x is not a function"))  # type: ignore[arg-type]

    path = tmp_path / "console.jsonl"
    collector.write(path)
    records = [json.loads(line) for line in path.read_text().splitlines()]

    assert records[0] == {
        "kind": "console",
        "type": "error",
        "text": "token=SECRET leaked here",
    }
    assert records[1] == {
        "kind": "pageerror",
        "name": "TypeError",
        "message": "x is not a function",
    }


def test_signal_never_carries_message_text() -> None:
    # §2h: the shareable signal is counts only. Its repr must not leak raw text,
    # so a secret logged to the console can't ride out on the summary object.
    collector = ConsoleCollector()
    collector._on_console(_FakeMessage("error", "authorization: Bearer abc123"))  # type: ignore[arg-type]
    assert "abc123" not in repr(collector.signal)
