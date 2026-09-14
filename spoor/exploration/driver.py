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

`perform` is the subtler of the two, and robust actuation (§2e sub-slice 7a) is why.
The explorer walks with reset-and-replay: to revisit a state it resets the driver and
replays the actions that first reached it. A reload reassigns every DOM/accessibility
node id, so an action's captured `backend_node_id` is only meaningful within the
snapshot it was discovered in and cannot be used to click after a replay. So `perform`
**re-locates** the element in the *current* page — but through the *same* engine
discovery used: it re-reads the live CDP accessibility tree and finds the node with
`find_target` (which runs `discover_actions` itself), so the act-time match cannot
diverge from the discovery-time match. An earlier cut re-located through Playwright's
separate ARIA-name engine, and the two computed accessible names differently, so a
visible, uncovered element could match nothing and be skipped — the bug 7a fixes.

Having the node, `perform` resolves it to a live DOM element over CDP, scrolls it into
view, reads its box centre live, and **verifies** with `elementFromPoint` that the
point resolves to the element (or a descendant) before clicking it by coordinate with
a real trusted mouse click — so a click is never fired blind at whatever happens to be
on top. The verification yields three outcomes: it clicks (ACTUATE), raises
`ElementCovered` when a different element is on top (COVERED — the hand-off to layer
recovery, 7c), or raises `ElementNotLocated` when no node matches (gone). The viewport
is pinned to a fixed size at device-scale 1 so CSS pixels equal device pixels equal the
coordinate space, and every computed centre is reproducible run to run, headless or
headed. When several elements share a role and name it acts on the first in document
order (deterministic; a known first-cut limitation, as are elements hosted in an
iframe, which the top document's `elementFromPoint` cannot reach).

Settling and reset fidelity (§2e sub-slice 7b) make reset-and-replay deterministic on a
real, stateful, asynchronously-rendered target. After a reset or a click the driver
waits for DOM mutations to go quiet — a real `MutationObserver` feeding the pure
`wait_for_quiescence` decision — before it reads the DOM or accessibility tree, so
discovery and actuation see the same settled render rather than two different rendering
instants. The wait is bounded: a page that never quiesces is recorded as unsettled (a
`settled=False` flag on its captured signals) and the run proceeds on the last snapshot,
where an earlier cut hung or crashed. And `reset` clears cookies and web storage before
navigating, so every reset is a true first visit rather than a returning-visitor render
that replay would diverge from. Nothing here is site-specific (§0): the same relocation,
verification, click, settle, and reset drive every target.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

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

from spoor.core.visual import InvalidImageError, perceptual_hash
from spoor.exploration.actuation import (
    CoveringElement,
    Verdict,
    classify,
    find_target,
)
from spoor.exploration.capture import StateSignals
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.explorer import (
    ActionError,
    ElementCovered,
    ElementNotLocated,
)
from spoor.exploration.settling import SettleResult, wait_for_quiescence

# JS that lists both web-storage areas' keys — the "storage-state diff" §2e signal.
_STORAGE_KEYS_JS = (
    "() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)]"
)

# The CDP command that returns the page's full accessibility node list — the same
# call the §2c accessibility signal uses, in the shape `discover_actions` expects.
_AX_TREE_COMMAND = "Accessibility.getFullAXTree"
_NAV_TIMEOUT_MS = 15_000

# Settling policy (§2e, 7b), in seconds to match `time.monotonic`. After a reset or a
# click the driver waits for DOM mutations to go quiet for `_QUIET_WINDOW_S` before it
# reads the page, so discovery and actuation see the same settled render; a page that
# never quiesces is reported unsettled at `_SETTLE_TIMEOUT_S` (a bounded safety net,
# never the normal path) rather than hanging or crashing the run.
_QUIET_WINDOW_S = 0.4
_SETTLE_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# Installed on every document (via add_init_script, which runs before page scripts on
# each navigation): a cumulative DOM-mutation counter behind a MutationObserver. The
# settle wait polls `window.__spoorMutations`; the page is quiet while it stops rising.
# Observing the document node itself is safe at document-start (documentElement may not
# exist yet); subtree/attributes/characterData catch every kind of render churn.
_MUTATION_OBSERVER_JS = """
(() => {
  window.__spoorMutations = 0;
  try {
    const observer = new MutationObserver((records) => {
      window.__spoorMutations += records.length;
    });
    observer.observe(document, {
      childList: true, subtree: true, attributes: true, characterData: true
    });
  } catch (e) { /* observation unsupported: count simply stays 0 (reads as quiet) */ }
})();
"""

# Clears both web-storage areas so a reset is a true first visit (§2e, 7b). Run on the
# previous document before navigating; harmless if an area is empty or unavailable.
_CLEAR_STORAGE_JS = "() => { localStorage.clear(); sessionStorage.clear(); }"

# Reads the cumulative mutation count the observer maintains; missing (a fresh document
# before the init script ran) reads as 0, i.e. quiet.
_MUTATION_COUNT_JS = "() => window.__spoorMutations || 0"

# A fixed viewport at device-scale 1: CSS pixels equal device pixels equal the
# coordinate space `elementFromPoint` and the mouse both use, so every computed click
# centre is reproducible run to run — the reproducibility robust actuation needs (7a).
_VIEWPORT_WIDTH = 1280
_VIEWPORT_HEIGHT = 800

# Run on the element `perform` resolved: scroll it into view, read its box centre, and
# hit-test that point in one call — so the point we verify is the point we click, with
# no window for a layout shift to open between reading and clicking. Returns the centre
# and whether the point lands on the element (or a descendant); when it does not, a
# best-effort description of what is on top, for the covered flag and recovery (7c).
_ACTUATION_PROBE_JS = """
function() {
  this.scrollIntoView({block: 'center', inline: 'center'});
  const r = this.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) {
    return {hitsTarget: false, covering: null, cx: null, cy: null};
  }
  const cx = r.left + r.width / 2;
  const cy = r.top + r.height / 2;
  const hit = document.elementFromPoint(cx, cy);
  if (hit === null) {
    return {hitsTarget: false, covering: null, cx: null, cy: null};
  }
  const hitsTarget = hit === this || this.contains(hit);
  let covering = null;
  if (!hitsTarget) {
    const label = hit.getAttribute('aria-label') || hit.textContent || '';
    covering = {
      role: hit.getAttribute('role') || hit.tagName.toLowerCase(),
      text: label.trim().slice(0, 200)
    };
  }
  return {hitsTarget, covering, cx, cy};
}
"""


class PlaywrightDriver:
    """Drives a headless Chromium page for the explorer (§2e, sub-slice 5b).

    Use as a context manager so the browser is always torn down::

        with PlaywrightDriver(url) as driver:
            graph = explore(driver, target=url, controller=controller)

    The driver is deterministic in the sense the explorer needs: resetting and
    replaying the same actions returns to the same state, as long as the target is.
    """

    def __init__(
        self,
        target: str,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        quiet_window: float = _QUIET_WINDOW_S,
        settle_timeout: float = _SETTLE_TIMEOUT_S,
        poll_interval: float = _POLL_INTERVAL_S,
    ) -> None:
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
        # Settling seams (§2e, 7b), mirroring the RunController clock seam so the wait
        # is deterministic in tests; production defaults use the real clock and sleep.
        self._clock = clock
        self._sleep = sleep
        self._quiet_window = quiet_window
        self._settle_timeout = settle_timeout
        self._poll_interval = poll_interval
        # Whether the last reset/click quiesced, and the last mutation count seen. The
        # settled flag rides the next captured StateSignals into the map and wiki.
        self._last_settled = True
        self._last_mutations = 0

    def __enter__(self) -> PlaywrightDriver:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        self._context = self._browser.new_context(
            viewport={"width": _VIEWPORT_WIDTH, "height": _VIEWPORT_HEIGHT},
            device_scale_factor=1,
        )
        # Install the mutation counter on every document the context loads, so the
        # settle wait (§2e, 7b) has a real rendering-stopped signal after each reset
        # and each in-page navigation.
        self._context.add_init_script(_MUTATION_OBSERVER_JS)
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

    @property
    def _live_context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("driver not started — use it as a context manager")
        return self._context

    def reset(self) -> None:
        """Return to the entry URL as a true first visit, then wait to settle (§2e, 7b).

        Reset-and-replay assumes reset restores the app's initial state, but a browser
        context persists cookies and web storage across navigations, so a plain
        re-navigation lands on a returning-visitor render and replay diverges from what
        discovery saw. So this clears cookies and both web-storage areas *before*
        navigating, making every reset a first visit. The storage clear runs on the
        previous document and is skipped when there isn't one yet (the first reset,
        still on about:blank). Navigation waits only for the document, then the settle
        wait waits for real DOM quiescence — so a page that never reaches "network idle"
        (which used to raise straight through and abort the run) is now a recorded
        unsettled fact, not a crash.
        """
        page = self._live_page
        self._live_context.clear_cookies()
        try:
            page.evaluate(_CLEAR_STORAGE_JS)
        except PlaywrightError:
            # No same-origin document to clear yet (first reset, or a blank page).
            pass
        page.goto(self._target, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
        self._wait_for_settle()

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
            settled=self._last_settled,
        )

    def _wait_for_settle(self) -> SettleResult:
        """Wait for DOM mutations to go quiet, recording whether the page settled (7b).

        Feeds the live mutation counter into the pure quiescence decision
        (`wait_for_quiescence`) through this driver's clock/sleep seams. A read that
        fails because the execution context was torn down mid-navigation reuses the
        last count rather than crashing, so the wait tolerates a full-page navigation in
        flight. Stores the settled verdict for the next captured bundle.
        """
        page = self._live_page

        def observe() -> int:
            try:
                value = page.evaluate(_MUTATION_COUNT_JS)
            except PlaywrightError:
                return self._last_mutations
            self._last_mutations = int(value) if isinstance(value, (int, float)) else 0
            return self._last_mutations

        result = wait_for_quiescence(
            observe=observe,
            clock=self._clock,
            sleep=self._sleep,
            quiet_window=self._quiet_window,
            timeout=self._settle_timeout,
            poll_interval=self._poll_interval,
        )
        self._last_settled = result.settled
        return result

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
        """Fire an action by re-locating its element and clicking a verified point.

        Re-reads the live accessibility tree and finds the node through the *same*
        function discovery uses (`find_target`), resolves it to a live DOM element over
        CDP, scrolls it into view, reads its box centre, and verifies with
        `elementFromPoint` that the point lands on the element before clicking it by
        coordinate. Three honest outcomes (7a): a real trusted click on ACTUATE;
        `ElementCovered` when a different element is on top (COVERED); or
        `ElementNotLocated` when no node matches (gone). Both raises are subclasses of
        `ActionError`, so the explorer records a skip and carries on rather than the
        whole run failing on one element (§2e). After a click, waits for the page to
        settle so `state_html` reflects the resulting state.
        """
        page = self._live_page
        target = find_target(self.ax_nodes(), action.role, action.name)
        if target is None or target.backend_node_id is None:
            # No matching node in the current page — or one without a resolvable DOM
            # id, so it cannot be actuated by coordinate. Either way it is gone.
            raise ElementNotLocated(action.role, action.name)
        probe = self._probe_click_point(page, target.backend_node_id)
        cx, cy = probe["cx"], probe["cy"]
        covering = probe["covering"]
        cover = (
            CoveringElement(str(covering["role"]), str(covering["text"]))
            if isinstance(covering, Mapping)
            else None
        )
        if cx is None or cy is None:
            # The element resolved but offers no clickable point (zero-size, or its
            # centre falls outside the page even after scrolling) — not actuatable and
            # nothing is on top of it, so it is effectively gone rather than covered.
            raise ElementNotLocated(action.role, action.name)
        verdict = classify(
            located=True,
            point_hits_target=bool(probe["hitsTarget"]),
            covering=cover,
        )
        if verdict.verdict is Verdict.COVERED:
            assert verdict.covering is not None  # COVERED always carries the layer
            raise ElementCovered(verdict.covering.role, verdict.covering.text)
        # ACTUATE: a real trusted mouse click at the verified centre.
        page.mouse.click(float(cx), float(cy))
        # Wait for the resulting render to go quiet before the explorer reads the new
        # state, so discovery and the state id see the settled page (§2e, 7b). A click
        # that only changes the page in place and one that navigates both resolve
        # through DOM quiescence; a page that never settles is recorded, not fatal.
        self._wait_for_settle()

    def _probe_click_point(
        self, page: Page, backend_node_id: int
    ) -> Mapping[str, Any]:
        """Resolve a backend node id to a live element and hit-test its centre.

        Bridges the CDP accessibility node (whose backend id we hold) to a live DOM
        element via `DOM.resolveNode`, then runs the scroll + centre + hit-test probe
        on it in one call. Staying on CDP end to end keeps us in Chrome's own
        engine — the same one discovery read — so the element we click is exactly the
        one we discovered. A CDP failure is wrapped as a plain `ActionError` (a skip),
        not a covered/not-located verdict, since it is a driver hiccup, not a fact
        about the element.
        """
        session = page.context.new_cdp_session(page)
        try:
            resolved = session.send(
                "DOM.resolveNode", {"backendNodeId": backend_node_id}
            )
            object_id = resolved["object"]["objectId"]
            result = session.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": object_id,
                    "functionDeclaration": _ACTUATION_PROBE_JS,
                    "returnByValue": True,
                },
            )
        except PlaywrightError as exc:
            raise ActionError("element could not be probed for actuation") from exc
        finally:
            session.detach()
        value = result.get("result", {}).get("value")
        if not isinstance(value, Mapping):
            raise ActionError("actuation probe returned no result")
        return value
