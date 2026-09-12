"""Response-header fingerprint — the third §2c signal (ROADMAP.md §2c).

Response headers — CSP, HSTS, X-Frame-Options, `Server`, `X-Powered-By`, CORS —
are a cheap fingerprint of a product's backend tech and security posture (§2c).

§2h decision (see the ROADMAP §2c note): header *values* are not surfaced to
shared output, because some headers (`set-cookie`, `authorization`) are known
secret shapes. So the split, unlike the console/accessibility count signals, is
about *which facts* are shareable, not just aggregation:

- the raw full headers (all values) are written to the local-only run cache
  (§2h) and never routed to shared output; and
- the `HeaderSignal` carries only non-sensitive derived facts — how many distinct
  headers were seen, and presence booleans for the key security headers.

Surfacing header values to shared output waits on the §2h redaction pipeline.
Nothing here is site-specific (§0): it records whatever headers a response
carried, and the security-header names checked are web standards, not per-target.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Security headers whose mere presence is a non-sensitive posture signal. Web
# standards, identical for every target (§0). Compared case-insensitively.
_CSP = "content-security-policy"
_HSTS = "strict-transport-security"
_X_FRAME_OPTIONS = "x-frame-options"


@dataclass(frozen=True)
class HeaderSignal:
    """Non-sensitive derived facts about a run's response headers (§2c/§2h).

    `count` is the number of distinct header names seen across the run's main
    responses. `csp`, `hsts`, and `x_frame_options` report whether those security
    headers were present anywhere. No header *values* — those stay in the
    local-only raw file, since some are secret shapes (§2h).
    """

    count: int
    csp: bool
    hsts: bool
    x_frame_options: bool


class HeaderCollector:
    """Collects response headers across a run's pages (§2c).

    One collector spans a whole run: `capture` a response's header map once per
    page and it accumulates them. `signal` is the shareable derived summary;
    `write` persists the raw header maps (all values) to the local-only cache.
    Keeping raw values only in the file — never in `signal` — holds the §2h line.
    """

    def __init__(self) -> None:
        # One entry per page: that page's main-response header map (raw values).
        self._responses: list[dict[str, str]] = []

    def capture(self, headers: dict[str, str]) -> None:
        """Record one response's header map (Playwright lowercases the names)."""
        self._responses.append(dict(headers))

    @property
    def signal(self) -> HeaderSignal:
        """The shareable derived summary — counts and presence, never values."""
        names = {name.lower() for headers in self._responses for name in headers}
        return HeaderSignal(
            count=len(names),
            csp=_CSP in names,
            hsts=_HSTS in names,
            x_frame_options=_X_FRAME_OPTIONS in names,
        )

    def write(self, path: Path) -> None:
        """Write the raw per-page header maps to `path` as JSON (§2h, local-only).

        Always writes when called — an empty list for a run with no responses — so
        the file's presence means "headers were captured", mirroring the other
        captures. A local-only artifact carrying all values; never shared output.
        """
        path.write_text(json.dumps(self._responses, indent=2), encoding="utf-8")
