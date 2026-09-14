"""A live-browser `BrowserDriver` for the explorer (ROADMAP.md §2e, sub-slice 5b).

Sub-slice 5a built the explorer orchestrator against the `BrowserDriver` protocol
and a fake in-process app; this is the real driver that satisfies that protocol with
a headless Chromium page, so `explore` can map an actual site. It mirrors the
tier-2 resolver's Playwright lifecycle (`spoor/core/extract.py`), but keeps one page
open across the whole run rather than one page per URL, because the explorer needs a
persistent live page to drive.

The one genuinely new piece is `perform`. The explorer walks with reset-and-replay:
to revisit a state it resets the driver and replays the actions that first reached
it. A reload reassigns every DOM/accessibility node id, so an action's captured
`backend_node_id` is only meaningful within the snapshot it was discovered in and
cannot be used to click after a replay. Instead `perform` **re-locates** the element
in the *current* page by its accessibility role and name — exactly what the action
carries — using Playwright's role locator, which also gives auto-waiting and
actionability checks for free. When several elements share a role and name it acts on
the first in document order (deterministic; a known first-cut limitation). Nothing
here is site-specific (§0): the same driver drives every target.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from spoor.exploration.capture import StateSignals
from spoor.exploration.discovery import ActionableElement

# The CDP command that returns the page's full accessibility node list — the same
# call the §2c accessibility signal uses, in the shape `discover_actions` expects.
_AX_TREE_COMMAND = "Accessibility.getFullAXTree"
_NAV_TIMEOUT_MS = 15_000
_CLICK_TIMEOUT_MS = 5_000


class PlaywrightDriver:
    """Drives a headless Chromium page for the explorer (§2e, sub-slice 5b).

    Use as a context manager so the browser is always torn down::

        with PlaywrightDriver(url) as driver:
            graph = explore(driver, target=url, controller=controller)

    The driver is deterministic in the sense the explorer needs: resetting and
    replaying the same actions returns to the same state, as long as the target is.
    """

    def __init__(self, target: str) -> None:
        self._target = target
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> PlaywrightDriver:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Tear down page, context, browser, and Playwright — each guarded."""
        for closer in (self._page, self._context, self._browser):
            if closer is not None:
                try:
                    closer.close()
                except PlaywrightError:
                    pass
        if self._playwright is not None:
            self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    @property
    def _live_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("driver not started — use it as a context manager")
        return self._page

    def reset(self) -> None:
        """Navigate back to the entry URL (the explorer's start state)."""
        self._live_page.goto(
            self._target, wait_until="networkidle", timeout=_NAV_TIMEOUT_MS
        )

    def state_html(self) -> str:
        """The current rendered DOM, for computing the abstract state id."""
        return self._live_page.content()

    def ax_nodes(self) -> Sequence[Mapping[str, object]]:
        """The current accessibility-tree nodes, read over CDP (for discovery)."""
        page = self._live_page
        session = page.context.new_cdp_session(page)
        try:
            result = session.send(_AX_TREE_COMMAND)
        finally:
            session.detach()
        nodes = result.get("nodes", [])
        return nodes if isinstance(nodes, list) else []

    def capture_signals(self) -> StateSignals:
        """The free-signal bundle for the current page (§2e sub-slice 5c).

        Sub-slice 5c-i wires the seam and fills the one signal already read for free
        here — the accessibility-node count. The screenshot hash, storage keys, and
        the console and network/HAR deltas are sub-slice 5c-ii; until then they stay
        at their empty defaults, so a transition's diff carries a real a11y delta and
        empty (not wrong) values elsewhere.
        """
        return StateSignals(ax_node_count=len(self.ax_nodes()))

    def perform(self, action: ActionableElement) -> None:
        """Fire an action by re-locating its element in the current page.

        Locates by accessibility role and name (not the captured backend id, which
        does not survive a reload), clicks the first match, then waits for the page
        to settle so `state_html` reflects the resulting state.
        """
        page = self._live_page
        # Playwright types the role as a Literal of ARIA roles; discovery only ever
        # yields real ARIA role strings, so the cast is safe.
        role = cast(Any, action.role)
        if action.name:
            locator = page.get_by_role(role, name=action.name, exact=True)
        else:
            locator = page.get_by_role(role)
        locator.first.click(timeout=_CLICK_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            # A click that triggers no navigation (an in-page state change) leaves
            # the page already idle; a slow tail shouldn't fail the exploration.
            pass
