"""Opt-in TCP boundary for existing disposable HTTP contract fixtures.

Run with PYTHONPATH=mnemo-server/tests and pytest -p http_tcp_audit_plugin.
Never used by normal CI. Backend fixtures remain disposable/test doubles; this
adds real network serialization, not a claim of public production exposure.
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import tempfile
import threading
import time
from typing import Any

import httpx
import uvicorn

_SEEN: set[tuple[str, str]] = set()


class TCPFixtureTransport(httpx.AsyncBaseTransport):
    def __init__(self, app: Any, **kwargs: Any) -> None:
        self.app = app
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        self.server = uvicorn.Server(
            uvicorn.Config(
                app,
                lifespan="off",
                log_level="critical",
                access_log=False,
            )
        )
        self.thread = threading.Thread(
            target=self.server.run,
            kwargs={"sockets": [self.socket]},
            daemon=True,
        )
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("disposable TCP fixture startup failed")
            time.sleep(0.01)
        self.transport = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for template in self.app.openapi()["paths"]:
            pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template))
            if re.fullmatch(pattern, path):
                path = template
                break
        _SEEN.add((request.method, path))
        network_request = httpx.Request(
            request.method,
            request.url.copy_with(scheme="http", host="127.0.0.1", port=self.port),
            headers=request.headers,
            content=await request.aread(),
            extensions=request.extensions,
        )
        return await self.transport.handle_async_request(network_request)

    async def aclose(self) -> None:
        await self.transport.aclose()
        self.server.should_exit = True
        await asyncio.to_thread(self.thread.join, 10)
        self.socket.close()
        if self.thread.is_alive():
            raise RuntimeError("disposable TCP fixture did not stop")


def pytest_configure() -> None:
    httpx.ASGITransport = TCPFixtureTransport  # type: ignore[assignment]


def pytest_sessionfinish() -> None:
    print("\nACTUAL DISPOSABLE TCP OPERATIONS:")
    for method, path in sorted(_SEEN):
        print(method, path)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="mnemo-tcp-operations-",
        delete=False,
        encoding="utf-8",
    ) as artifact:
        json.dump([{"method": method, "path": path} for method, path in sorted(_SEEN)], artifact)
        print(f"TCP operation manifest: {artifact.name}")
