"""Unit tests for HAR->spec synthesis (ROADMAP.md §2b layer 4).

Below api_discovery.feature: the scenarios prove synthesis end to end (a captured
HAR clustered into templated endpoints, the doc written, counts surfaced); these
pin the pure pieces — the ID/templating rule and the reader's edges (unreadable /
invalid / empty / non-JSON / cross-origin HARs, status union, determinism) —
without going through a run.
"""

from __future__ import annotations

import json
from pathlib import Path

from spoor.api_discovery.synthesis import (
    _looks_like_id,
    _template_path,
    synthesize_from_har,
)

_TARGET = "http://localhost:8000/index.html"
_ORIGIN = "http://localhost:8000"


# --- _looks_like_id / _template_path: the generic ID rule ----------------


def test_pure_digits_are_an_id() -> None:
    assert _looks_like_id("123")


def test_uuid_is_an_id() -> None:
    assert _looks_like_id("550e8400-e29b-41d4-a716-446655440000")


def test_long_hex_objectid_is_an_id() -> None:
    assert _looks_like_id("507f1f77bcf86cd799439011")  # 24-char Mongo ObjectId


def test_short_hex_word_is_not_an_id() -> None:
    # Conservative: a short hex-looking word is left literal, not templated.
    assert not _looks_like_id("cafe")


def test_plain_word_is_not_an_id() -> None:
    assert not _looks_like_id("users")
    assert not _looks_like_id("v1")


def test_empty_segment_is_not_an_id() -> None:
    assert not _looks_like_id("")


def test_template_numeric_segment() -> None:
    assert _template_path("/api/users/1") == "/api/users/{id}"


def test_template_leaves_version_and_words_literal() -> None:
    assert _template_path("/api/v1/orders") == "/api/v1/orders"


def test_template_uuid_segment() -> None:
    assert (
        _template_path("/things/550e8400-e29b-41d4-a716-446655440000")
        == "/things/{id}"
    )


def test_template_multiple_id_segments() -> None:
    assert _template_path("/users/1/orders/2") == "/users/{id}/orders/{id}"


# --- synthesize_from_har: edges ------------------------------------------


def _write_har(path: Path, entries: list[dict[str, object]]) -> Path:
    har = {"log": {"version": "1.2", "entries": entries}}
    path.write_text(json.dumps(har), encoding="utf-8")
    return path


def _entry(
    method: str, url: str, status: int = 200, mime: str = "application/json"
) -> dict[str, object]:
    return {
        "request": {"method": method, "url": url},
        "response": {"status": status, "content": {"mimeType": mime}},
    }


def test_missing_file_yields_none(tmp_path: Path) -> None:
    assert synthesize_from_har(tmp_path / "nope.har", _TARGET) is None


def test_invalid_json_yields_none(tmp_path: Path) -> None:
    path = tmp_path / "bad.har"
    path.write_text("{not json", encoding="utf-8")
    assert synthesize_from_har(path, _TARGET) is None


def test_har_without_entries_yields_none(tmp_path: Path) -> None:
    path = tmp_path / "empty.har"
    path.write_text(json.dumps({"log": {"version": "1.2"}}), encoding="utf-8")
    assert synthesize_from_har(path, _TARGET) is None


def test_non_json_responses_yield_none(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "html.har",
        [_entry("GET", _ORIGIN + "/page", mime="text/html")],
    )
    assert synthesize_from_har(har, _TARGET) is None


def test_repeated_ids_cluster_to_one_endpoint(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "n.har",
        [_entry("GET", _ORIGIN + f"/api/users/{i}") for i in (1, 2, 3)],
    )
    spec = synthesize_from_har(har, _TARGET)
    assert spec is not None
    assert spec.request_count == 3
    assert spec.endpoint_count == 1
    assert spec.endpoints[0].method == "GET"
    assert spec.endpoints[0].path == "/api/users/{id}"


def test_cross_origin_entry_is_excluded(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "x.har",
        [
            _entry("GET", _ORIGIN + "/api/me"),
            _entry("GET", "http://cdn.example.com/api/track"),
        ],
    )
    spec = synthesize_from_har(har, _TARGET)
    assert spec is not None
    assert spec.request_count == 1
    assert [(e.method, e.path) for e in spec.endpoints] == [("GET", "/api/me")]


def test_distinct_method_and_path_stay_distinct(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "d.har",
        [
            _entry("GET", _ORIGIN + "/api/products/10"),
            _entry("POST", _ORIGIN + "/api/orders"),
        ],
    )
    spec = synthesize_from_har(har, _TARGET)
    assert spec is not None
    assert spec.endpoint_count == 2
    assert {(e.method, e.path) for e in spec.endpoints} == {
        ("GET", "/api/products/{id}"),
        ("POST", "/api/orders"),
    }


def test_statuses_are_unioned_sorted_per_endpoint(tmp_path: Path) -> None:
    har = _write_har(
        tmp_path / "s.har",
        [
            _entry("GET", _ORIGIN + "/api/users/1", status=200),
            _entry("GET", _ORIGIN + "/api/users/2", status=404),
            _entry("GET", _ORIGIN + "/api/users/3", status=200),
        ],
    )
    spec = synthesize_from_har(har, _TARGET)
    assert spec is not None
    assert spec.endpoints[0].statuses == (200, 404)


def test_endpoints_are_ordered_deterministically(tmp_path: Path) -> None:
    # Capture order is orders-then-users; output must be sorted by (path, method).
    har = _write_har(
        tmp_path / "o.har",
        [
            _entry("POST", _ORIGIN + "/api/orders"),
            _entry("GET", _ORIGIN + "/api/users/1"),
        ],
    )
    spec = synthesize_from_har(har, _TARGET)
    assert spec is not None
    assert [e.path for e in spec.endpoints] == ["/api/orders", "/api/users/{id}"]


def test_openapi_doc_written_beside_har(tmp_path: Path) -> None:
    har = _write_har(tmp_path / "w.har", [_entry("GET", _ORIGIN + "/api/users/1")])
    spec = synthesize_from_har(har, _TARGET)
    assert spec is not None
    assert spec.doc_path == str(tmp_path / "synthesized_openapi.json")
    doc = json.loads(Path(spec.doc_path).read_text(encoding="utf-8"))
    assert doc["openapi"] == "3.0.0"
    assert doc["servers"] == [{"url": _ORIGIN}]
    assert "/api/users/{id}" in doc["paths"]
    assert "get" in doc["paths"]["/api/users/{id}"]
    assert "200" in doc["paths"]["/api/users/{id}"]["get"]["responses"]
