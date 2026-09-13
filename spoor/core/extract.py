"""Extraction and the resolution-tier dispatcher (ROADMAP.md §2).

Holds the escalation seam — an ordered ladder of `Resolver` rungs that a config
is dispatched through, never chosen by the config author (§2a, §0). Tier 1
(`httpx` fetch + `parsel` selectors) and tier 2 (headless-Chromium rendering via
Playwright, reusing tier 1's `parsel` extraction on the rendered HTML) are both
implemented here. Escalation reaches tier 2 two ways, both generic (§0): by
*capability* (a config requesting a browser-only feature such as JS-driven
infinite scroll, which tier 1 declines up front) and by *content* (tier 1 runs
but extracts zero records, so the dispatcher re-renders in a browser). Tier 3
(self-healing) is also wired here, but as a run-wide `Healer` threaded through
the resolving tier rather than as its own resolver rung. Per §0 there is no
site-specific logic: everything is driven by the config.
"""

from __future__ import annotations

import functools
import math
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

from spoor.api_discovery.correlation import (
    ActionCorrelation,
    Checkpoint,
    CheckpointRecorder,
    correlate,
)
from spoor.api_discovery.discovery import DiscoveredSpec, discover_spec
from spoor.api_discovery.graphql import DiscoveredGraphQL, discover_graphql
from spoor.api_discovery.synthesis import SynthesizedSpec, synthesize_from_har
from spoor.core.config import (
    ExtractionConfig,
    FieldSpec,
    PolitenessPolicy,
    RetryPolicy,
)
from spoor.core.fingerprint_cache import cache_for_target
from spoor.core.self_healing import Healer, HealEvent, Screenshotter
from spoor.core.visual import InvalidImageError, perceptual_hash
from spoor.operational.challenge import ChallengeSignal, detect_challenge
from spoor.operational.change_detection import detector_for_target
from spoor.operational.politeness import Politeness
from spoor.operational.retry import (
    FetchFailure,
    RetryingFetcher,
    RetryingNavigator,
)
from spoor.security import storage
from spoor.security.session import apply_cookies, load_session
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
# How long a per-element screenshot may wait for the element before giving up
# (ms), for the tier-3 visual signal. Short: a hidden or zero-size candidate must
# fail fast to "no visual signal" (None) rather than stall the heal on it.
_SCREENSHOT_TIMEOUT_MS = 2000


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
    when not captured. `synthesized_spec`, when set, is the API spec synthesized
    by clustering the captured HAR's requests into templated endpoints (§2b layer
    4) — only present when a HAR was captured; the OpenAPI document it wrote stays
    in the local-only cache (§2h). `checkpoints` are the action marks the browser
    tier recorded during the run (load, each scroll) — the raw timeline layer-5
    correlation attributes requests to; empty for a run that captured no HAR.
    `action_correlation`, when set, is that correlation — captured requests
    attributed to the action that likely triggered them (§2b layer 5) — only
    present when a HAR and checkpoints were captured; the document it wrote (with
    the templated paths) stays in the local-only cache (§2h).
    `spoor/operational/observability.py` turns these into the operator-facing
    summary.
    """

    records: list[dict[str, object]] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    # URLs the tier-1 fetch could not retrieve — a permanent error (e.g. 404) or
    # a transient one that exhausted its retries (ROADMAP.md §2d Phase 3.5). Each
    # carries a generic HTTP-category reason and the attempt count; recorded, not
    # raised, so a run degrades honestly. `retries` counts transient failures
    # that were retried this run (whether or not they eventually succeeded).
    dead_letter: list[FetchFailure] = field(default_factory=list)
    retries: int = 0
    # URLs a run with change detection on found unchanged since a prior run
    # (ROADMAP.md §2d Phase 3.5): a 304 Not Modified, or a body whose content hash
    # matched what was recorded. These pages were deliberately not re-extracted, so
    # a run whose only "result" is unchanged pages is a legitimate "nothing changed"
    # answer, not an empty miss to escalate. Empty on a plain (non-monitoring) run.
    unchanged: list[str] = field(default_factory=list)
    # An anti-bot challenge recognized in a fetched page (ROADMAP.md §2d): a
    # CAPTCHA/interstitial fingerprint, surfaced so the run reports "hit a wall"
    # rather than silently emitting challenge markup as data. Recognized whether
    # the wall rode a successful response or sat *behind* an error status (a
    # dead-lettered fetch carrying a challenge promotes it here). Detection, never
    # bypass; None on an ordinary run. Vendor name only, never a captured secret
    # (§2h).
    challenge: ChallengeSignal | None = None
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
    synthesized_spec: SynthesizedSpec | None = None
    checkpoints: list[Checkpoint] = field(default_factory=list)
    action_correlation: ActionCorrelation | None = None
    # Tier-3 self-healing events for this run (§2, §2d): each is a field whose
    # broken selector tier 3 re-resolved — confidently (field filled) or as an
    # uncertain match flagged for review (field left null). Field name + winning
    # confidence only, never the matched text (§2h). Empty when nothing healed.
    heal_events: list[HealEvent] = field(default_factory=list)


def _value_from_element(element: Selector, spec: FieldSpec) -> str | float | None:
    """The field value carried by an already-resolved element, per its spec.

    Text (normalized) by default, or the named `attr`; `number`-typed fields are
    coerced. Shared by the direct-hit path and the tier-3 heal path so a healed
    element yields exactly what the selector would have.
    """
    if spec.attr is not None:
        raw = element.attrib.get(spec.attr)
    else:
        text = element.xpath("normalize-space(string(.))").get()
        raw = text if text else None
    if raw is None:
        return None
    if spec.type == "number":
        return _coerce_number(raw)
    return raw


# The first numeric run in a string. The optional leading `-` is only taken as
# a sign when it isn't glued to a preceding word or digit (the lookbehind), so
# an internal hyphen — e.g. a SKU like "SKU-42" — is read as 42, not -42, while
# digits themselves are still found anywhere (e.g. "USD5" -> 5). Assumes `.`
# decimal / `,` thousands; locale-specific formats (e.g. "1.234,56") are out of
# scope.
_NUMBER_RE = re.compile(r"(?:(?<![\w.])-)?(?:\d[\d,]*(?:\.\d+)?|\.\d+)")


def _coerce_number(text: str) -> float | None:
    """Best-effort numeric coercion: parse the first number found in the text.

    Returns None when no number is found, and also when the parsed value is not a
    finite float: a numeral beyond float range (hundreds of digits) coerces to
    inf/-inf, which has no valid JSON representation (`json.dumps` emits the bare
    token `Infinity`, which strict parsers reject). Treating a non-finite result as
    "no usable number" keeps the output contract valid JSON rather than emitting a
    value that would corrupt the file or a downstream reload.
    """
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    try:
        value = float(match.group().replace(",", ""))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _extract_value(
    root: Selector,
    spec: FieldSpec,
    *,
    healer: Healer | None = None,
    field_name: str | None = None,
    item_selector: str | None = None,
) -> str | float | None:
    """The value for one field, resolving its selector against `root`.

    On a direct hit, the resolved element is remembered for tier-3 self-healing
    (when a `healer` is supplied). On a miss, tier 3 is asked to heal the field
    from what it saw before: a confident match fills the field, a weak one leaves
    it null but is flagged for review (see `Healer.attempt`). Without a healer the
    behavior is unchanged — a miss is simply a null field (§2a).

    `item_selector` set marks item mode: `root` is a single listing row, so the
    fingerprint is keyed per `(item_selector, field_name)` and captured
    text-agnostic, and healing scores only the candidates *within that row*. In
    item mode a heal only ever fires against a fingerprint a prior run persisted
    (see `Healer.attempt`), so a row that genuinely lacks the field is left null
    rather than filled from a sibling row.

    Note the two-step contract: healing resolves the *element*, then
    `_value_from_element` extracts the *value* from it. These are independent, so
    a confident heal to the right element can still yield a null value when the
    field has an `attr` the healed element happens not to carry — the run summary
    counts it as a confident heal (the element was re-resolved) even though the
    field is null. This is intentional and honest: the healer's job is element
    re-resolution, not guaranteeing a value the source markup no longer holds.
    """
    matches = root.css(spec.selector)
    element: Selector | None = matches[0] if matches else None
    if element is not None:
        if healer is not None and field_name is not None:
            healer.remember(field_name, element, item_selector=item_selector)
    elif healer is not None and field_name is not None:
        element = healer.attempt(field_name, root, item_selector=item_selector)
    if element is None:
        return None
    return _value_from_element(element, spec)


def extract_records(
    html: str, config: ExtractionConfig, healer: Healer | None = None
) -> list[dict[str, object]]:
    """Extract all records from one page's HTML per the config.

    Tier-3 self-healing (via `healer`) applies to both single-record and item
    (listing) configs. Single-record: each field selector maps to at most one
    element on the page — an unambiguous fingerprint-and-heal. Item mode: each
    field selector resolves *within* each matched row, so healing is per-row —
    the field's fingerprint is keyed by `(item, field_name)` and text-agnostic
    (a listing's rows share structure but differ in text), and a broken field is
    re-resolved against the candidates inside each row (§2 item-mode decision
    note).

    The `item` selector *itself* is healed too: on a successful resolve the row
    container is fingerprinted, and when a later run finds `item` matching nothing,
    tier 3 re-resolves the repeating row group (`Healer.attempt_container`) — but
    only when a single coherent sibling group is confident, refusing to fabricate a
    listing from a lone look-alike or ambiguous groups (§2 container decision note).
    A refusal leaves the listing with no rows, surfaced as an uncertain match.
    """
    page = Selector(text=html)
    if config.item:
        rows = list(page.css(config.item))
        if rows:
            if healer is not None:
                healer.remember_container(config.item, rows[0])
        elif healer is not None:
            healed = healer.attempt_container(config.item, page)
            if healed is not None:
                rows = healed
        return [
            {
                name: _extract_value(
                    root,
                    spec,
                    healer=healer,
                    field_name=name,
                    item_selector=config.item,
                )
                for name, spec in config.fields.items()
            }
            for root in rows
        ]
    return [
        {
            name: _extract_value(page, spec, healer=healer, field_name=name)
            for name, spec in config.fields.items()
        }
    ]


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
        healer: Healer | None = None,
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
        healer: Healer | None = None,
    ) -> RunResult:
        """Fetch and extract, following next-link pagination to the end.

        Honors the politeness policy (ROADMAP.md §2d/§6): robots.txt disallowed
        URLs are recorded as `blocked` and never fetched, and the crawl-delay is
        applied between fetches. `sleep` is injectable so timing can be asserted.
        When a `healer` is supplied, single-record field selectors are remembered
        on success and healed on failure through it (§2); its events are surfaced
        by the dispatcher.

        A supplied session (`config.session`, ROADMAP.md §2h) is validated up
        front — before the client is even built — so a missing or malformed
        session fails loudly with no fetch, then its cookies are loaded into the
        fetch client so an authenticated static run carries them. localStorage in
        the session has no meaning without JS; a localStorage-gated target extracts
        nothing here and escalates to the browser tier, which applies it (§2h).
        """
        session = (
            load_session(config.session) if config.session is not None else None
        )
        owns_client = client is None
        client = client or httpx.Client(follow_redirects=True, timeout=10.0)
        gate = Politeness(config.politeness or PolitenessPolicy(), client, sleep=sleep)
        fetcher = RetryingFetcher(client, config.retry or RetryPolicy(), sleep=sleep)
        detector = (
            detector_for_target(config.target) if config.change_detection else None
        )
        result = RunResult(tier=self.tier)
        seen: set[str] = set()
        url: str | None = config.target
        try:
            if session is not None:
                apply_cookies(session, client)
            while url and url not in seen and len(seen) < _MAX_PAGES:
                seen.add(url)
                if not gate.can_fetch(url):
                    result.blocked.append(url)
                    break
                gate.before_fetch(url)
                # Conditional-request validators from a prior run, when change
                # detection is on (empty on a first run or a plain run) (§2d).
                headers = detector.conditional_headers(url) if detector else None
                outcome = fetcher.get(url, headers=headers)
                if isinstance(outcome, FetchFailure):
                    # Classified fetch failure: record it and stop this crawl —
                    # a failed page has no next-link to follow (§2d). If a challenge
                    # was recognized *behind* the error status, surface it too — the
                    # failure was a wall, not just an opaque error (§2d).
                    result.dead_letter.append(outcome)
                    if result.challenge is None and outcome.challenge is not None:
                        result.challenge = outcome.challenge
                    break
                result.pages_fetched += 1
                # Change detection (§2d): an unchanged page (304, or a body whose
                # content hash matches a prior run) is recorded and *not* re-
                # extracted. A 304 carries no body, so `_next_url` finds no next
                # link and the crawl ends naturally; a hash-matched 200 still has a
                # body, so pagination continues past it.
                if detector is not None and detector.is_unchanged(url, outcome):
                    result.unchanged.append(url)
                    url = _next_url(outcome.text, url, config)
                    continue
                # Recognize an anti-bot challenge in the fetched page (§2d): a
                # 2xx challenge would otherwise be scraped as if it were data.
                # First page to look like one names the run's challenge.
                if result.challenge is None:
                    result.challenge = detect_challenge(outcome.text)
                result.records.extend(extract_records(outcome.text, config, healer))
                # Remember this page's validators for the next run's comparison.
                if detector is not None:
                    detector.record(url, outcome)
                url = _next_url(outcome.text, url, config)
        finally:
            result.retries = fetcher.retries
            if detector is not None:
                detector.save()
            if owns_client:
                client.close()
        return result


def _exhaust_infinite_scroll(
    page: Page, recorder: CheckpointRecorder | None = None
) -> None:
    """Scroll to the bottom until the page stops growing (a generic stop signal).

    JS-driven feeds append content as the viewport nears the bottom, whether by
    fetching more or by rendering held-back DOM — so the one signal every such
    feed shares is that `scrollHeight` grows. After each scroll we wait for the
    height to actually increase; a grace window with no growth means the end of
    the feed. This works for both network-driven and synchronous-DOM feeds, and
    is nothing site-specific (§0). `_MAX_SCROLLS` bounds a feed that never stops.

    When a `recorder` is supplied, each scroll is marked just before it happens,
    so layer-5 correlation can attribute the requests it triggered to it (§2b).
    """
    for index in range(_MAX_SCROLLS):
        height = page.evaluate("document.body.scrollHeight")
        if recorder is not None:
            recorder.mark(f"scroll #{index + 1}")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            page.wait_for_function(
                "previous => document.body.scrollHeight > previous",
                arg=height,
                timeout=_SCROLL_GROWTH_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            return


def _make_screenshotter(page: Page) -> Screenshotter:
    """A screenshotter bound to `page`: parsel element -> its crop's visual hash.

    Bridges the two worlds tier 3 spans — extraction works on the *parsel* tree
    parsed from `page.content()`, while a screenshot needs the *live* page — by
    computing the element's absolute XPath (stable across that identical
    serialization) and screenshotting it through a Playwright `xpath=` locator,
    then perceptual-hashing the PNG (§2 tier table). Purely opportunistic (§2c): a
    hidden, zero-size, unlocatable, or un-decodable element yields None (no visual
    signal), never an error that would fail the extraction it rode along with.
    Nothing here is site-specific (§0) — the same bridge runs for every target.
    """

    def screenshot_hash(element: Selector) -> int | None:
        try:
            xpath = element.root.getroottree().getpath(element.root)
            png = page.locator(f"xpath={xpath}").screenshot(
                timeout=_SCREENSHOT_TIMEOUT_MS
            )
            return perceptual_hash(png)
        except (PlaywrightError, PlaywrightTimeoutError, InvalidImageError, ValueError):
            return None

    return screenshot_hash


class Tier2Resolver:
    """Tier 2: JS-rendered pages via a headless browser (ROADMAP.md §2).

    A thin adapter over Playwright: it renders each page in headless Chromium,
    then reuses the very same `parsel` extraction as tier 1 on the rendered HTML,
    so field/`item`/pagination semantics stay identical across tiers. The
    dispatcher reaches it for browser-only capabilities — today, JS-driven
    infinite scroll. It honors the same politeness gate as tier 1 (robots.txt +
    crawl-delay) and retries a transient navigation failure through the same
    `RetryPolicy` (§2d) — a timeout, dropped connection, or 5xx/429 is retried
    with backoff, and a page it ultimately cannot load is dead-lettered rather
    than crashing the run. Nothing here is site-specific (§0). When the config
    opts into capture (`capture.har`), the whole run's network traffic is
    recorded to a local-only HAR (ROADMAP.md §2b/§2h) — see `run`.
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
        healer: Healer | None = None,
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

        A supplied session (`config.session`, ROADMAP.md §2h) is validated up
        front — before Chromium is launched — so a missing or malformed session
        fails loudly and cheaply, then handed to the browser context so Playwright
        applies the whole state (cookies *and* per-origin localStorage), reaching
        content gated behind either.
        """
        session = (
            load_session(config.session) if config.session is not None else None
        )
        owns_client = client is None
        client = client or httpx.Client(follow_redirects=True, timeout=10.0)
        gate = Politeness(config.politeness or PolitenessPolicy(), client, sleep=sleep)
        # Browser-tier navigation retry (§2d, Phase 3.5): a transient navigation
        # failure (a timeout, a dropped connection, a 5xx/429 on the response) is
        # retried with the same policy/backoff as tier 1, instead of an uncaught
        # Playwright error crashing the whole run. Same transport-agnostic
        # classification — only the transport differs.
        navigator = RetryingNavigator(config.retry or RetryPolicy(), sleep=sleep)
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
        # Checkpoints only matter when there is a HAR to correlate them against
        # (§2b layer 5); without capture there is nothing to attribute.
        recorder = CheckpointRecorder() if want_har else None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    # record_har_path is per-context; recording it on the context
                    # (not per page) captures the whole run in one HAR. A supplied
                    # session (§2h) is applied here too — Playwright loads the
                    # storage-state file's cookies + localStorage into the context.
                    # Branched explicitly (rather than building a kwargs dict) so
                    # each optional argument keeps its precise Playwright type.
                    session_path = str(session.path) if session is not None else None
                    if har_path is not None and session_path is not None:
                        context = browser.new_context(
                            record_har_path=har_path, storage_state=session_path
                        )
                    elif har_path is not None:
                        context = browser.new_context(record_har_path=har_path)
                    elif session_path is not None:
                        context = browser.new_context(storage_state=session_path)
                    else:
                        context = browser.new_context()
                    try:
                        self._crawl(
                            context,
                            config,
                            gate,
                            navigator,
                            result,
                            console,
                            a11y,
                            headers,
                            recorder,
                            healer,
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
            # The action timeline the crawl recorded (§2b layer 5). Just the
            # timestamps; the HAR they correlate against is the local-only artifact.
            if recorder is not None:
                result.checkpoints = recorder.checkpoints
        finally:
            result.retries = navigator.retries
            if owns_client:
                client.close()
        return result

    def _crawl(
        self,
        context: BrowserContext,
        config: ExtractionConfig,
        gate: Politeness,
        navigator: RetryingNavigator,
        result: RunResult,
        console: ConsoleCollector | None = None,
        a11y: AccessibilityCollector | None = None,
        headers: HeaderCollector | None = None,
        recorder: CheckpointRecorder | None = None,
        healer: Healer | None = None,
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
                # Mark the navigation just before it fires, so layer-5 correlation
                # can attribute the load's requests to it (§2b). One "load" mark per
                # page; a paginated crawl records several.
                if recorder is not None:
                    recorder.mark("load")
                # Navigate through the retrying navigator (§2d): a transient
                # timeout / dropped connection / 5xx-429 is retried; a permanent
                # or exhausted failure comes back as a FetchFailure to dead-letter.
                # `partial` binds this iteration's page/url eagerly (no loop-var
                # closure), and the navigator invokes it once per attempt.
                response = navigator.navigate(
                    functools.partial(page.goto, url, wait_until="networkidle"),
                    url,
                    transient_exceptions=(PlaywrightTimeoutError, PlaywrightError),
                )
                if isinstance(response, FetchFailure):
                    # Navigation failed unrecoverably: record it and stop this
                    # crawl — a page that never loaded has no next-link to follow
                    # (§2d), the same terminal handling as tier 1. page.close()
                    # still runs via the finally below. When the failure was an
                    # error *status* (a response arrived — status not None), scan
                    # the rendered body for an anti-bot wall served behind it: the
                    # browser holds the DOM, so `page.content()` is the right source
                    # (the navigator stays body-free). A pure transport failure
                    # (timeout / dropped connection, status None) has no body worth
                    # scanning — and this keeps page.content() off the path where a
                    # never-loaded page could make it raise, so the dead-letter path
                    # stays crash-proof. Mirrors tier 1, which likewise detects only
                    # on a response that arrived (§2d).
                    if result.challenge is None and response.status is not None:
                        result.challenge = detect_challenge(page.content())
                    result.dead_letter.append(response)
                    break
                # Record the main document's response headers (§2c), if any.
                if headers is not None and response is not None:
                    headers.capture(response.headers)
                self._await_items(page, config)
                if _requires_browser(config):
                    _exhaust_infinite_scroll(page, recorder)
                html = page.content()
                # Snapshot the a11y tree after the page has fully rendered.
                if a11y is not None:
                    a11y.capture(page)
                # Extract while the page is still open, so tier 3 can screenshot
                # elements for the perceptual-hash visual signal (§2 tier table).
                # The screenshotter is bound to this live page and cleared after,
                # so it never outlives the page it captures from.
                # Recognize an anti-bot challenge in the rendered page (§2d),
                # same tier-agnostic scan as tier 1 — a browser can render a
                # challenge just as a static fetch can land on one.
                if result.challenge is None:
                    result.challenge = detect_challenge(html)
                page_records = self._extract_on_live_page(html, config, healer, page)
            finally:
                page.close()
            result.pages_fetched += 1
            result.records.extend(page_records)
            url = _next_url(html, url, config)

    def _extract_on_live_page(
        self,
        html: str,
        config: ExtractionConfig,
        healer: Healer | None,
        page: Page,
    ) -> list[dict[str, object]]:
        """Extract `html`'s records with tier 3 able to screenshot the live page.

        Binds a screenshotter (element -> cropped-screenshot perceptual hash) to
        `page` on the healer for the duration of extraction, so `remember`/`heal`
        can capture and compare the visual signal (§2 tier table), then clears it —
        the screenshotter must never be used after the page closes. Without a
        healer this is a plain extraction; the DOM extraction itself is unchanged.
        """
        if healer is None:
            return extract_records(html, config, None)
        healer.screenshotter = _make_screenshotter(page)
        try:
            return extract_records(html, config, healer)
        finally:
            healer.screenshotter = None

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


# The resolution ladder, tried in order (ROADMAP.md §2). Tier 3 self-healing is
# not a resolver rung here; `run_report` threads one run-wide `Healer` through
# whichever resolver handles the run.
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
    A dead-lettered run is likewise not escalated: a classified fetch failure (a
    404, or a 503 that exhausted its retries, §2d) is a definite answer about the
    origin, not an empty page a browser might render differently — re-fetching it
    in a heavier tier would only hit the same failing server. An unchanged run
    (change detection found the page not modified, §2d) is not escalated either:
    the page deliberately wasn't re-extracted because it matches a prior run, not
    because a selector missed — a heavier tier would only re-render what hasn't
    changed.
    """
    return (
        not result.records
        and not result.blocked
        and not result.dead_letter
        and not result.unchanged
    )


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

    Tier-3 self-healing (§2) rides along: one `Healer` over the target's
    persistent per-domain fingerprint cache is created for the run and threaded
    through whichever tier resolves it, so field selectors are fingerprinted on
    success and healed on failure. Its newly-learned fingerprints are persisted
    after the walk, and its heal events (confident fills + uncertain matches) are
    stamped on the result for the run summary (§2d).
    """
    candidates = [resolver for resolver in tiers if resolver.accepts(config)]
    if not candidates:
        # The last (most capable) tier always accepts; reaching here is defensive.
        raise TierUnavailableError("no resolution tier can handle this config")
    healer = Healer(cache_for_target(config.target))
    result = RunResult()
    attempted: list[int] = []
    for resolver in candidates:
        result = resolver.run(config, client, sleep=sleep, healer=healer)
        attempted.append(resolver.tier)
        if not _should_escalate(result):
            break
    # Persist any fingerprints learned this run and surface the heal events on the
    # resolving tier's result (§2, §2d).
    healer.persist()
    result.heal_events = healer.events
    # Record the escalation path on the resolving tier's result, for §2d
    # observability (a directly-invoked resolver leaves this empty).
    result.tiers_attempted = attempted
    _discover_api_surface(config, client, result)
    _synthesize_from_capture(config, result)
    _correlate_from_capture(config, result)
    return result


def _synthesize_from_capture(config: ExtractionConfig, result: RunResult) -> None:
    """Synthesize an API spec from the run's captured HAR, if any (§2b layer 4).

    Runs only when a HAR was captured (`capture.har`, so `har_path` is set); it
    reads that local file, never the network, and never raises — a HAR that can't
    be read or holds no API entries simply leaves `synthesized_spec` None.
    """
    if result.har_path is None:
        return
    result.synthesized_spec = synthesize_from_har(result.har_path, config.target)


def _correlate_from_capture(config: ExtractionConfig, result: RunResult) -> None:
    """Attribute the captured HAR's requests to the run's actions (§2b layer 5).

    Runs only when a HAR was captured and the browser tier recorded action
    checkpoints; it reads that local file, never the network, and never raises —
    an unreadable HAR or nothing attributable simply leaves `action_correlation`
    None. The attribution is a time-window approximation, not proof (§2b).
    """
    if result.har_path is None or not result.checkpoints:
        return
    result.action_correlation = correlate(
        result.checkpoints, result.har_path, config.target
    )


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
