"""Unit tests for the bring-your-own-session loader (ROADMAP.md §2h).

The `.feature` scenarios drive session loading end to end through the tiers; these
probe `load_session`/`_cookies_from` directly at the boundaries Gherkin isn't the
grain for — the failure modes (missing / malformed / wrong-typed file), the
tolerant cookie shape-reading (a bad entry skipped, not raised), and the
host-scoped default for a cookie missing domain/path — plus that `apply_cookies`
scopes what the client will actually send.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from spoor.security.session import (
    SessionCookie,
    SessionError,
    apply_cookies,
    load_session,
)


def _write(tmp_path: Path, data: object) -> str:
    path = tmp_path / "session.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_a_missing_file_raises_session_error(tmp_path: Path) -> None:
    with pytest.raises(SessionError):
        load_session(tmp_path / "nope.json")


def test_malformed_json_raises_session_error(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_session(path)


def test_a_non_object_state_raises_session_error(tmp_path: Path) -> None:
    with pytest.raises(SessionError):
        load_session(_write(tmp_path, ["not", "an", "object"]))


def test_a_valid_state_with_no_cookies_loads_empty(tmp_path: Path) -> None:
    session = load_session(_write(tmp_path, {"cookies": [], "origins": []}))
    assert session.cookies == ()


def test_a_state_missing_keys_loads_empty(tmp_path: Path) -> None:
    # A localStorage-only export may carry no `cookies` key at all.
    session = load_session(_write(tmp_path, {"origins": []}))
    assert session.cookies == ()


def test_cookies_are_read_with_scope(tmp_path: Path) -> None:
    session = load_session(
        _write(
            tmp_path,
            {
                "cookies": [
                    {"name": "sid", "value": "abc", "domain": "x.test", "path": "/app"}
                ]
            },
        )
    )
    assert session.cookies == (SessionCookie("sid", "abc", "x.test", "/app"),)


def test_a_cookie_missing_scope_falls_back_to_host_root(tmp_path: Path) -> None:
    session = load_session(_write(tmp_path, {"cookies": [{"name": "s", "value": "v"}]}))
    assert session.cookies == (SessionCookie("s", "v", "", "/"),)


def test_a_bad_cookie_entry_is_skipped_not_raised(tmp_path: Path) -> None:
    # A non-dict entry, a non-list cookies value, and an entry with a non-string
    # name/value are each ignored — a real browser export degrades gracefully.
    session = load_session(
        _write(
            tmp_path,
            {
                "cookies": [
                    "not-a-dict",
                    {"name": "ok", "value": "v", "domain": "d", "path": "/"},
                    {"name": 1, "value": "v"},
                    {"name": "x", "value": None},
                ]
            },
        )
    )
    assert session.cookies == (SessionCookie("ok", "v", "d", "/"),)


def test_non_list_cookies_yields_empty(tmp_path: Path) -> None:
    session = load_session(_write(tmp_path, {"cookies": "nonsense"}))
    assert session.cookies == ()


def test_apply_cookies_scopes_what_the_client_sends(tmp_path: Path) -> None:
    # A cookie scoped to one host is sent there and not to another host.
    cookie = {"name": "sid", "value": "v", "domain": "in.test", "path": "/"}
    session = load_session(_write(tmp_path, {"cookies": [cookie]}))
    with httpx.Client() as client:
        apply_cookies(session, client)
        in_scope = client.cookies.get("sid", domain="in.test")
        assert in_scope == "v"
        assert client.cookies.get("sid", domain="out.test", default=None) is None
