"""Model Context Protocol (MCP) server core implementation for Mnemo."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import mcp.types as types
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mnemo import EngineState, KnowledgeEngine, MnemoConfig, __version__
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from mnemo_server.auth import AuthMiddleware
from mnemo_server.config import ServerConfig
from mnemo_server.tokenizer_provisioning import provision_tokenizer

from .tools import execute_mcp_tool, get_mcp_tools

logger = logging.getLogger("mnemo.mcp")


def configure_stderr_logging(level: str = "INFO") -> None:
    """Configure all root and mnemo loggers to emit exclusively to sys.stderr.

    This guarantees that standard I/O (stdout) remains reserved exclusively for
    framed JSON-RPC protocol packets in stdio mode.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    # Remove existing stdout/stderr handlers to prevent duplication
    root_logger.handlers = [handler]

    # Silence stdout leaks from ML libraries in stdio transport mode
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"


class MnemoServer(Server):
    """Subclass of MCP Server providing typed KnowledgeEngine association."""

    _engine: KnowledgeEngine | None = None


def create_mcp_server(engine: KnowledgeEngine | None = None) -> Server:
    """Create and configure the canonical Mnemo MCP Server instance.

    Module 8.1 registered the server identity, capability negotiation, and baseline
    transport infrastructure. Module 8.2 delivers the six authoritative knowledge
    retrieval tools.
    """
    server: MnemoServer = MnemoServer(name="mnemo-mcp", version=__version__)
    server._engine = engine

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        """List knowledge tools exposed by the Mnemo MCP server."""
        return get_mcp_tools()

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Execute an authorized Mnemo MCP knowledge tool call."""
        return await execute_mcp_tool(server._engine, name, arguments)

    @server.list_prompts()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_prompts() -> list[types.Prompt]:
        """List prompts exposed by Mnemo."""
        return []

    @server.list_resources()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_resources() -> list[types.Resource]:
        """List resources exposed by Mnemo."""
        return []

    return server


async def run_stdio_server(
    *,
    config: ServerConfig | None = None,
    mnemo_config: MnemoConfig | None = None,
    engine: KnowledgeEngine | None = None,
) -> None:
    """Run the Mnemo MCP server over standard I/O (stdio) transport.

    All diagnostic output is routed strictly to stderr to keep stdout 100% protocol-pure.
    """
    log_level = config.log_level if config else "INFO"
    configure_stderr_logging(log_level)

    logger.info("Starting Mnemo MCP stdio server (v%s)", __version__)

    owns_engine = engine is None
    active_engine = engine
    if active_engine is None:
        try:
            if mnemo_config is not None:
                resolved_cfg = mnemo_config
            elif os.path.exists("mnemo.toml"):
                resolved_cfg = MnemoConfig.from_file("mnemo.toml")
            else:
                resolved_cfg = MnemoConfig.from_env()
            active_engine = KnowledgeEngine(config=resolved_cfg)
        except Exception as err:
            logger.warning("KnowledgeEngine could not be loaded: %s", err)

    if active_engine is not None and active_engine.state != EngineState.READY:
        if owns_engine:
            try:
                await asyncio.to_thread(provision_tokenizer)
            except Exception as err:
                logger.warning("Tokenizer provisioning check skipped or failed: %s", err)
        try:
            await active_engine.initialize()
        except Exception as err:
            logger.warning("KnowledgeEngine initialization encountered error: %s", err)

    server = create_mcp_server(engine=active_engine)
    init_options = server.create_initialization_options()

    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Stdio transport stream connected; serving requests")
            await server.run(read_stream, write_stream, init_options)
    except asyncio.CancelledError:
        logger.info("Stdio server execution cancelled")
    finally:
        if owns_engine and active_engine is not None and active_engine.state == EngineState.READY:
            logger.info("Shutting down KnowledgeEngine")
            await active_engine.shutdown()


def create_sse_app(
    *,
    server: Server | None = None,
    config: ServerConfig | None = None,
    mnemo_config: MnemoConfig | None = None,
    engine: KnowledgeEngine | None = None,
) -> Starlette:
    """Create a Starlette ASGI application hosting the MCP SSE transport."""
    server_config = config or ServerConfig()
    owns_engine = engine is None
    active_engine = engine
    active_server = server or create_mcp_server(engine=active_engine)
    sse_transport = SseServerTransport(endpoint="/messages")

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        nonlocal active_engine
        if active_engine is None:
            try:
                if mnemo_config is not None:
                    resolved_config = mnemo_config
                elif os.path.exists("mnemo.toml"):
                    resolved_config = MnemoConfig.from_file("mnemo.toml")
                else:
                    resolved_config = MnemoConfig.from_env()
                active_engine = KnowledgeEngine(config=resolved_config)
            except Exception as err:
                logger.warning("KnowledgeEngine could not be loaded: %s", err)
            app.state.engine = active_engine
            if isinstance(active_server, MnemoServer):
                active_server._engine = active_engine

        if active_engine is not None and active_engine.state != EngineState.READY:
            if owns_engine:
                try:
                    await asyncio.to_thread(provision_tokenizer)
                except Exception as err:
                    logger.warning("Tokenizer provisioning check skipped or failed: %s", err)
            try:
                await active_engine.initialize()
            except Exception as err:
                logger.warning("KnowledgeEngine initialization encountered error: %s", err)
        else:
            app.state.engine = active_engine

        yield

        if owns_engine and active_engine is not None and active_engine.state == EngineState.READY:
            await active_engine.shutdown()

    class _SseEndpoint:
        """Raw ASGI endpoint because the MCP transport owns the HTTP response."""

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            init_options = active_server.create_initialization_options()
            async with sse_transport.connect_sse(scope, receive, send) as (
                read_stream,
                write_stream,
            ):
                await active_server.run(read_stream, write_stream, init_options)

    class _MessageEndpoint:
        """Raw ASGI endpoint preventing a second Starlette response write."""

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            await sse_transport.handle_post_message(scope, receive, send)

    async def handle_health(request: Request) -> Response:
        """Health check endpoint for MCP SSE service."""
        current_engine = getattr(request.app.state, "engine", active_engine)
        engine_state_str = (
            current_engine.state.value if current_engine else EngineState.UNINITIALIZED.value
        )
        return JSONResponse(
            {
                "status": "ok",
                "service": "mnemo-mcp",
                "version": __version__,
                "engine_state": engine_state_str,
            }
        )

    routes = [
        Route("/sse", endpoint=_SseEndpoint(), methods=["GET"]),
        Route("/messages", endpoint=_MessageEndpoint(), methods=["POST"]),
        Route("/health", endpoint=handle_health, methods=["GET"]),
    ]

    app = Starlette(routes=routes, lifespan=lifespan)
    if server_config.auth_mode in ("api-key", "jwt"):
        app.add_middleware(AuthMiddleware, config=server_config)

    return app


def run_sse_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8001,
    config: ServerConfig | None = None,
    engine: KnowledgeEngine | None = None,
) -> None:
    """Run the MCP SSE HTTP transport using Uvicorn."""
    server_config = config or ServerConfig(host=host, port=port)
    app = create_sse_app(config=server_config, engine=engine)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=server_config.log_level,
    )
