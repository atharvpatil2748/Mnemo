"""Protocol conformance and schema compliance tests for Mnemo MCP Server."""

from __future__ import annotations

from unittest.mock import MagicMock

import anyio
import mcp.types as types
import pytest
from mcp.client.session import ClientSession
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo_server.mcp.server import create_mcp_server
from mnemo_server.mcp.tools import get_mcp_tools


def _make_mock_engine() -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    return engine


@pytest.mark.anyio
async def test_mcp_protocol_conformance_handshake() -> None:
    """Verify MCP protocol initialization handshake and capabilities."""
    engine = _make_mock_engine()
    server = create_mcp_server(engine)
    init_opts = server.create_initialization_options()

    c2s_send, c2s_recv = anyio.create_memory_object_stream(10)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(10)

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await server.run(c2s_recv, s2c_send, init_opts)

        tg.start_soon(run_server)

        async with ClientSession(s2c_recv, c2s_send) as session:
            result = await session.initialize()
            assert result.serverInfo.name == "mnemo-mcp"
            assert result.protocolVersion is not None
            assert result.capabilities.tools is not None

            # Tool listing
            tools_result = await session.list_tools()
            assert len(tools_result.tools) == 6
            tool_names = {t.name for t in tools_result.tools}
            assert tool_names == {
                "query_notebook",
                "search_all_notebooks",
                "list_notebooks",
                "get_notebook_summary",
                "get_source_insights",
                "get_timeline",
            }

            tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_mcp_tool_schemas_compliance() -> None:
    """Verify that all tool schemas comply with standard MCP JSON-schema specifications."""
    tools = get_mcp_tools()
    assert len(tools) == 6

    for tool in tools:
        assert isinstance(tool.name, str) and tool.name
        assert isinstance(tool.description, str) and tool.description
        assert isinstance(tool.inputSchema, dict)
        assert tool.inputSchema.get("type") == "object"
        assert "properties" in tool.inputSchema

        # Check required properties if specified
        if "required" in tool.inputSchema:
            assert isinstance(tool.inputSchema["required"], list)
            for req_field in tool.inputSchema["required"]:
                assert req_field in tool.inputSchema["properties"]


@pytest.mark.anyio
async def test_mcp_invalid_tool_invocation_error_format() -> None:
    """Verify that calling an invalid or unknown tool returns an error structure."""
    engine = _make_mock_engine()
    server = create_mcp_server(engine)
    init_opts = server.create_initialization_options()

    c2s_send, c2s_recv = anyio.create_memory_object_stream(10)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(10)

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await server.run(c2s_recv, s2c_send, init_opts)

        tg.start_soon(run_server)

        async with ClientSession(s2c_recv, c2s_send) as session:
            await session.initialize()

            # 1. Unknown tool invocation
            res = await session.call_tool("unknown_tool", {})
            assert res.isError is True
            assert len(res.content) > 0
            first_content = res.content[0]
            assert isinstance(first_content, types.TextContent)
            assert "Unknown MCP tool" in first_content.text

            # 2. Invalid parameter type
            res2 = await session.call_tool(
                "query_notebook", {"notebook_id": "not-valid-uuid", "question": "test"}
            )
            assert res2.isError is True
            second_content = res2.content[0]
            assert isinstance(second_content, types.TextContent)
            assert "invalid UUID" in second_content.text

            tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_mcp_real_stdio_subprocess_handshake() -> None:
    """Verify that a real child process running mnemo-mcp stdio performs clean handshake."""
    from mcp.client.stdio import StdioServerParameters, stdio_client

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "mnemo-mcp", "--log-level", "error", "stdio"],
    )

    async with (
        stdio_client(server_params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        init_res = await session.initialize()
        assert init_res.serverInfo.name == "mnemo-mcp"
        tools_res = await session.list_tools()
        assert len(tools_res.tools) == 6
        tool_names = {t.name for t in tools_res.tools}
        assert "list_notebooks" in tool_names
        assert "query_notebook" in tool_names
