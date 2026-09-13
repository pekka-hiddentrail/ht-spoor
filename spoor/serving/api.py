"""Read-only REST API over the captured map (ROADMAP.md §2f).

The plain-API consumption mode from §2f: the same map the (future) MCP server
answers from, served over conventional HTTP GETs for scripts, dashboards, and CI
checks against a previously-mapped site.

NON-NEGOTIABLE (§2f/§2h, CLAUDE.md): this layer is READ-ONLY, always. It defines
only GET routes — no route mutates the store or acts on a target — so the
read-only guarantee is structural, not a matter of discipline. It serves the
extracted records a run already produced — plus the §2h-safe projection of the
observed API surface (published spec/GraphQL whole, synthesized/correlation as
counts only) — never a raw local-only capture, and —
because an API response is a shared surface §2h names explicitly — record values
pass through the secret-redaction primitive on their way out (the local store may
hold raw; the boundary out is redacted). Every answer carries the capture time
and its age; v1 shows the age and never auto-rechecks (§2f, §9 backlog).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query

from spoor.serving.store import MapStore
from spoor.serving.views import map_view


def create_app(store: MapStore) -> FastAPI:
    """Build the read-only serving app over a given map store.

    A factory (not a module-level app) so the store is injectable — tests pass
    one backed by a temp cache, and the CLI passes the default.
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

    return app
