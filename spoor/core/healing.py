"""Tier 3 self-healing: scored element matching, no model call (ROADMAP.md §2, §5.3).

Per §1 the highest-priority piece of engineering in the plan. When a resolved
element's selector later matches nothing (the site changed its markup), tier 3
re-finds the element by scoring every candidate on the page against a
*fingerprint* captured while the selector still worked. The scoring algorithm is
**written from scratch here** — Spoor takes no dependency on Healenium and vendors
none of its code; Healenium's published, Apache-2.0 core approach (a DOM
fingerprint + weighted similarity, *not* the commercial "Pro" tier) is only a
conceptual reference. What runs is entirely this module's own implementation: a
weighted blend of tag, id, class, other-attribute, inner-text, structural
(ancestor-chain + sibling-position), descendant-composition, and — when a
screenshot is available — perceptual-hash *visual* similarity. No LLM, no network
— deterministic arithmetic over the DOM and a cropped screenshot (§2 tier table:
"DOM fingerprint + attribute similarity + perceptual-hash on a cropped
screenshot", "no model call").

The descendant-composition signal (a multiset of the element's descendant tag
names) is what gives *container* elements — a listing row, a card — a stable
identity: a leaf field element (a price span, a heading) has no descendants, so
the signal is simply not part of its blend and leaf-element scoring is unchanged;
but a row whose identity is "a thing containing a link and a price" is
distinguished from a look-alike sibling group (e.g. a nav list) by *what it
contains*, which survives a class rename on the container itself.

Reliability-first (§2, §1). `heal` never silently guesses:

- A best candidate scoring at/above `threshold` is a confident auto-heal.
- A best candidate below `threshold` but above zero is returned flagged
  `confident=False` — an "uncertain match" a caller surfaces for manual review
  (§2d), never used as if certain.
- No candidates at all yields `None`.

Every result carries its winning score *and* the runner-up candidates it
considered, so "why did it heal to this element" is always answerable straight
from the `HealResult` (§2), not a separately bolted-on log.

§0: nothing here is site-specific — the same generic similarity math runs for
every target. This module is the pure scoring engine over static DOM (parsel).
It is wired into live runs by `self_healing.py` (the run-scoped `Healer`) and
`fingerprint_cache.py` (cross-run persistence), and reached from the dispatcher
in `extract.py`, for both single-record and item-mode (listing) configs, and a
confident heal re-anchors the stored fingerprint to the healed shape so drift
across successive redesigns is absorbed one step at a time. A broken row
*container* (the `item` selector matching nothing) is healed too, by
`find_container_groups` here plus the `Healer`'s single-group/ambiguity decision:
the descendant-composition signal gives a container the identity a leaf print
lacked, and a repeating-group gate refuses to fabricate a listing from a lone
look-alike or ambiguous groups (§2, §1). The visual signal (`spoor/core/visual.py`,
a from-scratch perceptual/difference hash of a cropped screenshot) rides with the
browser tier: `heal` re-scores its top DOM front-runners with visual similarity
when the stored print carries a screenshot hash and the caller supplies a
screenshotting `visual_lookup`, so a low-text element (an icon, a logo) that
re-renders the same is re-resolved even when its class/attrs churned below the
DOM-only bar. The merge-blocking ≥95% mutation corpus that guards this math lives
in tests/ under `pytest -m mutation` (§5.3).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

from parsel import Selector

from spoor.core.visual import visual_similarity

# Default "safe to auto-resolve" confidence threshold (§2). Tunable per call; a
# best candidate scoring below this but above zero is flagged uncertain, not used.
# 0.6 keeps a comfortable margin over the "half the signal survived" midpoint so a
# heal that lost most of an element's identity is not quietly trusted.
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# Per-signal weights for the blended similarity score. Weighting is deliberately
# tilted toward the signals that *survive* markup churn and carry identity: inner
# text (human-visible, stable), a stable id when present, the tag, and structural
# position. Classes and other attributes are exactly the volatile signals a
# redesign churns — the ones tier 3 exists to survive — so they contribute but
# never dominate; weighting them heavily would make confidence collapse in the
# precise case healing is for (a class rename). tag and structure are always
# compared; id/classes/attrs/text only count toward the blend when the stored
# element actually had that signal, so an element with (say) no id is not
# penalised for candidates that have one — the score is a weighted mean over the
# *applicable* signals only.
# Descendant composition is likewise applicable only when the stored element had
# descendants: a leaf field (a price span, a heading) has none, so the signal drops
# out and leaf scoring is unchanged; it is weighted heavily because for a
# *container* (a listing row, a card) "what it contains" is its most stable
# identity, and is exactly what survives a class rename on the container itself —
# the case container healing exists for.
_W_TAG = 1.5
_W_ID = 3.0
_W_CLASSES = 1.0
_W_ATTRS = 1.0
_W_TEXT = 3.0
_W_ANCESTORS = 1.5
_W_SIBLING = 0.5
_W_DESCENDANTS = 2.0
# Visual (perceptual-hash) similarity — applicable only when *both* the stored
# print and the candidate carry a screenshot hash (see `score`). Weighted as a
# strong signal because for a low-text element (an icon, a logo, an image) its
# rendered appearance is a more stable identity than its churning class/attrs —
# exactly the case the visual signal exists for — while still one voice among
# several, so a coincidental look-alike cannot single-handedly force a heal.
_W_VISUAL = 2.0

# How many runner-up candidates to retain for the "why did it heal here" record.
_MAX_RUNNERS_UP = 4
# How many of the top DOM-scored candidates to re-score with the visual signal at
# heal time (see `heal`). Bounded because each one costs a live screenshot; the
# visually-correct element is nigh-always among the DOM front-runners, so a small
# window re-ranks usefully without screenshotting the whole page.
_VISUAL_RERANK_K = 5


@dataclass(frozen=True)
class ElementFingerprint:
    """A snapshot of an element's identity, captured while its selector worked.

    Everything tier 3 scores against later. `attrs` excludes id and class (which
    have their own dedicated, higher-weighted fields); `ancestors` is the chain of
    ancestor tag names from the root down to the element's parent; `sibling_index`
    is the element's position among same-tag siblings under its parent.
    `descendants` is the multiset of the element's descendant tag names, as a sorted
    tuple of `(tag, count)` pairs — a leaf element's is empty. It is what gives a
    *container* (a listing row, a card) an identity that survives a class rename on
    the container itself; a leaf field carries none and is scored exactly as before.
    `visual_hash` is a 64-bit perceptual (difference) hash of the element's cropped
    screenshot, or None when no screenshot was taken — it is captured only by the
    browser tier (a hash needs rendered pixels), so a DOM-only (tier-1) fingerprint
    always has None here and is scored exactly as before. It is the identity a
    low-text element (an icon, a logo, an image) keeps when its markup churns but
    its appearance does not (§2 tier table).
    """

    tag: str
    element_id: str
    classes: frozenset[str]
    attrs: frozenset[tuple[str, str]]
    text: str
    ancestors: tuple[str, ...]
    sibling_index: int
    descendants: tuple[tuple[str, int], ...]
    visual_hash: int | None = None


@dataclass(frozen=True)
class ScoredCandidate:
    """One candidate element's index and its similarity score to the fingerprint."""

    index: int
    score: float


@dataclass(frozen=True)
class HealResult:
    """The outcome of a heal: the winning candidate, its score, and the field.

    `confident` is whether `score` met the threshold. `runners_up` are the next
    best candidates considered (descending), so the choice is always explainable
    (§2). `element` is the winning parsel `Selector`; it is excluded from equality
    so `HealResult`s compare by their decision, not by Selector identity.
    """

    index: int
    score: float
    confident: bool
    runners_up: tuple[ScoredCandidate, ...]
    element: Selector = field(compare=False)

    def explain(self) -> str:
        """A one-line, human-readable account of why this candidate won (§2)."""
        verdict = "confident" if self.confident else "UNCERTAIN"
        runners = (
            ", ".join(f"#{r.index}={r.score:.3f}" for r in self.runners_up) or "none"
        )
        return (
            f"healed to candidate #{self.index} score={self.score:.3f} ({verdict}); "
            f"runners-up: {runners}"
        )


def _normalize_text(value: str) -> str:
    """Collapse runs of whitespace to single spaces and strip — for stable text
    comparison across markup reflow."""
    return " ".join(value.split())


def fingerprint(selector: Selector, *, include_text: bool = True) -> ElementFingerprint:
    """Capture an element's fingerprint from a parsel `Selector` wrapping it.

    `include_text` captures the element's inner text as an identity signal — right
    for single-record healing, where text is a strong, stable anchor. Pass
    `include_text=False` for **item-mode** (listing) fingerprints: a listing's rows
    are structurally identical but differ in text, so text is per-row noise, not
    identity — a text-agnostic fingerprint (empty `text`, so the scorer skips that
    signal) is what generalizes a field's identity across every row.
    """
    root = selector.root
    # A parsel Selector can wrap a text/comment node or a bare string; only real
    # elements have a str tag we can fingerprint.
    tag = getattr(root, "tag", None)
    if not isinstance(tag, str):
        raise ValueError("fingerprint() requires a Selector wrapping an element")

    attrib = dict(getattr(root, "attrib", {}))
    element_id = attrib.pop("id", "")
    class_value = attrib.pop("class", "")
    classes = frozenset(class_value.split())
    attrs = frozenset((k, v) for k, v in attrib.items())

    text = _normalize_text("".join(root.itertext())) if include_text else ""

    ancestors = tuple(
        anc.tag
        for anc in reversed(list(root.iterancestors()))
        if isinstance(anc.tag, str)
    )

    parent = root.getparent()
    if parent is None:
        sibling_index = 0
    else:
        same_tag = [child for child in parent if child.tag == tag]
        sibling_index = same_tag.index(root)

    # Multiset of descendant element tag names (comments/PIs have non-str tags and
    # are skipped). Sorted to a canonical tuple so equal structures fingerprint
    # equally regardless of traversal order. Empty for a leaf element.
    descendant_counts = Counter(
        desc.tag for desc in root.iterdescendants() if isinstance(desc.tag, str)
    )
    descendants = tuple(sorted(descendant_counts.items()))

    return ElementFingerprint(
        tag=tag,
        element_id=element_id,
        classes=classes,
        attrs=attrs,
        text=text,
        ancestors=ancestors,
        sibling_index=sibling_index,
        descendants=descendants,
    )


def _jaccard(a: frozenset[object], b: frozenset[object]) -> float:
    """Jaccard similarity of two sets; 1.0 for two empty sets (nothing to differ)."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _multiset_similarity(
    a: tuple[tuple[str, int], ...], b: tuple[tuple[str, int], ...]
) -> float:
    """Weighted-Jaccard similarity of two tag-count multisets, in [0.0, 1.0].

    `sum(min(count)) / sum(max(count))` over the union of tags: identical
    compositions score 1.0, disjoint ones 0.0, and adding or dropping a descendant
    degrades the score proportionally rather than all-or-nothing. 1.0 for two empty
    multisets (nothing to differ), matching `_jaccard`.
    """
    count_a = dict(a)
    count_b = dict(b)
    tags = count_a.keys() | count_b.keys()
    if not tags:
        return 1.0
    intersection = sum(min(count_a.get(t, 0), count_b.get(t, 0)) for t in tags)
    union = sum(max(count_a.get(t, 0), count_b.get(t, 0)) for t in tags)
    return intersection / union if union else 1.0


def score(stored: ElementFingerprint, candidate: ElementFingerprint) -> float:
    """Blended similarity of `candidate` to `stored`, in [0.0, 1.0] (§2, §5.3).

    A weighted mean over the *applicable* signals: tag and structure always count;
    id/classes/attrs/text/descendants count only when `stored` had them, so an
    element with no id (or a leaf with no descendants) is never penalised for a
    candidate that has one. Deterministic.
    """
    total_weight = 0.0
    weighted = 0.0

    # Tag — always compared.
    total_weight += _W_TAG
    weighted += _W_TAG * (1.0 if stored.tag == candidate.tag else 0.0)

    # id — only when the stored element had one (a strong anchor when present).
    if stored.element_id:
        total_weight += _W_ID
        weighted += _W_ID * (
            1.0 if stored.element_id == candidate.element_id else 0.0
        )

    # Classes — only when the stored element had any.
    if stored.classes:
        total_weight += _W_CLASSES
        weighted += _W_CLASSES * _jaccard(stored.classes, candidate.classes)

    # Other attributes — only when the stored element had any.
    if stored.attrs:
        total_weight += _W_ATTRS
        weighted += _W_ATTRS * _jaccard(stored.attrs, candidate.attrs)

    # Inner text — only when the stored element had any.
    if stored.text:
        total_weight += _W_TEXT
        weighted += _W_TEXT * SequenceMatcher(
            None, stored.text, candidate.text
        ).ratio()

    # Structural context — always compared. Ancestor tag chain similarity plus a
    # softer sibling-position proximity, so reordering degrades rather than breaks.
    total_weight += _W_ANCESTORS
    weighted += _W_ANCESTORS * SequenceMatcher(
        None, stored.ancestors, candidate.ancestors
    ).ratio()

    total_weight += _W_SIBLING
    weighted += _W_SIBLING * (
        1.0 / (1.0 + abs(stored.sibling_index - candidate.sibling_index))
    )

    # Descendant composition — only when the stored element had descendants (a leaf
    # field has none, so this signal is simply absent and leaf scoring is unchanged).
    # For a container it is the identity that survives a rename of the container's
    # own class/id.
    if stored.descendants:
        total_weight += _W_DESCENDANTS
        weighted += _W_DESCENDANTS * _multiset_similarity(
            stored.descendants, candidate.descendants
        )

    # Visual appearance — applicable only when *both* prints carry a screenshot
    # hash. Unlike the other optional signals (gated on the stored element alone),
    # a candidate's hash is computed on demand at heal time for only a handful of
    # front-runners (see `heal`), so most candidates have none; blending it in only
    # when both sides have one keeps every other candidate's score unchanged.
    if stored.visual_hash is not None and candidate.visual_hash is not None:
        total_weight += _W_VISUAL
        weighted += _W_VISUAL * visual_similarity(
            stored.visual_hash, candidate.visual_hash
        )

    return weighted / total_weight if total_weight else 0.0


def heal(
    stored: ElementFingerprint,
    candidates: list[Selector],
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    *,
    visual_lookup: Callable[[int], int | None] | None = None,
) -> HealResult | None:
    """Re-resolve `stored` by scoring every candidate; pick the best (§2, §5.3).

    Returns the highest-scoring candidate as a `HealResult` — `confident` iff its
    score met `threshold` (below but above zero = an uncertain match to surface,
    not use silently) — with the runner-ups it considered so the choice stays
    explainable. Returns `None` only when there are no candidates. Deterministic:
    ties break toward the earlier candidate (stable sort by descending score).

    When `stored` carries a visual hash and `visual_lookup` is supplied (the
    browser tier passes one that screenshots a candidate by index and returns its
    perceptual hash, or None on failure), the top `_VISUAL_RERANK_K` DOM
    front-runners are re-scored with the visual signal blended in and the whole
    field re-sorted, so appearance can promote the visually-correct element over a
    DOM look-alike or lift a shaky DOM match to confident. The visual pass is
    bounded to those few screenshots; the remaining candidates keep their DOM
    score. With no visual hash or no lookup, this is a pure DOM heal, unchanged.
    """
    if not candidates:
        return None
    scored = sorted(
        (
            ScoredCandidate(index=i, score=score(stored, fingerprint(cand)))
            for i, cand in enumerate(candidates)
        ),
        key=lambda sc: (-sc.score, sc.index),
    )
    if stored.visual_hash is not None and visual_lookup is not None:
        scored = _visual_rerank(stored, candidates, scored, visual_lookup)
    best = scored[0]
    return HealResult(
        index=best.index,
        score=best.score,
        confident=best.score >= threshold,
        runners_up=tuple(scored[1 : 1 + _MAX_RUNNERS_UP]),
        element=candidates[best.index],
    )


def _visual_rerank(
    stored: ElementFingerprint,
    candidates: list[Selector],
    scored: list[ScoredCandidate],
    visual_lookup: Callable[[int], int | None],
) -> list[ScoredCandidate]:
    """Re-score the top DOM front-runners with the visual signal, then re-sort all.

    Screenshots at most `_VISUAL_RERANK_K` candidates (via `visual_lookup`), blends
    each one's perceptual hash into its score, and returns the full field re-sorted
    by the updated scores (unscored candidates keep their DOM score). A candidate
    whose screenshot fails (`visual_lookup` returns None) keeps its DOM score.
    Deterministic: ties still break toward the earlier candidate.
    """
    updated: dict[int, float] = {}
    for sc in scored[:_VISUAL_RERANK_K]:
        candidate_hash = visual_lookup(sc.index)
        if candidate_hash is None:
            continue
        enriched = replace(
            fingerprint(candidates[sc.index]), visual_hash=candidate_hash
        )
        updated[sc.index] = score(stored, enriched)
    if not updated:
        return scored
    rescored = [
        ScoredCandidate(index=sc.index, score=updated.get(sc.index, sc.score))
        for sc in scored
    ]
    rescored.sort(key=lambda sc: (-sc.score, sc.index))
    return rescored


def _sibling_group_key(selector: Selector) -> tuple[int, str] | None:
    """Identity of the coherent sibling group `selector` belongs to, or None.

    A "coherent sibling group" is the set of elements that share one parent element
    *and* one tag — a listing's repeating rows are exactly such a group. Keyed by
    `(id(parent), tag)`: `id()` is stable within a single call (the whole parsed
    tree stays referenced for the call's duration, so no id is reused), which is
    all the grouping needs. Returns None for a root element with no parent — a row
    always has a parent, so a parentless element is never a listing row.
    """
    parent = selector.root.getparent()
    if parent is None:
        return None
    return (id(parent), selector.root.tag)


@dataclass(frozen=True)
class ContainerMatch:
    """The confident repeating sibling groups found while healing a row container.

    `groups` are the coherent sibling groups (same parent + tag) whose members all
    scored at/above the threshold, each with **at least two** members — a lone
    confident element is not a repeating group and never appears here. `best_score`
    is the single highest candidate score seen, for the explainable heal event even
    when nothing qualified (§2). `has_confident` is whether *any* candidate cleared
    the threshold, grouped or not — it distinguishes a refusal worth flagging (a
    look-alike crossed the bar but was ambiguous or ungrouped) from a page where
    nothing resembled a row at all (a legitimately-empty or wholly-different page,
    which a caller should pass over silently rather than flag). A caller heals only
    when exactly one group qualified; zero (no repeating group) or more than one
    (ambiguous look-alikes) is a refusal, reliability-first (§2, §1).
    """

    groups: tuple[tuple[Selector, ...], ...] = field(compare=False)
    best_score: float = 0.0
    has_confident: bool = False


def find_container_groups(
    stored: ElementFingerprint,
    candidates: list[Selector],
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> ContainerMatch:
    """Score `candidates` against a container fingerprint and group the confident.

    Every candidate is scored **text-agnostic** (a listing's rows share structure
    but differ in text, so the container print carries no text either); those at or
    above `threshold` are grouped into coherent sibling groups (`_sibling_group_key`)
    and only groups of two or more members are kept. Deterministic: members keep
    document order (candidates arrive in document order) and groups keep the order
    of their first member. This is the pure grouping engine; the single-group /
    ambiguity / re-anchor decisions live in the `Healer` (§0: no site knowledge).
    """
    best_score = 0.0
    has_confident = False
    confident: dict[tuple[int, str], list[Selector]] = {}
    for candidate in candidates:
        candidate_score = score(stored, fingerprint(candidate, include_text=False))
        best_score = max(best_score, candidate_score)
        if candidate_score < threshold:
            continue
        has_confident = True
        key = _sibling_group_key(candidate)
        if key is None:
            continue
        confident.setdefault(key, []).append(candidate)
    groups = tuple(
        tuple(members) for members in confident.values() if len(members) >= 2
    )
    return ContainerMatch(
        groups=groups, best_score=best_score, has_confident=has_confident
    )


def candidate_elements(html: str) -> list[Selector]:
    """Every element node in `html`, as parsel `Selector`s — the candidate pool.

    A convenience for callers (and tests) that have raw HTML rather than a parsed
    tree; `heal` itself takes an already-collected candidate list.
    """
    return list(Selector(text=html).css("*"))
