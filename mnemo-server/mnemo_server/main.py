"""ASGI application entrypoint for mnemo-server."""

from __future__ import annotations

import uvicorn

from .app import create_app
from .config import ServerConfig

app = create_app()


def run() -> None:
    """Run the Uvicorn ASGI server with resolved ServerConfig."""
    config = ServerConfig.from_env()
    uvicorn.run(
        "mnemo_server.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level,
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    run()
