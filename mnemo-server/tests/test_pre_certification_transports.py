"""Isolated transport gates for the observation-only process."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import mcp.types as types
import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.engine import EngineState
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.server import create_pre_certification_mcp_server
from mnemo_server.services.pre_certification_observation import ObservationIdentity
from mnemo_server.services.v2_reranker_lifecycle import V2RerankerMode
from test_pre_certification_observation import _identity


def _config(tmp_path: Path) -> ServerConfig:
    return ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_reranker_mode="BGE_V2_M3",
        full_multilingual_v2_model_cache=tmp_path / "cache",
        final_qa_operational_store_path=tmp_path / "operational.db",
        mcp_stdio_principal_subject="local-observer",
        auth_mode="api-key",
        api_key="synthetic-test-only-key",
        delivery_cursor_secret="synthetic-test-only-cursor-key" * 2,
    )


@pytest.mark.anyio
async def test_http_observation_authenticates_and_exposes_no_chat_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mnemo_server.services import pre_certification_observation as observation_module

    config = _config(tmp_path)
    engine = MagicMock()
    engine.state = EngineState.READY
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
    identity = _identity(str(uuid4()))
    authority = SimpleNamespace(observe=AsyncMock())
    core = MagicMock()
    monkeypatch.setattr(
        observation_module,
        "resolve_pre_certification_observation",
        lambda **_kwargs: (core, identity, authority),
    )
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.repository_root", lambda: tmp_path
    )
    composition = SimpleNamespace(
        decision=object(),
        engine_config=core,
        certified_read_only=True,
        embedding_cache_path=None,
    )
    composition.materialize = lambda: composition
    monkeypatch.setattr(
        "mnemo_server.services.production_storage_composition.preflight_production_storage",
        lambda **_kwargs: composition,
    )
    monkeypatch.setattr("mnemo_server.app.KnowledgeEngine", lambda *_args, **_kwargs: engine)
    builder = MagicMock()
    builder.build = AsyncMock(return_value=(object(), object()))
    monkeypatch.setattr(
        "mnemo_server.services.production_store_readiness.ProductionV2ReadinessEvidenceBuilderV1",
        lambda **_kwargs: builder,
    )
    installed = SimpleNamespace(
        reranker=SimpleNamespace(mode=V2RerankerMode.BGE_V2_M3),
        reranker_activation=SimpleNamespace(activate=AsyncMock()),
        exposure_snapshot=object(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(
        "mnemo_server.services.full_multilingual_v2_startup.install_production_full_multilingual_v2",
        AsyncMock(return_value=installed),
    )
    monkeypatch.setattr(
        "mnemo_server.services.durable_reranker_activation.restore_production_reranker_activation",
        AsyncMock(return_value=object()),
    )
    app = create_app(
        server_config=config,
        pre_certification_observation=True,
        provision_tokenizer_on_startup=False,
    )
    assert {route.path for route in app.routes if route.path.startswith("/v1")} == set()
    assert {route.path for route in app.routes if route.path.startswith("/v2")} == set()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        url = "/internal/pre-certification/observe"
        assert (await client.get(url)).status_code == 401
        assert (await client.get(url, headers={"X-API-Key": "wrong"})).status_code == 401
        response = await client.get(url, headers={"X-API-Key": "synthetic-test-only-key"})
        assert response.status_code == 200
        assert response.json()["state"] == "PRE_CERTIFICATION_OBSERVATION"
        assert response.json()["identity"]["credential_generation_id"] == (
            identity.credential_generation_id
        )
        override = await client.get(
            url,
            params={"database_path": "historical.db", "credential_generation_id": str(uuid4())},
            headers={"X-API-Key": "synthetic-test-only-key"},
        )
        assert override.status_code == 200
        assert override.json()["identity"] == response.json()["identity"]
        engine.state = EngineState.UNINITIALIZED
        unavailable = await client.get(url, headers={"X-API-Key": "synthetic-test-only-key"})
        assert unavailable.status_code == 503
        engine.state = EngineState.READY
        assert (
            await client.post(
                "/v2/notebooks/example/final-qa",
                headers={"X-API-Key": "synthetic-test-only-key"},
                json={},
            )
        ).status_code == 404
        assert (
            await client.post(
                "/v1/notebooks",
                headers={"X-API-Key": "synthetic-test-only-key"},
                json={},
            )
        ).status_code == 404
    assert authority.observe.await_count == 2


def test_observation_http_rejects_injected_or_non_v2_runtime(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with pytest.raises(RuntimeError, match="INJECTED_RUNTIME_REJECTED"):
        create_app(
            server_config=config,
            engine=MagicMock(),
            pre_certification_observation=True,
        )


@pytest.mark.anyio
async def test_mcp_observer_exposes_one_tool_and_rejects_anonymous() -> None:
    identity: ObservationIdentity = _identity(str(uuid4()))
    authority = SimpleNamespace(observe=AsyncMock())
    engine = SimpleNamespace(state=EngineState.READY)
    runtime = SimpleNamespace(reranker=SimpleNamespace(mode=V2RerankerMode.BGE_V2_M3))
    from mnemo_server.services.authorization import principal_from_claims

    principal = principal_from_claims({"sub": "local-observer"})
    server = create_pre_certification_mcp_server(
        principal_provider=lambda: principal,
        runtime_provider=lambda: (engine, runtime, identity, authority),
        transport="stdio",
    )
    listed = await server.request_handlers[types.ListToolsRequest](
        types.ListToolsRequest(method="tools/list")
    )
    result = getattr(listed, "root", listed)
    assert [tool.name for tool in result.tools] == ["observe_runtime"]
    called = await server.request_handlers[types.CallToolRequest](
        types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name="observe_runtime", arguments={}),
        )
    )
    call_result = getattr(called, "root", called)
    assert call_result.isError is not True
    authority.observe.assert_awaited_once()
    unknown = await server.request_handlers[types.CallToolRequest](
        types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name="write_notebook", arguments={}),
        )
    )
    unknown_result = getattr(unknown, "root", unknown)
    assert unknown_result.isError is True
    anonymous = create_pre_certification_mcp_server(
        principal_provider=lambda: principal_from_claims(None),
        runtime_provider=lambda: (engine, runtime, identity, authority),
        transport="sse",
    )
    rejected = await anonymous.request_handlers[types.CallToolRequest](
        types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name="observe_runtime", arguments={}),
        )
    )
    rejection = getattr(rejected, "root", rejected)
    assert rejection.isError is True
