"""Unit tests for FastAPI app creation, lifespan, CORS, and health check."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo import __version__
from mnemo.engine import EngineInitializationError, EngineState, KnowledgeEngine
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig


def _make_mock_engine(
    *,
    initialize_side_effect: Exception | None = None,
    shutdown_side_effect: Exception | None = None,
) -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.UNINITIALIZED
    engine.version = __version__

    storage_mock = MagicMock()
    storage_mock.health_check = AsyncMock(return_value=())
    engine.storage = storage_mock

    emb_mock = MagicMock()
    emb_mock.health_check = AsyncMock(
        return_value=MagicMock(
            component="emb", healthy=True, checked_at=datetime.now(UTC), detail=None
        )
    )
    engine.embedding_provider = emb_mock

    llm_mock = MagicMock()
    llm_mock.health_check = AsyncMock(
        return_value=MagicMock(
            component="llm", healthy=True, checked_at=datetime.now(UTC), detail=None
        )
    )
    engine.llm = MagicMock(return_value=llm_mock)

    async def mock_initialize() -> None:
        if initialize_side_effect:
            engine.state = EngineState.FAILED
            raise initialize_side_effect
        engine.state = EngineState.READY

    async def mock_shutdown() -> None:
        if shutdown_side_effect:
            raise shutdown_side_effect
        engine.state = EngineState.STOPPED

    engine.initialize = AsyncMock(side_effect=mock_initialize)
    engine.shutdown = AsyncMock(side_effect=mock_shutdown)
    return engine


@pytest.mark.anyio
async def test_app_lifespan_success() -> None:
    mock_engine = _make_mock_engine()
    config = ServerConfig(cors_origins=("https://app.mnemo.local",))
    app = create_app(
        server_config=config,
        engine=mock_engine,
        provision_tokenizer_on_startup=False,
    )

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        # Verify engine was initialized
        mock_engine.initialize.assert_awaited_once()
        assert app.state.engine is mock_engine
        assert app.state.engine.state is EngineState.READY
        assert app.state.server_config is config

        # Test /health and /v1/health
        resp1 = await client.get("/health")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "ok"
        assert data1["version"] == __version__
        assert data1["engine_state"] == "ready"

        resp2 = await client.get("/v1/health")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"

    # After lifespan exit, engine shutdown must be called and state cleared
    mock_engine.shutdown.assert_awaited_once()
    assert getattr(app.state, "engine", None) is None


@pytest.mark.anyio
async def test_app_lifespan_initialization_failure() -> None:
    mock_engine = _make_mock_engine(
        initialize_side_effect=EngineInitializationError("Backend unavailable")
    )
    app = create_app(engine=mock_engine, provision_tokenizer_on_startup=False)

    with pytest.raises(EngineInitializationError):
        async with app.router.lifespan_context(app):
            pass

    assert getattr(app.state, "engine", None) is None


@pytest.mark.anyio
async def test_app_cors_headers() -> None:
    mock_engine = _make_mock_engine()
    config = ServerConfig(cors_origins=("https://allowed.example.com",))
    app = create_app(
        server_config=config,
        engine=mock_engine,
        provision_tokenizer_on_startup=False,
    )

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        # Request with Origin header
        resp = await client.get(
            "/health",
            headers={"Origin": "https://allowed.example.com"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "https://allowed.example.com"
        assert resp.headers.get("access-control-allow-credentials") == "true"

        # Preflight OPTIONS request
        options_resp = await client.options(
            "/health",
            headers={
                "Origin": "https://allowed.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert options_resp.status_code == 200
        assert (
            options_resp.headers.get("access-control-allow-origin") == "https://allowed.example.com"
        )


def test_main_run() -> None:
    from unittest.mock import patch

    from mnemo_server import main

    with patch("uvicorn.run") as mock_uvicorn_run:
        main.run()
        mock_uvicorn_run.assert_called_once_with(
            "mnemo_server.main:app",
            host="127.0.0.1",
            port=8000,
            log_level="info",
            reload=False,
            workers=1,
        )
