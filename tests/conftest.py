"""Shared test fixtures and pytest-bdd hooks.

Extraction scenarios target `http://localhost:8000/...` URLs. Rather than run a
real socket server, we serve the checked-in static fixtures (fixtures/static)
through an httpx MockTransport — fully deterministic, no ports, no network.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "static"


def _serve(request: httpx.Request) -> httpx.Response:
    rel = request.url.path.lstrip("/") or "index.html"
    target = (FIXTURES_DIR / rel).resolve()
    # Stay within the fixtures dir; serve the file if it exists.
    if FIXTURES_DIR in target.parents and target.is_file():
        return httpx.Response(200, text=target.read_text(encoding="utf-8"))
    return httpx.Response(404, text=f"no fixture for {request.url.path}")


@pytest.fixture
def mock_client() -> httpx.Client:
    """An httpx client that serves the static fixtures for any localhost URL."""
    with httpx.Client(transport=httpx.MockTransport(_serve)) as client:
        yield client


def pytest_bdd_apply_tag(tag: str, function: object) -> bool | None:
    """Skip scenarios that need capabilities not yet built."""
    if tag == "tier2":
        marker = pytest.mark.skip(
            reason="requires tier-2 browser rendering (later Phase 1/2)"
        )
        marker(function)
        return True
    return None
