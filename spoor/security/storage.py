"""Local-only run cache for raw captures (ROADMAP.md §2h).

§2h non-negotiable: raw, unredacted captures (a full HAR, a full storage state)
stay in a local-only cache and never reach shared output without a separate,
explicit export step. This module owns *where* that cache lives — a per-run
subdirectory of a git-ignored cache root — and nothing more. It deliberately
does not touch the output pipeline, the wiki, or any MCP/API response: routing a
raw capture to a shared surface is the (not-yet-built) export action, not a side
effect of writing one here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# The cache root, relative to the working directory and git-ignored. A
# configurable base is deferred to the full Phase 2.5 (see the ROADMAP §2h
# decision note); tests redirect this to a temp directory by monkeypatching it.
CACHE_ROOT = Path(".spoor-cache")

# The filename a run's captured HAR is written under, inside its run directory.
HAR_FILENAME = "network.har"

# The filename a run's captured console log (JSON Lines) is written under (§2c).
CONSOLE_FILENAME = "console.jsonl"


def new_run_id() -> str:
    """A sortable, collision-resistant id for one run's cache subdirectory.

    A UTC timestamp keeps directories in run order for a human browsing the
    cache; the random suffix keeps two runs started in the same second apart.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid4().hex[:8]}"


def new_run_cache_dir() -> Path:
    """Create and return a fresh, empty per-run cache directory under CACHE_ROOT.

    CACHE_ROOT is read at call time (not import), so a monkeypatch of it in a
    test takes effect here.
    """
    run_dir = CACHE_ROOT / new_run_id()
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
