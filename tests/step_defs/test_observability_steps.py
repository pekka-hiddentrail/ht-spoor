"""Step definitions for features/observability.feature (ROADMAP.md §2d).

Drives the dispatcher through an in-memory httpx MockTransport routing table
(deterministic, no ports, no network) and asserts against the `RunSummary`
projected from the run — items, pages fetched, resolving tier, escalation, and
what robots.txt blocked.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary

scenarios("observability.feature")


def _product_page(title: str) -> str:
    return f'<html><body><h1 class="product-title">{title}</h1></body></html>'


def _catalog_page(n: int, total: int) -> str:
    nxt = (
        ""
        if n == total
        else f'<a class="next-page" href="/catalog/page-{n + 1}.html">next</a>'
    )
    return f'<html><body><h2 class="item-title">Item {n}</h2>{nxt}</body></html>'


@pytest.fixture
def context() -> dict[str, Any]:
    """Per-scenario state: the routing table, the config, and the summary."""
    return {"routes": {}}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('a page at "{path}" with title "{title}"'))
def page_with_title(context: dict[str, Any], path: str, title: str) -> None:
    context["routes"][path] = (200, _product_page(title))


@given(parsers.parse('a {count:d}-page catalog linked by "{selector}"'))
def catalog(context: dict[str, Any], count: int, selector: str) -> None:
    for n in range(1, count + 1):
        context["routes"][f"/catalog/page-{n}.html"] = (200, _catalog_page(n, count))


@given(parsers.parse('a site whose robots.txt disallows "{path}"'))
def robots_disallow(context: dict[str, Any], path: str) -> None:
    context["routes"]["/robots.txt"] = (200, f"User-agent: *\nDisallow: {path}\n")


@given(parsers.parse('a config targeting "{url}"'))
def config_targeting(context: dict[str, Any], url: str) -> None:
    context["config_text"] = (
        f"target: {url}\nfields:\n  title: {{ selector: \"h1.product-title\" }}\n"
    )


@given("a config paginating the catalog")
def config_catalog(context: dict[str, Any]) -> None:
    context["config_text"] = (
        "target: http://localhost:8000/catalog/page-1.html\n"
        "fields:\n"
        '  title: { selector: "h2.item-title" }\n'
        "pagination:\n"
        '  next: "a.next-page"\n'
    )


# --- When ----------------------------------------------------------------


@when("I run the config and capture the summary")
def run_and_summarize(context: dict[str, Any]) -> None:
    routes = context["routes"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in routes:
            status, body = routes[request.url.path]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    cfg = load_config(context["config_text"])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract.run_report(cfg, client=client, sleep=lambda _: None)
    context["summary"] = RunSummary.from_result(result)


# --- Then ----------------------------------------------------------------


@then(parsers.parse("the summary reports {count:d} item scraped"))
@then(parsers.parse("the summary reports {count:d} items scraped"))
def summary_items(context: dict[str, Any], count: int) -> None:
    assert context["summary"].items == count


@then(parsers.parse("the summary reports {count:d} page fetched"))
@then(parsers.parse("the summary reports {count:d} pages fetched"))
def summary_pages(context: dict[str, Any], count: int) -> None:
    assert context["summary"].pages_fetched == count


@then(parsers.parse("the summary reports tier {tier:d} resolved the run"))
def summary_resolved_tier(context: dict[str, Any], tier: int) -> None:
    assert context["summary"].resolved_tier == tier


@then("the summary reports no escalation")
def summary_no_escalation(context: dict[str, Any]) -> None:
    assert context["summary"].escalated is False


@then(parsers.parse("the summary reports {count:d} blocked page"))
@then(parsers.parse("the summary reports {count:d} blocked pages"))
def summary_blocked_count(context: dict[str, Any], count: int) -> None:
    assert len(context["summary"].blocked) == count


@then(parsers.parse('the summary lists "{url}" as blocked'))
def summary_lists_blocked(context: dict[str, Any], url: str) -> None:
    assert url in context["summary"].blocked


@then(parsers.parse('the rendered summary mentions "{text}"'))
def rendered_mentions(context: dict[str, Any], text: str) -> None:
    assert text in context["summary"].render()
