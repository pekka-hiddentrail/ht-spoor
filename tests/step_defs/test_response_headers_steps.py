"""Step definitions for features/response_headers.feature (ROADMAP.md §2c, §2h).

The browser-tier scenario runs the full dispatcher against a live loopback server
and a real Chromium — the only honest way to prove response headers are actually
recorded — with the local cache root redirected into a temp directory. The tier-1
scenarios use the network-free `mock_client`; a run without a browser records no
header signal, and these pin that it writes nothing and says so.
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

scenarios("response_headers.feature")


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
        "a config whose items only exist after JS renders them, "
        "with header capture on:"
    )
)
@given(parsers.parse("a static config with header capture on:"))
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


@then("a response-headers file is written under the run cache directory")
def headers_file_written(context: dict[str, Any]) -> None:
    path = context["result"].headers_path
    assert path is not None
    # It lives under the redirected local-only cache root, nowhere else (§2h).
    assert context["cache_root"] in path.parents
    assert path.is_file()
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), list)


@then("the run records at least one response header")
def header_signal_populated(context: dict[str, Any]) -> None:
    signal = context["result"].headers
    assert signal is not None
    assert signal.count >= 1


@then("the run summary reports the response-header count")
def summary_reports_count(context: dict[str, Any]) -> None:
    signal = context["result"].headers
    assert f"headers:       {signal.count} captured" in context["summary"].render()


@then("the run summary reports the security-header presence")
def summary_reports_security(context: dict[str, Any]) -> None:
    rendered = context["summary"].render()
    assert "security:" in rendered
    assert "CSP" in rendered
    assert "HSTS" in rendered
    assert "X-Frame-Options" in rendered


@then("the run summary reports the response headers as a local-only capture")
def summary_reports_headers_path(context: dict[str, Any]) -> None:
    path = context["result"].headers_path
    summary = context["summary"]
    assert summary.headers_path == str(path)
    rendered = summary.render()
    assert "raw headers (local-only)" in rendered
    assert str(path) in rendered


@then("the run summary shows no header values")
def summary_shows_no_values(context: dict[str, Any]) -> None:
    # The raw file holds all header values; none may appear in shared output (§2h).
    # Only distinctive values are checked: short/numeric ones (e.g. a content-length
    # of "1") could coincidentally substring-match an unrelated summary number, so
    # they'd make this assertion flaky without proving anything about leakage.
    raw = json.loads(context["result"].headers_path.read_text(encoding="utf-8"))
    rendered = context["summary"].render()
    for headers in raw:
        for value in headers.values():
            if len(value) >= 6:
                assert value not in rendered


@then("no response-headers file is written to the cache")
def no_headers_file(context: dict[str, Any]) -> None:
    assert context["result"].headers_path is None
    # A tier-1 run touches nothing in the cache at all.
    assert not context["cache_root"].exists()


@then("the run summary reports no header signal")
def summary_no_headers(context: dict[str, Any]) -> None:
    summary = context["summary"]
    assert summary.headers is None
    assert "headers:" not in summary.render()
