"""Per-transition signal capture for exploration mode (ROADMAP.md §2e).

Sub-slice 5c of the fifth §2e slice, logic-first (sub-slice 5c-i). §2e captures a
"free/near-free" signal bundle for every transition — the accessibility snapshot,
console output, client-side storage, the network/HAR trace, and a screenshot — and
the wiki's value is showing what each fired action *changed*. This module is the pure
model behind that: `StateSignals` is the bundle captured at one state, and
`diff_signals` computes the before/after `TransitionSignals` for one fired action.

This slice defines and diffs the bundle; filling it from a live page (a real
screenshot hash, live console and network/HAR deltas over CDP) is sub-slice 5c-ii,
behind the same `capture_signals()` seam the explorer calls. Nothing here is
site-specific (§0): the same five signals are diffed for every target.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateSignals:
    """The free/near-free signal bundle captured at one state (§2e).

    One field per §2e free signal: the accessibility-node count (structural
    richness), the console messages visible, the client-side storage keys present,
    the network requests seen (the HAR trace, as request identifiers), and a hash
    of the screenshot (`None` when no screenshot was captured). Tuples, not lists,
    so the bundle is hashable and safe to share between a node and its diffs.

    `settled` records whether the page went quiet before this bundle was read (§2e,
    7b): `True` when DOM mutations stopped within the settle timeout, `False` when the
    page never quiesced and the snapshot is best-effort. It defaults to `True` so a
    state captured by a driver that does not track settling (or a fake app that is
    always settled) reads as settled; only the live driver flips it to `False` for a
    page that would not stop rendering.
    """

    ax_node_count: int = 0
    console_messages: tuple[str, ...] = ()
    storage_keys: tuple[str, ...] = ()
    network_requests: tuple[str, ...] = ()
    screenshot_hash: str | None = None
    settled: bool = True


@dataclass(frozen=True)
class TransitionSignals:
    """What one fired action changed, diffed from its before/after bundles (§2e).

    Additive fields keep first-seen order and no duplicates. `ax_node_delta` is
    signed (a screen that removes controls goes negative). `screenshot_changed` is
    a plain inequality of the two hashes — a bundle with no screenshot (`None`)
    compares like any other value, so "captured on one side only" reads as a
    change; whether an appearance *meaningfully* differs is 5c-ii's problem, not
    this diff's.
    """

    ax_node_delta: int
    console_added: tuple[str, ...]
    storage_added: tuple[str, ...]
    storage_removed: tuple[str, ...]
    network_added: tuple[str, ...]
    screenshot_changed: bool


def _added(before: tuple[str, ...], after: tuple[str, ...]) -> tuple[str, ...]:
    """Items present in `after` but not `before`, in `after` order, deduplicated."""
    seen: set[str] = set(before)
    result: list[str] = []
    for item in after:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def diff_signals(before: StateSignals, after: StateSignals) -> TransitionSignals:
    """Compute the before/after signal diff for one fired action (§2e).

    Additive signals (console, storage, network) report what appeared; storage also
    reports what was removed. The accessibility delta is a signed count difference,
    and the screenshot is a hash inequality.
    """
    return TransitionSignals(
        ax_node_delta=after.ax_node_count - before.ax_node_count,
        console_added=_added(before.console_messages, after.console_messages),
        storage_added=_added(before.storage_keys, after.storage_keys),
        storage_removed=_added(after.storage_keys, before.storage_keys),
        network_added=_added(before.network_requests, after.network_requests),
        screenshot_changed=before.screenshot_hash != after.screenshot_hash,
    )
