"""Frozen public-route declaration and dispatch identity for the 14 MCP tools."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import mcp.types as types
import pytest
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo_server.mcp import tools as tool_module
from mnemo_server.mcp.server import create_mcp_server
from mnemo_server.mcp.tools import (
    ToolBackendRoute,
    execute_mcp_tool,
    get_mcp_route_contracts,
    get_mcp_tools,
)

EXPECTED_ROUTES = {
    "list_notebooks": (ToolBackendRoute.RETAINED_V1, "collection"),
    "get_notebook_summary": (ToolBackendRoute.RETAINED_STORAGE, "notebook"),
    "get_timeline": (ToolBackendRoute.RETAINED_STORAGE, "notebook"),
    "get_source_insights": (ToolBackendRoute.RETAINED_STORAGE, "source"),
    "search_all_notebooks": (ToolBackendRoute.RETAINED_V1, "optional_notebook"),
    "query_notebook": (ToolBackendRoute.RETAINED_V1, "notebook"),
    "search_evidence": (ToolBackendRoute.V2_REPRESENTATIONS, "service"),
    "get_capabilities": (ToolBackendRoute.V2_CAPABILITIES, "capability"),
    "query_structured": (ToolBackendRoute.V2_STRUCTURED, "service"),
    "get_document": (ToolBackendRoute.SHARED_V2_DELIVERY, "document"),
    "get_document_chunk": (ToolBackendRoute.SHARED_V2_DELIVERY, "document"),
    "get_asset": (ToolBackendRoute.SHARED_V2_DELIVERY, "notebook"),
    "get_image_analysis": (ToolBackendRoute.SHARED_V2_DELIVERY, "notebook"),
    "run_final_qa_v2": (ToolBackendRoute.CERTIFIED_V2_FINAL_QA, "service"),
}


def test_registered_tools_have_one_frozen_route_and_handler() -> None:
    routes = get_mcp_route_contracts()
    assert set(routes) == {tool.name for tool in get_mcp_tools()} == set(EXPECTED_ROUTES)
    assert len(routes) == 14
    for name, (backend, scope) in EXPECTED_ROUTES.items():
        contract = routes[name]
        assert (contract.backend, contract.auth_scope) == (backend, scope)
        assert contract.handler.__module__ == tool_module.__name__
    assert routes["query_notebook"].handler is not routes["run_final_qa_v2"].handler
    assert routes["search_all_notebooks"].handler is not routes["search_evidence"].handler
    assert routes["get_document"].handler is routes["get_asset"].handler


@pytest.mark.anyio
@pytest.mark.parametrize("name", EXPECTED_ROUTES)
async def test_dispatch_invokes_the_declared_handler(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    original = tool_module._TOOL_ROUTES[name]
    calls: list[tuple[object, ...]] = []
    sentinel = [types.TextContent(type="text", text="route-sentinel")]

    async def handler(*args: object) -> list[types.TextContent]:
        calls.append(args)
        return sentinel

    monkeypatch.setitem(tool_module._TOOL_ROUTES, name, replace(original, handler=handler))
    assert await execute_mcp_tool(engine, name, {}) == sentinel
    assert len(calls) == 1
    assert calls[0][0] is engine
    if original.backend is ToolBackendRoute.SHARED_V2_DELIVERY:
        assert calls[0][1] == name


def test_registration_fails_closed_for_missing_or_nonexecutable_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(tool_module._TOOL_ROUTES, "query_notebook")
    with pytest.raises(RuntimeError, match="route declaration is incomplete"):
        get_mcp_tools()
    with pytest.raises(RuntimeError, match="route declaration is incomplete"):
        create_mcp_server(MagicMock(spec=KnowledgeEngine))


def test_route_snapshot_cannot_change_the_dispatcher() -> None:
    snapshot = get_mcp_route_contracts()
    snapshot.pop("get_document")
    assert "get_document" in get_mcp_route_contracts()


def test_startup_rejects_wrong_handler_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    route = tool_module._TOOL_ROUTES["get_document"]

    async def wrong_handler() -> list[types.TextContent]:
        return []

    monkeypatch.setitem(
        tool_module._TOOL_ROUTES, "get_document", replace(route, handler=wrong_handler)
    )
    with pytest.raises(RuntimeError, match="handler is not executable"):
        create_mcp_server(MagicMock(spec=KnowledgeEngine))
