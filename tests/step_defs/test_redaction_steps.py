"""Step definitions for features/redaction.feature (ROADMAP.md §2h, §9).

The redaction pipeline is a pure text primitive, so these steps need no browser
and no network — they feed strings through `redact` and pin the shared-output
contract: known secret shapes are scrubbed, surrounding structure is kept, and a
string with no secret is returned untouched.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import parsers, scenarios, then, when

from spoor.security.redaction import redact

scenarios("redaction.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {}


# --- When ----------------------------------------------------------------


@when(parsers.parse('I redact "{text}"'))
def redact_text(context: dict[str, Any], text: str) -> None:
    context["input"] = text
    context["result"] = redact(text)


@when(parsers.parse('I redact "{text}" twice'))
def redact_text_twice(context: dict[str, Any], text: str) -> None:
    once = redact(text)
    context["first"] = once
    context["second"] = redact(once)


@when("I redact the text:")
def redact_docstring(context: dict[str, Any], docstring: str) -> None:
    # Multi-line secrets (e.g. a PEM key block) can't ride the inline
    # `I redact "..."` step, so this variant takes a Gherkin docstring.
    context["input"] = docstring
    context["result"] = redact(docstring)


# --- Then ----------------------------------------------------------------


@then(parsers.parse('the result is "{expected}"'))
def result_is(context: dict[str, Any], expected: str) -> None:
    assert context["result"] == expected


@then("the result is unchanged")
def result_unchanged(context: dict[str, Any]) -> None:
    assert context["result"] == context["input"]


@then(parsers.parse('the result no longer contains "{substring}"'))
def result_lacks_substring(context: dict[str, Any], substring: str) -> None:
    assert substring not in context["result"]


@then("the two results are identical")
def results_identical(context: dict[str, Any]) -> None:
    assert context["first"] == context["second"]
