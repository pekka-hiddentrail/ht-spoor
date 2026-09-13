"""Bring-your-own-session: loading a supplied browser session (ROADMAP.md §2h).

§2h decided auth deliberately narrow for v1: Spoor implements no login/MFA/SSO
flow (a per-provider surface that would violate §0). Instead the user supplies a
storage state they captured once in a real browser — Playwright's
`context.storage_state()` JSON (cookies + per-origin localStorage) — as a run
input. This module owns reading that file: it is the input counterpart of the
storage-state *capture* signal (`spoor/signals/storage_state.py`), which writes
the same shape.

The state is secret-bearing but it is an *input*, not a capture: it is loaded
into the fetch and never routed to shared output, so the §2h redaction pipeline
(which guards captures on their way out) is not in play here — the discipline
that applies is simply that nothing loaded here is ever echoed into the run
summary or records. A missing or malformed file raises `SessionError` so a run
fails loudly rather than silently proceeding unauthenticated. Nothing here is
site-specific (§0): the same format is read for every target.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx


class SessionError(ValueError):
    """A supplied session file is missing, unreadable, or not a storage state.

    Raised (not swallowed) so a run configured with a bad session fails loudly
    before fetching, rather than silently running as an anonymous visitor.
    """


@dataclass(frozen=True)
class SessionCookie:
    """One cookie from a supplied session, as needed to send it via httpx.

    Only the fields the static tier needs to replay the cookie: `name`/`value`
    and the `domain`/`path` scope that decides which requests carry it. The
    browser tier does not use these — it loads the whole state file directly.
    """

    name: str
    value: str
    domain: str
    path: str


@dataclass(frozen=True)
class LoadedSession:
    """A validated supplied session (ROADMAP.md §2h).

    `path` is the on-disk storage-state file, handed to the browser tier as-is so
    Playwright applies cookies *and* localStorage. `cookies` is the subset the
    static (no-JS) tier can use; localStorage-gated auth has no static equivalent
    and naturally escalates to the browser tier, which applies the full state.
    """

    path: Path
    cookies: tuple[SessionCookie, ...]


def load_session(path: str | Path) -> LoadedSession:
    """Read and validate a supplied storage-state file (ROADMAP.md §2h).

    Raises `SessionError` on a file that cannot be read, is not valid JSON, or is
    not a storage-state object — so the failure surfaces before any fetch. A
    valid state with no cookies (e.g. a purely localStorage-based session) loads
    fine with an empty `cookies` tuple.
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SessionError(f"session file could not be read: {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SessionError(f"session file is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise SessionError(f"session file must be a storage-state object: {path}")
    return LoadedSession(path=file_path, cookies=_cookies_from(data))


def _cookies_from(data: dict[str, object]) -> tuple[SessionCookie, ...]:
    """The usable cookies in a storage state, defensively (a bad entry is skipped).

    Mirrors the capture side's tolerant shape-reading: a non-list `cookies`, a
    non-dict entry, or an entry missing a string name/value is ignored rather than
    raising — the file came from a real browser export, so partial oddities should
    degrade to "that cookie isn't sent", not fail the whole run. Domain/path fall
    back to a host-scoped default when absent.
    """
    raw = data.get("cookies", [])
    if not isinstance(raw, list):
        return ()
    cookies: list[SessionCookie] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        value = entry.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        domain = entry.get("domain")
        path = entry.get("path")
        cookies.append(
            SessionCookie(
                name=name,
                value=value,
                domain=domain if isinstance(domain, str) else "",
                path=path if isinstance(path, str) else "/",
            )
        )
    return tuple(cookies)


def apply_cookies(session: LoadedSession, client: httpx.Client) -> None:
    """Load a session's cookies into `client`'s jar so the static tier sends them.

    Domain/path scoping is preserved, so a cookie is sent only to the hosts and
    paths it was scoped to — the same targeting the originating browser applied.
    """
    for cookie in session.cookies:
        client.cookies.set(
            cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
        )
