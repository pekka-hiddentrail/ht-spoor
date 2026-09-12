"""Unit tests for the RunSummary projection and rendering (ROADMAP.md §2d).

Below observability.feature: the scenarios drive the dispatcher end to end for
the tier-1 cases, while these pin the projection contract directly — in
particular the escalation path (which needs a browser to exercise for real) and
the direct-resolver fallback.
"""

from __future__ import annotations

from spoor.core.extract import RunResult
from spoor.operational.observability import RunSummary


def test_from_result_projects_fields() -> None:
    result = RunResult(
        records=[{"title": "a"}, {"title": "b"}],
        blocked=["http://x/robots"],
        tier=1,
        pages_fetched=2,
        tiers_attempted=[1],
    )
    summary = RunSummary.from_result(result)
    assert summary.items == 2
    assert summary.pages_fetched == 2
    assert summary.resolved_tier == 1
    assert summary.blocked == ["http://x/robots"]
    assert summary.escalated is False


def test_escalation_path_is_reported() -> None:
    result = RunResult(records=[{"title": "a"}], tier=2, pages_fetched=1,
                        tiers_attempted=[1, 2])
    summary = RunSummary.from_result(result)
    assert summary.escalated is True
    assert summary.tiers_attempted == [1, 2]
    assert "escalated (tier 1 -> tier 2)" in summary.render()


def test_direct_resolver_result_falls_back_to_its_tier() -> None:
    # A resolver invoked directly leaves tiers_attempted empty; the summary still
    # names the resolving tier and reports no escalation.
    result = RunResult(records=[{"title": "a"}], tier=2, pages_fetched=1)
    summary = RunSummary.from_result(result)
    assert summary.tiers_attempted == [2]
    assert summary.escalated is False
    assert summary.resolved_tier == 2


def test_empty_run_renders_cleanly() -> None:
    # A run that fetched nothing and resolved no tier must still render, not crash.
    summary = RunSummary.from_result(RunResult())
    assert summary.items == 0
    assert summary.resolved_tier is None
    rendered = summary.render()
    assert "items scraped: 0" in rendered
    assert "resolved by:   none" in rendered
    assert "escalation:    none" in rendered


def test_blocked_urls_are_listed_in_render() -> None:
    result = RunResult(blocked=["http://x/secret"], tier=1, tiers_attempted=[1])
    rendered = RunSummary.from_result(result).render()
    assert "blocked:       1" in rendered
    assert "    - http://x/secret (robots.txt)" in rendered
