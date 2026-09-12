"""Run observability: an operator-facing summary of a run (ROADMAP.md §2d).

§2d asks for "a structured run summary — items scraped, how often each tier had
to escalate, error counts ... — so a user can tell whether a run actually went
well without reading raw logs." This is the Phase-1 slice: the facts the current
machinery can honestly report. Error/retry classification (needs the Phase-3.5
retry mechanism) and "which fields fell back to tier 3/4" (needs those tiers) are
deliberately absent, not faked — see the run-observability decision note in §2d.

Placement follows the §0 layout: the raw per-run facts are stamped on `RunResult`
by the dispatcher (core); this module is the operator-facing *presentation* of
them. `RunSummary` stays a plain structured object so a later phase can serialize
it (the §2d "signals-catalog thinking turned inward") without rework.
"""

from __future__ import annotations

from dataclasses import dataclass

from spoor.core.extract import RunResult


@dataclass(frozen=True)
class RunSummary:
    """A structured, operator-facing summary of one dispatched run (§2d)."""

    items: int
    pages_fetched: int
    resolved_tier: int | None
    tiers_attempted: list[int]
    blocked: list[str]

    @classmethod
    def from_result(cls, result: RunResult) -> RunSummary:
        """Project a `RunResult` into a summary.

        `tiers_attempted` comes from the dispatcher; a resolver invoked directly
        leaves it empty, so fall back to the single tier that produced the result.
        """
        attempted = result.tiers_attempted or (
            [result.tier] if result.tier is not None else []
        )
        return cls(
            items=len(result.records),
            pages_fetched=result.pages_fetched,
            resolved_tier=result.tier,
            tiers_attempted=list(attempted),
            blocked=list(result.blocked),
        )

    @property
    def escalated(self) -> bool:
        """Whether the run had to advance past its first attempted tier."""
        return len(self.tiers_attempted) > 1

    def render(self) -> str:
        """A compact, human-readable rendering for the CLI."""
        resolved = (
            f"tier {self.resolved_tier}" if self.resolved_tier is not None else "none"
        )
        if self.escalated:
            # Plain ASCII arrow: this string is printed to the console, which on
            # Windows may be cp1252 and would choke on a Unicode arrow.
            path = " -> ".join(f"tier {tier}" for tier in self.tiers_attempted)
            escalation = f"escalated ({path})"
        else:
            escalation = "none"
        lines = [
            "Run summary:",
            f"  items scraped: {self.items}",
            f"  pages fetched: {self.pages_fetched}",
            f"  resolved by:   {resolved}",
            f"  escalation:    {escalation}",
            f"  blocked:       {len(self.blocked)}",
        ]
        lines.extend(f"    - {url} (robots.txt)" for url in self.blocked)
        return "\n".join(lines)
