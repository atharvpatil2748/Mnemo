"""Disposable real-stdio MCP child for the local Module 8.8.4 fixture matrix.

This harness deliberately bypasses certified startup while retaining the real
MCP server, dispatcher, serializer, and stdio streams. It never addresses the
production configuration or tunnel.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

from mcp.server.stdio import stdio_server
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.mcp.server import create_mcp_server
from test_mcp_immutable_schema_matrix import _fixture


async def _main(root: Path, *, legacy: bool) -> None:
    engine, reader, config, _ = await _fixture(
        root,
        legacy=legacy,
        analysis=True,
        capability_ready=True,
        structured_ready=True,
        final_qa_ready=True,
        governed_multilingual=True,
    )
    server = create_mcp_server(
        engine,
        config=config,
        principal_provider=lambda: PrincipalContextV1(UUID(int=99), True),
    )
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await reader.close()


if __name__ == "__main__":
    asyncio.run(_main(Path(sys.argv[1]).resolve(), legacy=sys.argv[2] == "older"))
