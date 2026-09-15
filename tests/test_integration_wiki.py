"""Exploration-wiki reliability against the live archetype bench (§2e, §5.1).

Slice 6a proved the wiki renderer in-process against a hand-built graph; this proves
the *whole* §2e pipeline end to end against real, uncontrolled apps: point the real
headless-browser explorer at a live archetype, let it map a bounded slice of the site
into an `ExplorationGraph`, render that graph to a browsable wiki on disk, and assert
the wiki comes out **complete and internally consistent every time** — a page for
every state and every transition, an index whose counts and links match the graph, and
well-formed HTML throughout. This is the maintainer's "check the wikis are reliably
created every time" requirement: not a golden-count assertion (a live SPA's exact graph
isn't a contract), but a structural-completeness contract that holds for any target.

Juice Shop is the archetype exercised here. It is loopback, so the sandbox registry
recognises it generically (§2e) and the run is free to fire actions; the budget is kept
small so the test is fast and the disposable container is barely touched. Nothing here
is site-specific (§0): the same explorer and renderer run against any target. (Sauce
Demo was dropped from the *exploration* bench — its login wall yields nothing to map;
it still earns its keep in the extraction/session tests. See ROADMAP §5.1.)

Marked `integration`: needs the docker bench up
(`docker compose -f fixtures/docker-compose.yml up -d`) and skips cleanly when a
container isn't reachable, so the fast unit gate stays Docker-free.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import ElementShot, explore
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.screenshot_store import ImageRef
from spoor.exploration.wiki import render_wiki

pytestmark = pytest.mark.integration


def _is_embedded(ref: ImageRef, page: str) -> bool:
    """Whether `ref` is embedded on `page`, as a whole-file `<img>` or a crop span.

    Dedup (§2e slice 8g) means a clip may be a crop of a bigger picture rather than its
    own file: the wiki then references the shared `src` inside a CSS `url(...)` crop box
    rather than an `<img src>`. Either shape counts as embedded.
    """
    return f'src="{ref.src}"' in page or f"url('{ref.src}')" in page

_JUICE_SHOP_BASE = "http://127.0.0.1:3000"
_REPO_ROOT = Path(__file__).resolve().parent.parent
# A durable output dir (not a temp folder) so a produced wiki can be opened and
# inspected, or uploaded as a CI artifact, after the run.
_OUTPUT_ROOT = _REPO_ROOT / "test-output"

# The archetype to map. Polled and skipped when the container isn't reachable.
_ARCHETYPES = (pytest.param(_JUICE_SHOP_BASE, "juice-shop", id="juice-shop"),)


def _require_reachable(base: str) -> None:
    try:
        httpx.get(f"{base}/", timeout=3.0).raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        pytest.skip(
            f"{base} not reachable — start the bench with "
            f"`docker compose -f fixtures/docker-compose.yml up -d` ({exc})"
        )


def _explore_to_graph(base: str) -> ExplorationGraph:
    """Map a small, bounded slice of the live site into an ExplorationGraph."""
    # A tight budget: enough to produce a multi-state, multi-transition graph (so the
    # wiki has real content to render), small enough to stay fast and barely touch the
    # container. Wall-clock is the backstop so a slow SPA can never hang the suite.
    budget = RunBudget(max_states=4, max_requests=8, max_seconds=120)
    with PlaywrightDriver(base) as driver:
        return explore(driver, target=base, controller=RunController(budget))


@pytest.mark.parametrize(("base", "name"), _ARCHETYPES)
def test_wiki_is_reliably_created(base: str, name: str) -> None:
    _require_reachable(base)
    graph = _explore_to_graph(base)
    out_dir = _OUTPUT_ROOT / f"wiki-{name}"
    written = render_wiki(graph, out_dir, target=base)

    states = graph.states
    transitions = graph.transitions
    # A real site always yields at least the entry state, so the wiki is never empty.
    assert len(states) >= 1, "exploration produced no states to render"

    # 1) Exactly one page per state and per transition, plus the index and the fixed
    #    help/glossary page (6f) — no more, no fewer — so the wiki is a complete,
    #    faithful view of the graph.
    expected = (
        {"index.html", "help.html"}
        | {f"state-{i}.html" for i in range(len(states))}
        | {f"transition-{j}.html" for j in range(len(transitions))}
    )
    assert {p.name for p in written} == expected

    # 2) Every page is well-formed, non-empty HTML.
    for path in written:
        html = path.read_text(encoding="utf-8")
        assert html.startswith("<!DOCTYPE html>"), f"{path.name} is not HTML"
        assert html.rstrip().endswith("</html>"), f"{path.name} is truncated"

    index = (out_dir / "index.html").read_text(encoding="utf-8")

    # 3) The overview's counts match the graph exactly.
    assert f"<strong>{len(states)}</strong> states discovered" in index
    assert f"<strong>{len(transitions)}</strong> transitions" in index
    assert 'class="mermaid"' in index

    # 4) Every state/transition link in the index resolves to a written file — no
    #    dangling navigation in the generated site.
    for target_name in re.findall(r'href="((?:state|transition)-\d+\.html)"', index):
        assert (out_dir / target_name).is_file(), f"index links missing {target_name}"


def test_screenshots_are_captured_and_embedded_when_opted_in() -> None:
    """The live driver takes a real full-page PNG per state and the wiki embeds it (8b).

    Proves the opt-in path end to end against a real browser: `PlaywrightDriver.
    screenshot()` returns genuine PNG bytes, the explorer streams each to disk as it is
    captured and fills the sink with a reference per state (§2e slice 8f), and
    `render_wiki` embeds each `screenshots/state-N.png` — writing only HTML, since the
    images are already on disk. Juice Shop alone keeps it fast; the mechanism is generic
    (§0).
    """
    _require_reachable(_JUICE_SHOP_BASE)
    budget = RunBudget(max_states=3, max_requests=6, max_seconds=120)
    # The output dir is fixed up front and doubles as the screenshot directory the
    # explorer streams into, so its references resolve against the pages rendered here.
    out_dir = _OUTPUT_ROOT / "wiki-juice-shop-shots"
    shots: dict[str, ImageRef] = {}
    with PlaywrightDriver(_JUICE_SHOP_BASE) as driver:
        graph = explore(
            driver,
            target=_JUICE_SHOP_BASE,
            controller=RunController(budget),
            screenshots=shots,
            screenshot_dir=out_dir,
        )

    assert shots, "opting in should capture at least the entry state's screenshot"
    # Each sink value is a filename reference; the real PNG bytes were streamed to disk
    # as they were captured, so the image lives under the reference, not in the sink.
    # A full-page reference is always a whole file (dedup may point two states at one
    # shared file, but never a crop — a crop is an element-clip concern, §2e slice 8g).
    for sid, ref in shots.items():
        image = out_dir / ref.src
        assert image.is_file(), f"{sid[:12]} screenshot {ref.src} is not on disk"
        assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{ref.src} not a PNG"

    written = render_wiki(graph, out_dir, target=_JUICE_SHOP_BASE, screenshots=shots)

    assert not [p for p in written if p.suffix == ".png"], "render writes no images"
    for index, sid in enumerate(graph.states):
        if sid in shots:
            page = (out_dir / f"state-{index}.html").read_text(encoding="utf-8")
            # Each captured state embeds *its own* reference — which dedup (§2e slice
            # 8g) may point at a file first written for an earlier, identical-looking
            # state rather than this state's own index, so assert the ref it holds.
            assert _is_embedded(shots[sid], page), (
                f"state {index} does not embed its screenshot {shots[sid].src}"
            )


def test_element_screenshots_are_clipped_and_embedded_when_opted_in() -> None:
    """The live driver clips a real element PNG and the wiki embeds it per row (8d).

    Proves the opt-in per-element path end to end against a real browser: `Playwright
    Driver.element_screenshot()` re-locates a discovered element and returns genuine
    PNG bytes cropped to it, the explorer streams clips to disk as it is captured and
    fills the per-element sink with the filename reference in discovery order (§2e slice
    8f), and `render_wiki` embeds `screenshots/state-{i}-el-{e}.png` in the element's
    Actions row. Structural, not a golden count: a real page's exact element set isn't a
    contract, so it asserts at least one clip round-trips to disk and every clip on disk
    is embedded. Juice Shop alone keeps it fast; the mechanism is generic (§0).
    """
    _require_reachable(_JUICE_SHOP_BASE)
    budget = RunBudget(max_states=3, max_requests=6, max_seconds=120)
    out_dir = _OUTPUT_ROOT / "wiki-juice-shop-elements"
    element_shots: dict[str, list[ElementShot]] = {}
    with PlaywrightDriver(_JUICE_SHOP_BASE) as driver:
        graph = explore(
            driver,
            target=_JUICE_SHOP_BASE,
            controller=RunController(budget),
            element_screenshots=element_shots,
            screenshot_dir=out_dir,
        )

    clips = [s.clip for shots in element_shots.values() for s in shots if s.clip]
    assert clips, "opting in should clip at least one actionable element"
    # Each clip references a real PNG on disk. Dedup (§2e slice 8g) means the reference
    # may be a crop of the state's full-page picture rather than an own file — either
    # way `ref.src` names a real PNG that was streamed to disk.
    for ref in clips:
        image = out_dir / ref.src
        assert image.is_file(), f"element clip {ref.src} is not on disk"
        assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{ref.src} not a PNG"

    written = render_wiki(
        graph, out_dir, target=_JUICE_SHOP_BASE, element_screenshots=element_shots
    )
    assert not [p for p in written if p.suffix == ".png"], "render writes no images"
    pages = {
        i: (out_dir / f"state-{i}.html").read_text(encoding="utf-8")
        for i in range(len(graph.states))
    }
    for ref in clips:
        assert any(
            _is_embedded(ref, page) for page in pages.values()
        ), f"{ref} is not embedded on any state page"


def test_opened_contents_are_captured_and_embedded_when_opted_in() -> None:
    """The live driver opens a disclosure element; the wiki embeds what it reveals (8e).

    Proves the opt-in opened-contents path end to end against a real browser: for a
    gate-permitted disclosure element (a combobox/listbox), `PlaywrightDriver.opened_
    screenshot()` clicks it, captures the revealed overlay, and Escape-restores; the
    explorer streams it to disk as it is captured and fills the per-element sink's
    `opened` field with the filename reference (§2e slice 8f); and `render_wiki` embeds
    each `screenshots/state-{i}-el-{e}-opened.png` in its row. Structural, not
    a golden count: whether a real page exposes an openable disclosure element within a
    small budget isn't a contract, so if none was captured the test skips rather than
    asserting a shape the site doesn't owe us. Every image that *was* captured must
    be a real PNG on disk and must be embedded. Generic mechanism (§0).
    """
    _require_reachable(_JUICE_SHOP_BASE)
    budget = RunBudget(max_states=4, max_requests=10, max_seconds=180)
    out_dir = _OUTPUT_ROOT / "wiki-juice-shop-opened"
    element_shots: dict[str, list[ElementShot]] = {}
    with PlaywrightDriver(_JUICE_SHOP_BASE) as driver:
        graph = explore(
            driver,
            target=_JUICE_SHOP_BASE,
            controller=RunController(budget),
            element_screenshots=element_shots,
            screenshot_dir=out_dir,
        )

    opened = [s.opened for shots in element_shots.values() for s in shots if s.opened]
    if not opened:
        pytest.skip("no openable disclosure element reached within the budget")
    # Each opened value references a real PNG on disk; dedup may make it a crop of a
    # bigger picture (§2e slice 8g), so `ref.src` names the file that was streamed.
    for ref in opened:
        image = out_dir / ref.src
        assert image.is_file(), f"opened capture {ref.src} is not on disk"
        assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{ref.src} not a PNG"

    written = render_wiki(
        graph, out_dir, target=_JUICE_SHOP_BASE, element_screenshots=element_shots
    )
    assert not [p for p in written if p.suffix == ".png"], "render writes no images"
    pages = {
        i: (out_dir / f"state-{i}.html").read_text(encoding="utf-8")
        for i in range(len(graph.states))
    }
    for ref in opened:
        assert any(
            _is_embedded(ref, page) for page in pages.values()
        ), f"{ref} is not embedded on any state page"


def test_default_run_leaves_the_wiki_pixel_free(tmp_path: Path) -> None:
    """A default run (no opt-in) captures no pixels and embeds none: the §2h posture."""
    _require_reachable(_JUICE_SHOP_BASE)
    graph = _explore_to_graph(_JUICE_SHOP_BASE)
    written = render_wiki(graph, tmp_path / "wiki", target=_JUICE_SHOP_BASE)
    assert not [p for p in written if p.suffix == ".png"]
    for path in written:
        assert "<img" not in path.read_text(encoding="utf-8")
