"""Client-side storage-state capture — the fourth §2c signal (ROADMAP.md §2c, §2h).

The browser context's storage state — cookies plus per-origin localStorage,
read via Playwright's `context.storage_state()`. §2h names this both as
bring-your-own-session's input and as the archetypal *secret-bearing* capture:
session cookies and localStorage tokens are themselves the sensitive data. So
unlike the count-only console/accessibility/header signals, this one cannot
sidestep redaction — it is the first consumer of the §2h redaction pipeline
(`spoor/security/redaction.py`). The split:

- the raw, unredacted storage state (every cookie and localStorage value) is
  written to the local-only run cache (§2h) and never routed to shared output;
- the `StorageStateSignal` carries the entries with known secret shapes redacted
  — the cookie/entry *name* is kept (a structural signal: which cookies and
  localStorage keys the app uses), the *value* is passed through `redact`.

Redaction keys off the recognized `name=value` form, which is why entries are
reconstructed that way before redacting: a recognized session-cookie name or an
auth-token localStorage key is redacted, and a token-shaped value (JWT, API key)
is caught regardless of its key. Residual risk, stated plainly: because entries
(values) *are* surfaced, a secret value in no recognized shape under an
unrecognized name would reach shared output unredacted — the documented boundary
of known-shape redaction (§2h is not an entropy detector). The raw full state
additionally lives in the local-only cache; surfacing entry values accepts this
residual, and mitigations are deferred (see the §2c storage decision note).
Nothing here is site-specific (§0): it records whatever storage the context
held, and the redaction rules are generic secret shapes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from spoor.security.redaction import redact


@dataclass(frozen=True)
class StorageStateSignal:
    """Shareable, redacted view of a run's client-side storage state (§2c/§2h).

    `cookie_count`, `origin_count`, and `local_storage_count` are non-sensitive
    aggregates. `cookies` and `local_storage` are the entries as redacted
    `name=value` strings — names kept, secret-shaped values scrubbed — safe for
    shared output. The raw unredacted values live only in the local-only file.
    """

    cookie_count: int
    origin_count: int
    local_storage_count: int
    cookies: tuple[str, ...]
    local_storage: tuple[str, ...]


def _redact_pairs(pairs: list[tuple[str, str]]) -> tuple[str, ...]:
    """Redact each `name=value` pair for shared output (§2h).

    Reconstructing the `name=value` form is deliberate: it lets the redaction
    pipeline's cookie/auth-key rules fire on the name while its token-shape rules
    still catch a secret-shaped value under any name.
    """
    return tuple(redact(f"{name}={value}") for name, value in pairs)


class StorageStateCollector:
    """Collects the browser context's storage state for a run (§2c).

    Captured once at the context level (not per page): `capture` the dict
    `context.storage_state()` returns, before the context is closed. `signal` is
    the shareable redacted view; `write` persists the raw, unredacted state to
    the local-only cache. Raw values live only in the file — never in `signal` —
    which holds the §2h line.
    """

    def __init__(self) -> None:
        # The most recent storage_state() dict; {} until captured.
        self._state: dict[str, object] = {}

    def capture(self, state: dict[str, object]) -> None:
        """Record the storage-state dict from `context.storage_state()`."""
        self._state = state

    def _cookie_pairs(self) -> list[tuple[str, str]]:
        cookies = self._state.get("cookies", [])
        if not isinstance(cookies, list):
            return []
        return [
            (str(c.get("name", "")), str(c.get("value", "")))
            for c in cookies
            if isinstance(c, dict)
        ]

    def _origins(self) -> list[dict[str, object]]:
        origins = self._state.get("origins", [])
        if not isinstance(origins, list):
            return []
        return [o for o in origins if isinstance(o, dict)]

    def _local_storage_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for origin in self._origins():
            entries = origin.get("localStorage", [])
            if not isinstance(entries, list):
                continue
            pairs.extend(
                (str(e.get("name", "")), str(e.get("value", "")))
                for e in entries
                if isinstance(e, dict)
            )
        return pairs

    @property
    def signal(self) -> StorageStateSignal:
        """The shareable redacted view — names kept, secret-shaped values scrubbed."""
        cookie_pairs = self._cookie_pairs()
        ls_pairs = self._local_storage_pairs()
        return StorageStateSignal(
            cookie_count=len(cookie_pairs),
            origin_count=len(self._origins()),
            local_storage_count=len(ls_pairs),
            cookies=_redact_pairs(cookie_pairs),
            local_storage=_redact_pairs(ls_pairs),
        )

    def write(self, path: Path) -> None:
        """Write the raw, unredacted storage state to `path` (§2h, local-only).

        Always writes when called — an empty dict for a run that captured no
        state — so the file's presence means "storage state was captured",
        mirroring the other captures. A local-only artifact carrying every raw
        value; never shared output.
        """
        path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
