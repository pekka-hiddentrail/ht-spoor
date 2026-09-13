"""End-to-end authenticated extraction against the live archetype bench (§5.1, §2h).

Sauce Demo is the second live archetype and the first *login-gated* one. It proves
two things Juice Shop cannot:

- **bring-your-own-session end to end (§2h).** Its inventory is a client-rendered
  React route guarded by a login cookie. A user logs in once in a real browser and
  hands Spoor the captured session; Spoor replays it and extracts the gated page.
  This test does that against a real app instead of the synthetic loopback server
  `features/session.feature` uses. Spoor itself never logs in — a login/SSO flow
  would be a per-site surface that violates §0; the *capture* is done here in the
  test harness, standing in for the user, and only the resulting storage state is
  handed to Spoor.
- **§0 no-tailoring, second data point.** The same unmodified generic tiers that
  resolve Juice Shop resolve a structurally different SPA. If Spoor needed a special
  case for either, that would be a bug in the general mechanism, not a fixture quirk.

Two-sided by construction: the inventory is client-rendered, so tier 1 (static
fetch) sees only the app shell and the dispatcher escalates to the browser tier
(content-driven escalation, §2). And the route is login-gated, so a browser-tier
run *without* a session is redirected to the login page and extracts nothing —
only the run carrying the captured session sees products.

Marked `integration`: it needs the docker bench up
(`docker compose -f fixtures/docker-compose.yml up -d`) and skips cleanly when the
container isn't reachable, so the fast unit gate stays Docker-free. The bench host
port defaults to 3001; set SPOOR_SAUCE_DEMO_BASE (and the matching SAUCE_DEMO_PORT
for compose) when running on a different port.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from spoor.core import extract
from spoor.core.config import load_config

SAUCE_DEMO_BASE = os.environ.get("SPOOR_SAUCE_DEMO_BASE", "http://127.0.0.1:3001")
_DEFAULT_BASE = "http://127.0.0.1:3001"
_INVENTORY_PATH = "/inventory.html"
# The standard demo user; the app accepts a fixed password for every user and
# persists login in a readable `session-username` cookie (short-lived), which is
# why the session is captured fresh per run rather than committed to the repo.
_USERNAME = "standard_user"
_PASSWORD = "secret_sauce"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "fixtures" / "configs" / "sauce-demo-inventory.yaml"
# Committed baseline for §5.4 dogfooding: the deterministic inventory of the pinned
# source build, so a diff surfaces any silent change in Spoor OR the fixture.
_GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "sauce-demo-inventory.json"
# Where a run's actual output lands — a durable directory (not a temp folder), so a
# mismatch can be uploaded as a CI artifact and inspected.
_RUN_OUTPUT_PATH = _REPO_ROOT / "test-output" / "sauce-demo-inventory.json"

pytestmark = pytest.mark.integration


def _sorted_by_name(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Stable ordering for comparison — the page's render order isn't a contract."""
    return sorted(records, key=lambda record: str(record["name"]))


def _config_text(session_path: str | None) -> str:
    """The committed fixture config, retargeted to this bench and given a session.

    Reuses the *committed* yaml (dogfooding it, as the Juice Shop test does) rather
    than an inline string, rewriting only the base URL for the running host port and
    appending the captured session path. `None` yields the config with no session —
    the gated, extracts-nothing case.
    """
    text = _CONFIG_PATH.read_text(encoding="utf-8")
    text = text.replace(_DEFAULT_BASE, SAUCE_DEMO_BASE)
    if session_path is not None:
        text += f"session: {session_path}\n"
    return text


@pytest.fixture(scope="module")
def sauce_demo() -> str:
    """Skip the module unless the Sauce Demo bench answers on its port."""
    try:
        response = httpx.get(f"{SAUCE_DEMO_BASE}{_INVENTORY_PATH}", timeout=3.0)
        response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        pytest.skip(
            "Sauce Demo bench not reachable — start it with "
            "`docker compose -f fixtures/docker-compose.yml up -d` "
            f"({exc})"
        )
    return SAUCE_DEMO_BASE


@pytest.fixture(scope="module")
def captured_session(
    sauce_demo: str, tmp_path_factory: pytest.TempPathFactory
) -> str:
    """Log in as a user would and capture the browser session (§2h input side).

    This stands in for the human who captures a session in their own browser: it
    drives a real Chromium through the login form and writes the resulting
    `storage_state()` (cookies + localStorage) to a temp file — the exact shape
    Spoor's `session:` input consumes. Spoor never performs this login itself.
    """
    from playwright.sync_api import sync_playwright

    path = tmp_path_factory.mktemp("session") / "sauce-demo-session.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"{sauce_demo}/")
            page.fill("#user-name", _USERNAME)
            page.fill("#password", _PASSWORD)
            page.click("#login-button")
            page.wait_for_url(f"**{_INVENTORY_PATH}", timeout=10_000)
            state = context.storage_state()
        finally:
            browser.close()
    path.write_text(json.dumps(state), encoding="utf-8")
    return str(path)


def test_browser_tier_without_a_session_is_gated(sauce_demo: str) -> None:
    # The login gate is real: with no session the dispatcher still escalates to the
    # browser tier (tier 1 sees an empty shell), but the app redirects the browser
    # to the login page, so no products are ever rendered or extracted.
    result = extract.run_report(load_config(_config_text(None)))
    assert result.blocked == []
    assert result.records == []


def test_authenticated_run_escalates_and_matches_golden(
    sauce_demo: str, captured_session: str
) -> None:
    # The real end-to-end path: tier 1 comes up empty on the gated SPA, the
    # dispatcher escalates to the browser tier, which replays the captured session
    # and extracts the inventory behind the login (ROADMAP §2, §2h).
    result = extract.run_report(load_config(_config_text(captured_session)))
    assert result.blocked == []
    records = _sorted_by_name(result.records)

    # Persist first (uploaded as a CI artifact), then diff against the golden master
    # (§5.4) — a mismatch leaves the actual output on disk to inspect.
    _RUN_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RUN_OUTPUT_PATH.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    assert records == golden, (
        "Sauce Demo extraction drifted from the golden master; inspect "
        f"{_RUN_OUTPUT_PATH} against {_GOLDEN_PATH}"
    )
