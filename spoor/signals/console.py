"""Console output & JS-error capture — the first §2c signal (ROADMAP.md §2c).

A browser session sees the page's console and its uncaught exceptions, which a
bare fetch never does; developers leak useful debug output and stack traces in
production more often than expected (§2c). This module collects those events off
a Playwright `Page` and turns them into two things:

- a raw, per-message log written to the local-only run cache (§2h) — it can
  carry secrets (tokens logged in debug output), so it never reaches shared
  output; and
- a `ConsoleSignal`: counts only (total messages, errors, uncaught page errors),
  which carry no message content and so are safe to surface in the run summary.

Surfacing message *content* to shared output waits on the §2h redaction pipeline
(see the ROADMAP §2c decision note). Nothing here is site-specific (§0): it keys
off Playwright events alone, identically for every target.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Error, Page


@dataclass(frozen=True)
class ConsoleSignal:
    """Aggregate counts of a run's console activity (ROADMAP.md §2c).

    Counts only — no message text — so this is safe for shared output. `messages`
    is every `console.*` call the page made; `errors` is the subset at `error`
    level; `page_errors` is uncaught JS exceptions (`page.on("pageerror")`),
    which are distinct from `console.error` and a stronger "this page broke"
    signal.
    """

    messages: int
    errors: int
    page_errors: int


class ConsoleCollector:
    """Collects console + pageerror events across all of a run's pages (§2c).

    One collector spans a whole run: `attach` it to each page the browser tier
    opens and it accumulates every event. `signal` is the shareable count
    summary; `write` persists the raw per-message records to the local-only cache
    as JSON Lines. Keeping raw text only in the file (never in `signal`) is what
    holds the §2h line between local-only captures and shared output.
    """

    def __init__(self) -> None:
        self._records: list[dict[str, object]] = []
        self._messages = 0
        self._errors = 0
        self._page_errors = 0

    def attach(self, page: Page) -> None:
        """Subscribe to a page's console and pageerror events.

        Attach before navigating so load-time output and errors are caught.
        """
        page.on("console", self._on_console)
        page.on("pageerror", self._on_pageerror)

    def _on_console(self, message: ConsoleMessage) -> None:
        self._messages += 1
        if message.type == "error":
            self._errors += 1
        self._records.append(
            {"kind": "console", "type": message.type, "text": message.text}
        )

    def _on_pageerror(self, error: Error) -> None:
        self._page_errors += 1
        self._records.append(
            {"kind": "pageerror", "name": error.name, "message": error.message}
        )

    @property
    def signal(self) -> ConsoleSignal:
        """The shareable count summary of everything collected so far."""
        return ConsoleSignal(
            messages=self._messages,
            errors=self._errors,
            page_errors=self._page_errors,
        )

    def write(self, path: Path) -> None:
        """Write the raw per-message records to `path` as JSON Lines (§2h).

        Always writes a file when called — an empty file for a silent run — so the
        file's presence means "console was captured", mirroring the HAR. This is a
        local-only artifact; it must never be routed to shared output unredacted.
        """
        with path.open("w", encoding="utf-8") as handle:
            for record in self._records:
                handle.write(json.dumps(record) + "\n")
