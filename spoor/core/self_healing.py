"""The tier-3 healer: capture on success, heal on failure (ROADMAP.md §2, §2d).

Ties the three tier-3 pieces into one run-scoped object the extraction path uses:
the scoring engine (`healing`), the persistent per-domain fingerprint cache
(`fingerprint_cache`), and the run-summary events (§2d). The dispatcher creates
one `Healer` per run, hands it to the resolvers, and persists it at the end.

Flow, per §2 ("fingerprint capture on first success, scored matching on
failure"):

- `remember(field, element)` — the field's selector resolved; fingerprint the
  element so a later run can heal against it.
- `attempt(field, root)` — the selector matched nothing; if a fingerprint was
  remembered, score the page's candidates and return the winning element *only
  when confident*. A best candidate below the threshold is recorded as an
  uncertain match and `None` is returned, so the field stays null rather than
  being silently filled with a guess (§2, reliability-first).

Every heal attempt that finds a fingerprint and a candidate records a `HealEvent`
carrying the field name and the winning confidence — never the matched text
(§2h) — for the run summary. `used` distinguishes a confident heal (field filled)
from an uncertain match (flagged for review). §0 holds: the same generic engine
runs for every target; only runtime-learned fingerprints differ.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from parsel import Selector

from spoor.core.fingerprint_cache import FingerprintCache
from spoor.core.healing import fingerprint, heal


@dataclass(frozen=True)
class HealEvent:
    """One tier-3 heal attempt, for the run summary (§2d).

    `confidence` is the winning candidate's score; `used` is whether it cleared
    the confidence threshold and filled the field (True) or was flagged an
    uncertain match for review, leaving the field null (False). Field name and
    score only — never the matched text (§2h).
    """

    field: str
    confidence: float
    used: bool


@dataclass
class Healer:
    """Run-scoped tier-3 orchestrator over a per-domain fingerprint cache."""

    cache: FingerprintCache
    events: list[HealEvent] = field(default_factory=list)

    def remember(self, field_name: str, element: Selector) -> None:
        """Record the element a field's selector resolved to, for future heals."""
        self.cache.put(field_name, fingerprint(element))

    def attempt(self, field_name: str, root: Selector) -> Selector | None:
        """Heal a field whose selector matched nothing; None if not confidently.

        Returns the healed element only when the best candidate clears the
        confidence threshold. A sub-threshold best candidate is recorded as an
        uncertain match (surfaced in the summary) and None is returned — the field
        is never silently filled with a low-confidence guess (§2). Returns None
        with no event when nothing was remembered for the field or the page offers
        no candidates.
        """
        stored = self.cache.get(field_name)
        if stored is None:
            return None
        candidates = list(root.css("*"))
        result = heal(stored, candidates)
        if result is None:
            return None
        self.events.append(
            HealEvent(field=field_name, confidence=result.score, used=result.confident)
        )
        return result.element if result.confident else None

    def persist(self) -> None:
        """Persist any newly-remembered fingerprints to the per-domain cache."""
        self.cache.save()

    @property
    def confident_count(self) -> int:
        """How many fields tier 3 healed confidently this run."""
        return sum(1 for event in self.events if event.used)

    @property
    def uncertain_count(self) -> int:
        """How many uncertain matches tier 3 flagged for review this run."""
        return sum(1 for event in self.events if not event.used)
