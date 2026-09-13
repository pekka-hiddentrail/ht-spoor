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


def _remember_original(healer: Healer) -> None:
    element = Selector(text=_ORIGINAL).css("h2.title")[0]
    healer.remember("name", element)


def test_remember_stores_a_fingerprint_retrievable_from_the_cache(
    tmp_path: Path,
) -> None:
    healer = _healer(tmp_path)
    _remember_original(healer)
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
    healer = _healer(tmp_path)
    _remember_original(healer)
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
    healer = _healer(tmp_path)
    _remember_original(healer)
    root = Selector(text=_UNRELATED)
    assert healer.attempt("name", root) is None  # never silently filled
    assert len(healer.events) == 1
    event = healer.events[0]
    assert event.used is False
    assert healer.uncertain_count == 1
    assert healer.confident_count == 0


def test_a_heal_event_carries_no_matched_text(tmp_path: Path) -> None:
    healer = _healer(tmp_path)
    _remember_original(healer)
    healer.attempt("name", Selector(text=_CLASS_RENAMED))
    # §2h: only field name + confidence are exposed; the event has no text field.
    assert not hasattr(healer.events[0], "text")
    assert vars(healer.events[0]).keys() == {"field", "confidence", "used"}


def test_attempt_with_no_candidate_elements_returns_none(tmp_path: Path) -> None:
    healer = _healer(tmp_path)
    _remember_original(healer)
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
