"""Serving the map: MCP server & REST API (ROADMAP.md §2f).

Thin serving layer over data the rest of the stack already produces.

NON-NEGOTIABLE (§2f/§2h / CLAUDE.md): read-only, always. It may answer
questions about a captured map and trigger new read/observation runs; it must
never expose a tool that causes a destructive or state-changing action on a
target.
"""
