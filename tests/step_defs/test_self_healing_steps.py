"""Step definitions for features/self_healing.feature (ROADMAP.md §2, §5.3).

Drives the pure tier-3 scoring engine directly (no browser, no network): capture
a fingerprint from an original page, apply a markup change, then heal against the
mutated page's candidate elements. The true target is the unique "Beta Gadget"
heading; correctness is verified by the healed element's own text, never by a
marker the scorer could exploit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from parsel import Selector
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core.healing import (
    ElementFingerprint,
    HealResult,
    candidate_elements,
    fingerprint,
    heal,
)

scenarios("self_healing.feature")

# The original page: three cards with distinct headings. The target heading has a
# class and a data attribute the mutations below will attack, and unique text
# ("Beta Gadget") that — realistically — is what still identifies it afterward.
_ORIGINAL = """
<html><body>
  <nav><a href="/">Home</a></nav>
  <main>
    <section class="card"><h2 class="title" data-pos="1">Alpha Widget</h2></section>
    <section class="card"><h2 class="title" data-pos="2">Beta Gadget</h2></section>
    <section class="card"><h2 class="title" data-pos="3">Gamma Gizmo</h2></section>
  </main>
</body></html>
"""

# The selector that worked originally — used only to prove it is broken by each
# mutation before tier 3 is asked to heal.
_ORIGINAL_SELECTOR = "h2.title[data-pos='2']"

# Markup variants keyed by the change the scenarios describe.
_VARIANTS = {
    # Class renamed: `h2.title` matches nothing; text + tag + attrs still identify.
    "class-renamed": _ORIGINAL.replace('class="title"', 'class="heading"'),
    # Attributes shuffled (class + data-pos gone, a new one added) and the target
    # wrapped in a span: text still uniquely identifies it.
    "attrs-and-wrapper": _ORIGINAL.replace(
        '<h2 class="title" data-pos="2">Beta Gadget</h2>',
        '<span class="wrap"><h2 data-track="x">Beta Gadget</h2></span>',
    ),
    # Beyond confident recognition: the page is replaced with unrelated markup —
    # no heading, no sibling cards, nothing that resembles the stored element, so
    # the best any candidate can score is well below the confidence threshold.
    "obliterated": """
    <html><body>
      <div class="banner"><p>Totally different unrelated content here</p></div>
      <footer><small>copyright notice</small></footer>
    </body></html>
    """,
}


@dataclass
class _World:
    stored: ElementFingerprint | None = None
    candidates: list[Selector] = field(default_factory=list)
    result: HealResult | None = None
    healed: bool = False  # whether heal() was even called with candidates


@given("a page where the \"Beta Gadget\" heading was resolved and fingerprinted",
       target_fixture="world")
def world() -> _World:
    element = Selector(text=_ORIGINAL).css(_ORIGINAL_SELECTOR)
    assert element, "fixture invariant: original selector must resolve the heading"
    return _World(stored=fingerprint(element[0]))


def _apply(world: _World, variant: str) -> None:
    html = _VARIANTS[variant]
    # The original selector must genuinely be broken by the change (else there is
    # nothing for tier 3 to heal).
    assert not Selector(text=html).css(_ORIGINAL_SELECTOR), (
        f"variant {variant!r} did not break the original selector"
    )
    world.candidates = candidate_elements(html)


@when("the heading's class is renamed so the original selector matches nothing")
def _rename_class(world: _World) -> None:
    _apply(world, "class-renamed")


@when("the heading's attributes are shuffled and it is wrapped in a new element")
def _shuffle_and_wrap(world: _World) -> None:
    _apply(world, "attrs-and-wrapper")


@when("the heading is changed beyond confident recognition")
def _obliterate(world: _World) -> None:
    _apply(world, "obliterated")


@when("the page is replaced with one that has no candidate elements")
def _empty_page(world: _World) -> None:
    # A genuinely empty candidate pool: the page yielded nothing to score against.
    world.candidates = []


@when("tier 3 heals against the stored fingerprint")
def _do_heal(world: _World) -> None:
    assert world.stored is not None
    world.result = heal(world.stored, world.candidates)
    world.healed = True


@then(parsers.parse('tier 3 resolves the "{text}" heading'))
def _resolves_heading(world: _World, text: str) -> None:
    assert world.result is not None, "expected a heal result"
    resolved = " ".join(world.result.element.css("::text").getall()).split()
    assert text in " ".join(resolved), (
        f"healed element text {resolved!r} does not contain {text!r}"
    )


@then("the heal is confident")
def _is_confident(world: _World) -> None:
    assert world.result is not None
    assert world.result.confident, (
        f"expected a confident heal, score was {world.result.score:.3f}"
    )


@then("the heal records a winning confidence score")
def _records_score(world: _World) -> None:
    assert world.result is not None
    assert 0.0 < world.result.score <= 1.0


@then("the heal records the runner-up candidates it considered")
def _records_runners(world: _World) -> None:
    assert world.result is not None
    assert world.result.runners_up, "expected runner-up candidates to be recorded"
    # Runner-ups never outrank the winner and are ordered by descending score.
    scores = [r.score for r in world.result.runners_up]
    assert all(s <= world.result.score for s in scores)
    assert scores == sorted(scores, reverse=True)


@then("the heal is flagged as an uncertain match")
def _is_uncertain(world: _World) -> None:
    assert world.result is not None, "a weak match still returns a result to review"
    assert not world.result.confident, (
        f"expected an uncertain match, but score {world.result.score:.3f} was confident"
    )
    assert world.result.score > 0.0


@then("the heal still records why it chose its best candidate")
def _still_explains(world: _World) -> None:
    assert world.result is not None
    assert "UNCERTAIN" in world.result.explain()


@then("tier 3 resolves nothing")
def _resolves_nothing(world: _World) -> None:
    assert world.healed, "heal() should have been invoked"
    assert world.result is None
