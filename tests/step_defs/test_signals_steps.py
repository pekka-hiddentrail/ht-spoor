"""Step definitions for features/signals.feature (ROADMAP.md §2c, §2h).

The browser-tier scenario runs the full dispatcher against a live loopback
server and a real Chromium — the only honest way to prove console output and a
page error are actually observed — with the local cache root redirected into a
temp directory. The tier-1 scenarios use the network-free `mock_client`; a run
without a browser has no console to observe, and these pin that it records
nothing and says so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary
from spoor.security import storage

scenarios("signals.feature")


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
        "a config for a page that logs to the console and throws, "
        "with console capture on:"
    )
)
@given(parsers.parse("a static config with console capture on:"))
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


@then("a console log file is written under the run cache directory")
def console_log_written(context: dict[str, Any]) -> None:
    path = context["result"].console_log_path
    assert path is not None
    # It lives under the redirected local-only cache root, nowhere else (§2h).
    assert context["cache_root"] in path.parents
    assert path.is_file()


@then("the run records at least one console message, one error, and one uncaught error")
def console_signal_populated(context: dict[str, Any]) -> None:
    signal = context["result"].console
    assert signal is not None
    # >= to stay robust against the browser emitting extra console noise.
    assert signal.messages >= 1
    assert signal.errors >= 1
    assert signal.page_errors >= 1


@then("the run summary reports the console message counts")
def summary_reports_console(context: dict[str, Any]) -> None:
    signal = context["result"].console
    rendered = context["summary"].render()
    assert f"{signal.messages} messages" in rendered
    assert f"{signal.errors} errors" in rendered
    assert f"{signal.page_errors} uncaught" in rendered


@then("the run summary reports the console log as a local-only capture")
def summary_reports_console_path(context: dict[str, Any]) -> None:
    path = context["result"].console_log_path
    summary = context["summary"]
    assert summary.console_log_path == str(path)
    rendered = summary.render()
    assert "raw console log (local-only)" in rendered
    assert str(path) in rendered


@then("no console log file is written to the cache")
def no_console_log(context: dict[str, Any]) -> None:
    assert context["result"].console_log_path is None
    # A tier-1 run touches nothing in the cache at all.
    assert not context["cache_root"].exists()


@then("the run summary reports no console signal")
def summary_no_console(context: dict[str, Any]) -> None:
    summary = context["summary"]
    assert summary.console is None
    assert "console:" not in summary.render()
