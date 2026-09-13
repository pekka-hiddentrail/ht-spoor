"""Unit tests for the tier-3 Healer orchestrator (ROADMAP.md §2, §2d).

The Healer ties the scoring engine to the persistent cache and records the run's
heal events. These tests exercise its contract directly: remember-then-heal, the
confident/uncertain split (a weak best candidate never fills the field), the
no-fingerprint and no-candidate short circuits, and that events carry field name
+ confidence only — never matched text (§2h).
"""

from __future__ import annotations

from pathlib import Path

from parsel import Selector

from spoor.core.fingerprint_cache import FingerprintCache
from spoor.core.healing import fingerprint
from spoor.core.self_healing import Healer

_ORIGINAL = (
    "<html><body><main>"
    '<section class="card"><h2 class="title" data-pos="1">Beta Gadget</h2></section>'
    "</main></body></html>"
)
# Class renamed: the unique heading text/tag/structure survive -> confident heal.
_CLASS_RENAMED = _ORIGINAL.replace('class="title"', 'class="heading"')
# Nothing resembling the stored heading -> the best candidate is sub-threshold.
_UNRELATED = (
    "<html><body>"
    '<div class="banner"><p>Totally different unrelated content here</p></div>'
    "<footer><small>copyright notice</small></footer>"
    "</body></html>"
)


def _healer(tmp_path: Path) -> Healer:
    return Healer(FingerprintCache(tmp_path / "d.json"))


def _healer_having_remembered_original(tmp_path: Path) -> Healer:
    """A fresh healer whose cache holds the original fingerprint from a *prior*
    run. Healing reads only persisted (prior-run) fingerprints, so the remember
    and the heal must happen on separate healers over the same cache file — a
    remember-then-heal on one instance would never see its own fingerprint.
    """
    path = tmp_path / "d.json"
    first = Healer(FingerprintCache(path))
    first.remember("name", Selector(text=_ORIGINAL).css("h2.title")[0])
    first.persist()
    return Healer(FingerprintCache(path))


def test_remember_stores_a_fingerprint_retrievable_from_the_cache(
    tmp_path: Path,
) -> None:
    healer = _healer(tmp_path)
    healer.remember("name", Selector(text=_ORIGINAL).css("h2.title")[0])
    assert healer.cache.get("name") is not None


def test_attempt_without_a_stored_fingerprint_returns_none_and_no_event(
    tmp_path: Path,
) -> None:
    healer = _healer(tmp_path)
    root = Selector(text=_CLASS_RENAMED)
    assert healer.attempt("name", root) is None
    assert healer.events == []


def test_a_confident_heal_returns_the_element_and_records_a_used_event(
    tmp_path: Path,
) -> None:
    healer = _healer_having_remembered_original(tmp_path)
    root = Selector(text=_CLASS_RENAMED)
    healed = healer.attempt("name", root)
    assert healed is not None
    healed_text = healed.xpath("normalize-space(string(.))").get()
    assert healed_text is not None and "Beta Gadget" in healed_text
    assert len(healer.events) == 1
    event = healer.events[0]
    assert event.field == "name"
    assert event.used is True
    assert 0.0 < event.confidence <= 1.0
    assert healer.confident_count == 1
    assert healer.uncertain_count == 0


def test_an_uncertain_heal_returns_none_but_records_a_flagged_event(
    tmp_path: Path,
) -> None:
    healer = _healer_having_remembered_original(tmp_path)
    root = Selector(text=_UNRELATED)
    assert healer.attempt("name", root) is None  # never silently filled
    assert len(healer.events) == 1
    event = healer.events[0]
    assert event.used is False
    assert healer.uncertain_count == 1
    assert healer.confident_count == 0


def test_a_heal_event_carries_no_matched_text(tmp_path: Path) -> None:
    healer = _healer_having_remembered_original(tmp_path)
    healer.attempt("name", Selector(text=_CLASS_RENAMED))
    # §2h: only field name + confidence are exposed; the event has no text field.
    assert not hasattr(healer.events[0], "text")
    assert vars(healer.events[0]).keys() == {"field", "confidence", "used"}


def test_attempt_with_no_candidate_elements_returns_none(tmp_path: Path) -> None:
    healer = _healer_having_remembered_original(tmp_path)
    # An empty page yields no candidate elements to score against.
    assert healer.attempt("name", Selector(text="")) is None


def test_persist_writes_learned_fingerprints_for_a_later_run(
    tmp_path: Path,
) -> None:
    path = tmp_path / "d.json"
    first = Healer(FingerprintCache(path))
    first.remember("name", Selector(text=_ORIGINAL).css("h2.title")[0])
    first.persist()
    # A fresh Healer over the same cache file can heal from the persisted print.
    second = Healer(FingerprintCache(path))
    assert second.attempt("name", Selector(text=_CLASS_RENAMED)) is not None


# --- Cross-run re-anchoring -------------------------------------------------


def test_a_confident_heal_re_anchors_the_stored_fingerprint(tmp_path: Path) -> None:
    healer = _healer_having_remembered_original(tmp_path)
    original = healer.cache.get("name")
    healed = healer.attempt("name", Selector(text=_CLASS_RENAMED))
    assert healed is not None
    # The stored fingerprint is now the healed element's current shape, so a later
    # run heals from it rather than the (now outdated) original.
    assert healer.cache.get("name") == fingerprint(healed)
    assert healer.cache.get("name") != original
    # ...but the frozen prior-run snapshot is untouched, so anything else healing
    # within this same run still scores against the original shape.
    assert healer.cache.get_persisted("name") == original


def test_an_uncertain_heal_does_not_re_anchor(tmp_path: Path) -> None:
    healer = _healer_having_remembered_original(tmp_path)
    original = healer.cache.get("name")
    assert healer.attempt("name", Selector(text=_UNRELATED)) is None
    # An uncertain match must never overwrite the good anchor with a guess.
    assert healer.cache.get("name") == original


# --- Item mode (listing) ----------------------------------------------------
# A row shared across rows: structure is identical, text differs per row.
_ITEM = "li.product-card"


def _row(name: str, price: str, *, price_class: str = "price") -> str:
    return (
        '<li class="product-card">'
        f'<a class="name">{name}</a>'
        f'<span class="{price_class}">{price}</span>'
        "</li>"
    )


def test_item_mode_key_is_namespaced_by_the_item_selector(tmp_path: Path) -> None:
    healer = _healer(tmp_path)
    row = Selector(text=_row("Alpha", "10"))
    healer.remember("price", row.css("span.price")[0], item_selector=_ITEM)
    # Stored under the namespaced key, never the bare field name — so a listing's
    # "price" can't collide with a single-record "price" (or another listing's).
    assert healer.cache.get(f"{_ITEM}::price") is not None
    assert healer.cache.get("price") is None


def test_item_mode_heals_a_field_across_a_row_with_different_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "d.json"
    first = Healer(FingerprintCache(path))
    first.remember(
        "price",
        Selector(text=_row("Alpha", "10")).css("span.price")[0],
        item_selector=_ITEM,
    )
    first.persist()
    # A later run: the price class is renamed and this row's text differs. The
    # text-agnostic item fingerprint still re-resolves it (tag/class-shape/
    # structure survive), proving text is not required to identify the field.
    second = Healer(FingerprintCache(path))
    row = Selector(text=_row("Zeta", "999", price_class="cost"))
    healed = second.attempt("price", row.css(_ITEM)[0], item_selector=_ITEM)
    assert healed is not None
    assert second.confident_count == 1


def test_item_mode_does_not_fabricate_from_a_same_run_row(tmp_path: Path) -> None:
    # Within one run, remembering row 1's price must NOT let row 2 (which lacks a
    # price element) heal from it — healing reads only prior-run fingerprints.
    healer = _healer(tmp_path)
    healer.remember(
        "price",
        Selector(text=_row("Alpha", "10")).css("span.price")[0],
        item_selector=_ITEM,
    )
    row_without_price = Selector(
        text='<li class="product-card"><a class="name">B</a></li>'
    )
    assert (
        healer.attempt("price", row_without_price.css(_ITEM)[0], item_selector=_ITEM)
        is None
    )
    assert healer.events == []  # nothing to heal against -> no event at all


# --- Row-container healing --------------------------------------------------
_NAV = '<nav><a class="menu" href="#">Home</a><a class="menu" href="#">About</a></nav>'
_CONTAINER_ITEM = "ul.products > li"
_ROWS = (("Alpha", "10"), ("Beta", "20"), ("Gamma", "30"))


def _crow(name: str, price: str) -> str:
    return (
        f'<li class="card"><a class="name">{name}</a>'
        f'<span class="price">{price}</span></li>'
    )


def _clisting(ul_class: str, rows: tuple[tuple[str, str], ...]) -> str:
    return f'<ul class="{ul_class}">' + "".join(_crow(n, p) for n, p in rows) + "</ul>"


def _cpage(*sections: str) -> str:
    return "<html><body>" + "".join(sections) + "</body></html>"


def _healer_having_remembered_container(
    tmp_path: Path, body: str = _cpage(_NAV, _clisting("products", _ROWS))
) -> Healer:
    """A fresh healer whose cache holds a prior run's container fingerprint."""
    path = tmp_path / "d.json"
    first = Healer(FingerprintCache(path))
    first.remember_container(
        _CONTAINER_ITEM, Selector(text=body).css(_CONTAINER_ITEM)[0]
    )
    first.persist()
    return Healer(FingerprintCache(path))


def test_container_heal_re_resolves_the_row_group_after_a_rename(
    tmp_path: Path,
) -> None:
    healer = _healer_having_remembered_container(tmp_path)
    redesign = Selector(text=_cpage(_NAV, _clisting("grid", _ROWS)))
    rows = healer.attempt_container(_CONTAINER_ITEM, redesign)
    assert rows is not None
    assert len(rows) == len(_ROWS)
    assert healer.confident_count == 1
    assert healer.uncertain_count == 0


def test_container_heal_refuses_two_ambiguous_groups(tmp_path: Path) -> None:
    healer = _healer_having_remembered_container(tmp_path)
    redesign = Selector(
        text=_cpage(
            _NAV,
            _clisting("grid", _ROWS),
            _clisting("recommended", (("D", "4"), ("E", "5"))),
        )
    )
    assert healer.attempt_container(_CONTAINER_ITEM, redesign) is None
    # Refusal is surfaced as an uncertain match, never a silent empty result.
    assert healer.uncertain_count == 1
    assert healer.confident_count == 0


def test_container_heal_refuses_a_lone_lookalike(tmp_path: Path) -> None:
    healer = _healer_having_remembered_container(tmp_path)
    redesign = Selector(text=_cpage(_NAV, _clisting("grid", (("Solo", "99"),))))
    assert healer.attempt_container(_CONTAINER_ITEM, redesign) is None
    assert healer.uncertain_count == 1


def test_container_heal_stays_silent_when_nothing_resembles_a_row(
    tmp_path: Path,
) -> None:
    # A prior run remembered the container, but this page has nothing row-like (a
    # legitimately-empty or wholly-different page). A refusal here must NOT cry wolf
    # with an uncertain flag — no element crossed the confidence bar.
    healer = _healer_having_remembered_container(tmp_path)
    barren = Selector(
        text=_cpage("<main><p>No results found.</p></main>")
    )
    assert healer.attempt_container(_CONTAINER_ITEM, barren) is None
    assert healer.events == []


def test_container_heal_without_a_prior_fingerprint_is_a_noop(tmp_path: Path) -> None:
    healer = _healer(tmp_path)  # nothing remembered
    redesign = Selector(text=_cpage(_NAV, _clisting("grid", _ROWS)))
    assert healer.attempt_container(_CONTAINER_ITEM, redesign) is None
    assert healer.events == []  # nothing to heal against -> no event at all


def test_container_heal_within_same_run_does_not_fabricate(tmp_path: Path) -> None:
    # Remembering a container this run must not let attempt_container heal from it
    # (healing reads only prior-run fingerprints) — the guard that stops fabrication.
    healer = _healer(tmp_path)
    body = _cpage(_NAV, _clisting("products", _ROWS))
    row = Selector(text=body).css(_CONTAINER_ITEM)[0]
    healer.remember_container(_CONTAINER_ITEM, row)
    redesign = Selector(text=_cpage(_NAV, _clisting("grid", _ROWS)))
    assert healer.attempt_container(_CONTAINER_ITEM, redesign) is None
    assert healer.events == []


def test_container_key_never_collides_with_a_field_key(tmp_path: Path) -> None:
    # The container sentinel key must be distinct from any real field's key so a
    # field named like the container can never overwrite the container print.
    healer = _healer(tmp_path)
    body = _cpage(_NAV, _clisting("products", _ROWS))
    row = Selector(text=body).css(_CONTAINER_ITEM)[0]
    healer.remember_container(_CONTAINER_ITEM, row)
    healer.remember("name", row.css("a.name")[0], item_selector=_CONTAINER_ITEM)
    # Two distinct cache entries: the container print and the field print.
    assert healer.cache.get(f"{_CONTAINER_ITEM}::") is not None
    assert healer.cache.get(f"{_CONTAINER_ITEM}::name") is not None
    assert healer.cache.get(f"{_CONTAINER_ITEM}::") != healer.cache.get(
        f"{_CONTAINER_ITEM}::name"
    )
