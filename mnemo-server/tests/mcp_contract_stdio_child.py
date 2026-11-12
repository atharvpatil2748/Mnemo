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
from test_mcp_immutable_schema_matrix import _fixture, create_mcp_server


async def _main(root: Path, *, legacy: bool) -> None:
    ordered_only = "ordered" in sys.argv[3:]
    engine, reader, config, _ = await _fixture(
        root,
        legacy=legacy,
        analysis=not ordered_only,
        capability_ready=not ordered_only,
        structured_ready=not ordered_only,
        final_qa_ready=not ordered_only,
        governed_multilingual=not ordered_only,
    )
    if ordered_only:
        from ordered_text_fixture import install_ordered_fixture

        await install_ordered_fixture(reader, root)
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
