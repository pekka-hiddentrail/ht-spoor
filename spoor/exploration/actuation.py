"""Actuation: deciding whether a discovered element can be clicked (ROADMAP.md §2e).

Sub-slice 7a of the fifth §2e slice — the pure core of *robust actuation*. A live
diagnostic showed the explorer's skips on a real SPA were not overlay interception but
a **relocation** failure: `discover_actions` reads an element from the CDP accessibility
tree, while the old driver re-found it through Playwright's separate ARIA-name engine,
so a visible, uncovered element could match nothing and be skipped. The two engines
compute accessible names by different rules; that divergence was the bug.

This module removes the divergence and defines the actuation *verdict*. Relocation
reuses `discover_actions` itself (`find_target`), so the act-time match is computed by
the *same* function as discovery — the two cannot drift by construction. And the verdict
is a pure decision over what sits at the element's click point, taken by `classify`:

  * ACTUATE     — the click point resolves to the element (or a descendant); a real
                  click will land on it.
  * COVERED     — the point resolves to a *different* element on top; clicking the
                  coordinate would hit the wrong thing. This is the precise, generic
                  signal that a layer is in the way — the hand-off to layer recovery
                  (7c) — carrying what covers it, never a mute skip.
  * NOT LOCATED — no discovered node matches, so the element is genuinely gone.

The live half (the CDP relocation, scroll-into-view, coordinate click, and the
`elementFromPoint` verification that feed `classify` real values) lives in the driver
(`driver.py`). Nothing here is site-specific (§0): the match and the verdict are the
same for every target's every element.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from spoor.exploration.discovery import ActionableElement, discover_actions


class Verdict(Enum):
    """The three honest outcomes of trying to actuate a discovered element."""

    ACTUATE = "actuate"
    COVERED = "covered"
    NOT_LOCATED = "not located"


@dataclass(frozen=True)
class CoveringElement:
    """What sits on top of a covered element, so recovery (7c) can deal with it.

    `role` and `text` describe the intercepting element for a human-readable flag and
    for recovery to decide how to interact with the layer — not a bare "could not
    click". They are a best-effort description of the on-top element (its ARIA role or
    tag, and its label or text), not a guarantee of a matching accessibility node.
    """

    role: str
    text: str


@dataclass(frozen=True)
class ActuationVerdict:
    """A verdict plus, when COVERED, what is covering the element."""

    verdict: Verdict
    covering: CoveringElement | None = None


def classify(
    *,
    located: bool,
    point_hits_target: bool,
    covering: CoveringElement | None,
) -> ActuationVerdict:
    """Decide the actuation verdict from what was observed at the click point.

    Pure and total: `located` is whether the discovered node was found at all;
    `point_hits_target` is whether the click point resolves to the element or a
    descendant of it; `covering` is what sits on top when it does not. The live driver
    computes these three against a real page and calls this so the verdict has one
    definition, shared by the pure tests and the browser path.
    """
    if not located:
        return ActuationVerdict(Verdict.NOT_LOCATED)
    if point_hits_target:
        return ActuationVerdict(Verdict.ACTUATE)
    return ActuationVerdict(Verdict.COVERED, covering)


def find_target(
    ax_nodes: Sequence[Mapping[str, object]],
    role: str,
    name: str,
) -> ActionableElement | None:
    """Relocate a discovered action in a *current* accessibility-tree snapshot.

    Runs `discover_actions` — the exact function discovery uses — over the live nodes
    and returns the first element whose role and name match, in document order. Sharing
    the one function is deliberate: it is why the act-time match cannot diverge from the
    discovery-time match (the original skip bug). The returned element carries the fresh
    `backend_node_id` from *this* snapshot, which the driver resolves to a live DOM node
    to click. Returns None when nothing matches — the element is genuinely gone.
    """
    for action in discover_actions(ax_nodes):
        if action.role == role and action.name == name:
            return action
    return None
