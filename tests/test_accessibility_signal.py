"""Unit tests for the accessibility signal collector (ROADMAP.md §2c/§2h).

Below accessibility.feature: the scenario proves capture works against a real
browser; these pin the node-counting and aggregation across pages, the CDP
session lifecycle (it must be detached), and the §2h contract (raw node lists go
only to the local file, the shareable signal is a count) — all without a browser,
using tiny stand-ins for the Playwright Page / CDP session.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from spoor.signals.accessibility import AccessibilityCollector, AccessibilitySignal


@dataclass
class _FakeSession:
    result: dict[str, Any]
    detached: bool = False
    sent: list[str] = field(default_factory=list)

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.sent.append(method)
        return self.result

    def detach(self) -> None:
        self.detached = True


@dataclass
class _FakeContext:
    session: _FakeSession

    def new_cdp_session(self, page: object) -> _FakeSession:
        return self.session


@dataclass
class _FakePage:
    context: _FakeContext


def _page(nodes: object) -> tuple[_FakePage, _FakeSession]:
    session = _FakeSession(result={"nodes": nodes})
    return _FakePage(context=_FakeContext(session=session)), session


def test_signal_is_a_plain_count() -> None:
    assert AccessibilitySignal(nodes=7).nodes == 7


def test_capture_counts_nodes_and_detaches() -> None:
    collector = AccessibilityCollector()
    page, session = _page([{"nodeId": "1"}, {"nodeId": "2"}, {"nodeId": "3"}])
    collector.capture(page)  # type: ignore[arg-type]

    assert collector.signal.nodes == 3
    assert session.sent == ["Accessibility.getFullAXTree"]
    assert session.detached is True  # the CDP session is always released


def test_aggregates_across_pages() -> None:
    collector = AccessibilityCollector()
    page_a, _ = _page([{"nodeId": "1"}])
    page_b, _ = _page([{"nodeId": "1"}, {"nodeId": "2"}])
    collector.capture(page_a)  # type: ignore[arg-type]
    collector.capture(page_b)  # type: ignore[arg-type]
    assert collector.signal.nodes == 3


def test_missing_or_malformed_nodes_counts_zero() -> None:
    collector = AccessibilityCollector()
    empty, _ = _page([])
    missing = _FakePage(context=_FakeContext(session=_FakeSession(result={})))
    malformed, _ = _page("not-a-list")
    collector.capture(empty)  # type: ignore[arg-type]
    collector.capture(missing)  # type: ignore[arg-type]
    collector.capture(malformed)  # type: ignore[arg-type]
    assert collector.signal.nodes == 0


def test_cdp_error_is_swallowed_and_does_not_break_the_run() -> None:
    # A signal is opportunistic: a CDP failure must not abort extraction. It is
    # recorded as an empty snapshot for that page, and the run carries on.
    class _ErrorContext:
        def new_cdp_session(self, page: object) -> object:
            raise PlaywrightError("target closed")

    collector = AccessibilityCollector()
    page = _FakePage(context=_ErrorContext())  # type: ignore[arg-type]
    collector.capture(page)  # type: ignore[arg-type]  # must not raise
    assert collector.signal.nodes == 0


def test_write_persists_raw_node_lists_per_page(tmp_path: Path) -> None:
    collector = AccessibilityCollector()
    page, _ = _page([{"nodeId": "1", "role": {"value": "button"}}])
    collector.capture(page)  # type: ignore[arg-type]

    path = tmp_path / "accessibility.json"
    collector.write(path)
    trees = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(trees, list)
    assert len(trees) == 1  # one raw node list per page snapshotted
    assert trees[0][0]["nodeId"] == "1"


def test_write_persists_empty_list_for_no_snapshots(tmp_path: Path) -> None:
    collector = AccessibilityCollector()
    assert collector.signal.nodes == 0
    path = tmp_path / "accessibility.json"
    collector.write(path)
    # Written even for a run with no snapshots, so its presence means "captured".
    assert json.loads(path.read_text(encoding="utf-8")) == []
