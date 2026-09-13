"""Step definitions for features/serving_mcp.feature (ROADMAP.md §2f).

The MCP serving mode is a read-only server over the same map store as the REST
API. These steps build a store backed by a temp cache root, populate it the way
a run would, build the MCP server over it, and drive its tools in-process
(`list_tools` / `call_tool`, run synchronously via `asyncio.run`) — pinning the
read-only contract and that answers match the REST surface's redaction/freshness.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.security import storage
from spoor.serving.mcp_server import create_mcp_server
from spoor.serving.store import MapStore

scenarios("serving_mcp.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared state carried across steps within one scenario."""
    return {}


@pytest.fixture(autouse=True)
def temp_cache_root(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the local cache root so the map store writes under a temp dir."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / ".spoor-cache")


def _tool_json(context: dict[str, Any], name: str, arguments: dict[str, Any]) -> Any:
    """Call an MCP tool and parse its JSON text payload."""
    result = asyncio.run(context["server"].call_tool(name, arguments))
    return json.loads(result.content[0].text)


# --- Given ---------------------------------------------------------------


@given("an MCP server over a map containing:")
def mcp_server_over_map(context: dict[str, Any], datatable: list[list[str]]) -> None:
    store = MapStore()
    header, *rows = datatable
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        store.record(
            fields["url"],
            [{"title": fields["title"]}],
            tier=1,
            captured_at=datetime.fromisoformat(fields["captured_at"]),
        )
    context["server"] = create_mcp_server(store)


# --- When ----------------------------------------------------------------


@when(parsers.parse('I call the MCP tool "{name}" with url "{url}"'))
def call_get_map(context: dict[str, Any], name: str, url: str) -> None:
    try:
        context["result"] = _tool_json(context, name, {"url": url})
        context["error"] = None
    except ToolError as exc:
        context["error"] = exc


@when(parsers.parse('I call the MCP tool "{name}"'))
def call_no_args(context: dict[str, Any], name: str) -> None:
    context["result"] = _tool_json(context, name, {})


# --- Then ----------------------------------------------------------------


@then(parsers.parse('the MCP tools are exactly "{a}" and "{b}"'))
def tools_are_exactly(context: dict[str, Any], a: str, b: str) -> None:
    tools = asyncio.run(context["server"].list_tools())
    assert {t.name for t in tools} == {a, b}


@then("every MCP tool is marked read-only and non-destructive")
def tools_read_only(context: dict[str, Any]) -> None:
    # Structural proof of the §2f non-negotiable: no exposed tool advertises a
    # state-changing or destructive effect.
    tools = asyncio.run(context["server"].list_tools())
    assert tools, "expected the MCP server to expose tools"
    for tool in tools:
        ann = tool.annotations
        assert ann is not None and ann.read_only_hint is True, tool.name
        assert ann.destructive_hint is False, tool.name


@then(parsers.parse('the MCP result\'s first record "{field}" equals "{value}"'))
def first_record_field(context: dict[str, Any], field: str, value: str) -> None:
    assert context["result"]["records"][0][field] == value


@then("the MCP result carries a capture time and a non-negative age")
def result_freshness(context: dict[str, Any]) -> None:
    result = context["result"]
    assert isinstance(result["captured_at"], str) and result["captured_at"]
    assert isinstance(result["age_seconds"], (int, float))
    assert result["age_seconds"] >= 0


@then("the MCP call fails with a not-mapped error")
def call_failed(context: dict[str, Any]) -> None:
    assert isinstance(context["error"], ToolError)
    assert "not mapped" in str(context["error"]).lower()


@then(parsers.parse('the MCP domains include "{domain}"'))
def domains_include(context: dict[str, Any], domain: str) -> None:
    assert domain in context["result"]["domains"]
