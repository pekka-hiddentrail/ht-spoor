"""Tests for the exploration performance bench (scripts/perfbench.py, §5.5).

The bench's maths — reducing a finished run to metrics, timing each browser
operation, bracketing each call with a resident-memory reading, emitting the
per-operation timing trend and the resource timeline, and gating on deterministic
drift (the pure graph-shape counters only; call counts, capture counts, memory and
the skip histogram are advisory) — is pure, so it is unit-tested here with a
hand-built graph, fake timing samples, an injected RSS sampler, and a fake driver;
no browser is needed (that is the point of keeping `PlaywrightDriver` behind a lazy
import in `run`).
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from spoor.exploration.discovery import ActionableElement
from spoor.exploration.explorer import (
    ElementShot,
    _ElementBoxCapable,
    _ScreenshotCapable,
)
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.screenshot_store import ImageRef

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "perfbench", REPO_ROOT / "scripts" / "perfbench.py"
)
assert _SPEC and _SPEC.loader
perfbench = importlib.util.module_from_spec(_SPEC)
sys.modules["perfbench"] = perfbench
_SPEC.loader.exec_module(perfbench)


def _action(name: str) -> ActionableElement:
    return ActionableElement(role="button", name=name, backend_node_id=1)


def _graph(states: int, transitions: int, skips: int) -> ExplorationGraph:
    """A graph with the given counts of states, transitions and skips."""
    graph = ExplorationGraph()
    for i in range(states):
        graph.add_state(f"state-{i}", [])
    for j in range(transitions):
        # Edges reuse the states above; only the count matters to the bench.
        graph.add_transition("state-0", _action(f"t{j}"), "state-0")
    for k in range(skips):
        graph.record_skip("state-0", _action(f"s{k}"), "gated")
    return graph


def _txns(samples: dict[str, list[float]] | None) -> list[Any]:
    """Flatten an op -> [durations] dict into Transaction records (empty detail)."""
    return [
        perfbench.Transaction(op, d, "")
        for op, durations in (samples or {}).items()
        for d in durations
    ]


def _measure(
    graph: ExplorationGraph,
    shots: Any = None,
    element_shots: Any = None,
    samples: Any = None,
    elapsed: float = 1.0,
    transactions: Any = None,
) -> Any:
    return perfbench.measure(
        graph,
        shots or {},
        element_shots or {},
        _txns(samples) if transactions is None else transactions,
        elapsed,
    )


# --- _percentile / _aggregate --------------------------------------------


def test_percentile_nearest_rank() -> None:
    values = [0.1, 0.2, 0.3, 0.4, 1.0]  # already sorted
    assert perfbench._percentile(values, 0.95) == 1.0
    assert perfbench._percentile(values, 0.5) == 0.3
    assert perfbench._percentile([], 0.95) == 0.0  # empty is well-defined


def test_aggregate_reduces_each_operation() -> None:
    stats = perfbench._aggregate({"perform": [0.30, 0.10, 0.20], "reset": [0.5]})
    assert stats["perform"].count == 3
    assert stats["perform"].median_s == 0.2
    assert stats["perform"].total_s == 0.6
    assert stats["reset"].count == 1


# --- _TimingDriver -------------------------------------------------------


class _FakeInner:
    """A screenshot-capable driver (no element geometry) that records nothing."""

    def reset(self) -> None: ...
    def state_html(self) -> str:
        return "<html></html>"
    def ax_nodes(self) -> list[dict[str, object]]:
        return []
    def probe(self, action: Any) -> str:
        return "ACTUATE"
    def perform(self, action: Any) -> None: ...
    def capture_signals(self) -> str:
        return "signals"
    def screenshot(self) -> bytes:
        return b"png"


def test_timing_driver_counts_calls_per_operation() -> None:
    driver = perfbench._TimingDriver(_FakeInner())
    driver.state_html()
    driver.perform(_action("a"))
    driver.perform(_action("b"))
    driver.screenshot()  # opt-in capability, timed like the core methods
    counts = {op: len(times) for op, times in driver.samples.items()}
    assert counts == {"state_html": 1, "perform": 2, "screenshot": 1}
    # Durations are real, non-negative numbers.
    assert all(t >= 0 for times in driver.samples.values() for t in times)


def test_timing_driver_preserves_capability_detection() -> None:
    # The wrapper must look exactly as capable as the driver it wraps, so the
    # explorer's isinstance() capability gates behave identically.
    driver = perfbench._TimingDriver(_FakeInner())
    assert isinstance(driver, _ScreenshotCapable)  # inner has screenshot()
    assert not isinstance(driver, _ElementBoxCapable)  # inner has no element_box()


def test_timing_driver_labels_transactions_with_the_action() -> None:
    driver = perfbench._TimingDriver(_FakeInner())
    driver.perform(_action("Add to basket"))
    driver.state_html()
    labels = {(t.op, t.detail) for t in driver.transactions}
    assert ("perform", "button Add to basket") in labels  # action carried through
    assert ("state_html", "") in labels  # context-free core method


def test_timing_driver_brackets_each_call_with_rss_samples() -> None:
    # RSS is read once before and once after each call, so an injected sampler that
    # yields 100,200,300,400 pairs up as (before,after) per transaction in order.
    readings = iter([100, 200, 300, 400])
    driver = perfbench._TimingDriver(_FakeInner(), rss_sampler=lambda: next(readings))
    driver.perform(_action("a"))
    driver.state_html()
    txns = driver.transactions
    assert (txns[0].rss_before, txns[0].rss_after) == (100, 200)
    assert (txns[1].rss_before, txns[1].rss_after) == (300, 400)
    # Anchored on the run's time axis: non-negative and non-decreasing.
    assert 0 <= txns[0].start_offset <= txns[1].start_offset


def test_default_rss_sampler_returns_a_nonnegative_int() -> None:
    # With psutil present it reads the process tree; absent, it degrades to 0. Either
    # way the contract is a non-negative int, so the trace never carries garbage.
    sample = perfbench._default_rss_sampler()
    value = sample()
    assert isinstance(value, int) and value >= 0


def test_timing_driver_records_duration_even_when_a_call_raises() -> None:
    class _Boom:
        def perform(self, action: Any) -> None:
            raise RuntimeError("boom")

    driver = perfbench._TimingDriver(_Boom())
    with pytest.raises(RuntimeError):
        driver.perform(_action("x"))
    assert len(driver.samples["perform"]) == 1  # the failed round-trip still counts


# --- measure -------------------------------------------------------------


def test_measure_counts_states_transitions_skips_and_timings() -> None:
    metrics = _measure(_graph(3, 2, 1), samples={"perform": [0.1, 0.2]})
    assert (metrics.states, metrics.transitions, metrics.skipped) == (3, 2, 1)
    assert metrics.call_counts() == {"perform": 2}
    assert metrics.timings["perform"].median_s == 0.15


def test_measure_reports_dedup_files_below_refs() -> None:
    # Two states share one file; a third clip is a crop of that same file. Five
    # references, but only two distinct files behind them.
    shared = "screenshots/state-0.png"
    shots = {"a": ImageRef(shared), "b": ImageRef(shared)}
    element_shots = {
        "a": [
            ElementShot(clip=ImageRef(shared, (1, 2, 3, 4)), opened=None),
            ElementShot(clip=ImageRef("screenshots/state-0-el-1.png"), opened=None),
            ElementShot(clip=None, opened=ImageRef(shared, (0, 0, 5, 5))),
        ]
    }
    metrics = _measure(_graph(2, 1, 0), shots, element_shots)
    assert metrics.image_refs == 5
    assert metrics.image_files == 2


def test_measure_reports_discovered_actions_and_skip_histogram() -> None:
    # Coverage: three actions discovered across two states, one actuated (a
    # transition), three skipped for two distinct reasons.
    graph = ExplorationGraph()
    graph.add_state("s0", [_action("a"), _action("b")])
    graph.add_state("s1", [_action("c")])
    graph.add_transition("s0", _action("a"), "s1")
    graph.record_skip("s0", _action("d"), "destructive")
    graph.record_skip("s1", _action("e"), "destructive")
    graph.record_skip("s1", _action("f"), "duplicate")
    metrics = _measure(graph)
    assert metrics.discovered == 3  # a, b, c
    assert metrics.transitions == 1  # actuated
    assert metrics.skipped == 3
    assert metrics.skip_reasons == {"destructive": 2, "duplicate": 1}


def test_measure_ranks_slowest_transactions_with_context() -> None:
    txns = [
        perfbench.Transaction("state_html", 0.10, ""),
        perfbench.Transaction("perform", 0.90, "button Add"),
        perfbench.Transaction("screenshot", 0.50, ""),
    ]
    metrics = _measure(_graph(1, 0, 0), transactions=txns)
    ranked = [(t.op, t.detail) for t in metrics.slowest]
    assert ranked == [
        ("perform", "button Add"),  # slowest first, keeps its action label
        ("screenshot", ""),
        ("state_html", ""),
    ]


def test_measure_reports_peak_rss_and_ordered_trace() -> None:
    txns = [
        perfbench.Transaction(
            "reset", 0.1, "", start_offset=0.0, rss_before=100, rss_after=150
        ),
        perfbench.Transaction(
            "perform", 0.2, "button Add", start_offset=0.1, rss_before=150,
            rss_after=900,
        ),
    ]
    metrics = _measure(_graph(1, 0, 0), transactions=txns)
    assert metrics.peak_rss_bytes == 900  # largest bracket across the whole trace
    trace = perfbench.resource_trace(metrics)
    assert [(r["op"], r["t_start"], r["rss_after"]) for r in trace] == [
        ("reset", 0.0, 150),
        ("perform", 0.1, 900),  # preserves run order and the action label below
    ]
    assert trace[1]["detail"] == "button Add"


def test_resource_report_html_is_self_contained_and_embeds_the_trace() -> None:
    # An action name can itself be a URL (e.g. "link https://…"); that is embedded
    # data, not an external asset, so it must not trip the self-containment check.
    txns = [
        perfbench.Transaction(
            "perform", 0.2, "link https://owasp-juice.shop", start_offset=0.05,
            rss_before=10, rss_after=900_000,
        )
    ]
    metrics = _measure(_graph(1, 0, 0), transactions=txns)
    html = perfbench.resource_report_html(metrics, "juice-shop-small")
    assert html.startswith("<!doctype html>") and "<canvas id=c>" in html
    # Loads nothing external — renders offline, nothing to be blocked. (A URL inside
    # the embedded JSON is fine; what matters is no external script/style/img fetch.)
    for external_load in ("<script src", "<link ", 'src="http', "href=http"):
        assert external_load not in html
    # The run's data is embedded (op + action label, URL and all) and label shown.
    assert "link https://owasp-juice.shop" in html and "juice-shop-small" in html
    assert '"rss_after": 900000' in html


def test_measure_peak_rss_is_zero_without_samples() -> None:
    # No RSS readings (psutil absent, or timing-only): peak is a clean 0, not an error.
    assert _measure(_graph(1, 0, 0), samples={"reset": [0.1]}).peak_rss_bytes == 0


# --- benchmark_entries ---------------------------------------------------


def test_benchmark_entries_are_timing_only_per_operation() -> None:
    metrics = _measure(
        _graph(4, 3, 0), samples={"screenshot": [0.4], "perform": [0.1, 0.2]}
    )
    entries = perfbench.benchmark_entries(metrics, "small")
    names = {e["name"] for e in entries}
    assert names == {
        "small / total elapsed",
        "small / perform median",
        "small / perform total",
        "small / screenshot median",
        "small / screenshot total",
    }
    # No deterministic scalar counter leaks onto the (noisy) timing chart.
    assert all("states" not in str(e["name"]) for e in entries)


def test_benchmark_entries_include_peak_rss_when_measured() -> None:
    txns = [
        perfbench.Transaction(
            "reset", 0.1, "", rss_before=1_000_000, rss_after=2_500_000
        )
    ]
    metrics = _measure(_graph(1, 0, 0), transactions=txns)
    peak = [e for e in perfbench.benchmark_entries(metrics, "small")
            if e["name"] == "small / peak RSS"]
    assert len(peak) == 1
    assert peak[0]["unit"] == "MB" and peak[0]["value"] == 2.5  # bytes -> MB


def test_benchmark_entries_omit_peak_rss_when_unmeasured() -> None:
    # psutil absent => peak 0 => no row, so a zero never flatlines the memory chart.
    metrics = _measure(_graph(1, 0, 0), samples={"reset": [0.1]})
    entries = perfbench.benchmark_entries(metrics, "small")
    assert all("peak RSS" not in str(e["name"]) for e in entries)


# --- check_drift ---------------------------------------------------------


def _baseline_from(metrics: Any) -> dict[str, Any]:
    return json.loads(json.dumps(perfbench._baseline_payload(metrics)))


def test_check_drift_empty_when_structural_counters_match() -> None:
    m = _measure(_graph(5, 4, 1), samples={"perform": [0.1], "reset": [0.2, 0.3]})
    assert perfbench.check_drift(m, _baseline_from(m)) == []


def test_check_drift_flags_a_changed_scalar_counter() -> None:
    m = _measure(_graph(5, 4, 1))
    baseline = _baseline_from(m)
    baseline["states"] = m.states + 1
    drift = perfbench.check_drift(m, baseline)
    assert len(drift) == 1 and "states" in drift[0]


def test_check_drift_ignores_call_counts_and_skip_reasons() -> None:
    # The replay/recovery loop makes these vary run to run, so they are advisory
    # only: a baseline whose call counts and skip reasons differ from the run must
    # NOT drift (only the structural/dedup scalars gate).
    graph = ExplorationGraph()
    graph.add_state("s0", [])
    graph.record_skip("s0", _action("d"), "destructive")
    m = _measure(graph, samples={"perform": [0.1, 0.2, 0.3]})
    baseline = _baseline_from(m)
    baseline["calls"] = {"perform": 99, "screenshot": 6}  # nothing like the run
    baseline["skip_reasons"] = {"destructive": 5, "gated": 2}
    assert perfbench.check_drift(m, baseline) == []


def test_check_drift_ignores_timing_and_missing_fields() -> None:
    m = _measure(_graph(5, 4, 1), samples={"perform": [0.1]})
    # A baseline with only one scalar and a bogus timing key: timing is never
    # compared, missing scalars are skipped.
    assert perfbench.check_drift(m, {"states": m.states, "elapsed_seconds": 999}) == []


# --- main (drift gate exit codes, no browser) ----------------------------


def test_main_writes_baseline_then_passes_and_detects_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "baseline.json"
    bench_out = tmp_path / "bench.json"
    fixed = _measure(_graph(3, 2, 1), samples={"perform": [0.1, 0.2]})
    monkeypatch.setattr(perfbench, "run", lambda *a, **k: fixed)

    common = ["--target", "http://127.0.0.1:3000", "--label", "small"]

    # Seed: writes the deterministic counters (scalars + calls), exits 0.
    assert perfbench.main(
        [*common, "--baseline", str(baseline), "--update-baseline"]
    ) == 0
    seeded = json.loads(baseline.read_text(encoding="utf-8"))
    # Only the gated structural/dedup scalars are committed — no call counts or
    # skip reasons (those are advisory, not reproducible run to run).
    assert set(seeded) == set(perfbench._SCALAR_FIELDS)
    assert seeded["states"] == 3  # from _graph(3, 2, 1)

    # Re-run against the seeded baseline: matches, exits 0, writes the chart JSON.
    assert perfbench.main(
        [*common, "--baseline", str(baseline), "--bench-out", str(bench_out)]
    ) == 0
    assert json.loads(bench_out.read_text(encoding="utf-8"))  # timing rows written

    # Drift: a different graph shape against the same baseline fails the gate.
    drifted = _measure(_graph(9, 2, 1), samples={"perform": [0.1, 0.2]})
    monkeypatch.setattr(perfbench, "run", lambda *a, **k: drifted)
    assert perfbench.main([*common, "--baseline", str(baseline)]) == 1


def test_main_writes_resource_trace_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_out = tmp_path / "trace.json"
    txns = [
        perfbench.Transaction(
            "perform", 0.2, "button Add", start_offset=0.05, rss_before=10,
            rss_after=20,
        )
    ]
    fixed = _measure(_graph(1, 0, 0), transactions=txns)
    monkeypatch.setattr(perfbench, "run", lambda *a, **k: fixed)
    assert perfbench.main(
        ["--target", "http://127.0.0.1:3000", "--label", "s",
         "--trace-out", str(trace_out)]
    ) == 0
    rows = json.loads(trace_out.read_text(encoding="utf-8"))
    assert rows == [
        {
            "t_start": 0.05,
            "duration_s": 0.2,
            "op": "perform",
            "detail": "button Add",
            "rss_before": 10,
            "rss_after": 20,
        }
    ]


def test_main_writes_html_report_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_out = tmp_path / "trace.html"
    txns = [perfbench.Transaction("reset", 0.1, "", rss_before=1, rss_after=2)]
    fixed = _measure(_graph(1, 0, 0), transactions=txns)
    monkeypatch.setattr(perfbench, "run", lambda *a, **k: fixed)
    assert perfbench.main(
        ["--target", "http://127.0.0.1:3000", "--label", "s",
         "--report-out", str(report_out)]
    ) == 0
    html = report_out.read_text(encoding="utf-8")
    assert "<canvas id=c>" in html and "const DATA = " in html


def test_main_without_baseline_is_advisory_and_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed = _measure(_graph(2, 1, 0))
    monkeypatch.setattr(perfbench, "run", lambda *a, **k: fixed)
    # No baseline given: the bench records but never blocks.
    assert perfbench.main(["--target", "http://127.0.0.1:3000", "--label", "s"]) == 0
