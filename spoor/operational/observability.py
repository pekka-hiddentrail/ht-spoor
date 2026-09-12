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

from spoor.api_discovery.discovery import DiscoveredSpec
from spoor.api_discovery.graphql import DiscoveredGraphQL
from spoor.core.extract import RunResult
from spoor.signals.console import ConsoleSignal


@dataclass(frozen=True)
class RunSummary:
    """A structured, operator-facing summary of one dispatched run (§2d)."""

    items: int
    pages_fetched: int
    resolved_tier: int | None
    tiers_attempted: list[int]
    blocked: list[str]
    # The local-only HAR the browser tier captured, if any (ROADMAP.md §2b/§2h).
    # A string (not a Path) so the summary stays trivially serializable (§2d).
    har_path: str | None
    # An official API spec observed at a conventional path, if any (ROADMAP.md
    # §2b) — reported as *observed*, never as a complete API census.
    api_spec: DiscoveredSpec | None
    # An introspectable GraphQL endpoint observed at a conventional path, if any
    # (ROADMAP.md §2b layer 2) — likewise *observed*, never a complete census.
    graphql: DiscoveredGraphQL | None
    # Counts of the browser tier's console activity, if it was captured (§2c).
    # Counts only — the raw messages stay in the local-only log at
    # `console_log_path`, never surfaced here (§2h).
    console: ConsoleSignal | None
    console_log_path: str | None

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
            har_path=str(result.har_path) if result.har_path is not None else None,
            api_spec=result.api_spec,
            graphql=result.graphql,
            console=result.console,
            console_log_path=(
                str(result.console_log_path)
                if result.console_log_path is not None
                else None
            ),
        )

    @property
    def escalated(self) -> bool:
        """Whether the run had to advance past its first attempted tier."""
        return len(self.tiers_attempted) > 1

    def _render_api_spec(self) -> str:
        """The API-spec line: the observed spec, or that none was discovered.

        Worded as *observed* to hold §2b's bounded claim — a discovered spec is
        one Spoor saw published, never a promise of the complete API surface.
        """
        if self.api_spec is None:
            return "none discovered"
        spec = self.api_spec
        return f"{spec.kind} {spec.version} observed at {spec.url}"

    def _render_graphql(self) -> str:
        """The GraphQL line: an observed introspectable endpoint, or none.

        Worded as *observed* to hold §2b's bounded claim; a "none" means not
        observed / not exposed (introspection is often disabled), never proof no
        GraphQL exists.
        """
        if self.graphql is None:
            return "none discovered"
        gql = self.graphql
        return f"introspection observed at {gql.url} ({gql.types} types)"

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
            f"  api spec:      {self._render_api_spec()}",
            f"  graphql:       {self._render_graphql()}",
            f"  blocked:       {len(self.blocked)}",
        ]
        lines.extend(f"    - {url} (robots.txt)" for url in self.blocked)
        # Console counts, only when the console was captured (§2c). Counts only —
        # never message text — so nothing sensitive surfaces here (§2h).
        if self.console is not None:
            c = self.console
            lines.append(
                f"  console:       {c.messages} messages "
                f"({c.errors} errors, {c.page_errors} uncaught)"
            )
        # Capture lines: only shown when something was captured, so an ordinary run
        # stays quiet; named raw + local so it's clear this isn't shared output (§2h).
        if self.har_path is not None:
            lines.append(f"  captured:      raw HAR (local-only) {self.har_path}")
        if self.console_log_path is not None:
            lines.append(
                f"  captured:      raw console log (local-only) {self.console_log_path}"
            )
        return "\n".join(lines)
