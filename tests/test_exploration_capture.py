"""Unit tests for the exploration signal-diff model (ROADMAP.md §2e, 5c-i).

The BDD scenarios (exploration_signals.feature) pin the happy-path diff through the
explorer; these probe `diff_signals` directly on the edges the scenarios don't reach:
negative deltas, duplicates, order preservation, and the None-screenshot boundary.
"""

from __future__ import annotations

from spoor.exploration.capture import StateSignals, TransitionSignals, diff_signals


def test_identical_bundles_produce_an_empty_no_change_diff() -> None:
    bundle = StateSignals(
        ax_node_count=4,
        console_messages=("a", "b"),
        storage_keys=("k",),
        network_requests=("/x",),
        screenshot_hash="h",
    )
    assert diff_signals(bundle, bundle) == TransitionSignals(
        ax_node_delta=0,
        console_added=(),
        storage_added=(),
        storage_removed=(),
        network_added=(),
        screenshot_changed=False,
    )


def test_ax_delta_is_signed_when_controls_are_removed() -> None:
    before = StateSignals(ax_node_count=7)
    after = StateSignals(ax_node_count=3)
    assert diff_signals(before, after).ax_node_delta == -4


def test_additions_preserve_after_order_and_deduplicate() -> None:
    before = StateSignals(console_messages=("ready",))
    after = StateSignals(console_messages=("ready", "b", "a", "b"))
    # 'ready' was already present; 'b' appears twice but is reported once, in the
    # order it first appears in `after`.
    assert diff_signals(before, after).console_added == ("b", "a")


def test_storage_added_and_removed_are_independent() -> None:
    before = StateSignals(storage_keys=("guest", "cart"))
    after = StateSignals(storage_keys=("cart", "token"))
    diff = diff_signals(before, after)
    assert diff.storage_added == ("token",)
    assert diff.storage_removed == ("guest",)


def test_screenshot_appearing_on_one_side_reads_as_a_change() -> None:
    # None vs a hash is unequal, so a screenshot captured on only one side counts as
    # changed; two None bundles do not.
    appeared = diff_signals(StateSignals(), StateSignals(screenshot_hash="h"))
    assert appeared.screenshot_changed is True
    assert diff_signals(StateSignals(), StateSignals()).screenshot_changed is False
