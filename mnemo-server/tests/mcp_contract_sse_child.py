"""Disposable loopback MCP SSE child for the public transport contract matrix."""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import uvicorn
from mnemo_server.mcp.principal import session_principal
from mnemo_server.mcp.server import create_mcp_server, create_sse_app
from test_mcp_immutable_schema_matrix import _fixture


async def _main(root: Path, legacy: bool) -> None:
    engine, reader, config, _ = await _fixture(
        root,
        legacy=legacy,
        analysis=True,
        capability_ready=True,
        structured_ready=True,
        final_qa_ready=True,
        governed_multilingual=True,
    )
    try:
        with (
            patch(
                "mnemo_server.services.production_runtime_binding.resolve_certified_production_binding",
                return_value=(engine.config, None),
            ),
            patch(
                "mnemo_server.services.production_runtime_binding.record_certified_transport_startup"
            ),
            patch("mnemo_server.mcp.server._install_v2_if_enabled", new_callable=AsyncMock),
        ):
            server = create_mcp_server(engine, config=config, principal_provider=session_principal)
            app = create_sse_app(
                server=server, config=config, engine=engine, mnemo_config=engine.config
            )
            listener = uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="on", log_level="error")
            )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                sock.listen(128)
                port = sock.getsockname()[1]
                print(f"PORT={port}", flush=True)

                async def stop_on_stdin() -> None:
                    await asyncio.to_thread(sys.stdin.readline)
                    listener.should_exit = True

                await asyncio.gather(listener.serve(sockets=[sock]), stop_on_stdin())
    finally:
        await reader.close()


if __name__ == "__main__":
    asyncio.run(_main(Path(sys.argv[1]), sys.argv[2] == "older"))
