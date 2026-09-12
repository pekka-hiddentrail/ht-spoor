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
from pydantic import BaseModel, ConfigDict

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
    default (§6). Concurrency caps and Retry-After honoring are deferred until a
    request pool / retry mechanism exists (see the ROADMAP §2d decision note).
    """

    model_config = ConfigDict(extra="forbid")

    respect_robots: bool = True
    delay: float | None = None


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
    facts (a count and security-header presence) reach shared output. None of
    these has any effect on a run that resolves without a browser (tier 1), which
    has no browser session to observe. Default-off here; §2c's default-on capture
    is the full Phase-2.5 target (see the ROADMAP decision note).
    """

    model_config = ConfigDict(extra="forbid")

    har: bool = False
    console: bool = False
    accessibility: bool = False
    headers: bool = False


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
