"""Real SQLite/CompositeStorage validation for Module 6.4 parent promotion."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from mnemo.interfaces import IntegrityError
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    ScoredChunk,
)
from mnemo.retrieval import ParentRetriever
from mnemo.storage.composite import CompositeStorage
from mnemo.storage.sqlite import SQLiteStore

DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000011")
VERSION_ID = UUID("00000000-0000-4000-8000-000000000012")
CREATED_AT = datetime(2026, 8, 13, tzinfo=UTC)


def _chunk(
    index: int,
    *,
    parent_id: str | None = None,
    sibling_ids: tuple[str, ...] = (),
) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        text=f"Stored chunk {index}",
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Stored family",),
        parent_chunk_id=parent_id,
        sibling_ids=sibling_ids,
    )


def _composite(sqlite: SQLiteStore) -> CompositeStorage:
    unused = cast(Any, object())
    return CompositeStorage(unused, sqlite, unused, unused)


async def _store_document(sqlite: SQLiteStore) -> None:
    metadata = DocumentMetadata(content_hash="a" * 64, title="Stored hierarchy")
    version = DocumentVersion(
        version_id=VERSION_ID,
        document_id=DOCUMENT_ID,
        content_hash=metadata.content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=CREATED_AT,
    )
    await sqlite.upsert_document(
        Document(
            document_id=DOCUMENT_ID,
            versions=(version,),
            current_version_id=VERSION_ID,
            current_hash=metadata.content_hash,
            status=DocumentStatus.INDEXED,
            created_at=CREATED_AT,
            updated_at=CREATED_AT,
        )
    )


@pytest.mark.anyio
async def test_parent_retriever_uses_real_composite_sqlite_lookup(tmp_path: Path) -> None:
    sqlite = SQLiteStore(tmp_path / "parent-retriever.db")
    await sqlite.open()
    try:
        await _store_document(sqlite)
        parent = _chunk(100)
        child_one = _chunk(1, parent_id=parent.id, sibling_ids=(f"{2:064x}",))
        child_two = _chunk(2, parent_id=parent.id, sibling_ids=(child_one.id,))
        await sqlite.upsert_chunks((parent, child_one, child_two))
        candidates = (
            ScoredChunk(chunk=child_one, score=0.91, source="dense", rank=1),
            ScoredChunk(chunk=child_two, score=0.83, source="dense", rank=2),
        )

        result = await ParentRetriever(_composite(sqlite)).promote(candidates)

        assert len(result) == 1
        assert result[0].chunk == await sqlite.get_chunk(parent.id)
        assert result[0].chunk.document_id == DOCUMENT_ID
        assert result[0].chunk.version_id == VERSION_ID
        assert result[0].score == 0.91
        assert result[0].source == "dense"
        assert result[0].rank == 1
    finally:
        await sqlite.close()


@pytest.mark.anyio
async def test_real_storage_corruption_fails_without_partial_result(tmp_path: Path) -> None:
    sqlite = SQLiteStore(tmp_path / "parent-retriever-corrupt.db")
    await sqlite.open()
    try:
        await _store_document(sqlite)
        parent = _chunk(100)
        missing_id = f"{999:064x}"
        child = _chunk(1, parent_id=parent.id, sibling_ids=(missing_id,))
        await sqlite.upsert_chunks((parent, child))

        with pytest.raises(IntegrityError, match="missing"):
            await ParentRetriever(_composite(sqlite)).promote(
                (ScoredChunk(chunk=child, score=0.9, source="dense", rank=1),)
            )
    finally:
        await sqlite.close()
