"""Shared builders for the serving step definitions (ROADMAP.md §2f).

The REST (`serving.feature`) and MCP (`serving_mcp.feature`) surfaces answer from
the *same* store with the *same* view, so their scenarios exercise the same shapes.
This holds the one non-trivial fixture they share — a small exploration graph with a
secret planted in a captured signal — so both step files build it identically and
neither drifts. Not a step module itself: it defines no `@given/@when/@then`.
"""

from __future__ import annotations

from spoor.exploration.capture import StateSignals, TransitionSignals
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.graph import ExplorationGraph

# A bearer token planted in a captured console signal; the served exploration graph
# must redact it (the raw token must never appear in a response) exactly as it would
# in an extracted record (§2h).
# A fabricated token, not a real secret — only its *shape* matters (it must match
# the bearer-credential pattern so redaction fires on it).
EXPLORE_SECRET = "abcdef1234567890x"


def explored_graph() -> ExplorationGraph:
    """A two-state graph: one fired transition (carrying the secret it "changed")
    and one destructive action the safety gate skipped — enough to pin the projected
    counts, an action label, and redaction."""
    graph = ExplorationGraph()
    open_menu = ActionableElement(role="button", name="Open menu", backend_node_id=1)
    delete = ActionableElement(role="button", name="Delete account", backend_node_id=2)
    graph.add_state("state-a", [open_menu, delete], StateSignals(ax_node_count=5))
    graph.add_state("state-b", [], StateSignals(ax_node_count=9))
    graph.add_transition(
        "state-a",
        open_menu,
        "state-b",
        TransitionSignals(
            ax_node_delta=4,
            console_added=(f"auth header Bearer {EXPLORE_SECRET}",),
            storage_added=("cartId",),
            storage_removed=(),
            network_added=(),
            screenshot_changed=True,
        ),
    )
    graph.record_skip(
        "state-a", delete, "destructive action skipped outside a sandbox"
    )
    return graph
