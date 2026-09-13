"""Declarative extraction config model and loader (ROADMAP.md §2a).

The config schema shape is identical for every target (§0) — pointing Spoor at
a new site is a new config, never new code. The model is strict (`extra=forbid`)
so a typo'd key fails loudly rather than being silently ignored, and it carries
no tier-specific knobs: a field's `selector` is only the tier-1 starting point,
and escalation across tiers is entirely the dispatcher's concern (§2).
"""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

FieldType = Literal["string", "number"]


class FieldSpec(BaseModel):
    """One extracted field: a selector, an optional attribute, and a value type.

    By default the selected element's normalized text is taken. When `attr` is
    set, that attribute's value is taken instead (e.g. a link's `href`/`title`,
    an `<img>` `src`) — an element's data often lives in an attribute, not its
    text. `type` coercion (e.g. `number`) applies either way.
    """

    model_config = ConfigDict(extra="forbid")

    selector: str
    attr: str | None = None
    type: FieldType = "string"


class Pagination(BaseModel):
    """How to advance past the first page — a next-link or infinite scroll."""

    model_config = ConfigDict(extra="forbid")

    next: str | None = None
    infinite_scroll: bool = False


class PolitenessPolicy(BaseModel):
    """Operator-facing politeness knobs (ROADMAP.md §2d, §6).

    Defaults respect `robots.txt` and any crawl-delay it declares (§6 commits to
    this by default). `delay`, when set, is a minimum spacing in seconds applied
    between fetches and overrides the robots.txt crawl-delay. `respect_robots`
    may be set to false, but only as an explicit, deliberate opt-out — never the
    default (§6). Retry-After honoring now lives on `RetryPolicy` (§2d Phase 3.5);
    concurrency caps stay deferred until a request pool exists (§2d note).
    """

    model_config = ConfigDict(extra="forbid")

    respect_robots: bool = True
    delay: float | None = None


class RetryPolicy(BaseModel):
    """How a run retries transient failures (ROADMAP.md §2d, Phase 3.5).

    A flaky server's 503, a dropped connection, or a timeout is often momentary,
    so a bounded retry is worth it; a 404 (and other non-429 4xx) is a settled
    answer that retrying only wastes politeness budget on. `max_retries` caps the
    retries *after* the first attempt (0 disables retrying), and `backoff` is the
    base of the exponential wait between them (`backoff * 2**n` seconds).
    `respect_retry_after` honors a `Retry-After` header the server sends on a 503
    / 429 in place of that backoff — the item the `PolitenessPolicy` docstring
    deferred until a retry mechanism existed. Omitted means the defaults below.
    Nothing here is tier- or site-specific (§0): it is HTTP-category classification
    that drives both the tier-1 httpx fetch and the browser tier's navigation.
    """

    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(default=2, ge=0)
    backoff: float = Field(default=0.5, ge=0)
    respect_retry_after: bool = True


class Capture(BaseModel):
    """Opt-in raw network capture for a run (ROADMAP.md §2b/§2c, §2h).

    `har`, when true, tells the browser tier to record every request/response it
    makes as a HAR, written to the local-only run cache (§2h) — never to shared
    output. `console`, when true, tells the browser tier to record the page's
    console output and uncaught errors (§2c) to the same local-only cache; only
    non-sensitive counts of those reach shared output. `accessibility`, when
    true, snapshots the page's accessibility tree (§2c) to the local-only cache,
    surfacing only a node count. `headers`, when true, records the browser tier's
    response headers (§2c) to the local-only cache; only non-sensitive derived
    facts (a count and security-header presence) reach shared output. `storage`,
    when true, captures the browser context's client-side storage state — cookies
    and localStorage (§2c) — writing the raw unredacted state to the local-only
    cache; shared output carries the entries with known secret shapes redacted
    (§2h). None of these has any effect on a run that resolves without a browser
    (tier 1), which
    has no browser session to observe. Default-off here; §2c's default-on capture
    is the full Phase-2.5 target (see the ROADMAP decision note).
    """

    model_config = ConfigDict(extra="forbid")

    har: bool = False
    console: bool = False
    accessibility: bool = False
    headers: bool = False
    storage: bool = False


class ExtractionConfig(BaseModel):
    """A whole extraction job: target, fields, and optional repeating `item`,
    pagination, and politeness policy."""

    model_config = ConfigDict(extra="forbid")

    target: str
    # When set, each field selector resolves *relative to* every matched
    # element and the run emits one record per match (ROADMAP.md §2a). When
    # absent, fields resolve against the whole document (one record per page).
    item: str | None = None
    fields: dict[str, FieldSpec]
    pagination: Pagination | None = None
    # Politeness is a first-class object (ROADMAP.md §2d), not a README promise;
    # omitted means the default policy (respect robots.txt, honor crawl-delay).
    politeness: PolitenessPolicy | None = None
    # How transient tier-1 fetch failures are retried (ROADMAP.md §2d, Phase
    # 3.5); omitted means the default policy (bounded retry with backoff,
    # honoring Retry-After).
    retry: RetryPolicy | None = None
    # Skip re-extracting pages unchanged since the last run (ROADMAP.md §2d, Phase
    # 3.5). Opt-in and default off: on a re-fetch the tier-1 path sends the ETag /
    # Last-Modified a prior run recorded as a conditional request, and a "304 Not
    # Modified" (or a body whose content hash matches) marks the page unchanged and
    # skips its extraction. Off by default because skipping extraction is a
    # behavior change a one-shot scrape shouldn't get by surprise; a monitoring run
    # turns it on. Scope is the tier-1 fetch path (browser-tier is a follow-on).
    change_detection: bool = False
    # Opt-in raw network capture (ROADMAP.md §2b/§2c, §2h); omitted means no
    # capture. Only the browser tier acts on it.
    capture: Capture | None = None


def load_config(text: str) -> ExtractionConfig:
    """Parse YAML config text into a validated ExtractionConfig.

    Raises pydantic.ValidationError on a missing required field (e.g. `target`)
    or an unknown option, before anything is fetched.
    """
    data = yaml.safe_load(text)
    return ExtractionConfig.model_validate(data)
