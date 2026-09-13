"""Unit tests for landing-page spec-reference scanning (ROADMAP.md §2b layer 1).

Below api_discovery.feature: the scenarios prove the second half of layer 1 end
to end through a run; these pin the pure candidate extractor's edges — which
strings count as a reference, how they resolve and de-duplicate, and what is
ignored — without a client. Validation (is a candidate a real spec?) is the
strict JSON check tested via the feature, not here; this only fixes what gets
*proposed* for probing.
"""

from __future__ import annotations

from spoor.api_discovery.discovery import _spec_reference_candidates

_PAGE = "http://localhost:8000/app/index.html"


def test_no_html_yields_no_candidates() -> None:
    assert _spec_reference_candidates("", _PAGE) == []


def test_page_without_references_yields_nothing() -> None:
    html = '<html><body><h1>Hi</h1><a href="/about">About</a></body></html>'
    assert _spec_reference_candidates(html, _PAGE) == []


def test_vocab_link_is_found_and_made_absolute() -> None:
    html = '<a href="/v3/api-docs">docs</a>'
    assert _spec_reference_candidates(html, _PAGE) == [
        "http://localhost:8000/v3/api-docs"
    ]


def test_relative_reference_resolves_against_page_url() -> None:
    # Resolved against the page, not the origin — a page-relative swagger path.
    html = "SwaggerUIBundle({ url: 'swagger.json' })"
    assert _spec_reference_candidates(html, _PAGE) == [
        "http://localhost:8000/app/swagger.json"
    ]


def test_redoc_spec_url_without_vocab_is_found() -> None:
    # /internal/spec carries none of the vocabulary; only the spec-url attribute
    # pattern can surface it.
    html = '<redoc spec-url="/internal/spec"></redoc>'
    assert _spec_reference_candidates(html, _PAGE) == [
        "http://localhost:8000/internal/spec"
    ]


def test_duplicate_references_are_collapsed_first_seen() -> None:
    html = (
        '<a href="/openapi.json">a</a>'
        '<link href="/openapi.json"><script src="/openapi.json">'
    )
    assert _spec_reference_candidates(html, _PAGE) == [
        "http://localhost:8000/openapi.json"
    ]


def test_prose_containing_swagger_is_not_a_reference() -> None:
    # Whitespace-free matching: a title like "Swagger Petstore" is not a URL.
    html = "<title>Swagger Petstore</title><p>The swagger spec is nice</p>"
    assert _spec_reference_candidates(html, _PAGE) == []


def test_fragment_and_scheme_only_references_are_ignored() -> None:
    html = (
        "<a href=\"#swagger\">x</a>"
        "<a href=\"javascript:openapi()\">y</a>"
        "<img src=\"data:image/png;base64,api-docs\">"
    )
    assert _spec_reference_candidates(html, _PAGE) == []


def test_absolute_cross_origin_reference_is_kept() -> None:
    html = '<a href="https://cdn.example.com/openapi.json">spec</a>'
    assert _spec_reference_candidates(html, _PAGE) == [
        "https://cdn.example.com/openapi.json"
    ]


def test_multiple_distinct_references_preserve_order() -> None:
    html = '<redoc spec-url="/a/spec"></redoc><a href="/openapi.json">o</a>'
    # spec-url matches are scanned before vocabulary matches.
    assert _spec_reference_candidates(html, _PAGE) == [
        "http://localhost:8000/a/spec",
        "http://localhost:8000/openapi.json",
    ]
