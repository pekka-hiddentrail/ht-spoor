"""Step definitions for features/exploration_safety.feature (ROADMAP.md §2e).

The exploration safety gate is pure logic — no browser — so these steps drive it
directly: build a target (optionally declared a sandbox), classify actions, and
ask the gate for its verdict. They pin the §2e non-negotiable: destructive actions
are allowed only inside a sandbox, and nothing relaxes the skip on a real target.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.safety import GateDecision, evaluate_action, is_destructive
from spoor.security.sandbox import is_sandbox

scenarios("exploration_safety.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {"declared": False}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('an exploration target "{url}"'))
def exploration_target(context: dict[str, Any], url: str) -> None:
    context["target"] = url
    context["declared"] = False


@given(parsers.parse('an exploration target "{url}" declared as a sandbox'))
def declared_sandbox_target(context: dict[str, Any], url: str) -> None:
    context["target"] = url
    context["declared"] = True


# --- When ----------------------------------------------------------------


@when(parsers.parse('the interaction gate considers an action labeled "{label}"'))
def gate_considers(context: dict[str, Any], label: str) -> None:
    context["decision"] = evaluate_action(
        context["target"], label, declared_sandbox=context["declared"]
    )


# --- Then ----------------------------------------------------------------


@then("the target is recognized as a sandbox")
def target_is_sandbox(context: dict[str, Any]) -> None:
    assert is_sandbox(context["target"], declared=context["declared"]) is True


@then("the target is not recognized as a sandbox")
def target_is_not_sandbox(context: dict[str, Any]) -> None:
    assert is_sandbox(context["target"], declared=context["declared"]) is False


@then(parsers.parse('an action labeled "{label}" is {classification}'))
def action_classification(
    context: dict[str, Any], label: str, classification: str
) -> None:
    expected_destructive = classification == "destructive"
    assert classification in {"destructive", "safe"}, classification
    assert is_destructive(label) is expected_destructive


@then("the action is allowed")
def action_allowed(context: dict[str, Any]) -> None:
    decision: GateDecision = context["decision"]
    assert decision.allowed is True and decision.skipped is False


@then("the action is skipped as unsafe outside a sandbox")
def action_skipped(context: dict[str, Any]) -> None:
    decision: GateDecision = context["decision"]
    assert decision.skipped is True and decision.allowed is False
    assert "sandbox" in decision.reason.lower()


@then(
    "the interaction gate exposes no option to permit destructive actions "
    "outside a sandbox"
)
def gate_has_no_bypass(context: dict[str, Any]) -> None:
    # Structural proof of the §2e non-negotiable: the gate decides purely from the
    # target and the action. Its parameters are exactly these — any new knob (a
    # force/override/allow-destructive flag) would break this and demand review.
    params = set(inspect.signature(evaluate_action).parameters)
    assert params == {"target", "label", "role", "declared_sandbox"}, params
