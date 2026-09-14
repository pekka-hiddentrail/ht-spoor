"""Interaction safety gate for exploration mode (ROADMAP.md §2e).

The safety foundation of exploration mode, built before anything that can fire an
action exists. It answers one question for every candidate action: may exploration
perform it against this target? Two inputs combine into that answer:

- the destructive-action classifier here — does the action's label/role read as
  delete/remove/buy/purchase/pay/confirm/send/submit-payment/log-out (the §2e
  list)? A maintainable, PR-extendable keyword set, never a fixed one;
- the sandbox registry (`spoor/security/sandbox.py`) — is the target one the
  operator controls?

NON-NEGOTIABLE (§2e/CLAUDE.md): a destructive action is permitted only inside a
sandbox. Against any real target it is ALWAYS skipped, and there is deliberately no
parameter that relaxes this — `evaluate_action` decides purely from the target and
the action. Non-destructive actions are permitted anywhere. The gate only *decides*
(and hands back a log-ready reason); emitting the skipped-log and actually driving
the action belong to the explorer loop, a later §2e slice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from spoor.security.sandbox import is_sandbox

# Substrings that mark an action as destructive/irreversible, matched
# case-insensitively on whole words in the action's label (and role). Maintained
# by PR (§2e) — extend this set, never a runtime config, to teach the gate a new
# risky verb. "log out" / "sign out" are matched as their joined forms too.
DESTRUCTIVE_KEYWORDS = frozenset(
    {
        "delete",
        "remove",
        "buy",
        "purchase",
        "pay",
        "confirm",
        "send",
        "submit payment",
        "log out",
        "logout",
        "sign out",
        "signout",
    }
)

# Word-boundary alternation over the keywords, longest first so multi-word phrases
# ("submit payment") win over their parts. Built once at import.
_KEYWORDS_BY_LEN = sorted(DESTRUCTIVE_KEYWORDS, key=len, reverse=True)
_DESTRUCTIVE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in _KEYWORDS_BY_LEN) + r")\b",
    re.IGNORECASE,
)


def is_destructive(label: str, role: str | None = None) -> bool:
    """Whether an action reads as destructive/irreversible (§2e).

    Matches a destructive keyword as a whole word in the action's visible label
    (and its accessibility role, if given). Conservative by design: an unmatched
    label is treated as safe, but the gate still only performs it — a false
    negative on a real site is bounded by the sandbox rule, which skips *all*
    matched-destructive actions there regardless.
    """
    haystack = label if role is None else f"{label} {role}"
    return _DESTRUCTIVE_RE.search(haystack) is not None


@dataclass(frozen=True)
class GateDecision:
    """The gate's verdict for one candidate action: perform it, or skip it."""

    allowed: bool
    reason: str

    @property
    def skipped(self) -> bool:
        """True when the action must be skipped (the complement of `allowed`)."""
        return not self.allowed


def evaluate_action(
    target: str,
    label: str,
    role: str | None = None,
    declared_sandbox: bool = False,
) -> GateDecision:
    """Decide whether exploration may perform an action against a target (§2e).

    A non-destructive action is always allowed. A destructive one is allowed only
    when the target is a sandbox (loopback host, or declared via `declared_sandbox`)
    and is otherwise skipped with a log-ready reason. This is the whole of the
    §2e non-negotiable: there is deliberately no parameter that permits a
    destructive action on a non-sandbox target.
    """
    if not is_destructive(label, role):
        return GateDecision(allowed=True, reason="non-destructive action")
    if is_sandbox(target, declared=declared_sandbox):
        return GateDecision(
            allowed=True, reason="destructive action permitted in sandbox"
        )
    return GateDecision(
        allowed=False,
        reason="skipped: destructive action not allowed outside a sandbox",
    )
