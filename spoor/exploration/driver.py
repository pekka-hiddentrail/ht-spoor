"""A live-browser `BrowserDriver` for the explorer (ROADMAP.md §2e, slices 5b + 5c-ii).

Sub-slice 5a built the explorer orchestrator against the `BrowserDriver` protocol
and a fake in-process app; this is the real driver that satisfies that protocol with
a headless Chromium page, so `explore` can map an actual site. It mirrors the
tier-2 resolver's Playwright lifecycle (`spoor/core/extract.py`), but keeps one page
open across the whole run rather than one page per URL, because the explorer needs a
persistent live page to drive.

`perform` (5b) fires actions; `capture_signals` (5c-ii) reads §2e's free-signal
bundle from the live page — the accessibility-node count, the console and network
buffers accumulated by the page listeners, the current web-storage keys, and a
perceptual hash of a screenshot (reusing the tier-3 visual hasher). Each signal is
opportunistic: one that can't be read is recorded empty rather than failing the run.

`perform` is the subtler of the two. The explorer walks with reset-and-replay:
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
    ConsoleMessage,
    Page,
    Playwright,
    Request,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from spoor.core.visual import InvalidImageError, perceptual_hash
from spoor.exploration.capture import StateSignals
from spoor.exploration.discovery import ActionableElement

# JS that lists both web-storage areas' keys — the "storage-state diff" §2e signal.
_STORAGE_KEYS_JS = (
    "() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)]"
)

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
        # Console messages and network request URLs accumulate for the page's whole
        # life (across reloads); a transition's diff is the slice between its
        # before- and after-snapshots, so the running buffers are exactly right.
        self._console: list[str] = []
        self._network: list[str] = []

    def __enter__(self) -> PlaywrightDriver:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.on("console", self._on_console)
        self._page.on("request", self._on_request)
        return self

    def _on_console(self, message: ConsoleMessage) -> None:
        self._console.append(message.text)

    def _on_request(self, request: Request) -> None:
        self._network.append(request.url)

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

        Reads all five §2e free signals from the live page: the accessibility-node
        count, the console messages and network requests seen so far (running
        buffers), the current web-storage keys, and a perceptual hash of a
        screenshot. Each signal is opportunistic — a signal that can't be read is
        recorded empty rather than failing the exploration (§2c), the same stance
        the tier-2 signal collectors take.
        """
        page = self._live_page
        return StateSignals(
            ax_node_count=len(self.ax_nodes()),
            console_messages=tuple(self._console),
            storage_keys=self._storage_keys(page),
            network_requests=tuple(self._network),
            screenshot_hash=self._screenshot_hash(page),
        )

    @staticmethod
    def _storage_keys(page: Page) -> tuple[str, ...]:
        """localStorage + sessionStorage keys — the §2e storage-state signal."""
        try:
            keys = page.evaluate(_STORAGE_KEYS_JS)
        except PlaywrightError:
            return ()
        if not isinstance(keys, list):
            return ()
        return tuple(str(key) for key in keys)

    @staticmethod
    def _screenshot_hash(page: Page) -> str | None:
        """A perceptual (dHash) hash of the viewport screenshot, or None.

        Reuses the tier-3 visual hasher (`spoor/core/visual.py`), which keys off
        gradients — robust to the anti-aliasing/cursor noise a re-render adds, so a
        transition is flagged as changing the screenshot only when the page actually
        looks different, not on every step.
        """
        try:
            png = page.screenshot()
            return str(perceptual_hash(png))
        except (PlaywrightError, InvalidImageError):
            return None

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
