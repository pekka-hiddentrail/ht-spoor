"""Deterministic exploration performance bench (ROADMAP.md §5.5).

Spoor's crawl maps the **same graph** every time against a pinned archetype (§5.1)
under a count-based budget — the same states, transitions, skips and discovered
actions. Not everything a run touches is that reproducible, though: the capture
counts and the number of each browser operation depend on the walk, which the
replay/recovery loop makes nondeterministic against a live SPA. That makes
performance measurable as a trend rather than a one-off number, and it splits the
metrics along the axis of what is actually reproducible:

- **Gated shape counters** — states, transitions (actuated actions), skips, and the
  total actions *discovered* (coverage). These describe the *map* the crawl builds;
  for a pinned target and a count-based budget they reproduce exactly run to run
  (confirmed across repeated CI runs), so a change is real behavioural drift, never CI
  noise. They are checked against a committed baseline and **fail** the run on any
  drift — the golden-master model of §5.4 applied to the crawl shape.
- **Advisory counters** — the slice-8g image files/refs dedup counts, the
  per-operation *call counts* (`reset`/`state_html`/`probe`/`perform` …), and the
  *skip-reason histogram*. These are reported (dedup stays observable as files vs
  refs, and the counts are useful for triage) but **not gated**: the walk's
  replay/recovery loop reacts to the live target's runtime nondeterminism (an SPA
  whose reset does not always land identically), so the capture counts, the call
  counts, and which replay-failure message a skip carries legitimately vary between
  runs even though the crawl converges on the same map. A check run caught
  `image_refs` wobbling 151->152 with the map otherwise identical; gating any of
  these would be flaky.
- **Per-operation timing** — for every browser operation, the median, p95 and
  total wall-clock across all its calls in the run. Timing is noisy on GitHub's
  shared runners, so it is an **advisory trend** only (charted, alert-on-regression,
  never a hard gate).
- **Event-anchored resource trace** — every transaction also carries its start
  offset on the run's time axis and the resident memory (this process + children,
  so Chromium counts) sampled just before and after the call. This is a within-run
  diagnostic (nondeterministic like the call counts, so never gated): emitted as a
  per-run timeline artifact, with peak RSS reduced onto the advisory trend.

To turn "the run is slow" into "slow *here, because of this*", the run also emits two
localisation aids (advisory, never gating): a **triage verdict** that reads the
deterministic result against the timing — counters unchanged means a slowdown is
perf-code or runner noise, counters changed means the run did different work that
likely explains it — and the **slowest individual transactions**, the specific calls
(with the action they touched) that consumed the most wall-clock.

Timing the *individual operations* rather than one whole-run total is deliberate,
and it is what makes the timing signal usable at all:

- a regression **localises** — "`screenshot` got 2x slower", not "the run got
  slower" — so the dashboard points at the cause, and
- each operation yields **many samples per run**, so its **median** is far more
  stable against a noisy neighbour than a single end-to-end total ever is.

The instrument is a `_TimingDriver` that wraps the real driver and times each call,
so nothing in the explorer changes and the measurement is generic (§0): every
browser round-trip is one "transaction", named by the driver method. The wrapper
preserves the driver's opt-in capabilities (`isinstance(proxy, _ScreenshotCapable)`
still reflects the real driver), so capture is measured exactly as it runs.

This module is generic (§0): it takes the target URL as an argument — no site is
hardcoded here; the archetype URL lives only in the workflow — and drives the same
`explore` path the rest of the suite uses. Its reduction/emit/drift maths is pure
and unit-tested with a hand-built graph and fake samples; only `run` touches a real
browser, so the fast tier covers the maths with no Chromium. The budget is
**count-based only** (`max_states`/`max_depth`, never `max_seconds`, whose stop
point would depend on runner speed and so break reproducibility).

Usage (small set — a tight, deterministic Juice Shop slice):

    python scripts/perfbench.py \\
        --target http://127.0.0.1:3000 --label juice-shop-small \\
        --max-states 6 --max-depth 2 --screenshots \\
        --baseline scripts/perf_baselines/juice-shop-small.json \\
        --bench-out perf-out/juice-shop-small.json

Seed the baseline once (inspect, then commit) with `--update-baseline`.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.explorer import BrowserDriver, ElementShot, explore
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.screenshot_store import ImageRef

# The scalar counters that must reproduce exactly for a pinned target and a
# count-based budget; the per-operation call counts (see `BenchMetrics.timings`)
# are gated too. Timing values are excluded — they are noisy and only advisory.
# The gated counters: the pure graph shape only. These describe the *map* the crawl
# builds and reproduce exactly run to run (confirmed across repeated CI runs). The
# capture counts (image_files/image_refs) are deliberately excluded — they depend on
# the walk, which the replay/recovery loop makes nondeterministic against a live SPA
# (a check run caught image_refs wobbling 151->152), so they are advisory, not gated.
_SCALAR_FIELDS = (
    "states",
    "transitions",
    "skipped",
    "discovered",
)

# How many of the slowest individual transactions to surface for localisation.
_SLOWEST_N = 8


@dataclass(frozen=True)
class Transaction:
    """One timed browser round-trip: operation, duration, context, and resources.

    `detail` names the action a `perform`/`probe` acted on (role + name) when the
    call carried one, or is empty for the context-free core methods (`reset`,
    `state_html`, …). It is what lets the slowest-transaction list point at a
    specific call rather than just an operation kind.

    `start_offset` is the call's start in seconds from the run's origin, and
    `rss_before`/`rss_after` are resident memory (bytes, this process plus its
    children) sampled just outside the timed window — bracketing the call so a
    memory step attributes to the operation that caused it (§5.5, event-anchored
    resource trace). These are advisory, within-run only, and default to the
    zero/unmeasured case so a `Transaction` can be built from timing alone.
    """

    op: str
    duration_s: float
    detail: str
    start_offset: float = 0.0
    rss_before: int = 0
    rss_after: int = 0


@dataclass(frozen=True)
class OpStat:
    """Timing for one kind of browser operation across a whole run.

    `count` is deterministic (it is gated); `total_s`/`median_s`/`p95_s` are the
    advisory wall-clock trend. The median over many calls is the stable headline;
    p95 catches a slow tail a median would hide.
    """

    count: int
    total_s: float
    median_s: float
    p95_s: float


@dataclass(frozen=True)
class BenchMetrics:
    """One bench run's metrics: deterministic counters plus advisory timing.

    The scalar fields (`_SCALAR_FIELDS`) are the gated, runner-independent counters
    for a pinned target and a count-based budget. `discovered` is the total actionable
    elements found across all states — the coverage top-line that, read against
    `transitions` (actuated) and `skipped`, shows how much of what was found was
    actually driven. `image_files`/`image_refs`, the per-operation `count`s inside
    `timings`, and `skip_reasons` (the histogram of *why* actions were skipped) are
    **advisory, not gated** — the replay/recovery loop makes them vary run to run (see
    `check_drift`).
    `elapsed_seconds` and the timing values inside `timings`, plus `slowest` (the
    slowest transactions, for localising a regression), are wall-clock and advisory.
    `image_files`/`image_refs` are 0 when screenshots were not captured.

    `trace` is the full ordered transaction list — the event-anchored resource trace
    (§5.5), advisory and within-run only — from which the per-run timeline artifact is
    written. `peak_rss_bytes` is its single scalar reduction (the largest resident
    memory bracketing any call; 0 when psutil is absent), the one memory figure that
    rides the advisory trend dashboard as a smaller-is-better line.
    """

    states: int
    transitions: int
    skipped: int
    discovered: int
    image_files: int
    image_refs: int
    elapsed_seconds: float
    timings: dict[str, OpStat]
    skip_reasons: dict[str, int]
    slowest: tuple[Transaction, ...]
    trace: tuple[Transaction, ...]
    peak_rss_bytes: int

    def call_counts(self) -> dict[str, int]:
        """The deterministic per-operation call counts, op -> count."""
        return {op: stat.count for op, stat in self.timings.items()}


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """The `q` (0..1) nearest-rank percentile of an already-sorted sequence."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(q * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def _aggregate(samples: Mapping[str, Sequence[float]]) -> dict[str, OpStat]:
    """Reduce each operation's raw per-call durations to an `OpStat`."""
    stats: dict[str, OpStat] = {}
    for op, durations in samples.items():
        ordered = sorted(durations)
        stats[op] = OpStat(
            count=len(ordered),
            total_s=round(sum(ordered), 4),
            median_s=round(statistics.median(ordered), 5),
            p95_s=round(_percentile(ordered, 0.95), 5),
        )
    return stats


def _slowest(transactions: Sequence[Transaction], n: int) -> tuple[Transaction, ...]:
    """The `n` slowest transactions, slowest first — the localisation shortlist.

    Ties break on operation then detail so the order is deterministic for a given
    set of durations (only the durations themselves are runner-noisy).
    """
    ordered = sorted(
        transactions, key=lambda t: (-t.duration_s, t.op, t.detail)
    )
    return tuple(ordered[:n])


def _detail(args: Sequence[Any]) -> str:
    """A short context label for a call from its first argument, if it is an action.

    `perform`/`probe` receive an `ActionableElement` (has `role`/`name`); the core
    methods take no argument. Anything without a `name` yields an empty label.
    """
    if args and hasattr(args[0], "name"):
        action = args[0]
        role = getattr(action, "role", "")
        return f"{role} {action.name}".strip()
    return ""


# The opt-in capability methods the explorer detects with `isinstance` against its
# runtime_checkable protocols (screenshot/element/opened capture, element geometry,
# URL awareness). The wrapper exposes a timed version of exactly those the inner
# driver has, so its capabilities match the driver it wraps.
_OPTIONAL_OPS = (
    "screenshot",
    "element_screenshot",
    "opened_screenshot",
    "element_box",
    "current_url",
)


def _default_rss_sampler() -> Callable[[], int]:
    """A resident-memory sampler: this process plus its children, in bytes.

    Children are summed so the out-of-process Chromium that Playwright launches —
    where most of the memory lives — is counted, not just Spoor's own process. When
    `psutil` is not installed the sampler returns 0, so the bench still runs and the
    resource trace simply degrades to timing-only (§5.5). A dead child mid-walk is
    skipped rather than raised on.
    """
    try:
        import psutil
    except ImportError:
        return lambda: 0

    proc = psutil.Process()

    def sample() -> int:
        total = int(proc.memory_info().rss)
        for child in proc.children(recursive=True):
            try:
                total += int(child.memory_info().rss)
            except psutil.Error:
                pass  # child exited between the listing and the read
        return total

    return sample


class _TimingDriver:
    """Wrap a `BrowserDriver`, timing every call, keyed by method name (§5.5).

    Each browser round-trip is one "transaction"; `samples[method]` collects one
    duration per call. The core `BrowserDriver` methods are wrapped as normal methods
    (so the proxy statically *is* a `BrowserDriver`). Each opt-in capability method
    (`screenshot`, `element_screenshot`, …) is bound in `__init__` as an *instance
    attribute* — but only when the inner driver actually has it — so that both
    `hasattr` and (on Python 3.12+) `inspect.getattr_static`, which `runtime_checkable`
    isinstance uses and which does **not** consult `__getattr__`, see exactly the
    capabilities the real driver has. Durations are recorded in a `finally`, so a call
    that raises still counts (it was a real round-trip that took real time).

    Every transaction is also anchored on the run's time axis (`start_offset` from the
    origin captured at construction) and brackets the call with a resident-memory
    reading taken just *outside* the timed window (so RSS sampling never inflates the
    duration). `rss_sampler` is injectable for tests; it defaults to the psutil-backed
    process-tree sampler.
    """

    def __init__(
        self, inner: BrowserDriver, *, rss_sampler: Callable[[], int] | None = None
    ) -> None:
        self._inner = inner
        self._rss = rss_sampler if rss_sampler is not None else _default_rss_sampler()
        self._origin = time.perf_counter()
        self.transactions: list[Transaction] = []
        for op in _OPTIONAL_OPS:
            method = getattr(inner, op, None)
            if callable(method):
                # Bind as an instance attribute so getattr_static/isinstance find it.
                self.__dict__[op] = self._binding(op, method)

    @property
    def samples(self) -> dict[str, list[float]]:
        """Per-operation durations, op -> [seconds], derived from `transactions`."""
        out: dict[str, list[float]] = {}
        for txn in self.transactions:
            out.setdefault(txn.op, []).append(txn.duration_s)
        return out

    def _timed(self, op: str, func: Callable[..., Any], *args: Any) -> Any:
        # RSS is read *outside* the perf_counter window at both ends, so sampling
        # cost never lands in the reported duration.
        rss_before = self._rss()
        start = time.perf_counter()
        try:
            return func(*args)
        finally:
            duration = time.perf_counter() - start
            rss_after = self._rss()
            self.transactions.append(
                Transaction(
                    op,
                    duration,
                    _detail(args),
                    start_offset=start - self._origin,
                    rss_before=rss_before,
                    rss_after=rss_after,
                )
            )

    def _binding(self, op: str, method: Callable[..., Any]) -> Callable[..., Any]:
        def timed(*args: Any) -> Any:
            return self._timed(op, method, *args)

        return timed

    def reset(self) -> None:
        self._timed("reset", self._inner.reset)

    def state_html(self) -> str:
        return self._timed("state_html", self._inner.state_html)

    def ax_nodes(self) -> Sequence[Mapping[str, object]]:
        return self._timed("ax_nodes", self._inner.ax_nodes)

    def perform(self, action: Any) -> None:
        self._timed("perform", self._inner.perform, action)

    def probe(self, action: Any) -> Any:
        return self._timed("probe", self._inner.probe, action)

    def capture_signals(self) -> Any:
        return self._timed("capture_signals", self._inner.capture_signals)


def measure(
    graph: ExplorationGraph,
    shots: Mapping[str, ImageRef],
    element_shots: Mapping[str, Sequence[ElementShot]],
    transactions: Sequence[Transaction],
    elapsed: float,
) -> BenchMetrics:
    """Reduce a finished run to its metrics.

    `image_files` is the number of *distinct* files behind all references — the
    slice-8g dedup signal: it climbs back toward `image_refs` if dedup regresses.
    `discovered` sums the actionable elements found across every state (coverage,
    read against `transitions`/`skipped`). `skip_reasons` histograms the gate's skip
    reasons. `transactions` are the `_TimingDriver` records, reduced here to
    per-operation `OpStat`s, the slowest-transaction shortlist, the full ordered
    resource `trace`, and its peak-RSS scalar (§5.5).
    """
    refs: list[ImageRef] = list(shots.values())
    for element in element_shots.values():
        refs += [s.clip for s in element if s.clip is not None]
        refs += [s.opened for s in element if s.opened is not None]

    by_op: dict[str, list[float]] = {}
    for txn in transactions:
        by_op.setdefault(txn.op, []).append(txn.duration_s)

    skip_reasons: dict[str, int] = {}
    for skip in graph.skipped:
        skip_reasons[skip.reason] = skip_reasons.get(skip.reason, 0) + 1

    discovered = sum(len(graph.node(sid).actions) for sid in graph.states)
    peak_rss = max(
        (max(txn.rss_before, txn.rss_after) for txn in transactions), default=0
    )
    return BenchMetrics(
        states=len(graph.states),
        transitions=len(graph.transitions),
        skipped=len(graph.skipped),
        discovered=discovered,
        image_files=len({ref.src for ref in refs}),
        image_refs=len(refs),
        elapsed_seconds=round(elapsed, 3),
        timings=_aggregate(by_op),
        skip_reasons=skip_reasons,
        slowest=_slowest(transactions, _SLOWEST_N),
        trace=tuple(transactions),
        peak_rss_bytes=peak_rss,
    )


def benchmark_entries(metrics: BenchMetrics, label: str) -> list[dict[str, object]]:
    """The github-action-benchmark rows for the timing trend (smaller is better).

    One row for the whole-run elapsed (the top-line), then per operation its median
    and total — the granular signal that localises a regression. Deterministic
    counters are gated by `check_drift`, never trended. Peak resident memory is
    included as a smaller-is-better row too (the one memory reduction worth trending
    across commits); it is omitted when psutil is absent, so a zero never flatlines
    the chart. Every row is namespaced by `label` so several sets share one dashboard
    without colliding.
    """
    rows: list[dict[str, object]] = [
        {
            "name": f"{label} / total elapsed",
            "unit": "s",
            "value": metrics.elapsed_seconds,
        },
    ]
    for op, stat in sorted(metrics.timings.items()):
        rows.append(
            {"name": f"{label} / {op} median", "unit": "s", "value": stat.median_s}
        )
        rows.append(
            {"name": f"{label} / {op} total", "unit": "s", "value": stat.total_s}
        )
    if metrics.peak_rss_bytes > 0:
        rows.append(
            {
                "name": f"{label} / peak RSS",
                "unit": "MB",
                "value": round(metrics.peak_rss_bytes / 1_000_000, 1),
            }
        )
    return rows


def resource_trace(metrics: BenchMetrics) -> list[dict[str, object]]:
    """The per-run resource timeline: one ordered row per transaction (§5.5).

    Each row anchors an operation on the run's real time axis (`t_start`, seconds
    from the run origin) with its duration and the resident memory bracketing it
    (`rss_before`/`rss_after`, bytes), plus the `op`/`detail` it belongs to — so the
    rows can be stretched onto a timeline and a memory step read straight off the
    call that caused it. Advisory and nondeterministic run to run (the walk varies),
    so this is a within-run diagnostic, never gated.
    """
    return [
        {
            "t_start": round(txn.start_offset, 4),
            "duration_s": round(txn.duration_s, 4),
            "op": txn.op,
            "detail": txn.detail,
            "rss_before": txn.rss_before,
            "rss_after": txn.rss_after,
        }
        for txn in metrics.trace
    ]


def check_drift(metrics: BenchMetrics, baseline: Mapping[str, object]) -> list[str]:
    """Gated shape counters in `metrics` that differ from `baseline`.

    Only the reproducible counters (`_SCALAR_FIELDS`: the graph shape — states,
    transitions, skips, discovered) are compared — empty means the run reproduced the
    baseline exactly. The capture counts (`image_files`/`image_refs`), per-operation
    call counts, and skip-reason histogram are **not** gated here: the walk's
    replay/recovery loop reacts to the live target's runtime nondeterminism, so they
    vary run to run even for the same map (a check run caught `image_refs` wobbling by
    one); they are reported as advisory only. A baseline missing a scalar (an older
    baseline) skips it rather than false-alarming.
    """
    drift: list[str] = []
    for name in _SCALAR_FIELDS:
        expected = baseline.get(name)
        current = getattr(metrics, name)
        if expected is not None and current != expected:
            drift.append(f"{name}: baseline {expected} -> now {current}")
    return drift


def _baseline_payload(metrics: BenchMetrics) -> dict[str, object]:
    """The committed baseline: the gated structural/dedup counters only.

    Deliberately excludes the per-operation call counts and skip-reason histogram —
    they are advisory (reported by `main`), not gated, because they are not
    reproducible run to run (see `check_drift`).
    """
    return {name: getattr(metrics, name) for name in _SCALAR_FIELDS}


def _explore_target(
    target: str, budget: RunBudget, *, capture_dir: Path | None
) -> tuple[
    ExplorationGraph,
    dict[str, ImageRef],
    dict[str, list[ElementShot]],
    list[Transaction],
]:
    """Run the real browser explorer against `target`; return graph, sinks, timings.

    `PlaywrightDriver` is imported lazily so importing this module (for its pure
    functions, e.g. in the fast unit tier) never requires a browser. The driver is
    wrapped in a `_TimingDriver` so every browser call is timed. When `capture_dir`
    is given, screenshots are captured so the dedup counters and capture timings are
    measured too; otherwise no pixels are taken.
    """
    from spoor.exploration.driver import PlaywrightDriver

    shots: dict[str, ImageRef] = {}
    element_shots: dict[str, list[ElementShot]] = {}
    sinks: dict[str, object] = {}
    if capture_dir is not None:
        sinks = {
            "screenshots": shots,
            "element_screenshots": element_shots,
            "screenshot_dir": capture_dir,
        }
    with PlaywrightDriver(target) as driver:
        timing = _TimingDriver(driver)
        graph = explore(
            timing,
            target=target,
            controller=RunController(budget),
            **sinks,  # type: ignore[arg-type]
        )
    return graph, shots, element_shots, timing.transactions


def run(
    target: str,
    *,
    max_states: int | None,
    max_depth: int | None,
    screenshots: bool,
) -> BenchMetrics:
    """Run the bench once against `target` and return its metrics.

    The budget is count-based only so the stop point is reproducible regardless of
    runner speed. Captured pixels go to a throwaway temp dir — the bench measures the
    dedup counters and capture timings, not the files.
    """
    budget = RunBudget(max_states=max_states, max_depth=max_depth)
    start = time.perf_counter()
    if screenshots:
        with tempfile.TemporaryDirectory() as tmp:
            graph, shots, element_shots, transactions = _explore_target(
                target, budget, capture_dir=Path(tmp)
            )
            elapsed = time.perf_counter() - start
            return measure(graph, shots, element_shots, transactions, elapsed)
    graph, shots, element_shots, transactions = _explore_target(
        target, budget, capture_dir=None
    )
    elapsed = time.perf_counter() - start
    return measure(graph, shots, element_shots, transactions, elapsed)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exploration performance bench (§5.5)."
    )
    parser.add_argument(
        "--target", required=True, help="Base URL to explore (no site is hardcoded)."
    )
    parser.add_argument(
        "--label", required=True, help="Metric namespace, e.g. 'juice-shop-small'."
    )
    parser.add_argument(
        "--max-states", type=int, default=None, help="Stop after this many states."
    )
    parser.add_argument(
        "--max-depth", type=int, default=None, help="Do not crawl deeper than this."
    )
    parser.add_argument(
        "--screenshots",
        action="store_true",
        help="Capture screenshots so the dedup counters and capture timings show.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Deterministic-counter baseline JSON to check against.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the run's counters to --baseline instead of checking (seeding).",
    )
    parser.add_argument(
        "--bench-out",
        type=Path,
        default=None,
        help="Write the github-action-benchmark timing JSON here.",
    )
    parser.add_argument(
        "--trace-out",
        type=Path,
        default=None,
        help="Write the per-run resource timeline (RSS-per-transaction) JSON here.",
    )
    return parser.parse_args(argv)


def _print_localisation(metrics: BenchMetrics, shape: str) -> None:
    """Print the localisation aids: the triage verdict and the slowest calls.

    `shape` is the deterministic-counter outcome — "unchanged", "changed" or
    "uncompared" — which turns a timing shift into a diagnosis: with the shape
    unchanged a slowdown is perf-code or runner noise, while a changed shape means
    the run did different work and likely explains the timing itself. The slowest
    individual transactions then point at *which* calls to look at.
    """
    triage = {
        "unchanged": "crawl shape UNCHANGED — a timing shift is perf-code or runner "
        "noise, not behaviour",
        "changed": "crawl shape CHANGED (see drift above) — a timing shift is likely "
        "behavioural, explained by the drift",
        "uncompared": "crawl shape not compared (no baseline) — timing advisory only",
    }[shape]
    print(f"[perfbench] triage: {triage}")
    if metrics.slowest:
        print("[perfbench] slowest transactions (advisory — where the time went):")
        for txn in metrics.slowest:
            label = f"{txn.op}  {txn.detail}".rstrip()
            print(f"  {txn.duration_s:.4f}s  {label}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bench, emit the timing JSON, and gate on deterministic drift."""
    args = _parse_args(argv)
    metrics = run(
        args.target,
        max_states=args.max_states,
        max_depth=args.max_depth,
        screenshots=args.screenshots,
    )
    print(f"[perfbench] {args.label}: {json.dumps(_baseline_payload(metrics))}")
    # Advisory (not gated): capture counts and execution counters that vary with the
    # walk. Dedup stays observable as image_files vs image_refs.
    advisory = {
        "image_files": metrics.image_files,
        "image_refs": metrics.image_refs,
        "calls": dict(sorted(metrics.call_counts().items())),
        "peak_rss_mb": round(metrics.peak_rss_bytes / 1_000_000, 1),
    }
    print(f"[perfbench] advisory: {json.dumps(advisory)}")
    if metrics.skip_reasons:
        skips = json.dumps(dict(sorted(metrics.skip_reasons.items())))
        print(f"[perfbench] advisory skip reasons: {skips}")

    if args.bench_out is not None:
        args.bench_out.parent.mkdir(parents=True, exist_ok=True)
        args.bench_out.write_text(
            json.dumps(benchmark_entries(metrics, args.label), indent=2),
            encoding="utf-8",
        )

    if args.trace_out is not None:
        args.trace_out.parent.mkdir(parents=True, exist_ok=True)
        args.trace_out.write_text(
            json.dumps(resource_trace(metrics), indent=2), encoding="utf-8"
        )

    if args.update_baseline:
        if args.baseline is None:
            print("[perfbench] --update-baseline needs --baseline", file=sys.stderr)
            return 2
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(_baseline_payload(metrics), indent=2), encoding="utf-8"
        )
        print(f"[perfbench] wrote baseline {args.baseline} — inspect and commit it")
        return 0

    if args.baseline is not None and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        drift = check_drift(metrics, baseline)
        if drift:
            print("[perfbench] DETERMINISTIC DRIFT — the crawl shape changed:")
            for line in drift:
                print(f"  {line}")
            print("If intended, re-seed with --update-baseline and commit.")
            _print_localisation(metrics, "changed")
            return 1
        print("[perfbench] deterministic counters match the baseline")
        _print_localisation(metrics, "unchanged")
    else:
        print("[perfbench] no baseline yet — seed one with --update-baseline")
        _print_localisation(metrics, "uncompared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
