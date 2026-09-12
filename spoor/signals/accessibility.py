"""Accessibility-tree snapshot — the second §2c signal (ROADMAP.md §2c).

The accessibility tree is a structural view of a page independent of its visual
markup (§2c): the role/name nodes an assistive technology would see. It doubles
as a resilience signal for the selector-based tiers — a page that renders its UI
to a canvas or an opaque widget exposes almost no accessible structure, a red
flag that DOM selectors will struggle there.

Playwright's old `page.accessibility.snapshot()` was removed (>=1.55), so the
tree is read over the Chromium DevTools Protocol (`Accessibility.getFullAXTree`),
which returns the full flat list of accessibility nodes. That's Chromium-only,
which is exactly the browser the tier runs (§0: identical for every target).

Same shape as the console signal: the raw node list (potentially large) is
written to the local-only run cache (§2h) and never routed to shared output; the
run summary carries only an aggregate — the total number of accessible nodes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

# The CDP command that returns a page's full accessibility node list. Generic —
# the same call for every target (§0).
_AX_TREE_COMMAND = "Accessibility.getFullAXTree"


@dataclass(frozen=True)
class AccessibilitySignal:
    """Aggregate of a run's accessibility snapshots (ROADMAP.md §2c).

    `nodes` is the total number of accessibility nodes across every page
    snapshotted this run — a cheap structural-richness signal (near-zero on a
    canvas-only UI, high on a well-marked-up document). A count only; the raw
    node lists stay in the local-only cache.
    """

    nodes: int


class AccessibilityCollector:
    """Snapshots the accessibility tree of each of a run's pages (§2c).

    One collector spans a whole run: `capture` it once per rendered page and it
    accumulates each page's node list. `signal` is the shareable node count;
    `write` persists the raw node lists to the local-only cache. Keeping the raw
    nodes only in the file (never in `signal`) holds the §2h local-only /
    shared-output line.
    """

    def __init__(self) -> None:
        # One entry per page: that page's flat list of accessibility nodes.
        self._trees: list[list[object]] = []

    def capture(self, page: Page) -> None:
        """Snapshot the page's accessibility tree over CDP (call after render).

        A signal is an opportunistic bonus, never a reason to fail the run: a CDP
        error (e.g. the target closed mid-run) is swallowed and recorded as an
        empty snapshot for that page, so extraction is unaffected.
        """
        try:
            session = page.context.new_cdp_session(page)
            try:
                result = session.send(_AX_TREE_COMMAND)
            finally:
                session.detach()
        except PlaywrightError:
            self._trees.append([])
            return
        nodes = result.get("nodes", [])
        self._trees.append(nodes if isinstance(nodes, list) else [])

    @property
    def signal(self) -> AccessibilitySignal:
        """The shareable node-count summary across all pages snapshotted."""
        return AccessibilitySignal(nodes=sum(len(tree) for tree in self._trees))

    def write(self, path: Path) -> None:
        """Write the raw per-page node lists to `path` as JSON (§2h, local-only).

        Always writes when called — an empty list for a run with no snapshots — so
        the file's presence means "accessibility was captured", mirroring the HAR
        and console log. A local-only artifact; never routed to shared output.
        """
        path.write_text(json.dumps(self._trees, indent=2), encoding="utf-8")
