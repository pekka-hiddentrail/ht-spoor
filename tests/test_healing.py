"""Unit tests for the tier-3 scoring engine (ROADMAP.md §2, §5.3).

Covers fingerprint capture, the similarity score's boundaries and monotonicity,
and `heal`'s selection / confidence / explainability contract. The statistical
≥95% mutation-corpus bar lives in test_healing_mutation.py.
"""

from __future__ import annotations

import pytest
from parsel import Selector

from spoor.core.healing import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ElementFingerprint,
    candidate_elements,
    fingerprint,
    heal,
    score,
)

_PAGE = """
<html><body>
  <main>
    <section class="card"><h2 class="title" data-pos="1">Alpha Widget</h2></section>
    <section class="card"><h2 class="title" data-pos="2">Beta Gadget</h2></section>
    <section class="card"><h2 class="title" data-pos="3">Gamma Gizmo</h2></section>
  </main>
</body></html>
"""


def _fp(html: str, css: str) -> ElementFingerprint:
    matched = Selector(text=html).css(css)
    assert matched, f"fixture selector {css!r} matched nothing"
    return fingerprint(matched[0])


# --- fingerprint ----------------------------------------------------------


def test_fingerprint_captures_the_element_identity() -> None:
    fp = _fp(_PAGE, "h2[data-pos='2']")
    assert fp.tag == "h2"
    assert fp.element_id == ""
    assert fp.classes == frozenset({"title"})
    assert fp.attrs == frozenset({("data-pos", "2")})
    assert fp.text == "Beta Gadget"
    assert fp.ancestors == ("html", "body", "main", "section")


def test_fingerprint_separates_id_and_class_from_other_attrs() -> None:
    fp = _fp('<div id="x" class="a b" data-k="v" role="row">hi</div>', "div")
    assert fp.element_id == "x"
    assert fp.classes == frozenset({"a", "b"})
    assert fp.attrs == frozenset({("data-k", "v"), ("role", "row")})


def test_fingerprint_normalizes_whitespace_and_joins_descendant_text() -> None:
    fp = _fp("<p>  hello   <b>brave</b>\n  world </p>", "p")
    assert fp.text == "hello brave world"


def test_fingerprint_sibling_index_counts_same_tag_only() -> None:
    html = "<ul><li>a</li><li>b</li><li>c</li></ul>"
    third = _fp(html, "li:nth-child(3)")
    assert third.sibling_index == 2


def test_fingerprint_rejects_a_non_element_selector() -> None:
    text_node = Selector(text="<p>hi</p>").css("p::text")
    with pytest.raises(ValueError, match="element"):
        fingerprint(text_node[0])


def test_fingerprint_of_a_leaf_element_has_no_descendants() -> None:
    # A field element (a heading with only text) has no descendant elements, so its
    # descendant multiset is empty and the signal is inert for leaf scoring.
    fp = _fp(_PAGE, "h2[data-pos='2']")
    assert fp.descendants == ()


def test_fingerprint_captures_the_descendant_tag_multiset() -> None:
    # A container's descendants are captured as a sorted (tag, count) multiset —
    # the identity a leaf-oriented fingerprint can't see.
    row = "<li class='card'><a>n</a><span>p</span><span>was</span></li>"
    fp = _fp(row, "li")
    assert fp.descendants == (("a", 1), ("span", 2))


# --- score ----------------------------------------------------------------


def test_score_of_identical_fingerprints_is_one() -> None:
    fp = _fp(_PAGE, "h2[data-pos='2']")
    assert score(fp, fp) == pytest.approx(1.0)


def test_score_is_bounded_between_zero_and_one() -> None:
    a = _fp(_PAGE, "h2[data-pos='2']")
    b = _fp("<span class='z' data-q='1'>totally other</span>", "span")
    assert 0.0 <= score(a, b) <= 1.0


def test_a_renamed_class_scores_below_an_exact_match_but_stays_high() -> None:
    stored = _fp(_PAGE, "h2[data-pos='2']")
    renamed = _fp(
        _PAGE.replace('class="title"', 'class="heading"'), "h2[data-pos='2']"
    )
    exact = score(stored, stored)
    healed = score(stored, renamed)
    assert healed < exact
    assert healed >= DEFAULT_CONFIDENCE_THRESHOLD


def test_a_missing_id_does_not_penalise_when_stored_had_none() -> None:
    # Neither stored nor candidate has an id, so the id signal is simply not part
    # of the blend — an identical element still scores a perfect 1.0.
    stored = _fp("<p class='c'>text</p>", "p")
    other = _fp("<p id='surprise' class='c'>text</p>", "p")
    assert stored.element_id == ""
    # The candidate has an id the stored lacks; since stored had none, id is not
    # scored, so the shared tag/class/text/structure still dominate.
    assert score(stored, other) >= DEFAULT_CONFIDENCE_THRESHOLD


def test_descendant_signal_is_inert_when_the_stored_element_is_a_leaf() -> None:
    # Stored is a leaf (no descendants), so a candidate's descendants must not
    # affect the score: two candidates identical except for their children score
    # the same against a leaf stored fingerprint.
    stored = _fp("<span class='price'>10</span>", "span")
    plain = _fp("<span class='price'>10</span>", "span")
    # Empty children so only the descendant multiset differs (text stays "10").
    with_children = _fp("<span class='price'>10<b></b><i></i></span>", "span")
    assert with_children.descendants == (("b", 1), ("i", 1))
    assert score(stored, plain) == pytest.approx(score(stored, with_children))


def test_descendant_composition_distinguishes_a_container_from_a_lookalike() -> None:
    # Two same-tag sibling groups whose class is renamed identically: the product
    # row (a + span) and a nav item (a only). Text, tag, class-shape and structure
    # are held identical across the two candidates so the *only* thing that can
    # separate them is their descendant composition — the gap the signal exists to
    # create. The row that shares the stored container's composition must win.
    stored = _fp("<li class='card'><a>X</a><span></span></li>", "li")
    real_row = _fp("<li class='item'><a>X</a><span></span></li>", "li")
    nav_item = _fp("<li class='item'><a>X</a></li>", "li")
    assert score(stored, real_row) > score(stored, nav_item)


# --- heal -----------------------------------------------------------------


def test_heal_picks_the_correct_element_after_a_class_rename() -> None:
    stored = _fp(_PAGE, "h2[data-pos='2']")
    mutated = _PAGE.replace('class="title"', 'class="heading"')
    result = heal(stored, candidate_elements(mutated))
    assert result is not None
    assert result.confident
    assert "Beta Gadget" in "".join(result.element.css("::text").getall())


def test_heal_returns_none_only_for_an_empty_candidate_pool() -> None:
    stored = _fp(_PAGE, "h2[data-pos='2']")
    assert heal(stored, []) is None


def test_heal_flags_an_uncertain_match_below_threshold() -> None:
    stored = _fp(_PAGE, "h2[data-pos='2']")
    unrelated = "<html><body><footer><small>c</small></footer></body></html>"
    result = heal(stored, candidate_elements(unrelated))
    assert result is not None
    assert not result.confident
    assert result.score > 0.0
    assert "UNCERTAIN" in result.explain()


def test_heal_records_ordered_runners_up() -> None:
    stored = _fp(_PAGE, "h2[data-pos='2']")
    result = heal(stored, candidate_elements(_PAGE))
    assert result is not None
    scores = [r.score for r in result.runners_up]
    assert scores == sorted(scores, reverse=True)
    assert all(s <= result.score for s in scores)


def test_heal_is_deterministic_and_breaks_ties_toward_earlier_candidates() -> None:
    # Two indistinguishable candidates: the earlier index must win, every time.
    stored = _fp("<div class='c'>same</div>", "div")
    twins = candidate_elements(
        "<body><div class='c'>same</div><div class='c'>same</div></body>"
    )
    divs = [s for s in twins if s.root.tag == "div"]
    first = heal(stored, divs)
    assert first is not None
    # Winner is the first div; identity is stable across repeated calls.
    assert first.element.root is divs[0].root
    again = heal(stored, divs)
    assert again is not None
    assert again.index == first.index


def test_threshold_is_tunable_per_call() -> None:
    stored = _fp(_PAGE, "h2[data-pos='2']")
    unrelated = candidate_elements(
        "<html><body><footer><small>c</small></footer></body></html>"
    )
    strict = heal(stored, unrelated, threshold=0.6)
    lenient = heal(stored, unrelated, threshold=0.0)
    assert strict is not None and lenient is not None
    assert not strict.confident
    assert lenient.confident  # any positive score clears a zero threshold
