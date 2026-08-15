from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mnemo.config import QdrantStorageConfig
from mnemo.interfaces.errors import StorageError
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    Notebook,
    ParsedDocument,
    Source,
)
from mnemo.storage.composite import CompositeStorage
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.qdrant import QdrantStore
from mnemo.storage.retrieval_projection import RetrievalMetadataProjection
from mnemo.storage.sqlite import SQLiteStore
from mnemo.storage.surrealdb import SurrealDBStore
from pydantic import HttpUrl
from qdrant_client import AsyncQdrantClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_composite_projects_exact_versions_and_mutable_memberships(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_init = AsyncQdrantClient.__init__

    def memory_init(self: AsyncQdrantClient, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("url", None)
        kwargs.pop("api_key", None)
        kwargs["location"] = ":memory:"
        original_init(self, *args, **kwargs)

    monkeypatch.setattr("mnemo.storage.qdrant.AsyncQdrantClient.__init__", memory_init)
    filesystem = FilesystemBlobStore((tmp_path / "blobs").resolve())
    sqlite = SQLiteStore((tmp_path / "mnemo.db").resolve())
    qdrant = QdrantStore(
        QdrantStorageConfig(
            enabled=True,
            url=HttpUrl("http://localhost:6333"),
            collection_name="projection-test",
            on_disk=False,
        ),
        vector_dimensions=3,
    )
    surreal = AsyncMock(spec=SurrealDBStore)
    composite = CompositeStorage(filesystem, sqlite, qdrant, cast(SurrealDBStore, surreal))
    await filesystem.open()
    await sqlite.open()
    await qdrant.open()
    try:
        now = datetime(2026, 8, 13, tzinfo=UTC)
        document_id = uuid4()
        book_version_id = uuid4()
        paper_version_id = uuid4()
        book_metadata = DocumentMetadata(
            content_hash="a" * 64,
            publication_date=date(2020, 1, 1),
        )
        paper_metadata = DocumentMetadata(
            content_hash="b" * 64,
            publication_date=date(2024, 1, 1),
        )
        book_version = DocumentVersion(
            version_id=book_version_id,
            document_id=document_id,
            content_hash=book_metadata.content_hash,
            metadata=book_metadata,
            status=DocumentVersionStatus.SUPERSEDED,
            created_at=now,
        )
        paper_version = DocumentVersion(
            version_id=paper_version_id,
            document_id=document_id,
            content_hash=paper_metadata.content_hash,
            metadata=paper_metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=now,
        )
        await sqlite.upsert_document(
            Document(
                document_id=document_id,
                versions=(book_version, paper_version),
                current_version_id=paper_version_id,
                current_hash=paper_metadata.content_hash,
                status=DocumentStatus.INDEXED,
                created_at=now,
                updated_at=now,
            )
        )
        await filesystem.put_parsed_document(
            book_version_id,
            ParsedDocument(blocks=(), metadata=book_metadata, language="en", doc_type=DocType.BOOK),
        )
        await filesystem.put_parsed_document(
            paper_version_id,
            ParsedDocument(
                blocks=(), metadata=paper_metadata, language="en", doc_type=DocType.PAPER
            ),
        )
        notebook = Notebook(notebook_id=uuid4(), title="Notebook", created_at=now, updated_at=now)
        await sqlite.upsert_notebook(notebook)
        source = Source(
            source_id=uuid4(),
            notebook_id=notebook.notebook_id,
            document_id=document_id,
            created_at=now,
        )
        await composite.upsert_source(source)
        base = Chunk(
            id="1" * 64,
            text="superseded book",
            document_id=document_id,
            version_id=book_version_id,
            chunk_type=ChunkType.PASSAGE,
            position=ChunkPosition(section_index=0, chunk_index_in_section=0),
            source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
            heading_path=(),
            embedding=(1.0, 0.0, 0.0),
        )
        current = replace(
            base,
            id="2" * 64,
            text="current paper",
            version_id=paper_version_id,
            embedding=(0.99, 0.1, 0.0),
        )
        await composite.upsert_chunks((base,))
        await composite.upsert_chunks((current,))

        from mnemo.models import MetadataFilter

        book_results = await composite.search_dense(
            (1.0, 0.0, 0.0),
            MetadataFilter(
                notebook_id=notebook.notebook_id,
                source_ids=(source.source_id,),
                doc_types=(DocType.BOOK,),
                date_after=date(2020, 1, 1),
                date_before=date(2020, 1, 1),
            ),
            1,
        )
        assert tuple(result.chunk.id for result in book_results) == (base.id,)

        await composite.delete_source(source.source_id)
        assert (
            await composite.search_dense(
                (1.0, 0.0, 0.0), MetadataFilter(notebook_id=notebook.notebook_id), 10
            )
            == ()
        )
    finally:
        await qdrant.close()
        await sqlite.close()
        await filesystem.close()


@pytest.mark.anyio
async def test_source_projection_failure_rolls_back_canonical_write() -> None:
    sqlite = AsyncMock(spec=SQLiteStore)
    qdrant = AsyncMock(spec=QdrantStore)
    filesystem = AsyncMock(spec=FilesystemBlobStore)
    surreal = AsyncMock(spec=SurrealDBStore)
    source = Source(
        source_id=uuid4(),
        notebook_id=uuid4(),
        document_id=uuid4(),
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
    )
    sqlite.get_source.return_value = None
    sqlite._list_sources_for_document.return_value = (source,)
    qdrant._set_document_membership.side_effect = [RuntimeError("qdrant down"), None]
    composite = CompositeStorage(filesystem, sqlite, qdrant, surreal)

    with pytest.raises(StorageError, match="canonical write rolled back"):
        await composite.upsert_source(source)

    sqlite.upsert_source.assert_awaited_once_with(source)
    sqlite.delete_source.assert_awaited_once_with(source.source_id)
    assert qdrant._set_document_membership.await_count == 2


@pytest.mark.anyio
async def test_notebook_delete_projects_restrictively_before_cascade() -> None:
    sqlite = AsyncMock(spec=SQLiteStore)
    qdrant = AsyncMock(spec=QdrantStore)
    filesystem = AsyncMock(spec=FilesystemBlobStore)
    surreal = AsyncMock(spec=SurrealDBStore)
    now = datetime(2026, 8, 13, tzinfo=UTC)
    document_id = uuid4()
    deleted_notebook = uuid4()
    retained_notebook = uuid4()
    deleted_source = Source(
        source_id=uuid4(),
        notebook_id=deleted_notebook,
        document_id=document_id,
        created_at=now,
    )
    retained_source = Source(
        source_id=uuid4(),
        notebook_id=retained_notebook,
        document_id=document_id,
        created_at=now,
    )
    sqlite.get_notebook.return_value = object()
    sqlite._list_sources_for_notebook.return_value = (deleted_source,)
    sqlite._list_sources_for_document.return_value = (deleted_source, retained_source)
    sqlite.delete_notebook.return_value = True
    composite = CompositeStorage(filesystem, sqlite, qdrant, surreal)

    assert await composite.delete_notebook(deleted_notebook)

    qdrant._set_document_membership.assert_awaited_once_with(
        document_id,
        source_ids=(retained_source.source_id,),
        notebook_ids=(retained_notebook,),
    )
    sqlite.delete_notebook.assert_awaited_once_with(deleted_notebook)


@pytest.mark.anyio
async def test_notebook_delete_failure_restores_projection_from_canonical_rows() -> None:
    sqlite = AsyncMock(spec=SQLiteStore)
    qdrant = AsyncMock(spec=QdrantStore)
    filesystem = AsyncMock(spec=FilesystemBlobStore)
    surreal = AsyncMock(spec=SurrealDBStore)
    now = datetime(2026, 8, 13, tzinfo=UTC)
    source = Source(source_id=uuid4(), notebook_id=uuid4(), document_id=uuid4(), created_at=now)
    sqlite.get_notebook.return_value = object()
    sqlite._list_sources_for_notebook.return_value = (source,)
    sqlite._list_sources_for_document.return_value = (source,)
    sqlite.delete_notebook.side_effect = RuntimeError("sqlite locked")
    composite = CompositeStorage(filesystem, sqlite, qdrant, surreal)

    with pytest.raises(StorageError, match="projection restored"):
        await composite.delete_notebook(source.notebook_id)

    assert qdrant._set_document_membership.await_count == 2


def test_projection_value_validation_and_payload() -> None:
    first = uuid4()
    second = uuid4()
    ordered = tuple(sorted((first, second), key=str))
    projection = RetrievalMetadataProjection(
        doc_type=DocType.BOOK,
        publication_date=date(2020, 1, 1),
        source_ids=ordered,
        notebook_ids=(),
    )
    assert projection.payload() == {
        "doc_type": "book",
        "publication_date": "2020-01-01",
        "publication_date_ordinal": date(2020, 1, 1).toordinal(),
        "source_ids": [str(value) for value in ordered],
        "notebook_ids": [],
    }
    assert RetrievalMetadataProjection(doc_type=DocType.BOOK, publication_date=None).payload() == {
        "doc_type": "book",
        "source_ids": [],
        "notebook_ids": [],
    }
    with pytest.raises(TypeError, match="doc_type"):
        RetrievalMetadataProjection(doc_type=cast(Any, "book"), publication_date=None)
    with pytest.raises(TypeError, match="publication_date"):
        RetrievalMetadataProjection(doc_type=DocType.BOOK, publication_date=cast(Any, "2020-01-01"))
    with pytest.raises(TypeError, match="source_ids"):
        RetrievalMetadataProjection(
            doc_type=DocType.BOOK,
            publication_date=None,
            source_ids=cast(Any, ("bad",)),
        )
    with pytest.raises(TypeError, match="notebook_ids"):
        RetrievalMetadataProjection(
            doc_type=DocType.BOOK,
            publication_date=None,
            notebook_ids=cast(Any, ("bad",)),
        )
    with pytest.raises(ValueError, match="source_ids"):
        RetrievalMetadataProjection(
            doc_type=DocType.BOOK,
            publication_date=None,
            source_ids=(first, first),
        )
    with pytest.raises(ValueError, match="notebook_ids"):
        RetrievalMetadataProjection(
            doc_type=DocType.BOOK,
            publication_date=None,
            notebook_ids=(first, first),
        )


@pytest.mark.anyio
async def test_projection_requires_complete_consistent_canonical_state() -> None:
    filesystem = AsyncMock(spec=FilesystemBlobStore)
    sqlite = AsyncMock(spec=SQLiteStore)
    qdrant = AsyncMock(spec=QdrantStore)
    surreal = AsyncMock(spec=SurrealDBStore)
    composite = CompositeStorage(filesystem, sqlite, qdrant, surreal)
    document_id = uuid4()
    version_id = uuid4()
    now = datetime(2026, 8, 13, tzinfo=UTC)
    metadata = DocumentMetadata(content_hash="a" * 64)
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=metadata.content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    document = Document(
        document_id=document_id,
        versions=(version,),
        current_version_id=version_id,
        current_hash=metadata.content_hash,
        status=DocumentStatus.INDEXED,
        created_at=now,
        updated_at=now,
    )
    sqlite.get_document.return_value = None
    with pytest.raises(StorageError, match="canonical document"):
        await composite.upsert_chunks((_minimal_chunk(document_id, version_id),))
    sqlite.get_document.return_value = document
    missing_version = uuid4()
    with pytest.raises(StorageError, match="does not belong"):
        await composite.upsert_chunks((_minimal_chunk(document_id, missing_version),))
    filesystem.get_parsed_document.return_value = None
    with pytest.raises(StorageError, match="parsed IR"):
        await composite.upsert_chunks((_minimal_chunk(document_id, version_id),))
    filesystem.get_parsed_document.return_value = ParsedDocument(
        blocks=(),
        metadata=DocumentMetadata(content_hash="b" * 64),
        language="en",
        doc_type=DocType.BOOK,
    )
    with pytest.raises(StorageError, match="content hash"):
        await composite.upsert_chunks((_minimal_chunk(document_id, version_id),))
    sqlite.upsert_chunks.assert_not_awaited()
    qdrant._upsert_chunks_with_projection.assert_not_awaited()


def _minimal_chunk(document_id: Any, version_id: Any) -> Chunk:
    return Chunk(
        id="f" * 64,
        text="projection",
        document_id=document_id,
        version_id=version_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
        embedding=(1.0, 0.0, 0.0),
    )
