"""Unit and protocol integration tests for Mnemo MCP Server Core (Module 8.1)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import mcp.types as types
import pytest
from mcp.client.session import ClientSession
from mnemo import EngineState, KnowledgeEngine, __version__
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.server import (
    configure_stderr_logging,
    create_mcp_server,
    run_stdio_server,
)


def test_create_mcp_server_metadata() -> None:
    """Server exposes canonical name and package version."""
    server = create_mcp_server()
    assert server.name == "mnemo-mcp"
    assert server.version == __version__

    options = server.create_initialization_options()
    assert options.capabilities.tools is not None
    assert (
        getattr(
            options.capabilities.tools,
            "list_changed",
            getattr(options.capabilities.tools, "listChanged", None),
        )
        is False
    )
    assert options.server_name == "mnemo-mcp"
    assert options.server_version == __version__


@pytest.mark.anyio
async def test_mcp_server_protocol_handshake() -> None:
    """A real MCP ClientSession connects, initializes, and enumerates capabilities."""
    server = create_mcp_server()
    init_opts = server.create_initialization_options()

    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream(10)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream(10)

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await server.run(client_to_server_recv, server_to_client_send, init_opts)

        tg.start_soon(run_server)

        async with ClientSession(server_to_client_recv, client_to_server_send) as session:
            init_res = await session.initialize()
            info = getattr(init_res, "server_info", getattr(init_res, "serverInfo", None))
            assert info.name == "mnemo-mcp"
            assert info.version == __version__

            # Module 8.2 lists the 6 knowledge tools
            tools_res = await session.list_tools()
            assert len(tools_res.tools) == 6
            tool_names = [t.name for t in tools_res.tools]
            assert "query_notebook" in tool_names
            assert "search_all_notebooks" in tool_names
            assert "list_notebooks" in tool_names
            assert "get_notebook_summary" in tool_names
            assert "get_source_insights" in tool_names
            assert "get_timeline" in tool_names

            # Prompts and resources
            prompts_res = await session.list_prompts()
            assert prompts_res.prompts == []

            resources_res = await session.list_resources()
            assert resources_res.resources == []

            tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_mcp_server_call_unknown_tool_returns_error_result() -> None:
    """Tool invocation returns isError=True CallToolResult for unknown tools."""
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.READY
    server = create_mcp_server(mock_engine)
    handler = server.request_handlers[types.CallToolRequest]
    assert handler is not None

    req = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="non_existent_tool", arguments={}),
    )
    call_res = await handler(req)
    result = getattr(call_res, "root", call_res)
    assert isinstance(result, types.CallToolResult)
    is_err = getattr(result, "isError", getattr(result, "is_error", False))
    assert is_err is True
    assert len(result.content) == 1
    assert "Unknown MCP tool" in result.content[0].text


@pytest.mark.anyio
async def test_run_stdio_server_lifecycle() -> None:
    """run_stdio_server initializes and shuts down engine cleanly."""
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.UNINITIALIZED
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

    config = ServerConfig(log_level="debug")

    with patch("mnemo_server.mcp.server.stdio_server") as mock_stdio:
        # Mock stdio_server context manager yielding dummy streams
        mock_read = MagicMock()
        mock_write = MagicMock()

        @patch("mnemo_server.mcp.server.Server.run", new_callable=AsyncMock)
        async def _run_test(mock_run: AsyncMock) -> None:
            mock_stdio.return_value.__aenter__.return_value = (mock_read, mock_write)
            mock_stdio.return_value.__aexit__.return_value = False

            # Set mock_engine state to READY after initialize
            async def _init() -> None:
                mock_engine.state = EngineState.READY

            mock_engine.initialize.side_effect = _init

            await run_stdio_server(config=config, engine=mock_engine)

            assert mock_engine.initialize.called
            assert mock_run.called

        await _run_test()


@pytest.mark.anyio
async def test_run_stdio_server_owns_engine_cancellation() -> None:
    """run_stdio_server handles Cancellation and shuts down owned engine."""
    config = ServerConfig(log_level="debug")

    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.UNINITIALIZED
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

    async def _init() -> None:
        mock_engine.state = EngineState.READY

    mock_engine.initialize.side_effect = _init

    with (
        patch("mnemo_server.mcp.server.MnemoConfig.from_env", return_value=MagicMock()),
        patch("mnemo_server.mcp.server.KnowledgeEngine", return_value=mock_engine),
        patch(
            "mnemo_server.mcp.server.provision_tokenizer", side_effect=RuntimeError("tokenizer err")
        ),
        patch("mnemo_server.mcp.server.stdio_server") as mock_stdio,
        patch("mnemo_server.mcp.server.Server.run", side_effect=asyncio.CancelledError),
    ):
        mock_stdio.return_value.__aenter__.return_value = (MagicMock(), MagicMock())
        mock_stdio.return_value.__aexit__.return_value = False

        await run_stdio_server(config=config)

        assert mock_engine.initialize.called
        assert mock_engine.shutdown.called


def test_create_mcp_server_engine_attr() -> None:
    """create_mcp_server records injected engine instance."""
    mock_engine = MagicMock(spec=KnowledgeEngine)
    server = create_mcp_server(engine=mock_engine)
    assert getattr(server, "_engine", None) is mock_engine


def test_configure_stderr_logging() -> None:
    """Logging is configured to emit to stderr."""
    configure_stderr_logging("DEBUG")
    import logging
    import sys

    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 1
    assert getattr(root_logger.handlers[0], "stream", None) is sys.stderr
