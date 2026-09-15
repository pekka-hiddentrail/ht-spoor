"""Actionable-element discovery for exploration mode (ROADMAP.md §2e).

The third §2e slice, still pure logic. The explorer must decide what to try next on
a screen; this answers "what *can* be interacted with here?" without a new
mechanism, by reusing the §2c accessibility-tree signal. That snapshot (the CDP
`Accessibility.getFullAXTree` node list, as `AccessibilityCollector` captures it)
already labels every node with a generic ARIA role, so discovery is: keep the nodes
whose role is interactive and that aren't ignored, and read each one's role,
accessible name, backend DOM node id, and — when the driver enriched the node with
one — its destination hint (a link's target URL path, read from `href`; §2e slice 9b).

The accessible name is the label the safety gate (`safety.py`) classifies; the
backend node id is kept so the (later) explorer loop can locate the element to act
on it. This slice only discovers — driving actions is the explorer loop. Generic to
every target (§0): the interactive-role set is the same for all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Interactive ARIA roles — a node with one of these is something a user can act on.
# A maintainable, PR-extendable set (§2e), never a runtime config or site-specific.
ACTIONABLE_ROLES = frozenset(
    {
        "button",
        "link",
        "checkbox",
        "radio",
        "textbox",
        "searchbox",
        "combobox",
        "listbox",
        "option",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "tab",
        "switch",
        "slider",
        "spinbutton",
        "treeitem",
    }
)


@dataclass(frozen=True)
class ActionableElement:
    """One thing the explorer could interact with on a screen (§2e).

    `role` and `name` come straight from the accessibility node (the name is the
    label the safety gate classifies, and `role`+`name` are what the live driver
    re-locates the element by when it acts). `backend_node_id` is the CDP node
    handle *within the snapshot it was discovered in* — it does not survive a page
    reload, so it is kept for correlation/debugging rather than for clicking after a
    reset-and-replay; None when the node carried none.

    `destination` is a *hint* at where activating this element leads — the URL path
    of a link's target, read from its `href` before any click (§2e slice 9b) — or
    None when the element carries no static destination (a button, a JS-driven
    control, a non-navigational `href` like `javascript:`). It is only a hint: the
    real state reached is still whatever clicking produces, so the explorer clicks
    regardless. It lets the walk fire structural, shallow-destination links first
    (peel the site outward in priority order) and lets the map name a link's target
    even when the budget stops the run before it is clicked. None when the driver
    reports no destination, which every non-link element and every URL-less fake keep.
    """

    role: str
    name: str
    backend_node_id: int | None
    destination: str | None = None


def _ax_string(field: object) -> str:
    """Read a CDP AX value object (`{"value": ...}`) as a string, tolerantly."""
    if isinstance(field, Mapping):
        value = field.get("value", "")
        return str(value) if value is not None else ""
    return "" if field is None else str(field)


def _backend_node_id(node: Mapping[str, object]) -> int | None:
    raw = node.get("backendDOMNodeId")
    return raw if isinstance(raw, int) else None


def _destination(node: Mapping[str, object]) -> str | None:
    """The element's destination hint, if the driver enriched the node with one (9b).

    A plain string on the node under `destination` (the live driver injects the URL
    path of a link's `href`; a fake supplies it directly). Absent, empty, or non-string
    yields None — the pre-slice-9b shape every URL-less driver keeps.
    """
    raw = node.get("destination")
    return raw if isinstance(raw, str) and raw else None


def discover_actions(
    ax_nodes: Sequence[Mapping[str, object]],
) -> list[ActionableElement]:
    """Discover the actionable elements in an accessibility-tree node list (§2e).

    Keeps document order and every interactive occurrence — the explorer decides
    later what to do with each; deduplication is not this slice's job. Ignored
    nodes and non-interactive roles are dropped. Tolerant of missing fields: a node
    with no name yields an empty label, a node with no backend id yields None.
    """
    discovered: list[ActionableElement] = []
    for node in ax_nodes:
        if node.get("ignored") is True:
            continue
        role = _ax_string(node.get("role"))
        if role not in ACTIONABLE_ROLES:
            continue
        discovered.append(
            ActionableElement(
                role=role,
                name=_ax_string(node.get("name")),
                backend_node_id=_backend_node_id(node),
                destination=_destination(node),
            )
        )
    return discovered
