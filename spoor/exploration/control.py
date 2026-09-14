"""Run-level controls for exploration mode: budget + kill switch (ROADMAP.md §2e).

The fourth §2e slice, still pure logic. Per §2e these are core safety, not optional
hardening: a run that can't be bounded or stopped is itself a reliability/safety gap
(§1), so the budget and the manual kill switch ship *with* the rest of the safety
system rather than as a follow-up.

Two pieces:

- `RunBudget` — the user-set hard bounds for one run: max states discovered, max
  requests, max wall-clock seconds. Any dimension left `None` is unbounded; a set
  bound must be positive.
- `RunController` — tracks one run's consumption and holds the kill switch. The
  explorer loop (slice 5) records progress (`record_state` / `record_request`) and,
  before each step, asks `check()` whether to keep going. `kill()` throws the manual
  switch from anywhere (it is thread-safe), and the very next `check()` stops the run.

The kill switch is checked before the budget, so a manual stop is always reported as
such. Wall-clock time is read through an injectable `clock`, so the time bound is
exercised deterministically in tests (mirroring the retry module's injectable sleep).
Nothing here is site-specific (§0): the same controls bound every target.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RunBudget:
    """Hard, user-set bounds for one exploration run (§2e).

    Each dimension is optional; `None` means that dimension is unbounded. A run
    stops as soon as *any* set bound is reached. A set bound must be positive — a
    zero or negative bound is a configuration error, not a silent instant stop.
    """

    max_states: int | None = None
    max_requests: int | None = None
    max_seconds: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("max_states", self.max_states),
            ("max_requests", self.max_requests),
            ("max_seconds", self.max_seconds),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive, got {value!r}")


@dataclass(frozen=True)
class StopDecision:
    """Whether the run should stop, and a log-ready reason why (or why not)."""

    should_stop: bool
    reason: str

    @property
    def running(self) -> bool:
        return not self.should_stop


class RunController:
    """Tracks one run's budget consumption and its manual kill switch (§2e).

    Progress is recorded as it happens (`record_state` / `record_request`); the
    explorer loop calls `check()` before each step to learn whether to continue.
    `kill()` is thread-safe so a stop-on-command can arrive from another thread
    while the loop runs; the next `check()` observes it.
    """

    def __init__(
        self,
        budget: RunBudget,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._budget = budget
        self._clock = clock
        self._start = clock()
        self._states = 0
        self._requests = 0
        self._killed = threading.Event()

    def record_state(self, count: int = 1) -> None:
        """Record `count` newly discovered states."""
        self._states += count

    def record_request(self, count: int = 1) -> None:
        """Record `count` requests made."""
        self._requests += count

    def kill(self) -> None:
        """Throw the manual kill switch; the next `check()` stops the run."""
        self._killed.set()

    @property
    def killed(self) -> bool:
        return self._killed.is_set()

    def elapsed(self) -> float:
        """Wall-clock seconds since this controller was created."""
        return self._clock() - self._start

    def check(self) -> StopDecision:
        """Decide whether the run should stop now, and why.

        The kill switch is checked first, then each set budget dimension in order
        (states, requests, time). A run within every bound and not killed keeps
        running.
        """
        if self._killed.is_set():
            return StopDecision(True, "kill switch thrown")

        budget = self._budget
        if budget.max_states is not None and self._states >= budget.max_states:
            return StopDecision(
                True, f"budget reached: max_states ({budget.max_states})"
            )
        if budget.max_requests is not None and self._requests >= budget.max_requests:
            return StopDecision(
                True, f"budget reached: max_requests ({budget.max_requests})"
            )
        if budget.max_seconds is not None and self.elapsed() >= budget.max_seconds:
            return StopDecision(
                True, f"budget reached: max_seconds ({budget.max_seconds})"
            )
        return StopDecision(False, "within budget")
