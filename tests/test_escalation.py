"""Unit tests for content-driven escalation in the dispatcher (ROADMAP.md §2).

These sit below resolution.feature's browser-backed scenario: that scenario
proves escalation end to end through a real Chromium, while these lock the exact
walk contract deterministically with fake resolvers — which rungs run, in what
order, and precisely when the walk stops. In particular they pin the collision
the ROADMAP decision resolves: records-with-null-fields do *not* escalate, and a
robots-blocked result does *not* escalate.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from spoor.core import extract
from spoor.core.config import ExtractionConfig
from spoor.core.extract import RunResult, _should_escalate

_CONFIG = ExtractionConfig(
    target="http://localhost/x", fields={}
)  # content, not this config, drives the walk here


@dataclass
class _FakeResolver:
    """A resolver that records whether it ran and returns a canned result."""

    tier: int
    _result: RunResult
    _accepts: bool = True
    name: str = "fake"
    ran: bool = field(default=False, init=False)

    def accepts(self, config: ExtractionConfig) -> bool:
        return self._accepts

    def run(
        self,
        config: ExtractionConfig,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> RunResult:
        self.ran = True
        return self._result


def _records(*names: str) -> list[dict[str, object]]:
    return [{"title": name} for name in names]


# --- _should_escalate: the trigger in isolation ---------------------------


def test_empty_result_escalates() -> None:
    assert _should_escalate(RunResult(records=[])) is True


def test_records_do_not_escalate() -> None:
    assert _should_escalate(RunResult(records=_records("a"))) is False


def test_records_with_null_fields_do_not_escalate() -> None:
    # The collision the ROADMAP decision guards against: a record whose fields are
    # all null is still a record, and a missing field is legitimate (§2a).
    assert _should_escalate(RunResult(records=[{"title": None}])) is False


def test_blocked_result_does_not_escalate() -> None:
    # A robots block is a real result; a heavier tier must not work around it (§6).
    assert _should_escalate(RunResult(records=[], blocked=["http://x"])) is False


# --- run_report: the walk over the ladder ---------------------------------


def test_walk_stops_at_first_nonempty_tier() -> None:
    tier1 = _FakeResolver(tier=1, _result=RunResult(records=_records("a")))
    tier2 = _FakeResolver(tier=2, _result=RunResult(records=_records("b")))
    result = extract.run_report(_CONFIG, tiers=(tier1, tier2))
    assert result.records == _records("a")
    assert tier1.ran is True
    assert tier2.ran is False


def test_empty_first_tier_escalates_to_the_next() -> None:
    tier1 = _FakeResolver(tier=1, _result=RunResult(records=[]))
    tier2 = _FakeResolver(tier=2, _result=RunResult(records=_records("b")))
    result = extract.run_report(_CONFIG, tiers=(tier1, tier2))
    assert result.records == _records("b")
    assert tier1.ran is True
    assert tier2.ran is True


def test_blocked_first_tier_is_not_escalated() -> None:
    tier1 = _FakeResolver(tier=1, _result=RunResult(records=[], blocked=["http://x"]))
    tier2 = _FakeResolver(tier=2, _result=RunResult(records=_records("b")))
    result = extract.run_report(_CONFIG, tiers=(tier1, tier2))
    assert result.blocked == ["http://x"]
    assert result.records == []
    assert tier2.ran is False


def test_all_tiers_empty_returns_last_result() -> None:
    tier1 = _FakeResolver(tier=1, _result=RunResult(records=[]))
    tier2 = _FakeResolver(tier=2, _result=RunResult(records=[]))
    result = extract.run_report(_CONFIG, tiers=(tier1, tier2))
    assert result.records == []
    assert tier1.ran is True
    assert tier2.ran is True


def test_only_accepting_tiers_run() -> None:
    # A tier that declines the config is skipped entirely, even if tier 1 is empty.
    tier1 = _FakeResolver(tier=1, _result=RunResult(records=[]), _accepts=False)
    tier2 = _FakeResolver(tier=2, _result=RunResult(records=_records("b")))
    result = extract.run_report(_CONFIG, tiers=(tier1, tier2))
    assert result.records == _records("b")
    assert tier1.ran is False
    assert tier2.ran is True
