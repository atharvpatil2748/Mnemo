"""Integration and contract tests for /v1/notebooks/{notebook_id}/notes endpoints."""

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
    Note,
    Notebook,
    NoteOrigin,
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
async def test_list_notes_success(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    note_id1 = uuid4()
    note_id2 = uuid4()
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

    notes = [
        Note(
            note_id=note_id1,
            notebook_id=notebook_id,
            title="Note 1",
            content="Content 1",
            origin=NoteOrigin.USER,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({}),
        ),
        Note(
            note_id=note_id2,
            notebook_id=notebook_id,
            title="Note 2",
            content="Content 2",
            origin=NoteOrigin.GENERATED,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({}),
        ),
    ]
    mock_engine.storage.list_notes = AsyncMock(
        return_value=Page(items=tuple(notes), next_cursor=str(note_id2))
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/notes?limit=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["note_id"] == str(note_id1)
    assert data["items"][0]["origin"] == "user"
    assert data["items"][1]["note_id"] == str(note_id2)
    assert data["items"][1]["origin"] == "generated"
    assert data["next_cursor"] == str(note_id2)
    assert data["limit"] == 2


@pytest.mark.anyio
async def test_list_notes_notebook_not_found(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/notes")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_list_notes_invalid_cursor(app: Any, mock_engine: MagicMock) -> None:
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
        response = await client.get(f"/v1/notebooks/{notebook_id}/notes?cursor=not-a-uuid")

    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_note_success(app: Any, mock_engine: MagicMock) -> None:
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
    mock_engine.storage.upsert_note = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/v1/notebooks/{notebook_id}/notes",
            json={
                "title": "My Note",
                "content": "Key takeaways from chapter 1",
                "origin": "user",
                "metadata": {"importance": "high", "nested": {"labels": ["one", "two"]}},
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My Note"
    assert data["content"] == "Key takeaways from chapter 1"
    assert data["origin"] == "user"
    assert data["metadata"]["importance"] == "high"
    assert data["metadata"]["nested"] == {"labels": ["one", "two"]}
    assert "note_id" in data
    mock_engine.storage.upsert_note.assert_awaited_once()


@pytest.mark.anyio
async def test_create_note_empty_content_rejected(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/v1/notebooks/{notebook_id}/notes",
            json={"title": "My Note", "content": ""},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_get_note_success(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    note_id = uuid4()
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
    mock_engine.storage.get_note = AsyncMock(
        return_value=Note(
            note_id=note_id,
            notebook_id=notebook_id,
            title="Note 1",
            content="Content 1",
            origin=NoteOrigin.USER,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({"k": "v"}),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/notes/{note_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["note_id"] == str(note_id)
    assert data["title"] == "Note 1"
    assert data["metadata"]["k"] == "v"


@pytest.mark.anyio
async def test_get_note_cross_notebook_idor_protection(app: Any, mock_engine: MagicMock) -> None:
    notebook_a = uuid4()
    notebook_b = uuid4()
    note_id = uuid4()
    now = datetime.now(UTC)

    mock_engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=notebook_a,
            title="Test NB A",
            created_at=now,
            updated_at=now,
            description="desc",
            metadata=FrozenMetadata({}),
        )
    )
    mock_engine.storage.get_note = AsyncMock(
        return_value=Note(
            note_id=note_id,
            notebook_id=notebook_b,
            title="Note in NB B",
            content="Content in NB B",
            origin=NoteOrigin.USER,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({}),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_a}/notes/{note_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_update_note_success(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    note_id = uuid4()
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
    mock_engine.storage.get_note = AsyncMock(
        return_value=Note(
            note_id=note_id,
            notebook_id=notebook_id,
            title="Old Title",
            content="Old Content",
            origin=NoteOrigin.USER,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({}),
        )
    )
    mock_engine.storage.upsert_note = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/v1/notebooks/{notebook_id}/notes/{note_id}",
            json={"title": "Updated Title", "content": "Updated Content"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["content"] == "Updated Content"
    mock_engine.storage.upsert_note.assert_awaited_once()


@pytest.mark.anyio
async def test_update_note_empty_patch_rejected(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    note_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/v1/notebooks/{notebook_id}/notes/{note_id}",
            json={},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_delete_note_success(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    note_id = uuid4()
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
    mock_engine.storage.get_note = AsyncMock(
        return_value=Note(
            note_id=note_id,
            notebook_id=notebook_id,
            title="Note 1",
            content="Content 1",
            origin=NoteOrigin.USER,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({}),
        )
    )
    mock_engine.storage.delete_note = AsyncMock(return_value=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(f"/v1/notebooks/{notebook_id}/notes/{note_id}")

    assert response.status_code == 204
    mock_engine.storage.delete_note.assert_awaited_once_with(note_id)


@pytest.mark.anyio
async def test_delete_note_cross_notebook_rejected(app: Any, mock_engine: MagicMock) -> None:
    notebook_a = uuid4()
    notebook_b = uuid4()
    note_id = uuid4()
    now = datetime.now(UTC)

    mock_engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=notebook_a,
            title="Test NB A",
            created_at=now,
            updated_at=now,
            description="desc",
            metadata=FrozenMetadata({}),
        )
    )
    mock_engine.storage.get_note = AsyncMock(
        return_value=Note(
            note_id=note_id,
            notebook_id=notebook_b,
            title="Note in NB B",
            content="Content in NB B",
            origin=NoteOrigin.USER,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({}),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(f"/v1/notebooks/{notebook_a}/notes/{note_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_note_storage_error_maps_to_503(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(side_effect=StorageError("disk failure"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/notes")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "contract.storage"
