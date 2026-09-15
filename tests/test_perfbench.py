"""Tests for the exploration performance bench (scripts/perfbench.py, §5.5).

The bench's maths — reducing a finished run to metrics, timing each browser
operation, emitting the per-operation timing trend, and gating on deterministic
drift (scalar counters *and* per-operation call counts) — is pure, so it is
unit-tested here with a hand-built graph, fake timing samples, and a fake driver;
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


# --- check_drift ---------------------------------------------------------


def _baseline_from(metrics: Any) -> dict[str, Any]:
    return json.loads(json.dumps(perfbench._baseline_payload(metrics)))


def test_check_drift_empty_when_counters_and_calls_match() -> None:
    m = _measure(_graph(5, 4, 1), samples={"perform": [0.1], "reset": [0.2, 0.3]})
    assert perfbench.check_drift(m, _baseline_from(m)) == []


def test_check_drift_flags_a_changed_scalar_counter() -> None:
    m = _measure(_graph(5, 4, 1))
    baseline = _baseline_from(m)
    baseline["states"] = m.states + 1
    drift = perfbench.check_drift(m, baseline)
    assert len(drift) == 1 and "states" in drift[0]


def test_check_drift_flags_a_changed_call_count() -> None:
    m = _measure(_graph(5, 4, 0), samples={"perform": [0.1, 0.2, 0.3]})
    baseline = _baseline_from(m)
    baseline["calls"]["perform"] = 99  # the run made 3, baseline expects 99
    drift = perfbench.check_drift(m, baseline)
    assert drift == ["calls.perform: baseline 99 -> now 3"]


def test_check_drift_flags_a_vanished_operation() -> None:
    m = _measure(_graph(2, 1, 0), samples={"reset": [0.1]})
    baseline = _baseline_from(m)
    baseline["calls"]["screenshot"] = 6  # baseline had screenshots; run made none
    drift = perfbench.check_drift(m, baseline)
    assert drift == ["calls.screenshot: baseline 6 -> now 0"]


def test_check_drift_flags_a_changed_skip_reason() -> None:
    graph = ExplorationGraph()
    graph.add_state("s0", [])
    graph.record_skip("s0", _action("d"), "destructive")
    m = _measure(graph)
    baseline = _baseline_from(m)
    baseline["skip_reasons"]["destructive"] = 5  # run skipped 1, baseline expects 5
    drift = perfbench.check_drift(m, baseline)
    assert drift == ["skip_reasons.destructive: baseline 5 -> now 1"]


def test_check_drift_ignores_timing_and_missing_fields() -> None:
    m = _measure(_graph(5, 4, 1), samples={"perform": [0.1]})
    # A baseline with only one scalar and a bogus timing key: timing is never
    # compared, missing scalars/calls are skipped.
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
    assert set(seeded) == {*perfbench._SCALAR_FIELDS, "calls", "skip_reasons"}
    assert seeded["calls"] == {"perform": 2}

    # Re-run against the seeded baseline: matches, exits 0, writes the chart JSON.
    assert perfbench.main(
        [*common, "--baseline", str(baseline), "--bench-out", str(bench_out)]
    ) == 0
    assert json.loads(bench_out.read_text(encoding="utf-8"))  # timing rows written

    # Drift: a different graph shape against the same baseline fails the gate.
    drifted = _measure(_graph(9, 2, 1), samples={"perform": [0.1, 0.2]})
    monkeypatch.setattr(perfbench, "run", lambda *a, **k: drifted)
    assert perfbench.main([*common, "--baseline", str(baseline)]) == 1


def test_main_without_baseline_is_advisory_and_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed = _measure(_graph(2, 1, 0))
    monkeypatch.setattr(perfbench, "run", lambda *a, **k: fixed)
    # No baseline given: the bench records but never blocks.
    assert perfbench.main(["--target", "http://127.0.0.1:3000", "--label", "s"]) == 0
