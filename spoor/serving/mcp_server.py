"""Read-only MCP server over the captured map (ROADMAP.md §2f).

The second §2f consumption mode, beside the REST API (`api.py`): an MCP server so
an agent can consult what Spoor already mapped as a tool, without re-crawling. It
sits over the exact same `MapStore` and answers with the exact same
redaction-guarded view (`views.map_view`) as the REST surface.

NON-NEGOTIABLE (§2f/§2h, CLAUDE.md): this layer is READ-ONLY, always. It exposes
only tools that read the captured map — never a tool that changes a target or the
stored map. Every tool is registered with the MCP read-only / non-destructive
annotations, and `serving_mcp.feature` pins the guarantee with a scenario
asserting the exposed tool set is exactly the read-only allowlist and each tool is
marked read-only and non-destructive. Answers carry the capture time and its age;
v1 never auto-rechecks (§2f, §9 backlog).

`mcp` is an optional dependency (the `serve` extra); this module is imported only
by the `spoor serve-mcp` command and the serving tests, never by the core engine.
"""

from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from spoor.serving.store import MapStore
from spoor.serving.views import map_view

# Every tool this server exposes reads the map and nothing else: read-only, with
# no destructive effect, idempotent, and closed to the map it was given.
_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def create_mcp_server(store: MapStore) -> MCPServer:
    """Build the read-only MCP server over a given map store.

    A factory (not a module-level server) so the store is injectable — tests pass
    one backed by a temp cache, and the CLI passes the default.
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
            raise ValueError(f"URL not mapped: {url}")
        return map_view(entry)

    return server
