"""Integration and contract tests for /v1/notebooks/{notebook_id}/sessions endpoints."""

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
    Citation,
    FrozenMetadata,
    Notebook,
    Session,
    Turn,
    TurnRole,
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
async def test_list_sessions_success(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    session_id1 = uuid4()
    session_id2 = uuid4()
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

    sessions = [
        Session(
            session_id=session_id1,
            notebook_id=notebook_id,
            title="Session 1",
            created_at=now,
            updated_at=now,
            turns=(),
            metadata=FrozenMetadata({"tag": "one"}),
        ),
        Session(
            session_id=session_id2,
            notebook_id=notebook_id,
            title="Session 2",
            created_at=now,
            updated_at=now,
            turns=(),
            metadata=FrozenMetadata({"tag": "two"}),
        ),
    ]
    mock_engine.storage.list_sessions = AsyncMock(
        return_value=Page(items=tuple(sessions), next_cursor=str(session_id2))
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/sessions?limit=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["session_id"] == str(session_id1)
    assert data["items"][0]["title"] == "Session 1"
    assert data["items"][0]["metadata"]["tag"] == "one"
    assert data["next_cursor"] == str(session_id2)
    assert data["limit"] == 2


@pytest.mark.anyio
async def test_list_sessions_notebook_not_found(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/sessions")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_list_sessions_invalid_cursor(app: Any, mock_engine: MagicMock) -> None:
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
        response = await client.get(f"/v1/notebooks/{notebook_id}/sessions?cursor=invalid-uuid")

    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_session_success(app: Any, mock_engine: MagicMock) -> None:
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
    mock_engine.storage.upsert_session = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/v1/notebooks/{notebook_id}/sessions",
            json={
                "title": "My New Session",
                "metadata": {"origin": "web", "nested": {"labels": ["one", "two"]}},
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My New Session"
    assert data["notebook_id"] == str(notebook_id)
    assert data["metadata"]["origin"] == "web"
    assert data["metadata"]["nested"] == {"labels": ["one", "two"]}
    assert "session_id" in data
    mock_engine.storage.upsert_session.assert_awaited_once()


@pytest.mark.anyio
async def test_create_session_extra_fields_forbidden(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/v1/notebooks/{notebook_id}/sessions",
            json={"title": "New Session", "extra_field": "disallowed"},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_get_session_with_turns_and_citations(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    session_id = uuid4()
    turn_id = uuid4()
    citation_id = uuid4()
    doc_id = uuid4()
    ver_id = uuid4()
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

    turn = Turn(
        turn_id=turn_id,
        session_id=session_id,
        sequence=0,
        role=TurnRole.ASSISTANT,
        content="Here is the answer [source:1]",
        created_at=now,
        metadata=FrozenMetadata({}),
    )

    mock_engine.storage.get_session = AsyncMock(
        return_value=Session(
            session_id=session_id,
            notebook_id=notebook_id,
            title="Session 1",
            created_at=now,
            updated_at=now,
            turns=(turn,),
            metadata=FrozenMetadata({}),
        )
    )

    citation = Citation(
        citation_id=citation_id,
        turn_id=turn_id,
        source_number=1,
        chunk_id="a" * 64,
        document_id=doc_id,
        version_id=ver_id,
        document_title="Sample Doc",
        verbatim_quote="verbatim quote text",
        created_at=now,
        page_number=12,
        heading_path=("Chapter 1",),
    )
    mock_engine.storage.get_citations_for_turn = AsyncMock(return_value=(citation,))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/sessions/{session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == str(session_id)
    assert len(data["turns"]) == 1
    t = data["turns"][0]
    assert t["turn_id"] == str(turn_id)
    assert t["role"] == "assistant"
    assert len(t["citations"]) == 1
    c = t["citations"][0]
    assert c["citation_id"] == str(citation_id)
    assert c["document_title"] == "Sample Doc"
    assert c["page_number"] == 12
    assert c["heading_path"] == ["Chapter 1"]


@pytest.mark.anyio
async def test_get_session_cross_notebook_idor_protection(app: Any, mock_engine: MagicMock) -> None:
    notebook_a = uuid4()
    notebook_b = uuid4()
    session_id = uuid4()
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

    # Session actually belongs to notebook_b
    mock_engine.storage.get_session = AsyncMock(
        return_value=Session(
            session_id=session_id,
            notebook_id=notebook_b,
            title="Session in NB B",
            created_at=now,
            updated_at=now,
            turns=(),
            metadata=FrozenMetadata({}),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_a}/sessions/{session_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_append_turn_success(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    session_id = uuid4()
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

    existing_turn = Turn(
        turn_id=uuid4(),
        session_id=session_id,
        sequence=0,
        role=TurnRole.USER,
        content="Hello",
        created_at=now,
        metadata=FrozenMetadata({}),
    )

    mock_engine.storage.get_session = AsyncMock(
        return_value=Session(
            session_id=session_id,
            notebook_id=notebook_id,
            title="Session 1",
            created_at=now,
            updated_at=now,
            turns=(existing_turn,),
            metadata=FrozenMetadata({}),
        )
    )
    mock_engine.storage.append_turn = AsyncMock(return_value=None)
    mock_engine.storage.upsert_session = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/v1/notebooks/{notebook_id}/sessions/{session_id}/turns",
            json={
                "role": "assistant",
                "content": "How can I help you?",
                "metadata": {"model": "m"},
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["sequence"] == 1
    assert data["role"] == "assistant"
    assert data["content"] == "How can I help you?"
    assert data["metadata"]["model"] == "m"
    mock_engine.storage.append_turn.assert_awaited_once()
    mock_engine.storage.upsert_session.assert_awaited_once()


@pytest.mark.anyio
async def test_append_turn_empty_content_rejected(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    session_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/v1/notebooks/{notebook_id}/sessions/{session_id}/turns",
            json={"role": "user", "content": ""},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_delete_session_success(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    session_id = uuid4()
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
    mock_engine.storage.get_session = AsyncMock(
        return_value=Session(
            session_id=session_id,
            notebook_id=notebook_id,
            title="Session 1",
            created_at=now,
            updated_at=now,
            turns=(),
            metadata=FrozenMetadata({}),
        )
    )
    mock_engine.storage.delete_session = AsyncMock(return_value=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(f"/v1/notebooks/{notebook_id}/sessions/{session_id}")

    assert response.status_code == 204
    mock_engine.storage.delete_session.assert_awaited_once_with(session_id)


@pytest.mark.anyio
async def test_delete_session_cross_notebook_rejected(app: Any, mock_engine: MagicMock) -> None:
    notebook_a = uuid4()
    notebook_b = uuid4()
    session_id = uuid4()
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
    mock_engine.storage.get_session = AsyncMock(
        return_value=Session(
            session_id=session_id,
            notebook_id=notebook_b,
            title="Session in NB B",
            created_at=now,
            updated_at=now,
            turns=(),
            metadata=FrozenMetadata({}),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(f"/v1/notebooks/{notebook_a}/sessions/{session_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_session_storage_error_maps_to_503(app: Any, mock_engine: MagicMock) -> None:
    notebook_id = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(side_effect=StorageError("disk failure"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/notebooks/{notebook_id}/sessions")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "contract.storage"
