"""Unit and integration tests for Mnemo MCP SSE transport (Module 8.1)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
import uvicorn
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mnemo import EngineState, KnowledgeEngine, MnemoConfig, __version__
from mnemo.interfaces import Page
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.server import create_sse_app, run_sse_server


@pytest.fixture
def mock_engine() -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
    return engine


def _synthetic_config(tmp_path: Path) -> MnemoConfig:
    """Keep lifecycle tests away from the repository's certified DB."""
    repository = Path(__file__).resolve().parents[2]
    source = repository / "mnemo.toml"
    document = source.read_text(encoding="utf-8")
    document = document.replace(
        "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db",
        "synthetic/mnemo.db",
    ).replace("data/canonical_production/blobs", "synthetic/blobs")
    target = tmp_path / "mnemo.toml"
    target.write_text(document, encoding="utf-8")
    profile = tmp_path / "config/model_profiles/full_multilingual_v2_profiles.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_bytes(
        (repository / "config/model_profiles/full_multilingual_v2_profiles.toml").read_bytes()
    )
    return MnemoConfig.from_file(target)


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
    config = ServerConfig(
        auth_mode="api-key", api_key="secret-token", delivery_cursor_secret="c" * 32
    )
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


@pytest.mark.anyio
async def test_local_sse_tool_error_uses_typed_sanitized_result(
    mock_engine: MagicMock, tmp_path: Path
) -> None:
    """Exercise the actual SSE wire transport on a disposable loopback port."""
    config = ServerConfig(
        auth_mode="api-key", api_key="fixture-only-token", delivery_cursor_secret="c" * 32
    )
    mock_engine.storage.list_notebooks = AsyncMock(return_value=Page(items=(), next_cursor=None))
    app = create_sse_app(
        config=config, engine=mock_engine, mnemo_config=_synthetic_config(tmp_path)
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="on", log_level="error")
    )
    async with anyio.create_task_group() as tasks:
        tasks.start_soon(server.serve)
        try:
            with anyio.fail_after(20):
                while not server.started:
                    await anyio.sleep(0.05)
                assert server.servers
                port = server.servers[0].sockets[0].getsockname()[1]
                async with (
                    sse_client(
                        f"http://127.0.0.1:{port}/sse",
                        headers={"Authorization": "Bearer fixture-only-token"},
                    ) as (read_stream, write_stream),
                    ClientSession(read_stream, write_stream) as client,
                ):
                    await client.initialize()
                    inventory = await client.call_tool("list_notebooks", {"limit": 1})
                    assert not inventory.isError
                    assert json.loads(inventory.content[0].text)["notebooks"] == []
                    result = await client.call_tool("unknown_fixture_tool", {})
                    assert result.isError
                    error = json.loads(result.content[0].text)["error"]
                    assert error["category"] == "invalid_input"
                    assert error["message"] == "Request is invalid"
                    assert "unknown_fixture_tool" not in result.content[0].text
                    assert "fixture-only-token" not in result.content[0].text
        finally:
            server.should_exit = True


def test_mcp_sse_lifespan_lifecycle(tmp_path: Path) -> None:
    """Lifespan manages initialization when engine is provided uninitialized."""
    from starlette.testclient import TestClient

    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.UNINITIALIZED
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()

    async def _init() -> None:
        engine.state = EngineState.READY

    engine.initialize.side_effect = _init

    app = create_sse_app(engine=engine, mnemo_config=_synthetic_config(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert engine.initialize.called


def test_mcp_sse_lifespan_publishes_and_closes_v2_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A ready injected engine receives the governed V2 runtime during SSE startup."""
    from starlette.testclient import TestClient

    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.shutdown = AsyncMock()
    installed = SimpleNamespace(close=AsyncMock())
    installer = AsyncMock(return_value=installed)
    monkeypatch.setattr("mnemo_server.mcp.server._install_v2_if_enabled", installer)
    synthetic_config = _synthetic_config(tmp_path)
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.resolve_certified_production_binding",
        lambda **_kwargs: (synthetic_config, SimpleNamespace(binding_id="synthetic-test-binding")),
    )
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.record_certified_transport_startup",
        lambda **_kwargs: tmp_path / "synthetic-observation.json",
    )
    engine.certified_read_only = True
    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="key",
        delivery_cursor_secret="x" * 32,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "operational.db",
        mcp_stdio_principal_subject="stdio",
    )
    app = create_sse_app(config=config, engine=engine, mnemo_config=synthetic_config)
    with TestClient(app) as client:
        assert client.get("/health").json()["engine_state"] == "ready"
        assert app.state.full_multilingual_v2_runtime is installed
    installed.close.assert_awaited_once()


def test_certified_sse_rejects_injected_historical_model_before_exposure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from starlette.testclient import TestClient

    certified = _synthetic_config(tmp_path)
    historical = certified.model_copy(
        update={"embedding": certified.embedding.model_copy(update={"model": "historical-v1"})}
    )
    engine = MagicMock(spec=KnowledgeEngine)
    engine.config = historical
    engine.certified_read_only = True
    engine.state = EngineState.READY
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.resolve_certified_production_binding",
        lambda **_kwargs: (certified, SimpleNamespace(binding_id="synthetic-binding")),
    )
    config = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "operational.db",
        mcp_stdio_principal_subject="stdio",
        auth_mode="api-key",
        api_key="synthetic-key",
        delivery_cursor_secret="x" * 32,
    )
    app = create_sse_app(config=config, engine=engine, mnemo_config=certified)
    with (
        pytest.raises(RuntimeError, match="INJECTED_PRODUCTION_RUNTIME_MISMATCH"),
        TestClient(app),
    ):
        pass
    assert not (tmp_path / "operational.db").exists()


def test_mcp_sse_lifespan_creates_engine_from_config(tmp_path: Path) -> None:
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
        patch("mnemo_server.mcp.server.KnowledgeEngine", return_value=mock_engine),
        patch("mnemo_server.mcp.server.provision_tokenizer", side_effect=RuntimeError("skip")),
    ):
        app = create_sse_app(mnemo_config=_synthetic_config(tmp_path))
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
