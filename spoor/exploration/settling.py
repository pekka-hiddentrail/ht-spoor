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

7e widens the "is the page quiet?" signal to also cover the network. A live diagnostic
against the server-rendered PrestaShop bench (§5.1) showed DOM-quiet alone settles *too
early*: a hydration lull longer than the quiet window opens while an AJAX widget or
lazy-loaded images are still in flight, the wait fires during the lull, and then a late
burst of network responses mutates the DOM — so two captures of the same screen land on
different `state_id`s and reset-and-replay flags a spurious divergence (§2e, 7d). The
fully-settled page is deterministic; the wait just has to reach it. So an optional
`busy` predicate reports whether any request is in flight, and the page counts as quiet
only while `busy()` is false *and* mutations have held steady for the window. The bound
is unchanged: a request that never completes (a long-poll, a hung fetch) makes the page
*unsettled* at the timeout, exactly like a page that mutates forever — recorded, not
fatal. When no `busy` predicate is given the decision is exactly 7b's DOM-only quiet, so
targets and tests that don't supply a network signal are unaffected.

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
    busy: Callable[[], bool] | None = None,
) -> SettleResult:
    """Wait until the page goes quiet for `quiet_window`, bounded by `timeout`.

    `observe` returns the cumulative mutation count so far (monotonic non-decreasing);
    the page is quiet while that count stops rising. `busy`, when given, reports whether
    any request is still in flight — while it is true the page is treated as active, so
    a late network response that will mutate the DOM cannot be settled past (7e); omit
    it (the default) for 7b's DOM-only quiet. Polls every `poll_interval`, reading time
    through `clock` and waiting through `sleep` so the whole decision is deterministic
    under a fake clock. Returns settled once mutations have held steady *and* no request
    has been in flight for `quiet_window`; returns unsettled once `timeout` elapses
    without that happening — so a request that never completes is bounded exactly like a
    page that mutates forever. All three time arguments must share one unit and
    `poll_interval` must be positive.
    """
    if poll_interval <= 0:
        raise ValueError(f"poll_interval must be positive, got {poll_interval!r}")

    is_busy = busy if busy is not None else _never_busy
    start = clock()
    last_count = observe()
    # The last instant the page was active — a mutation or a request in flight. Quiet is
    # measured from here; either kind of activity pushes it forward.
    last_active = start
    while True:
        now = clock()
        if not is_busy() and now - last_active >= quiet_window:
            return SettleResult(settled=True, elapsed=now - start, mutations=last_count)
        if now - start >= timeout:
            return SettleResult(
                settled=False, elapsed=now - start, mutations=last_count
            )
        sleep(poll_interval)
        count = observe()
        if count != last_count or is_busy():
            last_count = count
            last_active = clock()


def _never_busy() -> bool:
    """The default network signal: nothing is ever in flight (7b DOM-only quiet)."""
    return False
