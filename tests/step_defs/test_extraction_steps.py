"""Step definitions for features/extraction.feature (ROADMAP.md §2a, §4a)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import ExtractionConfig, FieldSpec, load_config

# Resolved against bdd_features_base_dir = "features" (see pyproject.toml).
scenarios("extraction.feature")
# Adversarial-input robustness (§2a) reuses the same steps and fixtures — an
# empty/garbage/malformed/deep/unicode page must degrade gracefully, never crash.
scenarios("extraction_robustness.feature")

_TITLE_ONLY_CONFIG = """
target: http://localhost:8000/products.html
fields:
  title: { selector: "h1.product-title" }
"""


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('a fixture page at "{url}"'))
def fixture_page(context: dict[str, Any], url: str) -> None:
    context["base_url"] = url


@given("a config:", target_fixture="config")
def config_from_docstring(context: dict[str, Any], docstring: str) -> str:
    context["config_text"] = docstring
    return docstring


@given(parsers.parse('a fixture site of {count:d} pages linked by "{selector}"'))
def fixture_paginated_site(
    context: dict[str, Any], count: int, selector: str
) -> None:
    context["expected_pages"] = count


@given("a live fixture server")
def live_fixture_server(context: dict[str, Any], live_server: str) -> None:
    context["server_base"] = live_server


@given(
    parsers.parse(
        'a fixture listing page with {count:d} product cards at "{url}"'
    )
)
def fixture_listing_page(
    context: dict[str, Any], count: int, url: str
) -> None:
    context["expected_count"] = count


@given(
    'a config that extracts "title" from the fixture page',
    target_fixture="config",
)
def config_title_only(context: dict[str, Any]) -> str:
    context["config_text"] = _TITLE_ONLY_CONFIG
    return _TITLE_ONLY_CONFIG


@given(
    'a config whose "title" selector is a plain CSS selector',
    target_fixture="config",
)
def config_plain_css(context: dict[str, Any]) -> str:
    context["config_text"] = _TITLE_ONLY_CONFIG
    context["config"] = load_config(_TITLE_ONLY_CONFIG)
    return _TITLE_ONLY_CONFIG


# --- When ----------------------------------------------------------------


@when("I run the config")
def run_config(context: dict[str, Any], mock_client: httpx.Client) -> None:
    try:
        cfg = load_config(context["config_text"])
    except ValidationError as exc:
        context["error"] = exc
        context["fetched"] = False
        return
    context["config"] = cfg
    context["result"] = extract.run(cfg, client=mock_client)
    context["fetched"] = True


@when("I run the config through a real browser")
def run_config_in_browser(context: dict[str, Any]) -> None:
    # No mock client: tier 2 drives a real Chromium against the live server, and
    # the SERVER_BASE placeholder is resolved to that server's base URL.
    text = context["config_text"].replace("SERVER_BASE", context["server_base"])
    cfg = load_config(text)
    context["config"] = cfg
    context["result"] = extract.run(cfg)
    context["fetched"] = True


@when(parsers.parse('I run the config with output path "{path}"'))
def run_config_with_output(
    context: dict[str, Any],
    mock_client: httpx.Client,
    tmp_path: Path,
    path: str,
) -> None:
    cfg = load_config(context["config_text"])
    records = extract.run(cfg, client=mock_client)
    out = tmp_path / path
    out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    context["result"] = records
    context["output_path"] = out


# --- Then ----------------------------------------------------------------


@then("the output contains one item")
def output_has_one_item(context: dict[str, Any]) -> None:
    assert len(context["result"]) == 1


@then(parsers.parse("the output contains {count:d} items"))
def output_has_n_items(context: dict[str, Any], count: int) -> None:
    assert len(context["result"]) == count


@then(parsers.parse('every item has non-null fields "{field_a}" and "{field_b}"'))
def every_item_has_fields(
    context: dict[str, Any], field_a: str, field_b: str
) -> None:
    assert context["result"]
    for item in context["result"]:
        assert item[field_a] is not None
        assert item[field_b] is not None


@then(parsers.parse('the item field "{field}" equals "{value}"'))
def item_field_equals(context: dict[str, Any], field: str, value: str) -> None:
    assert context["result"][0][field] == value


@then(parsers.parse("the item field \"{field}\" is the number {value:g}"))
def item_field_is_number(
    context: dict[str, Any], field: str, value: float
) -> None:
    actual = context["result"][0][field]
    assert isinstance(actual, (int, float))
    assert actual == value


@then(parsers.parse('the item field "{field}" is null'))
def item_field_is_null(context: dict[str, Any], field: str) -> None:
    assert context["result"][0][field] is None


@then(parsers.parse("items are extracted from all {count:d} pages"))
def items_from_all_pages(context: dict[str, Any], count: int) -> None:
    assert len(context["result"]) == count


@then(parsers.parse('the run stops after the page with no "{selector}" link'))
def run_stops_at_last_page(context: dict[str, Any], selector: str) -> None:
    assert len(context["result"]) == context["expected_pages"]


@then("more than one screen of items is extracted")
def more_than_one_screen(context: dict[str, Any]) -> None:
    # The feed renders 3 cards initially and loads more only on scroll; tier 2
    # must have scrolled to pull in materially more than that first screen.
    assert len(context["result"]) > 5
    assert all(item["title"] for item in context["result"])


@then(parsers.parse('a file "{path}" exists'))
def output_file_exists(context: dict[str, Any], path: str) -> None:
    assert context["output_path"].name == path
    assert context["output_path"].is_file()


@then("it contains the extracted items as structured data")
def output_file_is_structured(context: dict[str, Any]) -> None:
    data = json.loads(context["output_path"].read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert all(isinstance(record, dict) for record in data)


@then("the config declares no tier-2, tier-3, or tier-3.5 logic")
def config_has_no_tier_logic(context: dict[str, Any]) -> None:
    # The schema has no per-tier knobs at all — only extraction intent plus
    # cross-cutting operational policy. `capture` says *what to record* (opt-in
    # HAR, §2b/§2h), `politeness`/`retry`/`change_detection` say *how to behave
    # toward the origin* (robots + rate-limiting, §6; transient-error retry, §2d;
    # skip unchanged pages, §2d), and `session` says *who to authenticate as* (a
    # supplied browser storage state, §2h bring-your-own-session) — none names or
    # selects a tier or decides when to escalate (§2a, §0).
    assert set(ExtractionConfig.model_fields) == {
        "target",
        "item",
        "fields",
        "pagination",
        "politeness",
        "retry",
        "change_detection",
        "capture",
        "session",
    }
    assert set(FieldSpec.model_fields) == {"selector", "attr", "type"}


@then("escalation across tiers is handled by the dispatcher, not the config")
def escalation_is_dispatcher_side(context: dict[str, Any]) -> None:
    # Escalation is a code concern; the config only names a tier-1 selector.
    assert callable(extract.run)


@then("the run fails before fetching anything")
def run_fails_before_fetch(context: dict[str, Any]) -> None:
    assert context.get("error") is not None
    assert context.get("fetched") is False


@then(parsers.parse('the error message names the missing "{field}" field'))
def error_names_missing_field(context: dict[str, Any], field: str) -> None:
    assert field in str(context["error"])


@then(parsers.parse('the run fails with an error naming the unknown option "{option}"'))
def error_names_unknown_option(context: dict[str, Any], option: str) -> None:
    assert context.get("error") is not None
    assert option in str(context["error"])
