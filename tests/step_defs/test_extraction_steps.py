"""Step definitions for features/extraction.feature (ROADMAP.md §2a, §4a).

BDD-first: these bind every step in the feature so the contract is executable,
but the bodies are pending until the Phase 1 tier-1 implementation lands. A
pending step raises NotImplementedError, so the suite stays honestly red until
the capability is actually built — never falsely green.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

# Resolved against bdd_features_base_dir = "features" (see pyproject.toml).
scenarios("extraction.feature")

_PENDING = "pending Phase 1 tier-1 extraction implementation (ROADMAP.md §2a)"


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('a fixture page at "{url}"'))
def fixture_page(context: dict[str, Any], url: str) -> None:
    raise NotImplementedError(_PENDING)


@given("a config:", target_fixture="config")
def config_from_docstring(context: dict[str, Any], docstring: str) -> str:
    raise NotImplementedError(_PENDING)


@given(parsers.parse('a fixture site of {count:d} pages linked by "{selector}"'))
def fixture_paginated_site(
    context: dict[str, Any], count: int, selector: str
) -> None:
    raise NotImplementedError(_PENDING)


@given("a fixture page that loads more items on scroll")
def fixture_infinite_scroll(context: dict[str, Any]) -> None:
    raise NotImplementedError(_PENDING)


@given(
    'a config that extracts "title" from the fixture page',
    target_fixture="config",
)
def config_title_only(context: dict[str, Any]) -> str:
    raise NotImplementedError(_PENDING)


@given(
    'a config whose "title" selector is a plain CSS selector',
    target_fixture="config",
)
def config_plain_css(context: dict[str, Any]) -> str:
    raise NotImplementedError(_PENDING)


# --- When ----------------------------------------------------------------


@when("I run the config")
def run_config(context: dict[str, Any]) -> None:
    raise NotImplementedError(_PENDING)


@when(parsers.parse('I run the config with output path "{path}"'))
def run_config_with_output(context: dict[str, Any], path: str) -> None:
    raise NotImplementedError(_PENDING)


# --- Then ----------------------------------------------------------------


@then("the output contains one item")
def output_has_one_item(context: dict[str, Any]) -> None:
    raise NotImplementedError(_PENDING)


@then(parsers.parse('the item field "{field}" equals "{value}"'))
def item_field_equals(context: dict[str, Any], field: str, value: str) -> None:
    raise NotImplementedError(_PENDING)


@then(parsers.parse("the item field \"{field}\" is the number {value:g}"))
def item_field_is_number(
    context: dict[str, Any], field: str, value: float
) -> None:
    raise NotImplementedError(_PENDING)


@then(parsers.parse('the item field "{field}" is null'))
def item_field_is_null(context: dict[str, Any], field: str) -> None:
    raise NotImplementedError(_PENDING)


@then(parsers.parse("items are extracted from all {count:d} pages"))
def items_from_all_pages(context: dict[str, Any], count: int) -> None:
    raise NotImplementedError(_PENDING)


@then(parsers.parse('the run stops after the page with no "{selector}" link'))
def run_stops_at_last_page(context: dict[str, Any], selector: str) -> None:
    raise NotImplementedError(_PENDING)


@then("more than one screen of items is extracted")
def more_than_one_screen(context: dict[str, Any]) -> None:
    raise NotImplementedError(_PENDING)


@then(parsers.parse('a file "{path}" exists'))
def output_file_exists(context: dict[str, Any], path: str) -> None:
    raise NotImplementedError(_PENDING)


@then("it contains the extracted items as structured data")
def output_file_is_structured(context: dict[str, Any]) -> None:
    raise NotImplementedError(_PENDING)


@then("the config declares no tier-2, tier-3, or tier-3.5 logic")
def config_has_no_tier_logic(context: dict[str, Any]) -> None:
    raise NotImplementedError(_PENDING)


@then("escalation across tiers is handled by the dispatcher, not the config")
def escalation_is_dispatcher_side(context: dict[str, Any]) -> None:
    raise NotImplementedError(_PENDING)


@then("the run fails before fetching anything")
def run_fails_before_fetch(context: dict[str, Any]) -> None:
    raise NotImplementedError(_PENDING)


@then(parsers.parse('the error message names the missing "{field}" field'))
def error_names_missing_field(context: dict[str, Any], field: str) -> None:
    raise NotImplementedError(_PENDING)


@then(parsers.parse('the run fails with an error naming the unknown option "{option}"'))
def error_names_unknown_option(context: dict[str, Any], option: str) -> None:
    raise NotImplementedError(_PENDING)
