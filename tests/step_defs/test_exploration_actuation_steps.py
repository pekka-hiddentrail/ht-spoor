"""Step definitions for features/exploration_actuation.feature (ROADMAP.md §2e, 7a).

The pure actuation *verdict* is exercised with no browser: each scenario describes what
sits at a discovered element's click point, and the steps translate that into the three
observations `classify` decides over — whether the node was located, whether the click
point lands on it, and what covers it when it does not — then assert the verdict. This
is the one definition of the verdict the live driver also calls, so pinning it here
pins the browser path's decision too.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.actuation import CoveringElement, Verdict, classify

scenarios("exploration_actuation.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


@given(parsers.parse('a target element "{role}" named "{name}"'))
def target_element(context: dict[str, Any], role: str, name: str) -> None:
    context["role"] = role
    context["name"] = name


@when(parsers.parse('the element at its click point is "{observed}"'))
def click_point_is(context: dict[str, Any], observed: str) -> None:
    # Translate the plain-language observation into the three facts `classify` decides
    # over. A "different element on top" is covered by an unnamed layer here; the
    # covered-with-details scenario below supplies a described one.
    if observed == "nothing — no matching node":
        context["verdict"] = classify(
            located=False, point_hits_target=False, covering=None
        )
    elif observed in ("the target itself", "a descendant of the target"):
        context["verdict"] = classify(
            located=True, point_hits_target=True, covering=None
        )
    elif observed == "a different element on top":
        context["verdict"] = classify(
            located=True,
            point_hits_target=False,
            covering=CoveringElement("generic", ""),
        )
    else:
        raise AssertionError(f"unrecognised observation: {observed!r}")


@when(parsers.parse('the element at its click point is a "{role}" reading "{text}"'))
def click_point_is_named(context: dict[str, Any], role: str, text: str) -> None:
    context["verdict"] = classify(
        located=True,
        point_hits_target=False,
        covering=CoveringElement(role, text),
    )


@then(parsers.parse('the actuation verdict is "{verdict}"'))
def verdict_is(context: dict[str, Any], verdict: str) -> None:
    assert context["verdict"].verdict is Verdict(verdict)


@then(parsers.parse('the covering element is reported as a "{role}" reading "{text}"'))
def covering_is(context: dict[str, Any], role: str, text: str) -> None:
    covering = context["verdict"].covering
    assert covering == CoveringElement(role, text), covering
