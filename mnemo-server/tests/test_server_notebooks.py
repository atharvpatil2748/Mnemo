"""Integration and contract tests for /v1/notebooks endpoints."""

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
    Entity,
    FrozenMetadata,
    Insight,
    InsightType,
    Note,
    Notebook,
    NoteOrigin,
    Session,
    Source,
)
from mnemo_server.app import create_app


def _make_mock_engine(*, supports_graph: bool = False) -> MagicMock:
    """Create a mock KnowledgeEngine in READY state with mock storage."""
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
        supports_graph=supports_graph,
        supports_transactions=True,
        supports_health_checks=True,
    )
    mock_engine.storage = storage_mock
    return mock_engine


@pytest.fixture
def mock_engine() -> MagicMock:
    return _make_mock_engine(supports_graph=False)


@pytest.fixture
def mock_graph_engine() -> MagicMock:
    return _make_mock_engine(supports_graph=True)


@pytest.fixture
def app(mock_engine: MagicMock) -> Any:
    application = create_app(engine=mock_engine, provision_tokenizer_on_startup=False)
    application.state.engine = mock_engine
    return application


@pytest.fixture
def graph_app(mock_graph_engine: MagicMock) -> Any:
    application = create_app(engine=mock_graph_engine, provision_tokenizer_on_startup=False)
    application.state.engine = mock_graph_engine
    return application


@pytest.mark.anyio
async def test_create_notebook_success(app: Any, mock_engine: MagicMock) -> None:
    """POST /v1/notebooks creates a notebook and returns 201 Created."""
    mock_engine.storage.upsert_notebook = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "title": "Quantum Computing",
            "description": "Research notes on NISQ algorithms",
            "metadata": {"topic": "physics", "priority": 1},
        }
        resp = await client.post("/v1/notebooks", json=payload)

    assert resp.status_code == 201
    data = resp.json()
    assert "notebook_id" in data
    assert data["title"] == "Quantum Computing"
    assert data["description"] == "Research notes on NISQ algorithms"
    assert data["metadata"] == {"topic": "physics", "priority": 1}
    assert "created_at" in data
    assert "updated_at" in data

    mock_engine.storage.upsert_notebook.assert_awaited_once()
    called_notebook = mock_engine.storage.upsert_notebook.call_args[0][0]
    assert isinstance(called_notebook, Notebook)
    assert called_notebook.title == "Quantum Computing"
    assert called_notebook.description == "Research notes on NISQ algorithms"


@pytest.mark.anyio
async def test_create_notebook_whitespace_title_rejected(app: Any) -> None:
    """POST /v1/notebooks with whitespace title returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/notebooks", json={"title": "   "})

    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "http.validation"


@pytest.mark.anyio
async def test_create_notebook_empty_title_rejected(app: Any) -> None:
    """POST /v1/notebooks with empty title returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/notebooks", json={"title": ""})

    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "http.validation"


@pytest.mark.anyio
async def test_get_notebook_success(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id} returns existing notebook."""
    nid = uuid4()
    now = datetime.now(UTC)
    nb = Notebook(
        notebook_id=nid,
        title="Existing Notebook",
        description="Some description",
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({"tag": "test"}),
    )
    mock_engine.storage.get_notebook = AsyncMock(return_value=nb)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["notebook_id"] == str(nid)
    assert data["title"] == "Existing Notebook"
    assert data["metadata"] == {"tag": "test"}


@pytest.mark.anyio
async def test_get_notebook_not_found(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id} returns 404 with ADR-0049 envelope when missing."""
    nid = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}")

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "contract.not_found"
    assert "was not found" in data["error"]["message"]


@pytest.mark.anyio
async def test_get_notebook_malformed_uuid(app: Any) -> None:
    """GET /v1/notebooks/{id} with malformed UUID returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/notebooks/not-a-valid-uuid")

    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "http.validation"


@pytest.mark.anyio
async def test_update_notebook_partial_title_and_metadata_merge(
    app: Any, mock_engine: MagicMock
) -> None:
    """PATCH /v1/notebooks/{id} partially updates fields and shallow-merges metadata."""
    nid = uuid4()
    now = datetime.now(UTC)
    existing = Notebook(
        notebook_id=nid,
        title="Old Title",
        description="Old Description",
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({"k1": "v1", "k2": "v2"}),
    )
    mock_engine.storage.get_notebook = AsyncMock(return_value=existing)
    mock_engine.storage.upsert_notebook = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        patch_payload = {
            "title": "New Title",
            "metadata": {"k2": "v2_updated", "k3": "v3_new"},
        }
        resp = await client.patch(f"/v1/notebooks/{nid}", json=patch_payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Title"
    assert data["description"] == "Old Description"
    assert data["metadata"] == {"k1": "v1", "k2": "v2_updated", "k3": "v3_new"}

    mock_engine.storage.upsert_notebook.assert_awaited_once()
    called = mock_engine.storage.upsert_notebook.call_args[0][0]
    assert called.title == "New Title"
    assert called.description == "Old Description"
    assert dict(called.metadata) == {"k1": "v1", "k2": "v2_updated", "k3": "v3_new"}


@pytest.mark.anyio
async def test_update_notebook_empty_body_rejected(app: Any) -> None:
    """PATCH /v1/notebooks/{id} with empty body {} returns 422."""
    nid = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/v1/notebooks/{nid}", json={})

    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "http.validation"


@pytest.mark.anyio
async def test_update_notebook_not_found(app: Any, mock_engine: MagicMock) -> None:
    """PATCH /v1/notebooks/{id} on missing notebook returns 404."""
    nid = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/v1/notebooks/{nid}", json={"title": "Updated"})

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_delete_notebook_success(app: Any, mock_engine: MagicMock) -> None:
    """DELETE /v1/notebooks/{id} returns 204 No Content on success."""
    nid = uuid4()
    mock_engine.storage.delete_notebook = AsyncMock(return_value=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/v1/notebooks/{nid}")

    assert resp.status_code == 204
    mock_engine.storage.delete_notebook.assert_awaited_once_with(nid)


@pytest.mark.anyio
async def test_delete_notebook_not_found(app: Any, mock_engine: MagicMock) -> None:
    """DELETE /v1/notebooks/{id} returns 404 if notebook did not exist."""
    nid = uuid4()
    mock_engine.storage.delete_notebook = AsyncMock(return_value=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/v1/notebooks/{nid}")

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_list_notebooks_pagination(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks paginates cleanly with keyset cursor."""
    nb1 = Notebook(
        notebook_id=uuid4(),
        title="NB 1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    nb2 = Notebook(
        notebook_id=uuid4(),
        title="NB 2",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    next_cur = str(uuid4())

    mock_engine.storage.list_notebooks = AsyncMock(
        return_value=Page(items=(nb1, nb2), next_cursor=next_cur)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/notebooks?limit=2")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["title"] == "NB 1"
    assert data["items"][1]["title"] == "NB 2"
    assert data["next_cursor"] == next_cur
    assert data["limit"] == 2


@pytest.mark.anyio
async def test_list_notebooks_invalid_cursor_returns_422(app: Any) -> None:
    """GET /v1/notebooks with non-UUID cursor returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/notebooks?cursor=invalid-cursor-string")

    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "http.validation"


@pytest.mark.anyio
async def test_list_notebooks_limit_bounds_rejected(app: Any) -> None:
    """GET /v1/notebooks with limit=0 or limit=101 returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp0 = await client.get("/v1/notebooks?limit=0")
        assert resp0.status_code == 422

        resp101 = await client.get("/v1/notebooks?limit=101")
        assert resp101.status_code == 422


@pytest.mark.anyio
async def test_get_summary_empty(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id}/summary returns status=empty when no summaries exist."""
    nid = uuid4()
    nb = Notebook(
        notebook_id=nid,
        title="Empty Summary NB",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_engine.storage.get_notebook = AsyncMock(return_value=nb)
    mock_engine.storage.list_insights = AsyncMock(return_value=Page(items=(), next_cursor=None))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["notebook_id"] == str(nid)
    assert data["summaries"] == []
    assert data["status"] == "empty"


@pytest.mark.anyio
async def test_get_summary_with_persisted_insights(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id}/summary returns persisted summary-type insights."""
    nid = uuid4()
    sid = uuid4()
    nb = Notebook(
        notebook_id=nid,
        title="Summary NB",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    summary_insight = Insight(
        insight_id=uuid4(),
        notebook_id=nid,
        source_id=sid,
        type=InsightType.SUMMARY,
        content="This document covers neural networks.",
        confidence=0.95,
        created_at=datetime.now(UTC),
    )
    fact_insight = Insight(
        insight_id=uuid4(),
        notebook_id=nid,
        source_id=sid,
        type=InsightType.KEY_FACT,
        content="Fact 1",
        created_at=datetime.now(UTC),
    )
    mock_engine.storage.get_notebook = AsyncMock(return_value=nb)
    mock_engine.storage.list_insights = AsyncMock(
        return_value=Page(items=(summary_insight, fact_insight), next_cursor=None)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert len(data["summaries"]) == 1
    assert data["summaries"][0]["content"] == "This document covers neural networks."
    assert data["summaries"][0]["confidence"] == 0.95


@pytest.mark.anyio
async def test_get_timeline_chronological_merge(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id}/timeline merges sources, notes, and sessions by timestamp DESC."""
    nid = uuid4()
    nb = Notebook(
        notebook_id=nid,
        title="Timeline NB",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    t1 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    t3 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    source = Source(source_id=uuid4(), notebook_id=nid, document_id=uuid4(), created_at=t1)
    note = Note(
        note_id=uuid4(),
        notebook_id=nid,
        title="Meeting Notes",
        content="Discussed roadmap",
        origin=NoteOrigin.USER,
        created_at=t3,
        updated_at=t3,
    )
    session = Session(
        session_id=uuid4(),
        notebook_id=nid,
        title="Brainstorming",
        created_at=t2,
        updated_at=t2,
    )

    mock_engine.storage.get_notebook = AsyncMock(return_value=nb)
    mock_engine.storage.list_sources = AsyncMock(
        return_value=Page(items=(source,), next_cursor=None)
    )
    mock_engine.storage.list_notes = AsyncMock(return_value=Page(items=(note,), next_cursor=None))
    mock_engine.storage.list_sessions = AsyncMock(
        return_value=Page(items=(session,), next_cursor=None)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}/timeline")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    events = data["events"]
    # Most recent first: note (t3), session (t2), source (t1)
    assert events[0]["event_type"] == "note_created"
    assert events[0]["title"] == "Meeting Notes"
    assert events[1]["event_type"] == "session_started"
    assert events[1]["title"] == "Brainstorming"
    assert events[2]["event_type"] == "source_added"
    assert events[2]["title"] == "Source Added"


@pytest.mark.anyio
async def test_get_graph_disabled_mode(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id}/graph returns status=disabled when supports_graph is False."""
    nid = uuid4()
    nb = Notebook(
        notebook_id=nid,
        title="Graph Disabled NB",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_engine.storage.get_notebook = AsyncMock(return_value=nb)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "disabled"
    assert data["nodes"] == []
    assert data["edges"] == []


@pytest.mark.anyio
async def test_get_graph_enabled_with_entities(
    graph_app: Any, mock_graph_engine: MagicMock
) -> None:
    """GET /v1/notebooks/{id}/graph returns entity nodes and empty edges when active."""
    nid = uuid4()
    doc_id = uuid4()
    nb = Notebook(
        notebook_id=nid,
        title="Graph Active NB",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    source = Source(
        source_id=uuid4(), notebook_id=nid, document_id=doc_id, created_at=datetime.now(UTC)
    )
    entity = Entity(
        entity_id=uuid4(),
        canonical_name="Quantum Computer",
        type="HARDWARE",
        confidence=0.98,
        document_id=doc_id,
        aliases=("QPU",),
    )

    mock_graph_engine.storage.get_notebook = AsyncMock(return_value=nb)
    mock_graph_engine.storage.list_sources = AsyncMock(
        return_value=Page(items=(source,), next_cursor=None)
    )
    mock_graph_engine.storage.find_entities = AsyncMock(return_value=(entity,))

    async with AsyncClient(
        transport=ASGITransport(app=graph_app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/v1/notebooks/{nid}/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["canonical_name"] == "Quantum Computer"
    assert data["nodes"][0]["aliases"] == ["QPU"]
    assert data["edges"] == []


@pytest.mark.anyio
async def test_storage_error_maps_to_503(app: Any, mock_engine: MagicMock) -> None:
    """StorageError raised during route handler maps to HTTP 503 retryable error."""
    mock_engine.storage.list_notebooks = AsyncMock(
        side_effect=StorageError("Database lock acquisition timed out", retryable=True)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/notebooks")

    assert resp.status_code == 503
    data = resp.json()
    assert data["error"]["code"] == "contract.storage"
    assert data["error"]["retryable"] is True


@pytest.mark.anyio
async def test_update_notebook_description_only(app: Any, mock_engine: MagicMock) -> None:
    """PATCH /v1/notebooks/{id} updating only description preserves title and metadata."""
    nid = uuid4()
    now = datetime.now(UTC)
    existing = Notebook(
        notebook_id=nid,
        title="Keep This Title",
        description="Old Description",
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({"tag": "immutable"}),
    )
    mock_engine.storage.get_notebook = AsyncMock(return_value=existing)
    mock_engine.storage.upsert_notebook = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/v1/notebooks/{nid}",
            json={"description": "Updated Description"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Keep This Title"
    assert data["description"] == "Updated Description"
    assert data["metadata"] == {"tag": "immutable"}


@pytest.mark.anyio
async def test_update_notebook_metadata_only(app: Any, mock_engine: MagicMock) -> None:
    """PATCH /v1/notebooks/{id} updating only metadata preserves title and description."""
    nid = uuid4()
    now = datetime.now(UTC)
    existing = Notebook(
        notebook_id=nid,
        title="Title",
        description="Desc",
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({"tag": "old"}),
    )
    mock_engine.storage.get_notebook = AsyncMock(return_value=existing)
    mock_engine.storage.upsert_notebook = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/v1/notebooks/{nid}",
            json={"metadata": {"tag": "new", "extra": 123}},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"] == {"tag": "new", "extra": 123}


@pytest.mark.anyio
async def test_create_notebook_whitespace_description_rejected(app: Any) -> None:
    """POST /v1/notebooks with whitespace-only description returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/notebooks",
            json={"title": "Valid Title", "description": "   "},
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_notebook_whitespace_fields_rejected(app: Any) -> None:
    """PATCH /v1/notebooks/{id} with whitespace-only title or description returns 422."""
    nid = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.patch(f"/v1/notebooks/{nid}", json={"title": "   "})
        assert resp1.status_code == 422

        resp2 = await client.patch(f"/v1/notebooks/{nid}", json={"description": "   "})
        assert resp2.status_code == 422


@pytest.mark.anyio
async def test_get_summary_not_found(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id}/summary returns 404 when notebook missing."""
    nid = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}/summary")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_timeline_not_found(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id}/timeline returns 404 when notebook missing."""
    nid = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}/timeline")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_timeline_defaults_for_missing_titles(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id}/timeline uses fallback titles when note or session title is None."""
    nid = uuid4()
    nb = Notebook(
        notebook_id=nid,
        title="Timeline NB",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    t = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    note = Note(
        note_id=uuid4(),
        notebook_id=nid,
        title=None,
        content="Content",
        origin=NoteOrigin.USER,
        created_at=t,
        updated_at=t,
    )
    session = Session(
        session_id=uuid4(),
        notebook_id=nid,
        title=None,
        created_at=t,
        updated_at=t,
    )
    mock_engine.storage.get_notebook = AsyncMock(return_value=nb)
    mock_engine.storage.list_sources = AsyncMock(return_value=Page(items=(), next_cursor=None))
    mock_engine.storage.list_notes = AsyncMock(return_value=Page(items=(note,), next_cursor=None))
    mock_engine.storage.list_sessions = AsyncMock(
        return_value=Page(items=(session,), next_cursor=None)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}/timeline")

    assert resp.status_code == 200
    events = resp.json()["events"]
    assert any(e["title"] == "Untitled Note" for e in events)
    assert any(e["title"] == "New Conversation" for e in events)


@pytest.mark.anyio
async def test_get_graph_not_found(app: Any, mock_engine: MagicMock) -> None:
    """GET /v1/notebooks/{id}/graph returns 404 when notebook missing."""
    nid = uuid4()
    mock_engine.storage.get_notebook = AsyncMock(return_value=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/notebooks/{nid}/graph")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_graph_enabled_empty_sources(
    graph_app: Any, mock_graph_engine: MagicMock
) -> None:
    """GET /v1/notebooks/{id}/graph returns status=empty when notebook has no sources."""
    nid = uuid4()
    nb = Notebook(
        notebook_id=nid,
        title="Graph Active NB",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_graph_engine.storage.get_notebook = AsyncMock(return_value=nb)
    mock_graph_engine.storage.list_sources = AsyncMock(
        return_value=Page(items=(), next_cursor=None)
    )

    async with AsyncClient(
        transport=ASGITransport(app=graph_app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/v1/notebooks/{nid}/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "empty"
    assert data["nodes"] == []
    assert data["edges"] == []


@pytest.mark.anyio
async def test_get_graph_enabled_no_matching_entities(
    graph_app: Any, mock_graph_engine: MagicMock
) -> None:
    """GET /v1/notebooks/{id}/graph returns status=empty when find_entities returns empty."""
    nid = uuid4()
    doc_id = uuid4()
    nb = Notebook(
        notebook_id=nid,
        title="Graph Active NB",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    source = Source(
        source_id=uuid4(), notebook_id=nid, document_id=doc_id, created_at=datetime.now(UTC)
    )
    mock_graph_engine.storage.get_notebook = AsyncMock(return_value=nb)
    mock_graph_engine.storage.list_sources = AsyncMock(
        return_value=Page(items=(source,), next_cursor=None)
    )
    mock_graph_engine.storage.find_entities = AsyncMock(return_value=())

    async with AsyncClient(
        transport=ASGITransport(app=graph_app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/v1/notebooks/{nid}/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "empty"
    assert data["nodes"] == []
    assert data["edges"] == []
