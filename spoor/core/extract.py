"""Extraction and the resolution-tier dispatcher (ROADMAP.md §2).

Holds the escalation seam — an ordered ladder of `Resolver` rungs that a config
is dispatched through, never chosen by the config author (§2a, §0). Tier 1
(`httpx` fetch + `parsel` selectors) and tier 2 (headless-Chromium rendering via
Playwright, reusing tier 1's `parsel` extraction on the rendered HTML) are both
implemented here. Escalation reaches tier 2 two ways, both generic (§0): by
*capability* (a config requesting a browser-only feature such as JS-driven
infinite scroll, which tier 1 declines up front) and by *content* (tier 1 runs
but extracts zero records, so the dispatcher re-renders in a browser). Tier 3
(self-healing) joins the ladder later. Per §0 there is no site-specific logic:
everything is driven by the config.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin

import httpx
from parsel import Selector
from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from spoor.api_discovery.discovery import DiscoveredSpec, discover_spec
from spoor.api_discovery.graphql import DiscoveredGraphQL, discover_graphql
from spoor.core.config import ExtractionConfig, FieldSpec, PolitenessPolicy
from spoor.operational.politeness import Politeness
from spoor.security import storage
from spoor.signals.accessibility import AccessibilityCollector, AccessibilitySignal
from spoor.signals.console import ConsoleCollector, ConsoleSignal
from spoor.signals.headers import HeaderCollector, HeaderSignal
from spoor.signals.storage_state import StorageStateCollector, StorageStateSignal

# Guard against a pagination cycle running forever on a self-linking page.
_MAX_PAGES = 1000
# Guard against an infinite feed that never stops growing (tier 2).
_MAX_SCROLLS = 100
# Grace window for a scroll to load more content before we call it the end of
# the feed (ms). Generous enough to cover a fetch round-trip, not per-site.
_SCROLL_GROWTH_TIMEOUT_MS = 2000
# How long tier 2 waits for a config's `item` selector to render before
# capturing (ms). `networkidle` alone doesn't bracket an SPA's async content
# load; this waits for the items themselves. A legitimately empty listing waits
# out this window once, then extracts zero — a bounded cost, not a hang.
_ITEM_RENDER_TIMEOUT_MS = 5000


@dataclass
class RunResult:
    """Outcome of a run: the extracted records plus run-observability facts (§2d).

    `blocked` holds URLs that robots.txt disallowed (ROADMAP.md §2d/§6) — these
    are recorded, never fetched. `tier` is the tier that produced these records
    and `pages_fetched` counts pages actually fetched (blocked URLs excluded);
    both are stamped by the resolver. `tiers_attempted` is the dispatcher's
    escalation path (set by `run_report`), so it stays empty for a resolver
    invoked directly. `har_path`, when set, is the local-only HAR the browser
    tier captured for this run (ROADMAP.md §2b/§2h) — a path into the local
    cache, never shared output; it stays None for a run that captured nothing.
    `api_spec`, when set, is an official API spec discovery observed at a
    conventional path alongside the run (ROADMAP.md §2b); None means none was
    found. `graphql`, when set, is an introspectable GraphQL endpoint observed
    the same way (§2b layer 2). `console`, when set, is the count summary of the
    browser tier's console activity (§2c) and `console_log_path` the local-only
    file its raw messages were written to (§2h) — both None for a run that didn't
    capture the console. `accessibility`, when set, is the node-count summary of
    the browser tier's accessibility snapshots (§2c) and `accessibility_path` the
    local-only file the raw trees were written to (§2h) — both None when not
    captured. `headers`, when set, is the non-sensitive derived summary of the
    browser tier's response headers (§2c) and `headers_path` the local-only file
    the raw headers (all values) were written to (§2h) — both None when not
    captured. `storage_state`, when set, is the redacted, shareable view of the
    browser context's client-side storage (§2c) and `storage_state_path` the
    local-only file the raw, unredacted state was written to (§2h) — both None
    when not captured. `spoor/operational/observability.py` turns these into the
    operator-facing summary.
    """

    records: list[dict[str, object]] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    tier: int | None = None
    pages_fetched: int = 0
    tiers_attempted: list[int] = field(default_factory=list)
    har_path: Path | None = None
    api_spec: DiscoveredSpec | None = None
    graphql: DiscoveredGraphQL | None = None
    console: ConsoleSignal | None = None
    console_log_path: Path | None = None
    accessibility: AccessibilitySignal | None = None
    accessibility_path: Path | None = None
    headers: HeaderSignal | None = None
    headers_path: Path | None = None
    storage_state: StorageStateSignal | None = None
    storage_state_path: Path | None = None


def _first_text(root: Selector, css: str) -> str | None:
    """First matching element's normalized text, or None if nothing matches."""
    matches = root.css(css)
    if not matches:
        return None
    text = matches[0].xpath("normalize-space(string(.))").get()
    return text if text else None


def _first_attr(root: Selector, css: str, attr: str) -> str | None:
    """First match's `attr` value, or None if the element or attribute is absent."""
    matches = root.css(css)
    if not matches:
        return None
    return matches[0].attrib.get(attr)


# The first numeric run in a string. The optional leading `-` is only taken as
# a sign when it isn't glued to a preceding word or digit (the lookbehind), so
# an internal hyphen — e.g. a SKU like "SKU-42" — is read as 42, not -42, while
# digits themselves are still found anywhere (e.g. "USD5" -> 5). Assumes `.`
# decimal / `,` thousands; locale-specific formats (e.g. "1.234,56") are out of
# scope.
_NUMBER_RE = re.compile(r"(?:(?<![\w.])-)?(?:\d[\d,]*(?:\.\d+)?|\.\d+)")


def _coerce_number(text: str) -> float | None:
    """Best-effort numeric coercion: parse the first number found in the text."""
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def _extract_value(root: Selector, spec: FieldSpec) -> str | float | None:
    if spec.attr is not None:
        raw = _first_attr(root, spec.selector, spec.attr)
    else:
        raw = _first_text(root, spec.selector)
    if raw is None:
        return None
    if spec.type == "number":
        return _coerce_number(raw)
    return raw


def extract_records(html: str, config: ExtractionConfig) -> list[dict[str, object]]:
    """Extract all records from one page's HTML per the config."""
    page = Selector(text=html)
    roots = page.css(config.item) if config.item else [page]
    records: list[dict[str, object]] = []
    for root in roots:
        records.append(
            {name: _extract_value(root, spec) for name, spec in config.fields.items()}
        )
    return records


def _next_url(html: str, current_url: str, config: ExtractionConfig) -> str | None:
    if not (config.pagination and config.pagination.next):
        return None
    href = Selector(text=html).css(f"{config.pagination.next}::attr(href)").get()
    return urljoin(current_url, href) if href else None


class TierUnavailableError(RuntimeError):
    """The dispatcher escalated to a resolution tier that is not yet implemented.

    Raised (not returned) so a config needing an unbuilt tier fails loudly with a
    clear reason, rather than silently returning partial or empty data.
    """


class Resolver(Protocol):
    """One rung of the resolution ladder (ROADMAP.md §2).

    The dispatcher runs the first resolver that `accepts` a config, then escalates
    to the next accepting one if that result comes up empty (see `run_report`). A
    config author never selects a tier (§2a, §0) — tier choice and escalation are
    entirely this seam's concern. `accepts` answers routing
    ("does this tier claim this config?"), which is distinct from whether the run
    then succeeds — a declared-but-stubbed tier can accept and still raise.
    """

    tier: int
    name: str

    def accepts(self, config: ExtractionConfig) -> bool: ...

    def run(
        self,
        config: ExtractionConfig,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> RunResult: ...


def _requires_browser(config: ExtractionConfig) -> bool:
    """Whether the config needs a browser tier (JS-driven infinite scroll)."""
    return bool(config.pagination and config.pagination.infinite_scroll)


class Tier1Resolver:
    """Tier 1: `httpx` fetch + `parsel` selectors, no browser (ROADMAP.md §2)."""

    tier = 1
    name = "tier-1 (static fetch + selectors)"

    def accepts(self, config: ExtractionConfig) -> bool:
        # Tier 1 handles anything achievable without a browser; JS-only
        # capabilities (infinite scroll) are left for tier 2 to pick up.
        return not _requires_browser(config)

    def run(
        self,
        config: ExtractionConfig,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> RunResult:
        """Fetch and extract, following next-link pagination to the end.

        Honors the politeness policy (ROADMAP.md §2d/§6): robots.txt disallowed
        URLs are recorded as `blocked` and never fetched, and the crawl-delay is
        applied between fetches. `sleep` is injectable so timing can be asserted.
        """
        owns_client = client is None
        client = client or httpx.Client(follow_redirects=True, timeout=10.0)
        gate = Politeness(config.politeness or PolitenessPolicy(), client, sleep=sleep)
        result = RunResult(tier=self.tier)
        seen: set[str] = set()
        url: str | None = config.target
        try:
            while url and url not in seen and len(seen) < _MAX_PAGES:
                seen.add(url)
                if not gate.can_fetch(url):
                    result.blocked.append(url)
                    break
                gate.before_fetch(url)
                response = client.get(url)
                response.raise_for_status()
                result.pages_fetched += 1
                result.records.extend(extract_records(response.text, config))
                url = _next_url(response.text, url, config)
        finally:
            if owns_client:
                client.close()
        return result


def _exhaust_infinite_scroll(page: Page) -> None:
    """Scroll to the bottom until the page stops growing (a generic stop signal).

    JS-driven feeds append content as the viewport nears the bottom, whether by
    fetching more or by rendering held-back DOM — so the one signal every such
    feed shares is that `scrollHeight` grows. After each scroll we wait for the
    height to actually increase; a grace window with no growth means the end of
    the feed. This works for both network-driven and synchronous-DOM feeds, and
    is nothing site-specific (§0). `_MAX_SCROLLS` bounds a feed that never stops.
    """
    for _ in range(_MAX_SCROLLS):
        height = page.evaluate("document.body.scrollHeight")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            page.wait_for_function(
                "previous => document.body.scrollHeight > previous",
                arg=height,
                timeout=_SCROLL_GROWTH_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            return


class Tier2Resolver:
    """Tier 2: JS-rendered pages via a headless browser (ROADMAP.md §2).

    A thin adapter over Playwright: it renders each page in headless Chromium,
    then reuses the very same `parsel` extraction as tier 1 on the rendered HTML,
    so field/`item`/pagination semantics stay identical across tiers. The
    dispatcher reaches it for browser-only capabilities — today, JS-driven
    infinite scroll. It honors the same politeness gate as tier 1 (robots.txt +
    crawl-delay); nothing here is site-specific (§0). When the config opts into
    capture (`capture.har`), the whole run's network traffic is recorded to a
    local-only HAR (ROADMAP.md §2b/§2h) — see `run`.
    """

    tier = 2
    name = "tier-2 (JS rendering)"

    def accepts(self, config: ExtractionConfig) -> bool:
        return True

    def run(
        self,
        config: ExtractionConfig,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> RunResult:
        """Render and extract, following the same politeness gate as tier 1.

        The gate (robots.txt + crawl-delay) runs on an `httpx` client, kept
        separate from the browser: robots is a plain HTTP concern, and the check
        must happen *before* a page is ever navigated to. Infinite scroll is
        exhausted per page; next-link pagination still works via `_next_url`.

        A single browser context spans the whole run's pages. When the config
        opts into capture, that context records a HAR of every request it makes,
        a console collector observes its console output and errors, an
        accessibility collector snapshots each rendered page's a11y tree, a
        header collector records each page's response headers, and/or a
        storage-state collector captures the context's cookies + localStorage —
        all written to one fresh local-only run cache directory (ROADMAP.md
        §2b/§2c/§2h); the HAR is flushed on `context.close()`, the rest after.
        Without capture, nothing is recorded and the paths stay None.
        """
        owns_client = client is None
        client = client or httpx.Client(follow_redirects=True, timeout=10.0)
        gate = Politeness(config.politeness or PolitenessPolicy(), client, sleep=sleep)
        result = RunResult(tier=self.tier)
        capture = config.capture
        want_har = bool(capture and capture.har)
        want_console = bool(capture and capture.console)
        want_a11y = bool(capture and capture.accessibility)
        want_headers = bool(capture and capture.headers)
        want_storage = bool(capture and capture.storage)
        # One run directory shared by every capture this run produces.
        run_dir = (
            storage.new_run_cache_dir()
            if (want_har or want_console or want_a11y or want_headers or want_storage)
            else None
        )
        har_path = run_dir / storage.HAR_FILENAME if (run_dir and want_har) else None
        if har_path is not None:
            result.har_path = har_path
        console = ConsoleCollector() if want_console else None
        a11y = AccessibilityCollector() if want_a11y else None
        headers = HeaderCollector() if want_headers else None
        storage_state = StorageStateCollector() if want_storage else None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    # record_har_path is per-context; recording it on the context
                    # (not per page) captures the whole run in one HAR.
                    context = (
                        browser.new_context(record_har_path=har_path)
                        if har_path is not None
                        else browser.new_context()
                    )
                    try:
                        self._crawl(
                            context, config, gate, result, console, a11y, headers
                        )
                        # Storage state is a context-level capture (cookies +
                        # localStorage span pages), taken once after the crawl and
                        # before close. Opportunistic like every signal: a capture
                        # failure must never fail the extraction it rode along with.
                        if storage_state is not None:
                            try:
                                # dict(...) coerces Playwright's StorageState
                                # TypedDict to a plain dict, keeping the signals
                                # module free of any Playwright type dependency.
                                storage_state.capture(dict(context.storage_state()))
                            except PlaywrightError:
                                pass
                    finally:
                        context.close()  # flushes the HAR to disk, if recording
                finally:
                    browser.close()
            # The collectors hold their records in memory; persist them once the
            # browser is closed and every event has been delivered (§2c/§2h).
            if console is not None and run_dir is not None:
                console_path = run_dir / storage.CONSOLE_FILENAME
                console.write(console_path)
                result.console = console.signal
                result.console_log_path = console_path
            if a11y is not None and run_dir is not None:
                a11y_path = run_dir / storage.ACCESSIBILITY_FILENAME
                a11y.write(a11y_path)
                result.accessibility = a11y.signal
                result.accessibility_path = a11y_path
            if headers is not None and run_dir is not None:
                headers_path = run_dir / storage.HEADERS_FILENAME
                headers.write(headers_path)
                result.headers = headers.signal
                result.headers_path = headers_path
            if storage_state is not None and run_dir is not None:
                storage_state_path = run_dir / storage.STORAGE_STATE_FILENAME
                storage_state.write(storage_state_path)
                result.storage_state = storage_state.signal
                result.storage_state_path = storage_state_path
        finally:
            if owns_client:
                client.close()
        return result

    def _crawl(
        self,
        context: BrowserContext,
        config: ExtractionConfig,
        gate: Politeness,
        result: RunResult,
        console: ConsoleCollector | None = None,
        a11y: AccessibilityCollector | None = None,
        headers: HeaderCollector | None = None,
    ) -> None:
        seen: set[str] = set()
        url: str | None = config.target
        while url and url not in seen and len(seen) < _MAX_PAGES:
            seen.add(url)
            if not gate.can_fetch(url):
                result.blocked.append(url)
                break
            gate.before_fetch(url)
            page = context.new_page()
            # Attach before navigating so load-time console output and errors count.
            if console is not None:
                console.attach(page)
            try:
                response = page.goto(url, wait_until="networkidle")
                # Record the main document's response headers (§2c), if any.
                if headers is not None and response is not None:
                    headers.capture(response.headers)
                self._await_items(page, config)
                if _requires_browser(config):
                    _exhaust_infinite_scroll(page)
                html = page.content()
                # Snapshot the a11y tree after the page has fully rendered.
                if a11y is not None:
                    a11y.capture(page)
            finally:
                page.close()
            result.pages_fetched += 1
            result.records.extend(extract_records(html, config))
            url = _next_url(html, url, config)

    def _await_items(self, page: Page, config: ExtractionConfig) -> None:
        """Wait for the config's `item` selector to render before capturing.

        `networkidle` reports the network settled, not that an SPA has populated
        its listing — the products often arrive on an XHR whose idle window fires
        before the DOM is updated. So when the config names a repeating `item`,
        wait for at least one to attach. This keys off the config's own selector,
        nothing site-specific (§0). A genuinely empty listing has no such element;
        we wait out the bounded window and fall through, extracting zero, rather
        than hang. Single-record configs (no `item`) skip the wait entirely.
        """
        if not config.item:
            return
        try:
            page.wait_for_selector(
                config.item, state="attached", timeout=_ITEM_RENDER_TIMEOUT_MS
            )
        except PlaywrightTimeoutError:
            return


# The resolution ladder, tried in order (ROADMAP.md §2). Tier 3 (self-healing)
# joins this tuple when it is built.
DEFAULT_TIERS: tuple[Resolver, ...] = (Tier1Resolver(), Tier2Resolver())


def select_resolver(
    config: ExtractionConfig, tiers: tuple[Resolver, ...] = DEFAULT_TIERS
) -> Resolver:
    """The first tier that can handle `config` — the one the dispatcher runs first.

    Capability routing only: it answers "which rung starts the run", not "which
    rung finishes it". Content-driven escalation (running a higher tier when this
    one comes up empty) is `run_report`'s job, not this function's.
    """
    for resolver in tiers:
        if resolver.accepts(config):
            return resolver
    # The last (most capable) tier always accepts; reaching here is defensive.
    raise TierUnavailableError("no resolution tier can handle this config")


def _should_escalate(result: RunResult) -> bool:
    """Whether an empty tier result warrants trying the next tier (ROADMAP.md §2).

    The trigger is **zero records**, never a null field: a run that produced
    records is a legitimate result even if some fields are null (§2a), so it is
    returned as-is. Zero records means the tier's selectors matched no items at
    all — the hallmark of a listing that only populates in a browser. A
    robots-blocked run is *not* escalated: `blocked` is a non-empty result, and a
    heavier tier is for rendering, never for working around the disallow (§6).
    """
    return not result.records and not result.blocked


def run_report(
    config: ExtractionConfig,
    client: httpx.Client | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
    tiers: tuple[Resolver, ...] = DEFAULT_TIERS,
) -> RunResult:
    """Resolve `config` through the dispatcher and return the full run report.

    Walks the tiers that accept the config in order, running the first and
    escalating to the next only while the result is empty (`_should_escalate`).
    A tier that returns records ends the walk; if every tier comes up empty, the
    most capable tier's (empty) result is returned. Alongside extraction, the run
    also probes the target's origin for a published API spec (§2b layer 1) and
    stamps any it observes on the result.
    """
    candidates = [resolver for resolver in tiers if resolver.accepts(config)]
    if not candidates:
        # The last (most capable) tier always accepts; reaching here is defensive.
        raise TierUnavailableError("no resolution tier can handle this config")
    result = RunResult()
    attempted: list[int] = []
    for resolver in candidates:
        result = resolver.run(config, client, sleep=sleep)
        attempted.append(resolver.tier)
        if not _should_escalate(result):
            break
    # Record the escalation path on the resolving tier's result, for §2d
    # observability (a directly-invoked resolver leaves this empty).
    result.tiers_attempted = attempted
    _discover_api_surface(config, client, result)
    return result


def _discover_api_surface(
    config: ExtractionConfig, client: httpx.Client | None, result: RunResult
) -> None:
    """Probe the target for a published spec and a GraphQL endpoint (§2b).

    §2b makes discovery a companion of every run, not a separate crawl. When the
    caller supplied a client we probe with it (so tests' mock transports and any
    connection reuse apply); otherwise we open and close a throwaway one, mirroring
    how the resolvers manage their own — a single client for both probes. Neither
    probe is crawl-delay-spaced (see the discovery modules), so they add no sleep
    to the run, and neither raises.
    """
    if client is not None:
        _probe_surface(config, client, result)
        return
    with httpx.Client(follow_redirects=True, timeout=10.0) as owned:
        _probe_surface(config, owned, result)


def _probe_surface(
    config: ExtractionConfig, client: httpx.Client, result: RunResult
) -> None:
    result.api_spec = discover_spec(config.target, client, policy=config.politeness)
    result.graphql = discover_graphql(config.target, client, policy=config.politeness)


def run(
    config: ExtractionConfig, client: httpx.Client | None = None
) -> list[dict[str, object]]:
    """Resolve `config` and return just the records (see `run_report`)."""
    return run_report(config, client).records
