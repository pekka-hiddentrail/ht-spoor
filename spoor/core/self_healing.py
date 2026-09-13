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
  being silently filled with a guess (§2, reliability-first). A confident heal
  also *re-anchors* the stored fingerprint to the healed element's current shape,
  so successive redesigns each heal from the most recent shape rather than only
  the first; an uncertain match never re-anchors.

When the browser tier supplies a `screenshotter`, capture and healing gain the
perceptual-hash *visual* signal (§2 tier table): `remember` stores the element's
cropped-screenshot hash alongside its DOM print, and `attempt` lets `heal`
re-score its top DOM front-runners by appearance — so a low-text element (an icon,
a logo) that re-renders the same is re-resolved even when its class/attrs churned
below the DOM-only bar. Tier 1 leaves the screenshotter None, so healing is
DOM-only and unchanged.

- `remember_container(item, row)` / `attempt_container(item, page)` — the same
  two-phase mechanic for a listing's **row container** (the `item` selector). On a
  successful run the row's shape is fingerprinted (text-agnostic); when a later run
  finds the `item` selector matching nothing, `attempt_container` re-resolves the
  repeating row group. It heals only when exactly one coherent sibling group of two
  or more members scores confidently — refusing (zero rows, flagged uncertain) when
  no repeating group is found (a lone look-alike is never promoted to a one-row
  listing) or when two distinct groups are both confident (ambiguous look-alikes
  are never guessed between). Reliability-first (§2, §1): better total data loss
  surfaced for review than a confidently-fabricated listing.

Every heal attempt that finds a fingerprint and a candidate records a `HealEvent`
carrying the field name and the winning confidence — never the matched text
(§2h) — for the run summary. `used` distinguishes a confident heal (field filled)
from an uncertain match (flagged for review). §0 holds: the same generic engine
runs for every target; only runtime-learned fingerprints differ.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from parsel import Selector

from spoor.core.fingerprint_cache import FingerprintCache
from spoor.core.healing import (
    ElementFingerprint,
    find_container_groups,
    fingerprint,
    heal,
)

# Sentinel "field name" for a listing's row-container fingerprint. Empty because no
# real field is (YAML keys are non-empty), so the container key `f"{item}::"` can
# never collide with a field key `f"{item}::{name}"`.
_CONTAINER_FIELD = ""

# A screenshotter maps a resolved/candidate element to a perceptual hash of its
# cropped screenshot, or None when no screenshot could be taken. The browser tier
# supplies one bound to the live page (§2 tier table); tier 1 and directly-invoked
# healers leave it None, so healing is DOM-only and behaves exactly as before.
Screenshotter = Callable[[Selector], int | None]


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
    screenshotter: Screenshotter | None = None

    def _capture(self, element: Selector, *, include_text: bool) -> ElementFingerprint:
        """Fingerprint `element`, attaching a visual hash when a screenshotter is set.

        The browser tier's screenshotter renders the element and returns a
        perceptual hash of its crop (or None on any failure — capture is
        opportunistic and never fails the extraction, §2c). Without a screenshotter
        (tier 1, or a directly-invoked healer) the print is DOM-only, exactly as
        before. Shared by capture and confident re-anchoring so both store the same
        shape of print.
        """
        fp = fingerprint(element, include_text=include_text)
        if self.screenshotter is not None:
            visual_hash = self.screenshotter(element)
            if visual_hash is not None:
                fp = replace(fp, visual_hash=visual_hash)
        return fp

    def remember(
        self, field_name: str, element: Selector, *, item_selector: str | None = None
    ) -> None:
        """Record the element a field's selector resolved to, for future heals.

        `item_selector` set = item-mode (a listing row): the fingerprint is keyed
        per `(item_selector, field_name)` and captured **text-agnostic**, because a
        listing's rows share structure but differ in text, so text is per-row noise
        rather than field identity (see `fingerprint`'s `include_text`). Left None
        for single-record configs, where text is a strong, stable anchor. When the
        browser tier supplied a screenshotter, the element's cropped-screenshot
        perceptual hash is captured too (§2 tier table), so a later run can heal on
        appearance when the markup churns.
        """
        self.cache.put(
            self._key(field_name, item_selector),
            self._capture(element, include_text=item_selector is None),
        )

    def attempt(
        self, field_name: str, root: Selector, *, item_selector: str | None = None
    ) -> Selector | None:
        """Heal a field whose selector matched nothing; None if not confidently.

        Returns the healed element only when the best candidate clears the
        confidence threshold. A sub-threshold best candidate is recorded as an
        uncertain match (surfaced in the summary) and None is returned — the field
        is never silently filled with a low-confidence guess (§2). Returns None
        with no event when nothing was remembered for the field or the page (in
        item mode, the row subtree) offers no candidates.

        Heals only against a **prior-run** fingerprint (`get_persisted`), never one
        remembered earlier in the *same* run. In item mode this is what stops a
        field present in one row from being fabricated onto a sibling row that
        legitimately lacks it: the sibling's absent selector finds no prior print
        of its own to heal from within this run (§2, §1).

        On a **confident** heal the stored fingerprint is *re-anchored* to the
        healed element's current shape, so a later run heals from the most recent
        shape rather than only the first — markup drift is absorbed one healable
        step at a time. An uncertain match never re-anchors: it would overwrite the
        good anchor with a guess. The re-anchor is a `put` (visible only to a future
        run's `get_persisted` snapshot), so it does not change what other fields or
        rows heal against within this same run.
        """
        key = self._key(field_name, item_selector)
        stored = self.cache.get_persisted(key)
        if stored is None:
            return None
        candidates = list(root.css("*"))
        result = heal(stored, candidates, visual_lookup=self._visual_lookup(candidates))
        if result is None:
            return None
        self.events.append(
            HealEvent(field=field_name, confidence=result.score, used=result.confident)
        )
        if not result.confident:
            return None
        self.cache.put(
            key, self._capture(result.element, include_text=item_selector is None)
        )
        return result.element

    def _visual_lookup(
        self, candidates: list[Selector]
    ) -> Callable[[int], int | None] | None:
        """A by-index screenshot-hash lookup over `candidates`, or None.

        Returns None (so `heal` stays a pure DOM heal) unless a screenshotter is
        set; otherwise wraps it so `heal` can screenshot a candidate on demand for
        its bounded visual re-rank (see `healing.heal`).
        """
        shot = self.screenshotter
        if shot is None:
            return None
        return lambda index: shot(candidates[index])

    def remember_container(self, item_selector: str, row: Selector) -> None:
        """Fingerprint a listing's row container on a successful resolve.

        Called with the first matched row when `item_selector` resolves, so a later
        run can re-find the row group if the selector breaks. Text-agnostic (rows
        share structure but differ in text), keyed by the container sentinel so it
        never collides with a field. `put` no-ops when unchanged, so re-running a
        stable listing writes nothing.
        """
        self.cache.put(
            self._key(_CONTAINER_FIELD, item_selector),
            fingerprint(row, include_text=False),
        )

    def attempt_container(
        self, item_selector: str, page: Selector
    ) -> list[Selector] | None:
        """Heal a broken row-container selector; None unless one group is confident.

        The `item` selector matched nothing, so re-resolve the repeating row group
        by scoring every element on the page against the container fingerprint a
        **prior** run recorded (`get_persisted`, never one remembered this run — the
        same fabrication guard as field healing) and grouping the confident matches
        into coherent sibling groups of two or more (`find_container_groups`).

        Heals only when **exactly one** such group qualifies: it returns that group's
        rows, records a confident `HealEvent`, and re-anchors the container print to
        the first healed row's current shape (drift absorbed one step at a time, as
        for fields). Refuses otherwise — zero qualifying groups (no repeating group:
        a lone look-alike is not a listing) or two-plus (ambiguous look-alikes we
        will not guess between) — returning None so the listing yields no records
        rather than a fabricated one (§2, §1). A refusal records an uncertain
        `HealEvent` **only when some element actually crossed the confidence
        threshold** — a genuinely reviewable "I saw a listing-shaped thing but could
        not safely use it." When nothing on the page resembled a row at all, no
        event is recorded: that is a legitimately-empty or wholly-different page, not
        a broken listing to cry wolf over.

        Returns None with no event when nothing was remembered for the container or
        the page has no candidate elements at all.
        """
        key = self._key(_CONTAINER_FIELD, item_selector)
        stored = self.cache.get_persisted(key)
        if stored is None:
            return None
        candidates = list(page.css("*"))
        if not candidates:
            return None
        match = find_container_groups(stored, candidates)
        if len(match.groups) == 1:
            rows = list(match.groups[0])
            self.events.append(
                HealEvent(field=item_selector, confidence=match.best_score, used=True)
            )
            self.cache.put(key, fingerprint(rows[0], include_text=False))
            return rows
        # Zero groups (no repeating group) or 2+ (ambiguous): refuse. Flag it for
        # review only if something crossed the bar; stay silent on a page where
        # nothing looked like a row (a legitimately-empty listing, not a break).
        if match.has_confident:
            self.events.append(
                HealEvent(field=item_selector, confidence=match.best_score, used=False)
            )
        return None

    @staticmethod
    def _key(field_name: str, item_selector: str | None) -> str:
        """Cache key for a field: bare in single-record mode, namespaced by the
        `item` selector in item mode so a listing's fields never collide with a
        single-record field (or another listing's) of the same name."""
        return field_name if item_selector is None else f"{item_selector}::{field_name}"

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
