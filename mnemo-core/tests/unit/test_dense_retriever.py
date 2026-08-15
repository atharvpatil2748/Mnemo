"""Focused tests for Phase 6 Module 6.2 dense retrieval."""

from __future__ import annotations

import inspect
from typing import Any, cast
from unittest.mock import AsyncMock, create_autospec
from uuid import UUID

import mnemo.retrieval.dense as dense_module
import pytest
from mnemo.interfaces import (
    IntegrityError,
    RetrieverInterfaceV1,
    StorageCapabilities,
    StorageError,
    StorageInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DocType,
    FrozenMetadata,
    MetadataFilter,
    ScoredChunk,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import DenseRetriever


def _chunk(index: int) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        text=f"Canonical source passage {index}",
        document_id=UUID("00000000-0000-4000-8000-000000000001"),
        version_id=UUID("00000000-0000-4000-8000-000000000002"),
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(
            page_number=index + 1,
            section_index=0,
            chunk_index_in_section=index,
        ),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Chapter One",),
        metadata=FrozenMetadata({"test.index": index}),
    )


def _result(index: int, score: float) -> ScoredChunk:
    return ScoredChunk(chunk=_chunk(index), score=score, source="qdrant", rank=index + 1)


def _storage(
    results: tuple[ScoredChunk, ...] = (),
    *,
    supports_dense: bool = True,
) -> tuple[StorageInterfaceV1, AsyncMock]:
    storage_mock = create_autospec(StorageInterfaceV1, instance=True)
    storage_mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=True,
        supports_dense_search=supports_dense,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=False,
        supports_transactions=True,
        supports_health_checks=True,
    )
    search = cast(AsyncMock, storage_mock.search_dense)
    search.return_value = results
    return cast(StorageInterfaceV1, storage_mock), search


@pytest.mark.anyio
async def test_dense_retriever_preserves_filter_top_k_scores_order_and_identity() -> None:
    backend = (_result(1, 0.931), _result(2, 0.827), _result(3, 0.614))
    storage, search = _storage(backend)
    retriever = DenseRetriever(storage)
    embedding = (0.1, 0.2, 0.3)
    filters = MetadataFilter(doc_types=(DocType.BOOK,))

    results = await retriever.retrieve("source-style HyDE paragraph", embedding, filters, 3)

    search.assert_awaited_once_with(embedding, filters, 3)
    assert tuple(result.score for result in results) == (0.931, 0.827, 0.614)
    assert tuple(result.chunk for result in results) == tuple(result.chunk for result in backend)
    assert tuple(result.chunk.id for result in results) == tuple(
        result.chunk.id for result in backend
    )
    assert tuple(result.source for result in results) == ("dense", "dense", "dense")
    assert tuple(result.rank for result in results) == (1, 2, 3)


@pytest.mark.anyio
async def test_dense_retriever_returns_empty_tuple_without_repair() -> None:
    storage, search = _storage()
    filters = MetadataFilter()

    results = await DenseRetriever(storage).retrieve("query", (0.1,), filters, 5)

    assert results == ()
    search.assert_awaited_once_with((0.1,), filters, 5)


@pytest.mark.anyio
async def test_dense_retriever_propagates_storage_and_dimension_failures() -> None:
    storage, search = _storage()
    failure = StorageError("Qdrant unavailable")
    search.side_effect = failure

    with pytest.raises(StorageError, match="Qdrant unavailable") as raised:
        await DenseRetriever(storage).retrieve("query", (0.1,), MetadataFilter(), 1)
    assert raised.value is failure

    mismatch = IntegrityError("embedding dimensions do not match collection")
    search.side_effect = mismatch
    with pytest.raises(IntegrityError, match="dimensions") as raised_mismatch:
        await DenseRetriever(storage).retrieve("query", (0.1, 0.2), MetadataFilter(), 1)
    assert raised_mismatch.value is mismatch


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("query", "embedding", "filters", "top_k"),
    (
        (cast(Any, 1), (0.1,), MetadataFilter(), 1),
        (" ", (0.1,), MetadataFilter(), 1),
        ("query", None, MetadataFilter(), 1),
        ("query", cast(Any, [0.1]), MetadataFilter(), 1),
        ("query", (), MetadataFilter(), 1),
        ("query", (float("nan"),), MetadataFilter(), 1),
        ("query", (True,), MetadataFilter(), 1),
        ("query", (0.1,), cast(Any, object()), 1),
        ("query", (0.1,), MetadataFilter(), 0),
        ("query", (0.1,), MetadataFilter(), -1),
        ("query", (0.1,), MetadataFilter(), cast(Any, True)),
        ("query", (0.1,), MetadataFilter(), cast(Any, 1.5)),
    ),
)
async def test_dense_retriever_rejects_invalid_runtime_inputs(
    query: str,
    embedding: tuple[float, ...] | None,
    filters: MetadataFilter,
    top_k: int,
) -> None:
    storage, search = _storage()

    with pytest.raises((TypeError, ValueError)):
        await DenseRetriever(storage).retrieve(query, embedding, filters, top_k)

    search.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("backend", "top_k"),
    (
        (cast(Any, []), 3),
        ((_result(1, 0.9), _result(1, 0.8)), 3),
        ((_result(1, 0.9), _result(2, 0.8)), 1),
        (cast(Any, (object(),)), 3),
    ),
)
async def test_dense_retriever_rejects_invalid_storage_results(
    backend: object,
    top_k: int,
) -> None:
    storage, search = _storage()
    search.return_value = backend

    with pytest.raises(IntegrityError):
        await DenseRetriever(storage).retrieve("query", (0.1,), MetadataFilter(), top_k)


def test_dense_retriever_capabilities_and_registry_slot() -> None:
    storage, _ = _storage()
    retriever = DenseRetriever(storage)
    registry = PluginRegistry(core_version="0.20.1")

    class DensePlugin:
        name = "test-dense-retriever"
        version = "0.20.1"
        core_version_range = ">=0.20.1"

        def capabilities(self) -> tuple[str, ...]:
            return ("retriever",)

        def register(self, target: PluginRegistry) -> None:
            target.register_retriever("dense", retriever, priority=0)

    load_results = registry.load_plugins((DensePlugin(),))
    registry.freeze()

    assert isinstance(retriever, RetrieverInterfaceV1)
    assert retriever.retrieval_mode == "dense"
    assert retriever.capabilities().supports_metadata_filters
    assert not retriever.capabilities().supports_hybrid
    assert not retriever.capabilities().supports_parent_child
    assert not retriever.capabilities().supports_reranking
    assert load_results[0].loaded
    assert registry.resolve_retriever("dense") is retriever


def test_dense_retriever_rejects_invalid_or_incapable_storage() -> None:
    with pytest.raises(TypeError, match="StorageInterfaceV1"):
        DenseRetriever(object())  # type: ignore[arg-type]

    storage, _ = _storage(supports_dense=False)
    with pytest.raises(UnsupportedError, match="dense search"):
        DenseRetriever(storage)


def test_dense_retriever_has_no_qdrant_embedding_llm_or_fusion_dependency() -> None:
    source = inspect.getsource(dense_module).casefold()
    forbidden = (
        "qdrant_client",
        "mnemo.storage.qdrant",
        "mnemo.embeddings",
        "mnemo.interfaces.llm",
        "mnemo.retrieval.planner",
        "mnemo.retrieval.fusion",
    )

    assert not any(name in source for name in forbidden)
