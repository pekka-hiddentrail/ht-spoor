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
iframe, which the top document's `elementFromPoint` cannot reach). Nothing here is
site-specific (§0): the same relocation, verification, and click drive every target.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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

# JS that lists both web-storage areas' keys — the "storage-state diff" §2e signal.
_STORAGE_KEYS_JS = (
    "() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)]"
)

# The CDP command that returns the page's full accessibility node list — the same
# call the §2c accessibility signal uses, in the shape `discover_actions` expects.
_AX_TREE_COMMAND = "Accessibility.getFullAXTree"
_NAV_TIMEOUT_MS = 15_000

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
        self._context = self._browser.new_context(
            viewport={"width": _VIEWPORT_WIDTH, "height": _VIEWPORT_HEIGHT},
            device_scale_factor=1,
        )
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
        try:
            page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            # A click that triggers no navigation (an in-page state change) leaves
            # the page already idle; a slow tail shouldn't fail the exploration.
            pass

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
