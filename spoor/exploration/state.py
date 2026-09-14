"""State abstraction for exploration mode (ROADMAP.md §2e).

The second §2e slice, still pure logic. Ported from Crawljax's central idea: to
build a *finite* state graph from an AJAX-heavy app, revisiting an equivalent
screen must be recognized as the same state rather than exploding into infinite
near-duplicates. So a page's DOM is normalized — volatile parts stripped — and
hashed into a stable `state_id`.

What identity is built from (a first, PR-tunable cut — §2e notes state-abstraction
tuning takes real iteration):

- **Structure**: every element's tag, in document order and nesting, dropping
  non-structural nodes (`script`/`style`/`noscript`, comments).
- **State-bearing attributes only**: a small allowlist (`role`, `type`, and the
  stable state flags `disabled`/`checked`/`selected`/`open` and their ARIA
  equivalents). These distinguish e.g. an enabled vs. disabled button. Every other
  attribute value — `id`, `class`, `href`, `value`, `nonce`, `data-*` — is ignored,
  so a session token or a random React id never forks a state.
- **Visible text, with volatile spans masked**: timestamps, clock times,
  UUID/long-token strings, and digit runs (counters, ids, prices) are replaced by a
  constant placeholder, so a cart badge reading 3 vs. 4 is one state, while a
  "Maintenance" vs. "Orders" heading is two.

Deliberately no site knowledge (§0): the same normalization runs for every target.
"""

from __future__ import annotations

import hashlib
import re

from parsel import Selector

# Attribute values that are stable *and* state-bearing — worth distinguishing one
# screen state from another. Everything else (id/class/href/value/nonce/data-*) is
# ignored, so volatile values can't fork a state. Extend by PR, not runtime config.
STATE_ATTRIBUTES = (
    "role",
    "type",
    "disabled",
    "checked",
    "selected",
    "open",
    "aria-expanded",
    "aria-selected",
    "aria-checked",
    "aria-disabled",
)

# Non-structural elements dropped before hashing.
_DROP_TAGS = frozenset({"script", "style", "noscript"})

# Volatile text spans, masked to a constant so they can't fork a state. Order
# matters: the specific shapes (datetime, time, uuid, long token) run before the
# catch-all digit run, which mops up counters/ids/prices.
_PLACEHOLDER = "\x00"
_VOLATILE_TEXT_PATTERNS = (
    re.compile(r"\d{4}-\d{2}-\d{2}([t ]\d{2}:\d{2}(:\d{2})?(\.\d+)?z?)?", re.I),
    re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\s*(am|pm)?\b", re.I),
    re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
    ),
    re.compile(r"\b[0-9a-f]{16,}\b", re.I),
    re.compile(r"\b[a-z0-9_-]{24,}\b", re.I),
    re.compile(r"\d+"),
)
_WHITESPACE = re.compile(r"\s+")


def _element_signature(tag: str, attrib: dict[str, str]) -> str:
    """One element's contribution: its tag plus its state-bearing attributes."""
    kept = sorted(
        f"{name}={attrib[name]}" for name in STATE_ATTRIBUTES if name in attrib
    )
    return f"{tag}[{','.join(kept)}]"


def _structure(root: object) -> list[str]:
    """Depth-tagged element signatures in document order (structure + state attrs)."""
    parts: list[str] = []

    def walk(element: object, depth: int) -> None:
        tag = getattr(element, "tag", None)
        if not isinstance(tag, str):  # comment / processing instruction
            return
        if tag in _DROP_TAGS:
            return
        attrib = dict(getattr(element, "attrib", {}))
        parts.append(f"{depth}:{_element_signature(tag, attrib)}")
        for child in element:  # type: ignore[attr-defined]
            walk(child, depth + 1)

    walk(root, 0)
    return parts


def _masked_text(selector: Selector) -> str:
    """Visible text with volatile spans masked and whitespace collapsed."""
    nodes = selector.xpath(
        "//text()[not(ancestor::script) and not(ancestor::style)"
        " and not(ancestor::noscript)]"
    ).getall()
    text = " ".join(nodes).lower()
    for pattern in _VOLATILE_TEXT_PATTERNS:
        text = pattern.sub(_PLACEHOLDER, text)
    return _WHITESPACE.sub(" ", text).strip()


def state_id(html: str) -> str:
    """A stable identifier for a page's abstract state (§2e).

    Equivalent renderings — differing only in timestamps, session tokens, counters,
    whitespace, attribute order, or script/style content — return the same value;
    genuinely different structure, text, or state-bearing attributes return a
    different one. Returns a 64-character SHA-256 hex digest, deterministic across
    calls and process runs.
    """
    selector = Selector(text=html)
    structure = "\n".join(_structure(selector.root))
    canonical = f"{structure}\x00{_masked_text(selector)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
