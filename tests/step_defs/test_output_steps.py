"""Step definitions for features/output.feature (ROADMAP.md §2d).

The sink is content, not network: these scenarios drive the output module
directly against tmp files and read them back, so format and schema-validation
behavior is asserted deterministically.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core.config import load_config
from spoor.operational import output

scenarios("output.feature")

_CONFIG_TEXT = """
target: http://localhost:8000/x.html
fields:
  title: { selector: "h1" }
  price: { selector: ".price", type: number }
"""


@pytest.fixture
def context() -> dict[str, Any]:
    return {}


# --- Given ---------------------------------------------------------------


@given('a config with a "title" string field and a "price" number field')
def a_config(context: dict[str, Any]) -> None:
    context["config"] = load_config(_CONFIG_TEXT)


@given("two extracted records, the second missing its price")
def two_records(context: dict[str, Any]) -> None:
    context["records"] = [
        {"title": "Ceramic Mug", "price": 12.5},
        {"title": "Steel Flask", "price": None},
    ]


@given('an extra record carrying an undeclared "sku" field')
def extra_record(context: dict[str, Any]) -> None:
    context["records"].append({"title": "Rogue", "price": 1.0, "sku": "X-1"})


@given('a single record whose "title" carries a bearer token')
def secret_record(context: dict[str, Any]) -> None:
    # An obviously-fake token in a declared field; the price is present-but-null
    # so the record still satisfies the config schema.
    context["raw_token"] = "abcdef1234567890x"
    context["records"] = [
        {"title": f"Bearer {context['raw_token']}", "price": None}
    ]


# --- When ----------------------------------------------------------------


def _write(context: dict[str, Any], tmp_path: Path, name: str, fmt: str | None) -> None:
    path = tmp_path / name
    resolved = output.resolve_format(path, fmt)
    output.write_records(context["records"], context["config"], path, resolved)
    context["path"] = path
    context["format"] = resolved


@when(parsers.parse('I write the records to "{name}"'))
def write_inferred(context: dict[str, Any], tmp_path: Path, name: str) -> None:
    _write(context, tmp_path, name, None)


@when(parsers.parse('I write the records to "{name}" as "{fmt}"'))
def write_explicit(
    context: dict[str, Any], tmp_path: Path, name: str, fmt: str
) -> None:
    _write(context, tmp_path, name, fmt)


@when(parsers.parse('I try to write the records to "{name}"'))
def try_write(context: dict[str, Any], tmp_path: Path, name: str) -> None:
    try:
        _write(context, tmp_path, name, None)
        context["error"] = None
    except (ValueError, ValidationError) as exc:
        context["error"] = exc


@when(parsers.parse('I read the first written object\'s "{field}"'))
def read_first_field(context: dict[str, Any], field: str) -> None:
    data = json.loads(_read(context))
    context["value"] = data[0][field]


# --- Then ----------------------------------------------------------------


@then("it no longer contains the raw token")
def value_lacks_raw_token(context: dict[str, Any]) -> None:
    assert context["raw_token"] not in context["value"]


@then(parsers.parse('it equals "{value}"'))
def value_equals(context: dict[str, Any], value: str) -> None:
    assert context["value"] == value


def _read(context: dict[str, Any]) -> str:
    return context["path"].read_text(encoding="utf-8")


@then(parsers.parse('"{name}" holds a JSON array of {count:d} objects'))
def json_array(context: dict[str, Any], name: str, count: int) -> None:
    data = json.loads(_read(context))
    assert isinstance(data, list)
    assert len(data) == count
    assert all(isinstance(item, dict) for item in data)


@then(
    parsers.parse(
        'the first object has "{field}" of "{value}" and "price" of {price:g}'
    )
)
def first_object(
    context: dict[str, Any], field: str, value: str, price: float
) -> None:
    data = json.loads(_read(context))
    assert data[0][field] == value
    assert data[0]["price"] == price


@then(parsers.parse('the second object has a null "{field}"'))
def second_null(context: dict[str, Any], field: str) -> None:
    data = json.loads(_read(context))
    assert data[1][field] is None


@then(parsers.parse('"{name}" has {count:d} lines, each a standalone JSON object'))
def jsonl_lines(context: dict[str, Any], name: str, count: int) -> None:
    lines = _read(context).splitlines()
    assert len(lines) == count
    for line in lines:
        assert isinstance(json.loads(line), dict)


@then(parsers.parse('the CSV header row is "{header}"'))
def csv_header(context: dict[str, Any], header: str) -> None:
    rows = list(csv.reader(_read(context).splitlines()))
    assert rows[0] == header.split(",")


@then(parsers.parse("the CSV has {count:d} data rows"))
def csv_row_count(context: dict[str, Any], count: int) -> None:
    rows = list(csv.reader(_read(context).splitlines()))
    assert len(rows) - 1 == count


@then("the missing price is written as an empty cell")
def csv_empty_cell(context: dict[str, Any]) -> None:
    rows = list(csv.DictReader(_read(context).splitlines()))
    assert rows[1]["price"] == ""


@then(parsers.parse('the output was written as "{fmt}"'))
def written_as(context: dict[str, Any], fmt: str) -> None:
    assert context["format"] == fmt


@then(parsers.parse("it fails before writing with an error naming the format"))
def fails_naming_format(context: dict[str, Any]) -> None:
    assert isinstance(context["error"], ValueError)
    assert "format" in str(context["error"])
    assert not context.get("path", Path("nonexistent")).exists()


@then(parsers.parse('it fails before writing with an error naming "{token}"'))
def fails_naming_token(context: dict[str, Any], token: str) -> None:
    assert context["error"] is not None
    assert token in str(context["error"])
    assert not context.get("path", Path("nonexistent")).exists()
