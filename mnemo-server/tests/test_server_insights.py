"""Integration and contract tests for /v1/notebooks/{notebook_id}/insights endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces.errors import StorageError
from mnemo.interfaces.types import Page, StorageCapabilities
from mnemo.models import (
    FrozenMetadata,
    Insight,
    InsightType,
    Notebook,
)
from mnemo_server.app import create_app


def _make_mock_engine() -> MagicMock:
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.READY
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

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
    mock_engine.storage = storage_mock
    return mock_engine


@pytest.fixture
def mock_engine() -> MagicMock:
    return _make_mock_engine()


@pytest.fixture
def app(mock_engine: MagicMock) -> Any:
    application = create_app(engine=mock_engine, provision_tokenizer_on_startup=False)
    application.state.engine = mock_engine
    return application


@pytest.mark.anyio
async def test_list_insights_success(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    source_id = uuid4()
    ins_id1 = uuid4()
    ins_id2 = uuid4()
    now = datetime.now(UTC)

    mock_engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=notebook_id,
            title="Test NB",
            created_at=now,
            updated_at=now,
            description="desc",
            metadata=FrozenMetadata({}),
        )
    )

    insights = [
        Insight(
            insight_id=ins_id1,
            notebook_id=notebook_id,
            source_id=source_id,
            type=InsightType.KEY_FACT,
            content="Fact 1",
            created_at=now,
            confidence=0.95,
            metadata=FrozenMetadata({}),
        ),
        Insight(
            insight_id=ins_id2,
            notebook_id=notebook_id,
            source_id=source_id,
            type=InsightType.CLAIM,
            content="Claim 1",
            created_at=now,
            confidence=0.88,
            metadata=FrozenMetadata({}),
        ),
    ]
    mock_engine.storage.list_insights = AsyncMock(
        return_value=Page(items=tuple(insights), next_cursor=str(ins_id2))
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/insights?limit=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["insight_id"] == str(ins_id1)
    assert data["items"][0]["type"] == "key_fact"
    assert data["items"][0]["confidence"] == 0.95
    assert data["items"][1]["insight_id"] == str(ins_id2)
    assert data["items"][1]["type"] == "claim"
    assert data["next_cursor"] == str(ins_id2)
    assert data["limit"] == 2


@pytest.mark.anyio
async def test_list_insights_with_type_filter(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    source_id = uuid4()
    ins_id1 = uuid4()
    ins_id2 = uuid4()
    now = datetime.now(UTC)

    mock_engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=notebook_id,
            title="Test NB",
            created_at=now,
            updated_at=now,
            description="desc",
            metadata=FrozenMetadata({}),
        )
    )

    insights = [
        Insight(
            insight_id=ins_id1,
            notebook_id=notebook_id,
            source_id=source_id,
            type=InsightType.KEY_FACT,
            content="Fact 1",
            created_at=now,
            confidence=0.95,
            metadata=FrozenMetadata({}),
        ),
        Insight(
            insight_id=ins_id2,
            notebook_id=notebook_id,
            source_id=source_id,
            type=InsightType.CLAIM,
            content="Claim 1",
            created_at=now,
            confidence=0.88,
            metadata=FrozenMetadata({}),
        ),
    ]
    mock_engine.storage.list_insights = AsyncMock(
        return_value=Page(items=tuple(insights), next_cursor=None)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/insights?type=key_fact")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["insight_id"] == str(ins_id1)
    assert data["items"][0]["type"] == "key_fact"


@pytest.mark.anyio
async def test_list_insights_notebook_not_found(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/insights")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_list_insights_invalid_cursor(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    now = datetime.now(UTC)
    mock_engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=notebook_id,
            title="Test NB",
            created_at=now,
            updated_at=now,
            description="desc",
            metadata=FrozenMetadata({}),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/insights?cursor=not-a-valid-uuid")

    assert response.status_code == 422


@pytest.mark.anyio
async def test_generate_insights_returns_501_not_implemented(
    app: Any, mock_engine: MagicMock
) -> None:
    notebook_id = uuid4()
    now = datetime.now(UTC)
    mock_engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=notebook_id,
            title="Test NB",
            created_at=now,
            updated_at=now,
            description="desc",
            metadata=FrozenMetadata({}),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/v1/notebooks/{notebook_id}/insights/generate")

    assert response.status_code == 501
    assert "Phase 10" in response.json()["error"]["message"]


@pytest.mark.anyio
async def test_generate_insights_notebook_not_found(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/v1/notebooks/{notebook_id}/insights/generate")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_insights_storage_error_maps_to_503(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(side_effect=StorageError("database unreachable"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/insights")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "contract.storage"
