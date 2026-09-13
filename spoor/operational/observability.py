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

from spoor.api_discovery.correlation import ActionCorrelation
from spoor.api_discovery.discovery import DiscoveredSpec
from spoor.api_discovery.graphql import DiscoveredGraphQL
from spoor.api_discovery.synthesis import SynthesizedSpec
from spoor.core.extract import RunResult
from spoor.signals.accessibility import AccessibilitySignal
from spoor.signals.console import ConsoleSignal
from spoor.signals.headers import HeaderSignal
from spoor.signals.storage_state import StorageStateSignal


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
    # Node count of the browser tier's accessibility snapshots, if captured (§2c).
    # A count only; the raw trees stay in the local-only file at `accessibility_path`.
    accessibility: AccessibilitySignal | None
    accessibility_path: str | None
    # Non-sensitive derived facts about response headers, if captured (§2c). A
    # count + security-header presence only; raw values stay in the local-only
    # file at `headers_path` (some headers are secret shapes, §2h).
    headers: HeaderSignal | None
    headers_path: str | None
    # Redacted, shareable view of the browser context's client-side storage, if
    # captured (§2c). Names + secret-redacted values only; the raw unredacted
    # state stays in the local-only file at `storage_state_path` (§2h).
    storage_state: StorageStateSignal | None
    storage_state_path: str | None
    # API spec synthesized by clustering the captured HAR's requests into
    # templated endpoints (§2b layer 4), if a HAR was captured. Counts surface
    # here; the OpenAPI document (with the templated paths) stays local-only at
    # `synthesized_spec.doc_path` — a synthesized path can embed an un-clustered
    # secret, so promoting paths to shared output waits for a redaction slice (§2h).
    synthesized_spec: SynthesizedSpec | None
    # Captured requests attributed to the action that likely triggered them (§2b
    # layer 5), if a HAR and action checkpoints were captured. Counts surface here;
    # the correlation document (with the templated paths) stays local-only at
    # `action_correlation.doc_path`, same §2h reasoning as the synthesized spec. A
    # time-window approximation, not proven causation (§2b).
    action_correlation: ActionCorrelation | None
    # Tier-3 self-healing outcome counts for this run (§2, §2d): fields whose
    # broken selector tier 3 re-resolved confidently (field filled) versus
    # uncertain matches it flagged for review (field left null, never guessed).
    # Counts only — the matched text never reaches the summary (§2h). Both zero
    # for a run where nothing broke or nothing was remembered.
    heal_confident: int
    heal_uncertain: int

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
            accessibility=result.accessibility,
            accessibility_path=(
                str(result.accessibility_path)
                if result.accessibility_path is not None
                else None
            ),
            headers=result.headers,
            headers_path=(
                str(result.headers_path)
                if result.headers_path is not None
                else None
            ),
            storage_state=result.storage_state,
            storage_state_path=(
                str(result.storage_state_path)
                if result.storage_state_path is not None
                else None
            ),
            synthesized_spec=result.synthesized_spec,
            action_correlation=result.action_correlation,
            heal_confident=sum(1 for e in result.heal_events if e.used),
            heal_uncertain=sum(1 for e in result.heal_events if not e.used),
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
        # Self-healing outcome, only when tier 3 actually healed something this run
        # (§2/§2d). Confident heals filled a field; uncertain matches were flagged
        # for review and left the field null (never silently guessed). Counts only,
        # never the matched text (§2h). Stays quiet on an ordinary run.
        if self.heal_confident or self.heal_uncertain:
            lines.append(
                f"  self-healing:  {self.heal_confident} confident, "
                f"{self.heal_uncertain} uncertain (flagged for review)"
            )
        # Console counts, only when the console was captured (§2c). Counts only —
        # never message text — so nothing sensitive surfaces here (§2h).
        if self.console is not None:
            c = self.console
            lines.append(
                f"  console:       {c.messages} messages "
                f"({c.errors} errors, {c.page_errors} uncaught)"
            )
        # Accessibility node count, only when the a11y tree was captured (§2c).
        if self.accessibility is not None:
            lines.append(f"  a11y nodes:    {self.accessibility.nodes}")
        # Response-header fingerprint, only when captured (§2c). Count + security-
        # header presence, never values (§2h — some headers are secret shapes).
        if self.headers is not None:
            h = self.headers
            yn = {True: "yes", False: "no"}
            lines.append(f"  headers:       {h.count} captured")
            lines.append(
                f"    security:    CSP {yn[h.csp]}, HSTS {yn[h.hsts]}, "
                f"X-Frame-Options {yn[h.x_frame_options]}"
            )
        # Client-side storage-state summary, only when captured (§2c). Counts of
        # cookies / localStorage entries / origins; the redacted entries ride on
        # the structured signal object, and raw values stay local-only (§2h).
        if self.storage_state is not None:
            s = self.storage_state
            lines.append(
                f"  storage:       {s.cookie_count} cookies, "
                f"{s.local_storage_count} localStorage entries "
                f"({s.origin_count} origins)"
            )
        # Synthesized-spec counts, only when a HAR was captured and clustered into
        # endpoints (§2b layer 4). Counts only — the templated paths stay in the
        # local-only OpenAPI document, never surfaced here (§2h).
        if self.synthesized_spec is not None:
            syn = self.synthesized_spec
            lines.append(
                f"  api synth:     {syn.endpoint_count} endpoints synthesized "
                f"from {syn.request_count} requests"
            )
        # Action-correlation counts, only when a HAR + checkpoints were captured and
        # something was attributable (§2b layer 5). Counts only — the per-action
        # templated paths stay in the local-only correlation document (§2h). Worded
        # "likely" to hold §2b's bounded claim: a time window, not proven causation.
        if self.action_correlation is not None:
            corr = self.action_correlation
            lines.append(
                f"  api actions:   {corr.request_count} requests likely triggered "
                f"by {corr.action_count} actions"
            )
        # Capture lines: only shown when something was captured, so an ordinary run
        # stays quiet; named raw + local so it's clear this isn't shared output (§2h).
        if self.har_path is not None:
            lines.append(f"  captured:      raw HAR (local-only) {self.har_path}")
        if self.console_log_path is not None:
            lines.append(
                f"  captured:      raw console log (local-only) {self.console_log_path}"
            )
        if self.accessibility_path is not None:
            lines.append(
                f"  captured:      raw a11y tree (local-only) {self.accessibility_path}"
            )
        if self.headers_path is not None:
            lines.append(
                f"  captured:      raw headers (local-only) {self.headers_path}"
            )
        if self.storage_state_path is not None:
            lines.append(
                "  captured:      raw storage state (local-only) "
                f"{self.storage_state_path}"
            )
        if (
            self.synthesized_spec is not None
            and self.synthesized_spec.doc_path is not None
        ):
            lines.append(
                "  captured:      synthesized OpenAPI (local-only) "
                f"{self.synthesized_spec.doc_path}"
            )
        if (
            self.action_correlation is not None
            and self.action_correlation.doc_path is not None
        ):
            lines.append(
                "  captured:      action correlation (local-only) "
                f"{self.action_correlation.doc_path}"
            )
        return "\n".join(lines)
