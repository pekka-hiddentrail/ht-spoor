"""Step definitions for features/capture.feature (ROADMAP.md §2b/§2c, §2h).

The browser-tier scenario runs the full dispatcher against a live loopback
server and a real Chromium — the only honest way to prove a HAR is actually
recorded — with the local cache root redirected into a temp directory. The
tier-1 scenarios use the network-free `mock_client`; a run without a browser has
no traffic to capture, and these pin that it writes nothing and says so.
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
from spoor.operational.observability import RunSummary
from spoor.security import storage

scenarios("capture.feature")


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
        "a config whose items only exist after JS renders them, with capture on:"
    )
)
@given(parsers.parse("a static config with capture on:"))
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


@then("a HAR file is written under the run cache directory")
def har_written(context: dict[str, Any]) -> None:
    har_path = context["result"].har_path
    assert har_path is not None
    # It lives under the redirected local-only cache root, nowhere else (§2h).
    assert context["cache_root"] in har_path.parents
    assert har_path.is_file()


@then("the HAR parses as JSON with a request for the rendered page")
def har_has_entries(context: dict[str, Any]) -> None:
    har_path: Path = context["result"].har_path
    har = json.loads(har_path.read_text(encoding="utf-8"))
    entries = har["log"]["entries"]
    assert entries
    urls = [entry["request"]["url"] for entry in entries]
    assert any(url.endswith("/js-rendered.html") for url in urls)


@then("the run summary reports the captured HAR path")
def summary_reports_har(context: dict[str, Any]) -> None:
    summary = context["summary"]
    har_path = context["result"].har_path
    assert summary.har_path == str(har_path)
    assert str(har_path) in summary.render()


@then("no HAR file is written to the cache")
def no_har_written(context: dict[str, Any]) -> None:
    assert context["result"].har_path is None
    # Nothing should have touched the cache root at all.
    assert not context["cache_root"].exists()


@then("the run summary reports no capture")
def summary_no_capture(context: dict[str, Any]) -> None:
    summary = context["summary"]
    assert summary.har_path is None
    assert "captured" not in summary.render()
