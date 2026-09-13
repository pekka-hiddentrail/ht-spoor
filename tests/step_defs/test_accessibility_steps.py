"""Step definitions for features/accessibility.feature (ROADMAP.md §2c, §2h).

The browser-tier scenario runs the full dispatcher against a live loopback
server and a real Chromium — the only honest way to prove an accessibility tree
is actually snapshotted — with the local cache root redirected into a temp
directory. The tier-1 scenarios use the network-free `mock_client`; a run without
a browser has no rendered tree to snapshot, and these pin that it writes nothing
and says so.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.core.fingerprint_cache import FINGERPRINT_DIRNAME
from spoor.operational.observability import RunSummary
from spoor.security import storage

scenarios("accessibility.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {}


# --- Given ---------------------------------------------------------------


@given("a live fixture server")
def live_fixture_server(context: dict[str, Any], live_server: str) -> None:
    context["server_base"] = live_server


@given("capture is enabled with the cache redirected to a temp directory")
def redirect_cache(
    context: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_root = tmp_path / ".spoor-cache"
    monkeypatch.setattr(storage, "CACHE_ROOT", cache_root)
    context["cache_root"] = cache_root


@given(
    parsers.parse(
        "a config whose items only exist after JS renders them, with a11y capture on:"
    )
)
@given(parsers.parse("a static config with a11y capture on:"))
@given(parsers.parse("a static config with no capture section:"))
def config_text(context: dict[str, Any], docstring: str) -> None:
    context["config_text"] = docstring


# --- When ----------------------------------------------------------------


@when("I run the config through the dispatcher against a real browser")
def run_against_browser(context: dict[str, Any]) -> None:
    text = context["config_text"].replace("SERVER_BASE", context["server_base"])
    cfg = load_config(text)
    result = extract.run_report(cfg)
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


@when("I run the config with the mock client")
def run_with_mock(context: dict[str, Any], mock_client: httpx.Client) -> None:
    cfg = load_config(context["config_text"])
    result = extract.run_report(cfg, client=mock_client, sleep=lambda _: None)
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


# --- Then ----------------------------------------------------------------


@then("an accessibility snapshot file is written under the run cache directory")
def a11y_file_written(context: dict[str, Any]) -> None:
    path = context["result"].accessibility_path
    assert path is not None
    # It lives under the redirected local-only cache root, nowhere else (§2h).
    assert context["cache_root"] in path.parents
    assert path.is_file()
    # And it parses as JSON (a list of per-page trees).
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), list)


@then("the run records at least one accessible node")
def a11y_signal_populated(context: dict[str, Any]) -> None:
    signal = context["result"].accessibility
    assert signal is not None
    assert signal.nodes >= 1


@then("the run summary reports the accessible node count")
def summary_reports_a11y(context: dict[str, Any]) -> None:
    signal = context["result"].accessibility
    assert f"a11y nodes:    {signal.nodes}" in context["summary"].render()


@then("the run summary reports the accessibility snapshot as a local-only capture")
def summary_reports_a11y_path(context: dict[str, Any]) -> None:
    path = context["result"].accessibility_path
    summary = context["summary"]
    assert summary.accessibility_path == str(path)
    rendered = summary.render()
    assert "raw a11y tree (local-only)" in rendered
    assert str(path) in rendered


@then("no accessibility snapshot file is written to the cache")
def no_a11y_file(context: dict[str, Any]) -> None:
    assert context["result"].accessibility_path is None
    # No capture artifact was written. Tier-3 fingerprint persistence is always-on
    # and independent of the capture opt-in (local-only, §2h), so the only thing a
    # no-capture tier-1 run may leave in the cache root is that fingerprints/ subdir.
    cache_root: Path = context["cache_root"]
    leftovers = {p.name for p in cache_root.iterdir()} if cache_root.exists() else set()
    assert leftovers <= {FINGERPRINT_DIRNAME}


@then("the run summary reports no accessibility signal")
def summary_no_a11y(context: dict[str, Any]) -> None:
    summary = context["summary"]
    assert summary.accessibility is None
    assert "a11y nodes:" not in summary.render()
