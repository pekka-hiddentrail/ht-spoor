"""Tier-1 extraction: fast selectors over fetched HTML, no browser (ROADMAP.md §2).

This is the tier-1 rung only — `httpx` fetch + `parsel` selectors. Escalation to
tiers 2–3 (JS rendering, self-healing) and infinite-scroll pagination require a
browser session and are not handled here; they arrive with later Phase 1/2 work.
Per §0 there is no site-specific logic: everything is driven by the config.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx
from parsel import Selector

from spoor.core.config import ExtractionConfig, FieldSpec

# Guard against a pagination cycle running forever on a self-linking page.
_MAX_PAGES = 1000


def _first_text(root: Selector, css: str) -> str | None:
    """First matching element's normalized text, or None if nothing matches."""
    matches = root.css(css)
    if not matches:
        return None
    text = matches[0].xpath("normalize-space(string(.))").get()
    return text if text else None


def _coerce_number(text: str) -> float | None:
    """Best-effort numeric coercion: strip currency/formatting, parse a float."""
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_value(root: Selector, spec: FieldSpec) -> str | float | None:
    text = _first_text(root, spec.selector)
    if text is None:
        return None
    if spec.type == "number":
        return _coerce_number(text)
    return text


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


def run(
    config: ExtractionConfig, client: httpx.Client | None = None
) -> list[dict[str, object]]:
    """Run a tier-1 extraction, following next-link pagination to the end."""
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=10.0)
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    url: str | None = config.target
    try:
        while url and url not in seen and len(seen) < _MAX_PAGES:
            seen.add(url)
            response = client.get(url)
            response.raise_for_status()
            records.extend(extract_records(response.text, config))
            url = _next_url(response.text, url, config)
    finally:
        if owns_client:
            client.close()
    return records
