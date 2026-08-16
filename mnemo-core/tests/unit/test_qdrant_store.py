import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from mnemo.config import QdrantStorageConfig
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DocType,
    FrozenMetadata,
    MetadataFilter,
)
from mnemo.storage.qdrant import QdrantStore, _projection_from_payload
from mnemo.storage.retrieval_projection import RetrievalMetadataProjection
from pydantic import HttpUrl
from qdrant_client import AsyncQdrantClient


@pytest.fixture
def mock_qdrant_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch AsyncQdrantClient to use memory storage."""
    original_init = AsyncQdrantClient.__init__

    def mock_init(self: AsyncQdrantClient, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("url", None)
        kwargs.pop("api_key", None)
        kwargs["location"] = ":memory:"
        original_init(self, *args, **kwargs)

    monkeypatch.setattr("mnemo.storage.qdrant.AsyncQdrantClient.__init__", mock_init)


@pytest.fixture
def qdrant_config() -> QdrantStorageConfig:
    return QdrantStorageConfig(
        enabled=True,
        url=HttpUrl("http://localhost:6333"),
        collection_name="test_collection",
        on_disk=False,
    )


@pytest.fixture
async def qdrant_store(
    qdrant_config: QdrantStorageConfig, mock_qdrant_client: None
) -> AsyncGenerator[QdrantStore, None]:
    store = QdrantStore(config=qdrant_config, vector_dimensions=3)
    await store.open()
    yield store
    await store.close()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_qdrant_lifecycle(
    qdrant_config: QdrantStorageConfig, mock_qdrant_client: None
) -> None:
    store = QdrantStore(config=qdrant_config, vector_dimensions=10)

    # Should not be healthy before open
    health = await store.health_check()
    assert len(health) == 1
    assert not health[0].healthy

    await store.open()

    # Should be healthy after open
    health = await store.health_check()
    assert health[0].healthy

    await store.close()


@pytest.mark.anyio
async def test_qdrant_upsert_and_search(qdrant_store: QdrantStore) -> None:
    doc_id = uuid4()
    ver_id = uuid4()

    chunk = Chunk(
        id="a" * 64,
        text="test chunk",
        document_id=doc_id,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
        sibling_ids=(),
        metadata=FrozenMetadata({"foo": "bar"}),
        embedding=(0.1, 0.2, 0.3),
    )

    await qdrant_store.upsert_chunks((chunk,))

    filters = MetadataFilter()
    results = await qdrant_store.search_dense(
        embedding=(0.1, 0.2, 0.3),
        filters=filters,
        top_k=5,
    )

    assert len(results) == 1
    scored = results[0]
    assert scored.chunk.id == "a" * 64
    assert scored.chunk.document_id == doc_id
    assert scored.score > 0.99
    assert scored.source == "qdrant"
    assert scored.rank == 1
    assert scored.chunk.metadata["foo"] == "bar"
    assert scored.chunk.source_span == chunk.source_span


def _projected_chunk(
    *, chunk_id: str, document_id: Any, version_id: Any, embedding: tuple[float, ...]
) -> Chunk:
    return Chunk(
        id=chunk_id,
        text=f"chunk {chunk_id[0]}",
        document_id=document_id,
        version_id=version_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
        sibling_ids=(),
        metadata=FrozenMetadata(),
        embedding=embedding,
    )


@pytest.mark.anyio
async def test_qdrant_version_aware_metadata_filters_before_top_k(
    qdrant_store: QdrantStore,
) -> None:
    document_id = uuid4()
    book_version = uuid4()
    paper_version = uuid4()
    undated_version = uuid4()
    notebook_one = uuid4()
    notebook_two = uuid4()
    source_one = uuid4()
    source_two = uuid4()
    source_three = uuid4()
    book = _projected_chunk(
        chunk_id="1" * 64,
        document_id=document_id,
        version_id=book_version,
        embedding=(1.0, 0.0, 0.0),
    )
    paper = _projected_chunk(
        chunk_id="2" * 64,
        document_id=document_id,
        version_id=paper_version,
        embedding=(0.99, 0.1, 0.0),
    )
    undated = _projected_chunk(
        chunk_id="3" * 64,
        document_id=document_id,
        version_id=undated_version,
        embedding=(0.98, 0.2, 0.0),
    )
    await qdrant_store._upsert_chunks_with_projection(
        (book,),
        RetrievalMetadataProjection(
            doc_type=DocType.BOOK,
            publication_date=date(2020, 1, 1),
            source_ids=tuple(sorted((source_one, source_two), key=str)),
            notebook_ids=(notebook_one,),
        ),
    )
    await qdrant_store._upsert_chunks_with_projection(
        (paper,),
        RetrievalMetadataProjection(
            doc_type=DocType.PAPER,
            publication_date=date(2022, 1, 1),
            source_ids=(source_three,),
            notebook_ids=(notebook_two,),
        ),
    )
    await qdrant_store._upsert_chunks_with_projection(
        (undated,),
        RetrievalMetadataProjection(
            doc_type=DocType.BOOK,
            publication_date=None,
            source_ids=(source_one,),
            notebook_ids=(notebook_one,),
        ),
    )

    async def ids(filters: MetadataFilter, top_k: int = 10) -> tuple[str, ...]:
        results = await qdrant_store.search_dense((1.0, 0.0, 0.0), filters, top_k)
        return tuple(result.chunk.id for result in results)

    assert await ids(MetadataFilter()) == (book.id, paper.id, undated.id)
    assert await ids(MetadataFilter(notebook_id=notebook_two), top_k=1) == (paper.id,)
    assert await ids(MetadataFilter(source_ids=(source_two,))) == (book.id,)
    assert await ids(MetadataFilter(source_ids=(source_two, source_three))) == (
        book.id,
        paper.id,
    )
    assert await ids(MetadataFilter(doc_types=(DocType.BOOK,))) == (book.id, undated.id)
    assert await ids(MetadataFilter(doc_types=(DocType.BOOK, DocType.PAPER))) == (
        book.id,
        paper.id,
        undated.id,
    )
    assert await ids(MetadataFilter(date_after=date(2020, 1, 1))) == (book.id, paper.id)
    assert await ids(MetadataFilter(date_before=date(2022, 1, 1))) == (book.id, paper.id)
    assert await ids(
        MetadataFilter(
            notebook_id=notebook_one,
            source_ids=(source_two, source_three),
            doc_types=(DocType.BOOK,),
            date_after=date(2020, 1, 1),
            date_before=date(2020, 1, 1),
        )
    ) == (book.id,)
    assert await ids(MetadataFilter(date_after=date(2023, 1, 1))) == ()

    paper_only = await qdrant_store.search_dense(
        (1.0, 0.0, 0.0), MetadataFilter(doc_types=(DocType.PAPER,)), 1
    )
    assert paper_only[0].chunk.version_id == paper_version
    assert paper_only[0].chunk is not paper
    assert paper_only[0].chunk.id == paper.id
    assert paper_only[0].score > 0


@pytest.mark.anyio
async def test_qdrant_empty_filter_uses_direct_query_fast_path(
    qdrant_store: QdrantStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = qdrant_store._require_open()
    original = client.query_points
    seen_filters: list[object] = []

    async def capture(*args: Any, **kwargs: Any) -> Any:
        seen_filters.append(kwargs.get("query_filter"))
        return await original(*args, **kwargs)

    monkeypatch.setattr(client, "query_points", capture)
    await qdrant_store.search_dense((1.0, 0.0, 0.0), MetadataFilter(), 1)
    assert seen_filters == [None]


def test_projected_payload_deserialization_validation() -> None:
    assert _projection_from_payload(None) is None
    assert _projection_from_payload({}) is None
    with pytest.raises(ValueError, match="membership payload"):
        _projection_from_payload({"doc_type": "book", "source_ids": "invalid"})
    projection = _projection_from_payload(
        {
            "doc_type": "paper",
            "publication_date": "2024-01-01",
            "source_ids": [],
            "notebook_ids": [],
        }
    )
    assert projection == RetrievalMetadataProjection(
        doc_type=DocType.PAPER, publication_date=date(2024, 1, 1)
    )


@pytest.mark.anyio
async def test_qdrant_snapshot_restore_preserves_replaced_points(
    qdrant_store: QdrantStore,
) -> None:
    """Restoration reinstates prior payload/vector and removes only new points."""
    original = Chunk(
        id="a" * 64,
        text="original",
        document_id=uuid4(),
        version_id=uuid4(),
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=("old",),
        metadata=FrozenMetadata({"parser.source": "old"}),
        embedding=(0.1, 0.2, 0.3),
    )
    introduced = replace(original, id="b" * 64, text="introduced")
    await qdrant_store.upsert_chunks((original,))
    snapshot = await qdrant_store._snapshot_chunks((original.id, introduced.id))

    await qdrant_store.upsert_chunks(
        (replace(original, text="replacement", embedding=(0.3, 0.2, 0.1)), introduced)
    )
    await qdrant_store._restore_chunk_snapshot((original.id, introduced.id), snapshot)

    restored = await qdrant_store._snapshot_chunks((original.id, introduced.id))
    assert restored[0].source_span == original.source_span
    assert len(restored) == 1
    assert restored[0].text == original.text
    assert restored[0].heading_path == original.heading_path
    assert dict(restored[0].metadata) == dict(original.metadata)
    assert restored[0].embedding == pytest.approx(snapshot[0].embedding)


@pytest.mark.anyio
async def test_qdrant_projected_snapshot_restores_derived_payload(
    qdrant_store: QdrantStore,
) -> None:
    chunk = _projected_chunk(
        chunk_id="d" * 64,
        document_id=uuid4(),
        version_id=uuid4(),
        embedding=(0.1, 0.2, 0.3),
    )
    source_id = uuid4()
    notebook_id = uuid4()
    original = RetrievalMetadataProjection(
        doc_type=DocType.BOOK,
        publication_date=date(2020, 1, 1),
        source_ids=(source_id,),
        notebook_ids=(notebook_id,),
    )
    await qdrant_store._upsert_chunks_with_projection((chunk,), original)
    snapshot = await qdrant_store._snapshot_chunks_with_projection((chunk.id,))
    await qdrant_store._upsert_chunks_with_projection(
        (chunk,),
        RetrievalMetadataProjection(doc_type=DocType.PAPER, publication_date=None),
    )
    await qdrant_store._restore_projected_chunk_snapshot((chunk.id,), snapshot)

    assert snapshot[0].projection == original
    results = await qdrant_store.search_dense(
        (0.1, 0.2, 0.3), MetadataFilter(doc_types=(DocType.BOOK,)), 1
    )
    assert tuple(result.chunk.id for result in results) == (chunk.id,)


@pytest.mark.anyio
async def test_qdrant_delete_chunks_for_document(qdrant_store: QdrantStore) -> None:
    doc_id_1 = uuid4()
    doc_id_2 = uuid4()
    ver_id = uuid4()

    chunk1 = Chunk(
        id="a" * 64,
        text="doc 1",
        document_id=doc_id_1,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
        sibling_ids=(),
        metadata=FrozenMetadata(),
        embedding=(0.1, 0.0, 0.0),
    )
    chunk2 = Chunk(
        id="b" * 64,
        text="doc 2",
        document_id=doc_id_2,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
        sibling_ids=(),
        metadata=FrozenMetadata(),
        embedding=(0.0, 0.1, 0.0),
    )

    await qdrant_store.upsert_chunks((chunk1, chunk2))

    # Delete doc 1
    await qdrant_store.delete_chunks_for_document(doc_id_1, version_id=None)

    # Qdrant deletes can be asynchronous; the local memory adapter is normally immediate.
    await asyncio.sleep(0.1)

    # Search should only find doc 2
    results = await qdrant_store.search_dense(
        embedding=(0.1, 0.1, 0.0),
        filters=MetadataFilter(),
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].chunk.id == "b" * 64


@pytest.mark.anyio
async def test_qdrant_unsupported_methods(qdrant_store: QdrantStore) -> None:
    uid = uuid4()
    with pytest.raises(NotImplementedError):
        await qdrant_store.put_asset(b"", "text/plain", FrozenMetadata())
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_asset(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_asset(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.put_parsed_document(uid, None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_parsed_document(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.contains_hash("abc")
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_document(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_document(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.list_documents(None, 10, None)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_document(uid, None)
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_notebook(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_notebook(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_notebook(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.list_notebooks(10, None)
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_source(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_source(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_source(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.list_sources(uid, 10, None)
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_note(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_note(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_note(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.list_notes(uid, 10, None)
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_insight(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_insight(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_insight(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.list_insights(uid, 10, None)
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_session(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_session(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.list_sessions(uid, 10, None)
    with pytest.raises(NotImplementedError):
        await qdrant_store.append_turn(uid, None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.list_turns(uid, None, 10)
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_citation(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_citations_for_turn(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_session(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_entity(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.upsert_edge(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_entity(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.find_entities("test", None, (), 10)
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_related_entities(uid, 1, (), 10)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_graph_for_document(uid)
    with pytest.raises(NotImplementedError):
        await qdrant_store.get_chunk("abc")
    with pytest.raises(NotImplementedError):
        await qdrant_store.search_sparse("q", MetadataFilter(), 10)
    with pytest.raises(NotImplementedError):
        await qdrant_store.delete_document_cascade(uid)


@pytest.mark.anyio
async def test_qdrant_disabled_behavior() -> None:
    """Verify disabled QdrantStore operations are safe no-ops and return empty results."""
    disabled_config = QdrantStorageConfig(
        enabled=False,
        url=HttpUrl("http://localhost:6333"),
        collection_name="disabled_collection",
        on_disk=False,
    )
    store = QdrantStore(config=disabled_config, vector_dimensions=3)

    # open() should perform no network I/O and keep _client as None
    await store.open()
    assert store._client is None

    # health_check() should report disabled
    health = await store.health_check()
    assert len(health) == 1
    assert not health[0].healthy
    assert "disabled" in (health[0].detail or "").lower()

    # search_dense() should return empty tuple
    results = await store.search_dense(
        embedding=(0.1, 0.2, 0.3),
        filters=MetadataFilter(),
        top_k=5,
    )
    assert results == ()

    # write and delete operations should be safe no-ops
    doc_id = uuid4()
    ver_id = uuid4()
    chunk = Chunk(
        id="c" * 64,
        text="disabled test chunk",
        document_id=doc_id,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
        sibling_ids=(),
        metadata=FrozenMetadata(),
        embedding=(0.1, 0.2, 0.3),
    )
    await store.upsert_chunks((chunk,))
    await store.delete_chunks_for_document(doc_id, ver_id)
    assert await store._snapshot_chunks(("c" * 64,)) == ()
    await store._restore_chunk_snapshot(("c" * 64,), ())
    await store.close()


@pytest.mark.anyio
async def test_qdrant_enabled_unopened_raises() -> None:
    """Verify enabled but unopened QdrantStore raises RuntimeError rather than masking failure."""
    enabled_config = QdrantStorageConfig(
        enabled=True,
        url=HttpUrl("http://localhost:6333"),
        collection_name="test_collection",
        on_disk=False,
    )
    store = QdrantStore(config=enabled_config, vector_dimensions=3)

    with pytest.raises(RuntimeError, match="QdrantStore is not open"):
        await store.search_dense(
            embedding=(0.1, 0.2, 0.3),
            filters=MetadataFilter(),
            top_k=5,
        )

    doc_id = uuid4()
    ver_id = uuid4()
    chunk = Chunk(
        id="d" * 64,
        text="unopened test chunk",
        document_id=doc_id,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
        sibling_ids=(),
        metadata=FrozenMetadata(),
        embedding=(0.1, 0.2, 0.3),
    )
    with pytest.raises(RuntimeError, match="QdrantStore is not open"):
        await store.upsert_chunks((chunk,))
