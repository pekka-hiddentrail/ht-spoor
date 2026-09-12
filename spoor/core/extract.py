"""Tier-1 extraction: fast selectors over fetched HTML, no browser (ROADMAP.md §2).

This is the tier-1 rung only — `httpx` fetch + `parsel` selectors. Escalation to
tiers 2–3 (JS rendering, self-healing) and infinite-scroll pagination require a
browser session and are not handled here; they arrive with later Phase 1/2 work.
Per §0 there is no site-specific logic: everything is driven by the config.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from parsel import Selector

from spoor.core.config import ExtractionConfig, FieldSpec, PolitenessPolicy
from spoor.operational.politeness import Politeness

# Guard against a pagination cycle running forever on a self-linking page.
_MAX_PAGES = 1000


@dataclass
class RunResult:
    """Outcome of a run: the extracted records plus what politeness skipped.

    `blocked` holds URLs that robots.txt disallowed (ROADMAP.md §2d/§6) — these
    are recorded, never fetched. This is deliberately minimal; the full §2d run
    observability summary is Phase 3.5 work.
    """

    records: list[dict[str, object]] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


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


def run_report(
    config: ExtractionConfig,
    client: httpx.Client | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> RunResult:
    """Run a tier-1 extraction, following next-link pagination to the end.

    Honors the politeness policy (ROADMAP.md §2d/§6): robots.txt disallowed URLs
    are recorded as `blocked` and never fetched, and the crawl-delay is applied
    between fetches. `sleep` is injectable so timing can be asserted in tests.
    """
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=10.0)
    gate = Politeness(config.politeness or PolitenessPolicy(), client, sleep=sleep)
    result = RunResult()
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
            result.records.extend(extract_records(response.text, config))
            url = _next_url(response.text, url, config)
    finally:
        if owns_client:
            client.close()
    return result


def run(
    config: ExtractionConfig, client: httpx.Client | None = None
) -> list[dict[str, object]]:
    """Run a tier-1 extraction and return just the records (see `run_report`)."""
    return run_report(config, client).records
