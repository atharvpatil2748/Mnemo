"""Unit tests for the CompositeStorage atomic router."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from mnemo.interfaces.errors import ContractValidationError, StorageError
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.interfaces.types import (
    HealthStatus,
    StorageCapabilities,
)
from mnemo.models import (
    Chunk,
    ChunkPosition,
    ChunkType,
    FrozenMetadata,
)
from mnemo.storage.composite import CompositeStorage


def _chunk() -> Chunk:
    return Chunk(
        id="a" * 64,
        document_id=uuid4(),
        version_id=uuid4(),
        text="abc",
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        heading_path=(),
        parent_chunk_id=None,
        sibling_ids=(),
        metadata=FrozenMetadata(),
    )


@pytest.fixture
def fs_mock() -> StorageInterfaceV1:
    mock = AsyncMock(spec=StorageInterfaceV1)
    mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=True,
        supports_dense_search=False,
        supports_sparse_search=False,
        supports_metadata=False,
        supports_graph=False,
        supports_transactions=False,
        supports_health_checks=True,
    )
    return mock


@pytest.fixture
def sql_mock() -> StorageInterfaceV1:
    mock = AsyncMock(spec=StorageInterfaceV1)
    mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=False,
        supports_dense_search=False,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=False,
        supports_transactions=True,
        supports_health_checks=True,
    )
    return mock


@pytest.fixture
def qdr_mock() -> StorageInterfaceV1:
    mock = AsyncMock(spec=StorageInterfaceV1)
    mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=False,
        supports_dense_search=True,
        supports_sparse_search=False,
        supports_metadata=False,
        supports_graph=False,
        supports_transactions=False,
        supports_health_checks=True,
    )
    return mock


@pytest.fixture
def sur_mock() -> StorageInterfaceV1:
    mock = AsyncMock(spec=StorageInterfaceV1)
    mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=False,
        supports_dense_search=False,
        supports_sparse_search=False,
        supports_metadata=False,
        supports_graph=True,
        supports_transactions=False,
        supports_health_checks=True,
    )
    return mock


@pytest.fixture
def composite(
    fs_mock: StorageInterfaceV1,
    sql_mock: StorageInterfaceV1,
    qdr_mock: StorageInterfaceV1,
    sur_mock: StorageInterfaceV1,
) -> CompositeStorage:
    return CompositeStorage(
        filesystem=fs_mock,
        sqlite=sql_mock,
        qdrant=qdr_mock,
        surrealdb=sur_mock,
    )


@pytest.mark.anyio
async def test_open_closes_on_failure(
    composite: CompositeStorage,
    fs_mock: Mock,
    sql_mock: Mock,
) -> None:
    """Test that open gracefully closes backends if one fails."""
    sql_mock.open.side_effect = Exception("DB error")

    with pytest.raises(StorageError, match="Failed to open composite storage"):
        await composite.open()

    fs_mock.open.assert_awaited_once()
    sql_mock.open.assert_awaited_once()
    fs_mock.close.assert_awaited_once()
    sql_mock.close.assert_awaited_once()


@pytest.mark.anyio
async def test_close_aggregates_errors(
    composite: CompositeStorage,
    fs_mock: Mock,
    sql_mock: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that close ignores errors from backends and continues."""
    fs_mock.close.side_effect = Exception("FS close error")
    sql_mock.close.side_effect = Exception("SQL close error")

    await composite.close()

    assert "FS close error" in caplog.text
    assert "SQL close error" in caplog.text


@pytest.mark.anyio
async def test_health_check_aggregates(
    composite: CompositeStorage,
    fs_mock: Mock,
    sql_mock: Mock,
    qdr_mock: Mock,
    sur_mock: Mock,
) -> None:
    """Test that health check results are aggregated."""
    now = datetime.now(UTC)
    fs_mock.health_check.return_value = (
        HealthStatus(healthy=True, component="fs", checked_at=now),
    )
    sql_mock.health_check.return_value = (
        HealthStatus(healthy=False, component="sql", checked_at=now),
    )
    qdr_mock.health_check.return_value = (
        HealthStatus(healthy=True, component="qdrant", checked_at=now),
    )
    sur_mock.health_check.return_value = (
        HealthStatus(healthy=True, component="surrealdb", checked_at=now),
    )

    results = await composite.health_check()
    assert len(results) == 4


def test_capabilities_aggregation(composite: CompositeStorage) -> None:
    """Test that capabilities merge correctly across all backends."""
    caps = composite.capabilities()
    assert caps.supports_blobs is True
    assert caps.supports_transactions is True
    assert caps.supports_dense_search is True
    assert caps.supports_sparse_search is True
    assert caps.supports_graph is True


@pytest.mark.anyio
async def test_single_backend_delegation(
    composite: CompositeStorage,
    fs_mock: Mock,
    sql_mock: Mock,
) -> None:
    """Test single backend routing with success and error translation."""
    asset_id = uuid4()
    fs_mock.get_asset.return_value = b"data"

    data = await composite.get_asset(asset_id)
    assert data == b"data"
    fs_mock.get_asset.assert_awaited_once_with(asset_id)

    fs_mock.delete_asset.side_effect = StorageError("Unknown OS error")
    with pytest.raises(StorageError):
        await composite.delete_asset(asset_id)


@pytest.mark.anyio
async def test_metadata_and_blob_operations_route_to_owners(
    composite: CompositeStorage,
    fs_mock: Mock,
    sql_mock: Mock,
) -> None:
    """Facade operations delegate only to the backend owning each record family."""
    identity = uuid4()
    record = Mock()

    await composite.put_asset(b"data", "text/plain", FrozenMetadata())
    await composite.put_parsed_document(identity, record)
    await composite.get_parsed_document(identity)
    await composite.contains_hash("a" * 64)
    await composite.upsert_document(record)
    await composite.get_document(identity)
    await composite.list_documents(None, 10, None)
    await composite.delete_document(identity, None)
    await composite.upsert_notebook(record)
    await composite.get_notebook(identity)
    await composite.list_notebooks(10, None)
    await composite.delete_notebook(identity)
    await composite.upsert_source(record)
    await composite.get_source(identity)
    await composite.delete_source(identity)
    await composite.list_sources(identity, 10, None)
    await composite.upsert_note(record)
    await composite.get_note(identity)
    await composite.delete_note(identity)
    await composite.list_notes(identity, 10, None)
    await composite.upsert_insight(record)
    await composite.get_insight(identity)
    await composite.delete_insight(identity)
    await composite.list_insights(identity, 10, None)
    await composite.upsert_session(record)
    await composite.get_session(identity)
    await composite.list_sessions(identity, 10, None)
    await composite.append_turn(identity, record)
    await composite.list_turns(identity, None, 10)
    await composite.upsert_citation(record)
    await composite.get_citations_for_turn(identity)
    await composite.delete_session(identity)

    fs_mock.put_asset.assert_awaited_once_with(b"data", "text/plain", FrozenMetadata())
    fs_mock.put_parsed_document.assert_awaited_once_with(identity, record)
    fs_mock.get_parsed_document.assert_awaited_once_with(identity)
    fs_mock.contains_hash.assert_awaited_once_with("a" * 64)
    sql_mock.upsert_document.assert_awaited_once_with(record)
    sql_mock.get_document.assert_awaited_once_with(identity)
    sql_mock.list_documents.assert_awaited_once_with(None, 10, None)
    sql_mock.delete_document.assert_awaited_once_with(identity, None)
    sql_mock.upsert_notebook.assert_awaited_once_with(record)
    sql_mock.get_notebook.assert_awaited_once_with(identity)
    sql_mock.list_notebooks.assert_awaited_once_with(10, None)
    sql_mock.delete_notebook.assert_awaited_once_with(identity)
    sql_mock.upsert_source.assert_awaited_once_with(record)
    sql_mock.list_notes.assert_awaited_once_with(identity, 10, None)
    sql_mock.list_insights.assert_awaited_once_with(identity, 10, None)
    sql_mock.list_sessions.assert_awaited_once_with(identity, 10, None)
    sql_mock.append_turn.assert_awaited_once_with(identity, record)
    sql_mock.get_citations_for_turn.assert_awaited_once_with(identity)


@pytest.mark.anyio
async def test_upsert_chunks_success(
    composite: CompositeStorage,
    sql_mock: Mock,
    qdr_mock: Mock,
) -> None:
    """Test successful distributed chunk upsertion."""
    chunk = Chunk(
        id="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        document_id=uuid4(),
        version_id=uuid4(),
        text="abc",
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        heading_path=(),
        parent_chunk_id=None,
        sibling_ids=(),
        metadata=FrozenMetadata(),
    )
    chunks = (chunk,)

    await composite.upsert_chunks(chunks)

    sql_mock.upsert_chunks.assert_awaited_once_with(chunks)
    qdr_mock.upsert_chunks.assert_awaited_once_with(chunks)
    # Rollback should not be triggered
    sql_mock.delete_chunks_for_document.assert_not_called()


@pytest.mark.anyio
async def test_upsert_chunks_rollback(
    composite: CompositeStorage,
    sql_mock: Mock,
    qdr_mock: Mock,
) -> None:
    """Test rollback of SQLite chunks if Qdrant insertion fails."""
    chunk = Chunk(
        id="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        document_id=uuid4(),
        version_id=uuid4(),
        text="abc",
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        heading_path=(),
        parent_chunk_id=None,
        sibling_ids=(),
        metadata=FrozenMetadata(),
    )
    chunks = (chunk,)

    qdr_mock.upsert_chunks.side_effect = Exception("Network timeout")

    with pytest.raises(StorageError, match="multi-store write failed"):
        await composite.upsert_chunks(chunks)

    sql_mock.upsert_chunks.assert_awaited_once_with(chunks)
    qdr_mock.upsert_chunks.assert_awaited_once_with(chunks)
    sql_mock.delete_chunks_for_document.assert_awaited_once_with(
        chunk.document_id, chunk.version_id
    )


@pytest.mark.anyio
async def test_upsert_chunks_rejects_mixed_document_batches(
    composite: CompositeStorage,
    sql_mock: Mock,
    qdr_mock: Mock,
) -> None:
    """Rollback scope is unambiguous because a batch belongs to one version."""
    first = _chunk()
    second = replace(first, id="b" * 64, document_id=uuid4())

    with pytest.raises(ContractValidationError, match="share one document_id"):
        await composite.upsert_chunks((first, second))

    sql_mock.upsert_chunks.assert_not_awaited()
    qdr_mock.upsert_chunks.assert_not_awaited()


@pytest.mark.anyio
async def test_upsert_chunks_reports_failed_compensation(
    composite: CompositeStorage,
    sql_mock: Mock,
    qdr_mock: Mock,
) -> None:
    """A failed rollback is surfaced instead of hiding possible inconsistency."""
    qdr_mock.upsert_chunks.side_effect = RuntimeError("vector write failed")
    sql_mock.delete_chunks_for_document.side_effect = RuntimeError("rollback failed")

    with pytest.raises(StorageError, match="compensating rollback failed"):
        await composite.upsert_chunks((_chunk(),))


@pytest.mark.anyio
async def test_delete_chunks_success(
    composite: CompositeStorage,
    sql_mock: Mock,
    qdr_mock: Mock,
) -> None:
    """Test distributed chunk deletion."""
    doc_id = uuid4()
    ver_id = uuid4()

    await composite.delete_chunks_for_document(doc_id, ver_id)

    qdr_mock.delete_chunks_for_document.assert_awaited_once_with(doc_id, ver_id)
    sql_mock.delete_chunks_for_document.assert_awaited_once_with(doc_id, ver_id)


@pytest.mark.anyio
async def test_delete_chunks_failure(
    composite: CompositeStorage,
    sql_mock: Mock,
    qdr_mock: Mock,
) -> None:
    """Test distributed chunk deletion where one store fails."""
    doc_id = uuid4()
    ver_id = uuid4()

    sql_mock.delete_chunks_for_document.side_effect = Exception("DB locked")

    with pytest.raises(StorageError):
        await composite.delete_chunks_for_document(doc_id, ver_id)

    qdr_mock.delete_chunks_for_document.assert_awaited_once_with(doc_id, ver_id)
    sql_mock.delete_chunks_for_document.assert_awaited_once_with(doc_id, ver_id)


@pytest.mark.anyio
async def test_cascade_delete_success(
    composite: CompositeStorage,
    sql_mock: Mock,
    qdr_mock: Mock,
    sur_mock: Mock,
) -> None:
    """Test full document cascade deletion."""
    doc_id = uuid4()

    await composite.delete_document_cascade(doc_id)

    qdr_mock.delete_chunks_for_document.assert_awaited_once_with(doc_id, None)
    sur_mock.delete_graph_for_document.assert_awaited_once_with(doc_id)
    sql_mock.delete_document_cascade.assert_awaited_once_with(doc_id)


@pytest.mark.anyio
async def test_cascade_delete_rollback_logging(
    composite: CompositeStorage,
    sql_mock: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that failure during cascade delete safely raises."""
    doc_id = uuid4()
    sql_mock.delete_document_cascade.side_effect = Exception("Internal Error")

    with pytest.raises(StorageError):
        await composite.delete_document_cascade(doc_id)
