"""Shared payload builder for the read-only serving surfaces (ROADMAP.md §2f).

Both serving modes — the REST API (`api.py`) and the MCP server (`mcp_server.py`)
— must answer with the *same* shape and the *same* §2h guarantees, so the one
function that turns a stored `MapEntry` into a served answer lives here rather
than being duplicated per surface. It attaches the freshness age (§2f "always
show the age") and runs the records and the observed API surface through the
secret-redaction guard on the way out (§2h): an output that reaches either shared
surface is redacted, and neither surface can drift from the other.
"""

from __future__ import annotations

from datetime import UTC, datetime

from spoor.security.redaction import redact_records, redact_value
from spoor.serving.store import MapEntry


def map_view(entry: MapEntry) -> dict[str, object]:
    """The served answer for one mapped URL: redacted content plus freshness.

    Records and the observed API surface pass through redaction here (§2h); the
    capture time is echoed and a non-negative `age_seconds` computed against now.
    Deliberately omits `entry.config` — the stored extraction config is local-only
    (kept solely to reproduce a forced recheck, §2f) and must never be served.
    """
    captured = datetime.fromisoformat(entry.captured_at)
    age_seconds = (datetime.now(UTC) - captured).total_seconds()
    return {
        "url": entry.url,
        "domain": entry.domain,
        "tier": entry.tier,
        "records": redact_records(entry.records),
        "api_surface": redact_value(entry.api_surface),
        "captured_at": entry.captured_at,
        "age_seconds": age_seconds,
    }
