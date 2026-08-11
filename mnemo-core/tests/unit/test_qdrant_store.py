import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from mnemo.config import QdrantStorageConfig
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    FrozenMetadata,
    MetadataFilter,
)
from mnemo.storage.qdrant import QdrantStore
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
