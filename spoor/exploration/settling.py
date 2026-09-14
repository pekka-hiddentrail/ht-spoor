"""The pure quiescence decision for exploration settling (ROADMAP.md §2e, 7b).

Sub-slice 7b's core, logic-first. A live diagnostic showed the explorer discovered a
page at one rendering instant and fired actions at another: on an asynchronously-
rendered SPA an element present at discovery time was gone by click time, so every
action was skipped "not located" and the map stayed shallow. The cause is rendering
that continues after the crude "network is idle" heuristic.

`wait_for_quiescence` waits for a *real* signal that rendering has stopped — DOM
mutations going quiet for a window — so a later read (discovery, state id, actuation)
sees the same settled page. The wait is bounded: a page that never goes quiet (a busy
SPA that polls or animates forever) is reported *unsettled* at a safety timeout rather
than hanging or crashing the run; the caller records the state as "did not settle" and
proceeds on the last snapshot.

This is the decision alone, over a monotonic mutation-count signal and injectable
`clock`/`sleep` (the `RunController` clock seam), so it is exercised deterministically
with no browser. The real `MutationObserver` that feeds `observe` and the reset that
restores a clean first visit are the live half (`spoor/exploration/driver.py`). The
function is time-unit-agnostic — `clock`, the windows, and `elapsed` share whatever
unit the caller uses (seconds live, milliseconds in tests). Nothing here is
site-specific (§0): the same rule waits for every target.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SettleResult:
    """The outcome of waiting for a page to go quiet (§2e, 7b).

    `settled` is whether mutations went quiet within the timeout; `elapsed` is how long
    the wait took in the caller's time unit; `mutations` is the last observed cumulative
    mutation count (useful for diagnostics). An unsettled result is a recorded fact, not
    an error — the caller proceeds on the last snapshot and flags the state.
    """

    settled: bool
    elapsed: float
    mutations: int


def wait_for_quiescence(
    *,
    observe: Callable[[], int],
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    quiet_window: float,
    timeout: float,
    poll_interval: float,
) -> SettleResult:
    """Wait until DOM mutations go quiet for `quiet_window`, bounded by `timeout`.

    `observe` returns the cumulative mutation count so far (monotonic non-decreasing);
    the page is quiet while that count stops rising. Polls every `poll_interval`,
    reading the clock through `clock` and waiting through `sleep` so the whole decision
    is deterministic under a fake clock. Returns settled once the count has held steady
    for `quiet_window`; returns unsettled once `timeout` elapses without that happening.
    All three time arguments must share one unit and `poll_interval` must be positive.
    """
    if poll_interval <= 0:
        raise ValueError(f"poll_interval must be positive, got {poll_interval!r}")

    start = clock()
    last_count = observe()
    last_change = start
    while True:
        now = clock()
        if now - last_change >= quiet_window:
            return SettleResult(settled=True, elapsed=now - start, mutations=last_count)
        if now - start >= timeout:
            return SettleResult(
                settled=False, elapsed=now - start, mutations=last_count
            )
        sleep(poll_interval)
        count = observe()
        if count != last_count:
            last_count = count
            last_change = clock()
