"""Step definitions for features/storage_state.feature (ROADMAP.md §2c, §2h).

The browser-tier scenario runs the full dispatcher against a live loopback server
and a real Chromium — the only honest way to prove the context's cookies and
localStorage are captured and redacted — with the local cache root redirected
into a temp directory. The tier-1 scenarios use the network-free `mock_client`;
a run without a browser captures no storage state, and these pin that it writes
nothing and says so.

The fixture (stateful.html) writes a recognized session cookie and a token-shaped
localStorage entry (both secret shapes) plus a plainly non-secret entry, so the
§2h split is exercised end to end: raw values reach only the local-only file, and
shared output shows the entries with the secrets redacted.
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

scenarios("storage_state.feature")

# The secret-shaped values stateful.html writes; redaction must keep these out of
# shared output while the raw local-only file retains them verbatim.
_RAW_COOKIE_VALUE = "8f9a1b2c3d4e5f60718293a4b5c6d7e8"
_RAW_TOKEN_VALUE = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhYmMifQ.s1gnatur3-x_Y"


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
        "with storage capture on:"
    )
)
@given(parsers.parse("a static config with storage capture on:"))
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


@then("a storage-state file is written under the run cache directory")
def storage_file_written(context: dict[str, Any]) -> None:
    path = context["result"].storage_state_path
    assert path is not None
    # It lives under the redirected local-only cache root, nowhere else (§2h).
    assert context["cache_root"] in path.parents
    assert path.is_file()
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


@then("the run records at least one cookie and one localStorage entry")
def storage_signal_populated(context: dict[str, Any]) -> None:
    signal = context["result"].storage_state
    assert signal is not None
    assert signal.cookie_count >= 1
    assert signal.local_storage_count >= 1


@then("the shared storage signal shows the recognized session cookie redacted")
def cookie_redacted(context: dict[str, Any]) -> None:
    signal = context["result"].storage_state
    assert "sessionid=[REDACTED]" in signal.cookies


@then("the shared storage signal keeps the non-secret entry intact")
def non_secret_intact(context: dict[str, Any]) -> None:
    signal = context["result"].storage_state
    assert "theme=dark" in signal.local_storage


@then("no raw secret value appears in shared output")
def no_raw_secret_in_shared_output(context: dict[str, Any]) -> None:
    # Shared output is both the structured signal object and the rendered summary
    # (§2h): the raw cookie value and the raw token must appear in neither.
    signal = context["result"].storage_state
    rendered = context["summary"].render()
    for surface in (repr(signal), rendered):
        assert _RAW_COOKIE_VALUE not in surface
        assert _RAW_TOKEN_VALUE not in surface


@then("the raw storage-state file still contains the unredacted secret value")
def raw_file_has_secret(context: dict[str, Any]) -> None:
    raw = context["result"].storage_state_path.read_text(encoding="utf-8")
    assert _RAW_COOKIE_VALUE in raw
    assert _RAW_TOKEN_VALUE in raw


@then("the run summary reports the storage-state counts")
def summary_reports_counts(context: dict[str, Any]) -> None:
    signal = context["result"].storage_state
    rendered = context["summary"].render()
    assert f"storage:       {signal.cookie_count} cookies" in rendered
    assert f"{signal.local_storage_count} localStorage entries" in rendered


@then("the run summary reports the storage state as a local-only capture")
def summary_reports_path(context: dict[str, Any]) -> None:
    path = context["result"].storage_state_path
    summary = context["summary"]
    assert summary.storage_state_path == str(path)
    rendered = summary.render()
    assert "raw storage state (local-only)" in rendered
    assert str(path) in rendered


@then("no storage-state file is written to the cache")
def no_storage_file(context: dict[str, Any]) -> None:
    assert context["result"].storage_state_path is None
    # No capture artifact was written. Tier-3 fingerprint persistence is always-on
    # and independent of the capture opt-in (local-only, §2h), so the only thing a
    # no-capture tier-1 run may leave in the cache root is that fingerprints/ subdir.
    cache_root: Path = context["cache_root"]
    leftovers = {p.name for p in cache_root.iterdir()} if cache_root.exists() else set()
    assert leftovers <= {FINGERPRINT_DIRNAME}


@then("the run summary reports no storage signal")
def summary_no_storage(context: dict[str, Any]) -> None:
    summary = context["summary"]
    assert summary.storage_state is None
    assert "storage:" not in summary.render()
