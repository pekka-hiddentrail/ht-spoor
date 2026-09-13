"""Step definitions for features/self_healing_container.feature (§2, §2d).

The row-*container* companion to test_self_healing_item_steps.py. Drives the
dispatcher through an in-memory httpx MockTransport against a listing config, with
the persistent per-domain fingerprint cache under a per-scenario temp directory
(`storage.CACHE_ROOT` monkeypatched) so a first run's container fingerprint
survives into a second run.

The dispatcher is pinned to **tier 1 only** here: a container-heal refusal is a
deliberate zero-record result, which would otherwise escalate to the browser tier
(§2 zero-records trigger) — irrelevant to what these scenarios assert and unable to
reach the MockTransport. Pinning tier 1 keeps the refusal observable in place.

The served page is mutable and swapped between runs to model a container redesign:
the row container's class is renamed so the `item` selector matches nothing, while
the rows themselves survive (scenario 1), a second identical listing is present so
two groups match (scenario 2), or the listing collapses to a lone element
(scenario 3). Assertions are against the extracted records and the `RunSummary`'s
heal counts, never any matched text (§2h).
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

scenarios("self_healing_container.feature")

_TARGET = "http://localhost:8000/list.html"
_PATH = "/list.html"

_MAIN_ROWS = (("Alpha", "10"), ("Beta", "20"), ("Gamma", "30"))
_RECOMMENDED_ROWS = (("Delta", "40"), ("Epsilon", "50"))
# A nav whose links are structurally unlike a product row (bare <a>, no price
# span), so it never forms a confident row group — only the products can.
_NAV = '<nav><a class="menu" href="#">Home</a><a class="menu" href="#">About</a></nav>'


def _row(name: str, price: str, *, li_class: str = "card") -> str:
    return (
        f'<li class="{li_class}">'
        f'<a class="name">{name}</a><span class="price">{price}</span>'
        "</li>"
    )


def _listing(ul_class: str, rows: tuple[tuple[str, str], ...]) -> str:
    cells = "".join(_row(name, price) for name, price in rows)
    return f'<ul class="{ul_class}">{cells}</ul>'


def _page(*sections: str) -> str:
    return "<html><body>" + "".join(sections) + "</body></html>"


# Original: the product listing the config's `item` selects, plus an unrelated nav.
_ORIGINAL = _page(_NAV, _listing("products", _MAIN_ROWS))
# Original with a second, structurally-identical listing also on the page (only the
# `ul.products` one is selected on the first run).
_ORIGINAL_TWO_LISTINGS = _page(
    _NAV, _listing("products", _MAIN_ROWS), _listing("recommended", _RECOMMENDED_ROWS)
)
# Redesign: the container class is renamed (products -> grid), so "ul.products > li"
# matches nothing, but the rows survive as a confident repeating group under ul.grid.
_REDESIGN = _page(_NAV, _listing("grid", _MAIN_ROWS))
# Redesign of the two-listing page: renaming products -> grid leaves *two* identical
# li.card groups (ul.grid and ul.recommended) both matching the container print.
_REDESIGN_AMBIGUOUS = _page(
    _NAV, _listing("grid", _MAIN_ROWS), _listing("recommended", _RECOMMENDED_ROWS)
)
# Collapse: the listing is gone and only a single row-like element remains — no
# repeating group, so the >=2-member gate refuses to fabricate a one-row listing.
_REDESIGN_SINGLE = _page(_NAV, _listing("grid", (("Solo", "99"),)))


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Per-scenario state, with the fingerprint cache under a fresh temp root."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    return {"body": _ORIGINAL}


def _run(context: dict[str, Any]) -> None:
    body = context["body"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _PATH:
            return httpx.Response(200, text=body)
        return httpx.Response(404, text="not found")

    cfg = load_config(context["config_text"])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        # Pin to tier 1: a refusal is a deliberate zero-record result that must not
        # escalate to the (real) browser tier under an in-memory transport.
        result = extract.run_report(
            cfg,
            client=client,
            sleep=lambda _: None,
            tiers=(extract.Tier1Resolver(),),
        )
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


@given("a first run has recorded the row-container fingerprint")
def first_run_records(context: dict[str, Any]) -> None:
    context["body"] = _ORIGINAL
    _run(context)
    assert len(context["result"].records) == len(_MAIN_ROWS)


@given(
    "a first run has recorded the row-container fingerprint, "
    "with a second identical listing also present"
)
def first_run_records_two_listings(context: dict[str, Any]) -> None:
    context["body"] = _ORIGINAL_TWO_LISTINGS
    _run(context)
    # Only the ul.products listing is selected; the recommended one is ignored.
    assert len(context["result"].records) == len(_MAIN_ROWS)


@given("the container never matched in a prior run")
def no_prior_run(context: dict[str, Any]) -> None:
    # No first run at all: the container was never fingerprinted, and the page is
    # already redesigned so the item selector matches nothing.
    context["body"] = _REDESIGN


# --- When ----------------------------------------------------------------


@when(parsers.parse('the container\'s class is renamed so "{item}" matches no rows'))
def rename_container(context: dict[str, Any], item: str) -> None:
    context["body"] = _REDESIGN


@when(
    parsers.parse(
        "the container's class is renamed so two identical row groups both match"
    )
)
def rename_container_ambiguous(context: dict[str, Any]) -> None:
    context["body"] = _REDESIGN_AMBIGUOUS


@when("the listing collapses so only a single row-like element remains")
def collapse_to_single(context: dict[str, Any]) -> None:
    context["body"] = _REDESIGN_SINGLE


@when("I run the config again")
@when("I run the config")
def run_config(context: dict[str, Any]) -> None:
    _run(context)


# --- Then ----------------------------------------------------------------


@then("every row is extracted again")
def every_row_extracted(context: dict[str, Any]) -> None:
    records = context["result"].records
    assert len(records) == len(_MAIN_ROWS)
    assert all(rec["name"] is not None and rec["price"] is not None for rec in records)


@then("no records are extracted")
def no_records(context: dict[str, Any]) -> None:
    assert context["result"].records == []


@then(parsers.parse("the run summary reports {count:d} confident heal"))
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
