"""Step definitions for features/operational.feature (ROADMAP.md §2d, §6).

Politeness is about response headers and robots.txt, not page content, so these
scenarios drive an in-memory httpx MockTransport routing table built per
scenario — deterministic, no ports, no network, no real sleeping (the crawl
delay is asserted via an injected recording `sleep`).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config

# Resolved against bdd_features_base_dir = "features" (see pyproject.toml).
scenarios("operational.feature")


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
    """Per-scenario state: the routing table, the config, and run outputs."""
    return {"routes": {}}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('a site whose robots.txt disallows "{path}"'))
def robots_disallow(context: dict[str, Any], path: str) -> None:
    context["routes"]["/robots.txt"] = (
        200,
        f"User-agent: *\nDisallow: {path}\n",
    )


@given(
    parsers.parse("a site whose robots.txt sets a crawl-delay of {seconds:d} seconds")
)
def robots_crawl_delay(context: dict[str, Any], seconds: int) -> None:
    context["routes"]["/robots.txt"] = (
        200,
        f"User-agent: *\nCrawl-delay: {seconds}\n",
    )


@given("a site with no robots.txt")
def no_robots(context: dict[str, Any]) -> None:
    # Nothing to register: an unmatched /robots.txt returns 404 → allow all.
    pass


@given("a site whose robots.txt fails with a 503 error")
def robots_503(context: dict[str, Any]) -> None:
    context["routes"]["/robots.txt"] = (503, "service unavailable")


@given(parsers.parse('a page at "{path}" with title "{title}"'))
def page_with_title(context: dict[str, Any], path: str, title: str) -> None:
    context["routes"][path] = (200, _product_page(title))


@given(parsers.parse('a {count:d}-page catalog linked by "{selector}"'))
def catalog(context: dict[str, Any], count: int, selector: str) -> None:
    for n in range(1, count + 1):
        context["routes"][f"/catalog/page-{n}.html"] = (200, _catalog_page(n, count))


@given(parsers.parse('a config targeting "{url}"'))
def config_targeting(context: dict[str, Any], url: str) -> None:
    context["config_text"] = (
        f"target: {url}\n"
        'fields:\n'
        '  title: { selector: "h1.product-title" }\n'
    )


@given(parsers.parse('a config targeting "{url}" that opts out of robots.txt'))
def config_opt_out(context: dict[str, Any], url: str) -> None:
    context["config_text"] = (
        f"target: {url}\n"
        'fields:\n'
        '  title: { selector: "h1.product-title" }\n'
        "politeness:\n"
        "  respect_robots: false\n"
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


@given(
    parsers.parse(
        "a config paginating the catalog with a politeness delay of {seconds:d} seconds"
    )
)
def config_catalog_delay(context: dict[str, Any], seconds: int) -> None:
    context["config_text"] = (
        "target: http://localhost:8000/catalog/page-1.html\n"
        "fields:\n"
        '  title: { selector: "h2.item-title" }\n'
        "pagination:\n"
        '  next: "a.next-page"\n'
        "politeness:\n"
        f"  delay: {seconds}\n"
    )


# --- When ----------------------------------------------------------------


@when("I run the config with politeness")
def run_with_politeness(context: dict[str, Any]) -> None:
    routes = context["routes"]
    requested: list[str] = []
    sleeps: list[float] = []
    context["requested"] = requested
    context["sleeps"] = sleeps

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path in routes:
            status, body = routes[request.url.path]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    cfg = load_config(context["config_text"])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        context["result"] = extract.run_report(
            cfg, client=client, sleep=sleeps.append
        )


# --- Then ----------------------------------------------------------------


@then(parsers.parse('no request is made to "{path}"'))
def no_request_to(context: dict[str, Any], path: str) -> None:
    assert path not in context["requested"]


@then("the output contains no items")
def output_empty(context: dict[str, Any]) -> None:
    assert context["result"].records == []


@then("the output contains one item")
def output_one(context: dict[str, Any]) -> None:
    assert len(context["result"].records) == 1


@then(parsers.parse("the output contains {count:d} items"))
def output_n(context: dict[str, Any], count: int) -> None:
    assert len(context["result"].records) == count


@then(parsers.parse('the run reports "{url}" as blocked by robots.txt'))
def reports_blocked(context: dict[str, Any], url: str) -> None:
    assert url in context["result"].blocked


@then(parsers.parse('the item field "{field}" equals "{value}"'))
def item_field_equals(context: dict[str, Any], field: str, value: str) -> None:
    assert context["result"].records[0][field] == value


@then(parsers.parse("it waits {seconds:d} seconds before each fetch after the first"))
def waits_each_fetch(context: dict[str, Any], seconds: int) -> None:
    sleeps = context["sleeps"]
    assert sleeps, "expected at least one crawl-delay wait"
    assert set(sleeps) == {float(seconds)}


@then(parsers.parse("it waits {count:d} times in total"))
def waits_n_times(context: dict[str, Any], count: int) -> None:
    assert len(context["sleeps"]) == count
