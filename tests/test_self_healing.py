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
