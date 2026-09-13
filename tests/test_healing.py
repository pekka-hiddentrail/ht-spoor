"""Unit tests for the tier-3 scoring engine (ROADMAP.md §2, §5.3).

Covers fingerprint capture, the similarity score's boundaries and monotonicity,
and `heal`'s selection / confidence / explainability contract. The statistical
≥95% mutation-corpus bar lives in test_healing_mutation.py.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from parsel import Selector

from spoor.core.healing import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ElementFingerprint,
    candidate_elements,
    find_container_groups,
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


# --- find_container_groups (row-container healing) ------------------------

_NAV = '<nav><a class="menu" href="#">Home</a><a class="menu" href="#">About</a></nav>'


def _container_row(name: str, price: str, *, li_class: str = "card") -> str:
    return (
        f'<li class="{li_class}">'
        f'<a class="name">{name}</a><span class="price">{price}</span></li>'
    )


def _listing(ul_class: str, rows: list[tuple[str, str]]) -> str:
    cells = "".join(_container_row(n, p) for n, p in rows)
    return f'<ul class="{ul_class}">{cells}</ul>'


def _container_page(*sections: str) -> str:
    return "<html><body>" + "".join(sections) + "</body></html>"


_STORED_ROWS = [("Alpha", "10"), ("Beta", "20"), ("Gamma", "30")]


def _stored_container() -> ElementFingerprint:
    page = _container_page(_NAV, _listing("products", _STORED_ROWS))
    # Container fingerprints are text-agnostic, as the Healer captures them.
    return fingerprint(
        Selector(text=page).css("ul.products > li")[0], include_text=False
    )


def test_find_container_groups_finds_the_one_repeating_group_after_rename() -> None:
    stored = _stored_container()
    # Container class renamed (products -> grid); the rows survive as a group.
    redesign = _container_page(_NAV, _listing("grid", _STORED_ROWS))
    match = find_container_groups(stored, candidate_elements(redesign))
    assert len(match.groups) == 1
    assert len(match.groups[0]) == len(_STORED_ROWS)
    assert match.best_score >= DEFAULT_CONFIDENCE_THRESHOLD


def test_find_container_groups_returns_both_when_two_groups_match() -> None:
    stored = _stored_container()
    # Two structurally-identical listings both survive the rename -> ambiguous.
    redesign = _container_page(
        _NAV,
        _listing("grid", _STORED_ROWS),
        _listing("recommended", [("D", "4"), ("E", "5")]),
    )
    match = find_container_groups(stored, candidate_elements(redesign))
    assert len(match.groups) == 2


def test_find_container_groups_gates_out_a_lone_lookalike() -> None:
    stored = _stored_container()
    # A single row-like element is not a repeating group: no group of >= 2.
    redesign = _container_page(_NAV, _listing("grid", [("Solo", "99")]))
    match = find_container_groups(stored, candidate_elements(redesign))
    assert match.groups == ()
    # ...even though that lone element itself scores confidently.
    assert match.best_score >= DEFAULT_CONFIDENCE_THRESHOLD


def test_find_container_groups_groups_by_parent_not_just_tag() -> None:
    stored = _stored_container()
    # Same tag+class rows split across two parents are two groups, not one.
    redesign = _container_page(
        _NAV,
        _listing("grid", [("A", "1"), ("B", "2")]),
        _listing("other", [("C", "3"), ("D", "4")]),
    )
    match = find_container_groups(stored, candidate_elements(redesign))
    assert len(match.groups) == 2
    assert all(len(group) == 2 for group in match.groups)


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


# --- Visual (perceptual-hash) signal --------------------------------------
# The visual hash is an opaque 64-bit int here; visual.py's own tests cover the
# hashing. These exercise how `score`/`heal` *blend* it: only when both prints
# carry one, and re-ranking the DOM front-runners at heal time.
_STORED_VISUAL = 0xABCD1234ABCD1234
_ALL_ONES_64 = (1 << 64) - 1

# A low-text leaf (an <img>) whose class/attrs churn and which gains a wrapper in
# the redesign — calibrated so the DOM-only heal lands *below* the confidence bar.
_IMG_ORIGINAL = (
    '<html><body><img class="brand-logo" data-v="1" src="/a.png"></body></html>'
)
_IMG_REDESIGN = (
    '<html><body><div><img class="hero" data-v="2" src="/b.png"></div></body></html>'
)


def _img_index(candidates: list) -> int:
    return next(i for i, c in enumerate(candidates) if c.root.tag == "img")


def test_visual_signal_is_skipped_when_the_candidate_has_no_hash() -> None:
    stored = replace(_fp(_IMG_ORIGINAL, "img"), visual_hash=_STORED_VISUAL)
    candidate = _fp(_IMG_REDESIGN, "img")  # no visual hash
    # With no candidate hash the visual signal drops out entirely, so the score is
    # exactly the DOM-only score a candidate-without-hash would get from any stored
    # print (whether or not the stored one happens to carry a visual hash).
    dom_only_stored = _fp(_IMG_ORIGINAL, "img")
    assert score(stored, candidate) == score(dom_only_stored, candidate)


def test_a_matching_visual_hash_raises_the_score() -> None:
    stored = replace(_fp(_IMG_ORIGINAL, "img"), visual_hash=_STORED_VISUAL)
    dom_only = score(_fp(_IMG_ORIGINAL, "img"), _fp(_IMG_REDESIGN, "img"))
    matched = replace(_fp(_IMG_REDESIGN, "img"), visual_hash=_STORED_VISUAL)
    assert score(stored, matched) > dom_only  # identical appearance pulls it up


def test_a_clashing_visual_hash_lowers_the_score() -> None:
    stored = replace(_fp(_IMG_ORIGINAL, "img"), visual_hash=_STORED_VISUAL)
    dom_only = score(_fp(_IMG_ORIGINAL, "img"), _fp(_IMG_REDESIGN, "img"))
    clash_hash = _STORED_VISUAL ^ _ALL_ONES_64
    clashing = replace(_fp(_IMG_REDESIGN, "img"), visual_hash=clash_hash)
    assert score(stored, clashing) < dom_only  # a different look drags it down


def test_dom_only_heal_of_the_churned_logo_is_uncertain() -> None:
    # Baseline: without the visual signal the churned logo is a sub-threshold
    # (uncertain) match — this is the gap the visual signal exists to close.
    stored = _fp(_IMG_ORIGINAL, "img")
    result = heal(stored, candidate_elements(_IMG_REDESIGN))
    assert result is not None
    assert result.element.root.tag == "img"
    assert not result.confident


def test_a_matching_visual_hash_lifts_the_heal_to_confident() -> None:
    stored = replace(_fp(_IMG_ORIGINAL, "img"), visual_hash=_STORED_VISUAL)
    candidates = candidate_elements(_IMG_REDESIGN)
    img = _img_index(candidates)
    # The live page would screenshot each front-runner; here the img re-renders
    # the same (its stored hash) and everything else has no capturable crop.
    lookup = lambda i: _STORED_VISUAL if i == img else None  # noqa: E731
    result = heal(stored, candidates, visual_lookup=lookup)
    assert result is not None
    assert result.element.root.tag == "img"
    assert result.confident  # DOM-uncertain + identical appearance -> confident


def test_visual_rerank_promotes_the_visually_correct_candidate() -> None:
    # Two DOM-identical images; DOM scoring ties and would keep the earlier one.
    # The visual signal (the second one looks like the stored logo, the first does
    # not) promotes the correct one.
    stored = replace(_fp(_IMG_ORIGINAL, "img"), visual_hash=_STORED_VISUAL)
    page = (
        '<html><body>'
        '<img class="hero" data-v="2" src="/b.png">'      # decoy, document order 0
        '<img class="hero" data-v="2" src="/b.png">'      # the real logo
        '</body></html>'
    )
    candidates = candidate_elements(page)
    imgs = [i for i, c in enumerate(candidates) if c.root.tag == "img"]
    decoy, correct = imgs[0], imgs[1]
    lookup = lambda i: (  # noqa: E731
        _STORED_VISUAL if i == correct
        else _STORED_VISUAL ^ _ALL_ONES_64 if i == decoy
        else None
    )
    result = heal(stored, candidates, visual_lookup=lookup)
    assert result is not None
    assert result.index == correct


def test_visual_lookup_is_ignored_without_a_stored_visual_hash() -> None:
    # A stored print with no visual hash never triggers the visual pass, even if a
    # lookup is offered (a candidate hash alone must not manufacture the signal).
    stored = _fp(_IMG_ORIGINAL, "img")  # no visual hash
    candidates = candidate_elements(_IMG_REDESIGN)
    called = False

    def lookup(_: int) -> int | None:
        nonlocal called
        called = True
        return _STORED_VISUAL

    heal(stored, candidates, visual_lookup=lookup)
    assert not called  # the visual pass never ran
