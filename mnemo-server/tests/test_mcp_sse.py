"""Unit and integration tests for Mnemo MCP SSE transport (Module 8.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo import EngineState, KnowledgeEngine, __version__
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.server import create_sse_app, run_sse_server


@pytest.fixture
def mock_engine() -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
    return engine


@pytest.mark.anyio
async def test_mcp_sse_health_endpoint(mock_engine: MagicMock) -> None:
    """GET /health returns 200 OK and service metadata."""
    app = create_sse_app(engine=mock_engine)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "mnemo-mcp"
        assert data["version"] == __version__
        assert data["engine_state"] == "ready"


@pytest.mark.anyio
async def test_mcp_sse_auth_protection(mock_engine: MagicMock) -> None:
    """When api-key auth mode is enabled, non-exempt paths require Authorization."""
    config = ServerConfig(auth_mode="api-key", api_key="secret-token")
    app = create_sse_app(config=config, engine=mock_engine)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # /health is exempt
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200

        # /messages without auth fails with 401
        msg_resp = await client.post("/messages")
        assert msg_resp.status_code == 401
        assert msg_resp.json()["error"]["code"] == "auth.unauthorized"

        # /messages with valid auth header passes AuthMiddleware
        # (returns 400/404 from SseServerTransport since session_id query param is missing)
        authed_resp = await client.post(
            "/messages",
            headers={"Authorization": "Bearer secret-token"},
        )
        assert authed_resp.status_code in (400, 404, 202)


def test_mcp_sse_lifespan_lifecycle() -> None:
    """Lifespan manages initialization when engine is provided uninitialized."""
    from starlette.testclient import TestClient

    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.UNINITIALIZED
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()

    async def _init() -> None:
        engine.state = EngineState.READY

    engine.initialize.side_effect = _init

    app = create_sse_app(engine=engine)

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert engine.initialize.called


def test_mcp_sse_lifespan_creates_engine_from_config() -> None:
    """Lifespan creates and shuts down default engine when engine is None."""
    from starlette.testclient import TestClient

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
        patch("mnemo_server.mcp.server.provision_tokenizer", side_effect=RuntimeError("skip")),
    ):
        app = create_sse_app()
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert mock_engine.initialize.called

        assert mock_engine.shutdown.called


def test_run_sse_server_invokes_uvicorn() -> None:
    """run_sse_server forwards host and port to uvicorn.run."""
    with patch("mnemo_server.mcp.server.uvicorn.run") as mock_uvicorn:
        run_sse_server(host="0.0.0.0", port=9000)
        assert mock_uvicorn.called
        call_kwargs = mock_uvicorn.call_args.kwargs
        assert call_kwargs["host"] == "0.0.0.0"
        assert call_kwargs["port"] == 9000
