"""Unit tests for get_engine dependency."""

from __future__ import annotations

from typing import Annotated
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo_server.dependencies import get_engine
from mnemo_server.errors import register_error_handlers


def _make_mock_engine(state: EngineState) -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = state
    engine.version = "0.22.0"
    return engine


@pytest.fixture
def dep_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/engine/version")
    async def get_version(
        engine: Annotated[KnowledgeEngine, Depends(get_engine)],
    ) -> dict[str, str]:
        return {"version": getattr(engine, "version", "0.22.0")}

    return app


@pytest.mark.anyio
async def test_get_engine_ready(dep_app: FastAPI) -> None:
    mock_engine = _make_mock_engine(EngineState.READY)
    dep_app.state.engine = mock_engine

    async with AsyncClient(transport=ASGITransport(app=dep_app), base_url="http://test") as client:
        resp = await client.get("/engine/version")
        assert resp.status_code == 200
        assert resp.json() == {"version": "0.22.0"}


@pytest.mark.anyio
async def test_get_engine_missing(dep_app: FastAPI) -> None:
    if hasattr(dep_app.state, "engine"):
        delattr(dep_app.state, "engine")

    async with AsyncClient(transport=ASGITransport(app=dep_app), base_url="http://test") as client:
        resp = await client.get("/engine/version")
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "contract.dependency_unavailable"
        assert "not ready" in data["error"]["message"]


@pytest.mark.parametrize(
    "state",
    [
        EngineState.UNINITIALIZED,
        EngineState.INITIALIZING,
        EngineState.STOPPING,
        EngineState.STOPPED,
        EngineState.FAILED,
    ],
)
@pytest.mark.anyio
async def test_get_engine_non_ready_states(dep_app: FastAPI, state: EngineState) -> None:
    dep_app.state.engine = _make_mock_engine(state)

    async with AsyncClient(transport=ASGITransport(app=dep_app), base_url="http://test") as client:
        resp = await client.get("/engine/version")
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "contract.dependency_unavailable"
