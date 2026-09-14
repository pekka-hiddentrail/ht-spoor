"""Read-only REST API over the captured map (ROADMAP.md §2f).

The plain-API consumption mode from §2f: the same map the (future) MCP server
answers from, served over conventional HTTP GETs for scripts, dashboards, and CI
checks against a previously-mapped site.

NON-NEGOTIABLE (§2f/§2h, CLAUDE.md): this layer is READ-ONLY with respect to the
TARGET, always. A plain reader app defines only GET routes — no route acts on a
target — so the guarantee is structural, not a matter of discipline. It serves the
extracted records a run already produced — plus the §2h-safe projection of the
observed API surface (published spec/GraphQL whole, synthesized/correlation as
counts only) — never a raw local-only capture, and —
because an API response is a shared surface §2h names explicitly — record values
pass through the secret-redaction primitive on their way out (the local store may
hold raw; the boundary out is redacted). The non-negotiable explicitly permits
triggering a new read/observation run, so an opt-in ``recheck`` seam adds exactly
one non-GET route (``POST /map/recheck``) that re-runs a mapped URL's extraction —
a read of the target, never a change to it — and refreshes the local map. Every
answer carries the capture time and its age; v1 shows the age and never
*auto*-rechecks (§2f, §9 backlog) — a recheck only happens when a caller asks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from spoor.serving.store import MapEntry, MapStore
from spoor.serving.views import map_view

# A recheck seam: given a URL, re-run its read/observation and return the fresh
# entry, or None if the URL was never mapped. Injected only when recheck is
# enabled; a plain reader app leaves it unset and stays GET-only.
RecheckFn = Callable[[str], MapEntry | None]


def create_app(store: MapStore, recheck: RecheckFn | None = None) -> FastAPI:
    """Build the serving app over a given map store.

    A factory (not a module-level app) so the store is injectable — tests pass
    one backed by a temp cache, and the CLI passes the default. With ``recheck``
    unset the app is GET-only (read-only w.r.t. the target); passing a recheck
    function adds the opt-in ``POST /map/recheck`` route (§2f).
    """
    app = FastAPI(
        title="Spoor",
        description="Read-only serving of a captured map (ROADMAP.md §2f).",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/domains")
    def domains() -> dict[str, list[str]]:
        return {"domains": store.domains()}

    @app.get("/map")
    def get_map(
        url: str = Query(..., description="The mapped URL to look up."),
    ) -> dict[str, Any]:
        entry = store.get(url)
        if entry is None:
            # Never fabricate an answer for a URL that was never mapped.
            raise HTTPException(status_code=404, detail="url not mapped")
        # Shared with the MCP surface: one redaction-guarded view (§2f/§2h).
        return map_view(entry)

    if recheck is not None:

        @app.post("/map/recheck")
        def recheck_map(
            url: str = Query(..., description="The mapped URL to re-check."),
        ) -> dict[str, Any]:
            # The sole non-GET route, and read-only w.r.t. the target: it re-runs
            # the URL's read/observation and refreshes the local map (§2f).
            entry = recheck(url)
            if entry is None:
                # Never fabricate an answer for a URL that was never mapped.
                raise HTTPException(status_code=404, detail="url not mapped")
            return map_view(entry)

    return app
