"""Read-only MCP server over the captured map (ROADMAP.md §2f).

The second §2f consumption mode, beside the REST API (`api.py`): an MCP server so
an agent can consult what Spoor already mapped as a tool, without re-crawling. It
sits over the exact same `MapStore` and answers with the exact same
redaction-guarded view (`views.map_view`) as the REST surface.

NON-NEGOTIABLE (§2f/§2h, CLAUDE.md): this layer is READ-ONLY with respect to the
TARGET, always. It never exposes a tool that changes a target. A plain server
exposes only tools that read the captured map, each marked read-only and
non-destructive. The non-negotiable explicitly permits triggering a new
read/observation run, so an opt-in `recheck` seam adds one more tool
(`recheck_map`) that re-runs a mapped URL's extraction — a read of the target,
never a change to it — and refreshes the local map. That tool is honestly
annotated NON-read-only (it fetches and writes the local map) but stays
NON-destructive; no tool on this server is ever destructive to a target.
`serving_mcp.feature` pins both shapes. Answers carry the capture time and its
age; v1 never *auto*-rechecks (§2f, §9 backlog) — a recheck only happens when a
caller asks for it.

`mcp` is an optional dependency (the `serve` extra); this module is imported only
by the `spoor serve-mcp` command and the serving tests, never by the core engine.
"""

from __future__ import annotations

from collections.abc import Callable

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from spoor.serving.store import MapEntry, MapStore
from spoor.serving.views import map_view

# A recheck seam: given a URL, re-run its read/observation and return the fresh
# entry, or None if the URL was never mapped. Injected only when recheck is
# enabled; a plain reader server leaves it unset and stays read-only.
RecheckFn = Callable[[str], MapEntry | None]

# Every read tool reads the map and nothing else: read-only, with no destructive
# effect, idempotent, and closed to the map it was given.
_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# The recheck tool is honestly NOT read-only — it fetches the target and rewrites
# the local map — and not idempotent, but it is still NON-destructive: it observes
# the target, never changes it (§2f). open_world because it reaches out.
_RECHECK = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)


def create_mcp_server(
    store: MapStore, recheck: RecheckFn | None = None
) -> MCPServer:
    """Build the MCP server over a given map store.

    A factory (not a module-level server) so the store is injectable — tests pass
    one backed by a temp cache, and the CLI passes the default. With ``recheck``
    unset the server is read-only w.r.t. the target (read tools only); passing a
    recheck function adds the opt-in ``recheck_map`` tool (§2f).
    """
    server: MCPServer = MCPServer(
        name="spoor",
        instructions=(
            "Read-only access to the map Spoor already captured. Answers carry "
            "how long ago each entry was captured and never re-fetch a target."
        ),
    )

    @server.tool(annotations=_READ_ONLY)
    def list_mapped_domains() -> dict[str, object]:
        """List the domains Spoor has already mapped."""
        return {"domains": store.domains()}

    @server.tool(annotations=_READ_ONLY)
    def get_map(url: str) -> dict[str, object]:
        """Return a mapped URL's extracted records and observed API surface.

        Includes how long ago the entry was captured. Read-only: it never
        re-fetches the target. A URL that was never mapped is an error, not a
        fabricated answer.
        """
        entry = store.get(url)
        if entry is None:
            raise ToolError(f"URL not mapped: {url}")
        return map_view(entry)

    if recheck is not None:

        @server.tool(annotations=_RECHECK)
        def recheck_map(url: str) -> dict[str, object]:
            """Re-run a mapped URL's read/observation and return the fresh result.

            Fetches the target again (a read, never a change to it) and refreshes
            the local map, resetting the capture age. A URL that was never mapped
            is an error, not a fabricated answer.
            """
            entry = recheck(url)
            if entry is None:
                raise ToolError(f"URL not mapped: {url}")
            return map_view(entry)

    return server
