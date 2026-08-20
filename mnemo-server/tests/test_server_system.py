"""Integration and contract tests for /v1/health, /v1/config, and /v1/jobs system endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.config import MnemoConfig
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import (
    HealthStatus,
    StorageCapabilities,
    StorageError,
)
from mnemo_server.app import create_app
from mnemo_server.schemas.system import JobStatus
from mnemo_server.services import JobService


def _make_mock_engine(*, config: MnemoConfig | None = None) -> MagicMock:
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.READY
    mock_engine.version = "0.25.0"
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

    # Core config
    if config is None:
        mock_engine.config = MnemoConfig.model_validate(
            {
                "llm": {
                    "planner": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                    "synthesizer": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                    "extractor": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                    "classifier": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                },
                "embedding": {
                    "provider": "ollama",
                    "model": "nomic-embed-text",
                    "dimensions": 768,
                },
                "reranker": {
                    "provider": "cross-encoder",
                    "model": "ms-marco-MiniLM-L-6-v2",
                },
            }
        )
    else:
        mock_engine.config = config

    # Storage health
    storage_mock = MagicMock()
    storage_mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=True,
        supports_dense_search=True,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=False,
        supports_transactions=True,
        supports_health_checks=True,
    )
    now = datetime.now(UTC)
    storage_mock.health_check = AsyncMock(
        return_value=(
            HealthStatus(component="sqlite", healthy=True, checked_at=now),
            HealthStatus(component="filesystem", healthy=True, checked_at=now),
        )
    )
    mock_engine.storage = storage_mock

    # Embedding health
    emb_mock = MagicMock()
    emb_mock.health_check = AsyncMock(
        return_value=HealthStatus(component="ollama", healthy=True, checked_at=now)
    )
    mock_engine.embedding_provider = emb_mock

    # LLM health
    llm_planner = MagicMock()
    llm_planner.health_check = AsyncMock(
        return_value=HealthStatus(component="ollama_planner", healthy=True, checked_at=now)
    )
    llm_synth = MagicMock()
    llm_synth.health_check = AsyncMock(
        return_value=HealthStatus(component="ollama_synthesizer", healthy=True, checked_at=now)
    )

    def _llm_side_effect(role: str) -> MagicMock:
        if role == "planner":
            return llm_planner
        return llm_synth

    mock_engine.llm = MagicMock(side_effect=_llm_side_effect)

    return mock_engine


@pytest.fixture
def mock_engine() -> MagicMock:
    return _make_mock_engine()


@pytest.fixture
def app(mock_engine: MagicMock) -> Any:
    application = create_app(engine=mock_engine, provision_tokenizer_on_startup=False)
    application.state.engine = mock_engine
    application.state.job_service = JobService()
    return application


@pytest.mark.anyio
async def test_health_check_all_healthy(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["healthy"] is True
    assert data["version"] == "0.25.0"
    assert data["engine_state"] == "ready"
    assert len(data["components"]) >= 3
    components_map = {c["component"]: c["healthy"] for c in data["components"]}
    assert components_map["storage.sqlite"] is True
    assert components_map["storage.filesystem"] is True
    assert components_map["embedding.ollama"] is True
    assert components_map["llm.planner"] is True
    assert components_map["llm.synthesizer"] is True


@pytest.mark.anyio
async def test_health_check_storage_error_degraded(app: Any, mock_engine: MagicMock) -> None:
    mock_engine.storage.health_check = AsyncMock(side_effect=StorageError("Database corrupted"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["healthy"] is False
    storage_comp = next(c for c in data["components"] if c["component"] == "storage")
    assert storage_comp["healthy"] is False
    assert "Database corrupted" in storage_comp["detail"]


@pytest.mark.anyio
async def test_health_check_embedding_error_degraded(app: Any, mock_engine: MagicMock) -> None:
    mock_engine.embedding_provider.health_check = AsyncMock(
        side_effect=RuntimeError("Embedding model offline")
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["healthy"] is False
    emb_comp = next(c for c in data["components"] if c["component"] == "embedding")
    assert emb_comp["healthy"] is False
    assert "Embedding model offline" in emb_comp["detail"]


@pytest.mark.anyio
async def test_health_check_llm_error_degraded(app: Any, mock_engine: MagicMock) -> None:
    llm_bad = MagicMock()
    llm_bad.health_check = AsyncMock(side_effect=RuntimeError("Ollama connection refused"))
    mock_engine.llm = MagicMock(return_value=llm_bad)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["healthy"] is False


@pytest.mark.anyio
async def test_health_check_legacy_alias(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["healthy"] is True


@pytest.mark.anyio
async def test_get_config_success_and_secrets_redacted(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/config")

    assert resp.status_code == 200
    data = resp.json()
    assert "server" in data
    assert data["server"]["host"] == "127.0.0.1"
    assert data["server"]["port"] == 8000
    assert "storage" in data
    assert data["storage"]["sqlite"]["enabled"] is True
    assert data["storage"]["qdrant"]["api_key_configured"] is False
    # Verify no plaintext secrets
    assert "password" not in str(data["storage"]["surrealdb"])
    assert (
        "api_key" not in str(data["storage"]["qdrant"])
        or "api_key_configured" in data["storage"]["qdrant"]
    )
    assert "llm" in data
    assert data["llm"]["planner"]["provider"] == "ollama"
    assert "embedding" in data
    assert data["embedding"]["dimensions"] == 768
    assert "reranker" in data
    assert data["reranker"]["model"] == "ms-marco-MiniLM-L-6-v2"


@pytest.mark.anyio
async def test_get_config_models_success(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/config/models")

    assert resp.status_code == 200
    data = resp.json()
    assert "llm" in data
    assert data["llm"]["planner"]["model"] == "qwen2.5:7b-instruct"
    assert data["llm"]["synthesizer"]["model"] == "qwen2.5:7b-instruct"
    assert "embedding" in data
    assert data["embedding"]["model"] == "nomic-embed-text"
    assert "reranker" in data
    assert data["reranker"]["model"] == "ms-marco-MiniLM-L-6-v2"


@pytest.mark.anyio
async def test_patch_config_success(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/v1/config",
            json={
                "log_level": "debug",
                "max_upload_bytes": 104857600,
                "cors_origins": ["https://app.custom.local"],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["server"]["log_level"] == "debug"
    assert data["server"]["max_upload_bytes"] == 104857600
    assert data["server"]["cors_origins"] == ["https://app.custom.local"]


@pytest.mark.anyio
async def test_patch_config_empty_rejected(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch("/v1/config", json={})

    assert resp.status_code == 422


@pytest.mark.anyio
async def test_patch_config_extra_field_forbidden(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch("/v1/config", json={"unknown_key": "forbidden"})

    assert resp.status_code == 422


@pytest.mark.anyio
async def test_list_jobs_empty(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/jobs")

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["next_cursor"] is None
    assert data["limit"] == 20


@pytest.mark.anyio
async def test_job_lifecycle_operations(app: Any, mock_engine: MagicMock) -> None:
    job_service = app.state.job_service
    job1 = await job_service.create_job(
        "ingestion",
        detail="Ingesting research paper",
        metadata={"filename": "paper.pdf"},
    )
    _job2 = await job_service.create_job(
        "reindex",
        detail="Reindexing vectors",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Get Job 1
        resp = await client.get(f"/v1/jobs/{job1.job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == str(job1.job_id)
        assert data["job_type"] == "ingestion"
        assert data["status"] == "queued"
        assert data["detail"] == "Ingesting research paper"

        # Update Job 1 to running then completed
        await job_service.update_job(
            job1.job_id,
            status=JobStatus.RUNNING,
            progress=0.5,
            detail="Parsed 50%",
        )
        resp = await client.get(f"/v1/jobs/{job1.job_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert resp.json()["progress"] == 0.5

        await job_service.update_job(
            job1.job_id,
            status=JobStatus.COMPLETED,
            progress=1.0,
            detail="Done",
        )
        resp = await client.get(f"/v1/jobs/{job1.job_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        assert resp.json()["completed_at"] is not None

        # List all jobs
        resp = await client.get("/v1/jobs")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2

        # List with status filter
        resp = await client.get("/v1/jobs?status=completed")
        assert resp.status_code == 200
        completed_items = resp.json()["items"]
        assert len(completed_items) == 1
        assert completed_items[0]["job_id"] == str(job1.job_id)


@pytest.mark.anyio
async def test_get_job_not_found(app: Any, mock_engine: MagicMock) -> None:
    nonexistent_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/jobs/{nonexistent_id}")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_list_jobs_invalid_cursor(app: Any, mock_engine: MagicMock) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/jobs?cursor=invalid-uuid-format")

    assert resp.status_code == 422
