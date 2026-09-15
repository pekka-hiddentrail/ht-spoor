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

Both archetypes are exercised. Each is loopback, so the sandbox registry recognises it
generically (§2e) and the run is free to fire actions; the budget is kept small so the
test is fast and the disposable container is barely touched. Nothing here is
site-specific (§0): the same explorer and renderer run against both.

Marked `integration`: needs the docker bench up
(`docker compose -f fixtures/docker-compose.yml up -d`) and skips cleanly when a
container isn't reachable, so the fast unit gate stays Docker-free.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
import pytest

from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.driver import PlaywrightDriver
from spoor.exploration.explorer import explore
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.wiki import render_wiki

pytestmark = pytest.mark.integration

_JUICE_SHOP_BASE = "http://127.0.0.1:3000"
_SAUCE_DEMO_BASE = os.environ.get("SPOOR_SAUCE_DEMO_BASE", "http://127.0.0.1:3001")
_REPO_ROOT = Path(__file__).resolve().parent.parent
# A durable output dir (not a temp folder) so a produced wiki can be opened and
# inspected, or uploaded as a CI artifact, after the run.
_OUTPUT_ROOT = _REPO_ROOT / "test-output"

# The archetypes to map. Each is polled and skipped independently, so running only one
# container still exercises this test against it.
_ARCHETYPES = (
    pytest.param(_JUICE_SHOP_BASE, "juice-shop", id="juice-shop"),
    pytest.param(_SAUCE_DEMO_BASE, "sauce-demo", id="sauce-demo"),
)


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
