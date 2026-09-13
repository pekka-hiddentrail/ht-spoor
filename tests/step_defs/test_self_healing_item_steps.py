"""Step definitions for features/self_healing_items.feature (ROADMAP.md §2, §2d).

The item-mode companion to test_self_healing_run_steps.py. Drives the dispatcher
end to end through an in-memory httpx MockTransport (tier 1, no browser, no
network) against a *listing* config — an `item` selector with per-row fields —
with the persistent per-domain fingerprint cache pointed at a per-scenario temp
directory (`storage.CACHE_ROOT` monkeypatched) so a first run's per-row field
fingerprints survive into a second run.

The served page body is mutable: a scenario records the rows' fingerprints on the
original markup, then swaps in changed markup (a field class renamed across every
row, optionally with one row dropping the element) before the next run, so a
field's selector genuinely breaks inside the rows and tier 3 heals it per row.
Assertions are against the extracted records and the `RunSummary`'s heal counts,
never any matched text (§2h).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary
from spoor.security import storage

scenarios("self_healing_items.feature")

_TARGET = "http://localhost:8000/list.html"
_PATH = "/list.html"

# Three structurally-identical rows differing only in text. `price_class` lets a
# scenario rename the price field's class across every row; `drop_price` drops the
# price element from the last row so it genuinely lacks the field.
_NAMES = ("Alpha", "Beta", "Gamma")
_PRICES = ("10", "20", "30")


def _page(*, price_class: str = "price", drop_price_in_last: bool = False) -> str:
    rows = []
    for i, (name, price) in enumerate(zip(_NAMES, _PRICES, strict=True)):
        price_cell = (
            ""
            if (drop_price_in_last and i == len(_NAMES) - 1)
            else f'<span class="{price_class}">{price}</span>'
        )
        rows.append(
            f'<li class="product-card"><a class="name">{name}</a>{price_cell}</li>'
        )
    return "<html><body><ul>" + "".join(rows) + "</ul></body></html>"


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Per-scenario state, with the fingerprint cache under a fresh temp root."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    return {"body": _page()}


def _run(context: dict[str, Any]) -> None:
    body = context["body"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _PATH:
            return httpx.Response(200, text=body)
        return httpx.Response(404, text="not found")

    cfg = load_config(context["config_text"])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract.run_report(cfg, client=client, sleep=lambda _: None)
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


# --- Given ---------------------------------------------------------------


@given(
    parsers.parse(
        'a listing config with item "{item}" extracting '
        '"{f1}" from "{s1}" and "{f2}" from "{s2}"'
    )
)
def listing_config(
    context: dict[str, Any], item: str, f1: str, s1: str, f2: str, s2: str
) -> None:
    context["config_text"] = (
        f"target: {_TARGET}\n"
        f"item: {item}\n"
        "fields:\n"
        f'  {f1}: {{ selector: "{s1}" }}\n'
        f'  {f2}: {{ selector: "{s2}" }}\n'
    )


@given("a first run has recorded the rows' field fingerprints")
def first_run_records(context: dict[str, Any]) -> None:
    context["body"] = _page()
    _run(context)
    # Invariant: the original run actually resolved (and fingerprinted) every price.
    assert all(rec["price"] is not None for rec in context["result"].records)
    assert len(context["result"].records) == len(_NAMES)


@given(parsers.parse('the rows do not match "{selector}"'))
def rows_do_not_match(context: dict[str, Any], selector: str) -> None:
    # No prior run: the price field never matched and was never fingerprinted.
    context["body"] = _page(price_class="cost")


# --- When ----------------------------------------------------------------


@when(
    parsers.parse(
        'the "{field}" field\'s class is renamed so "{selector}" '
        "matches nothing in any row"
    )
)
def rename_field_all_rows(context: dict[str, Any], field: str, selector: str) -> None:
    context["body"] = _page(price_class="cost")


@when(
    parsers.parse(
        'the "{field}" field\'s class is renamed and one row drops its '
        "{element} element"
    )
)
def rename_and_drop(context: dict[str, Any], field: str, element: str) -> None:
    context["body"] = _page(price_class="cost", drop_price_in_last=True)


@when("I run the config again")
@when("I run the config")
def run_config(context: dict[str, Any]) -> None:
    _run(context)


# --- Then ----------------------------------------------------------------


@then(parsers.parse('every row still has a "{name}" value'))
def every_row_has_value(context: dict[str, Any], name: str) -> None:
    records = context["result"].records
    assert records and all(rec[name] is not None for rec in records)


@then(
    parsers.parse('the rows that kept a {element} element still have a "{name}" value')
)
def kept_rows_have_value(context: dict[str, Any], element: str, name: str) -> None:
    # The last row dropped its element; every earlier row kept it.
    records = context["result"].records
    assert all(rec[name] is not None for rec in records[:-1])


@then(parsers.parse('the row missing its {element} element has a null "{name}"'))
def missing_row_is_null(context: dict[str, Any], element: str, name: str) -> None:
    assert context["result"].records[-1][name] is None


@then(parsers.parse('every row has a null "{name}"'))
def every_row_null(context: dict[str, Any], name: str) -> None:
    records = context["result"].records
    assert records and all(rec[name] is None for rec in records)


@then(parsers.parse("the run summary reports {count:d} confident heals"))
def summary_confident(context: dict[str, Any], count: int) -> None:
    assert context["summary"].heal_confident == count


@then(parsers.parse("the run summary reports {count:d} uncertain match"))
def summary_uncertain(context: dict[str, Any], count: int) -> None:
    assert context["summary"].heal_uncertain == count


@then("the run summary reports no heals")
def summary_no_heals(context: dict[str, Any]) -> None:
    summary = context["summary"]
    assert summary.heal_confident == 0
    assert summary.heal_uncertain == 0
