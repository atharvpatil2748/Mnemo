"""Focused contract tests for the Module 6.3 SparseRetriever."""

from unittest.mock import AsyncMock, create_autospec
from uuid import uuid4

import pytest
from mnemo.interfaces import (
    IntegrityError,
    RetrieverInterfaceV1,
    StorageCapabilities,
    StorageInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    FrozenMetadata,
    MetadataFilter,
    ScoredChunk,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import SparseRetriever


def _chunk(index: int) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        document_id=uuid4(),
        version_id=uuid4(),
        text=f"duty passage {index}",
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Chapter",),
        metadata=FrozenMetadata(),
    )


def _storage(results: tuple[ScoredChunk, ...] = (), *, supported: bool = True):
    storage = create_autospec(StorageInterfaceV1, instance=True)
    storage.capabilities.return_value = StorageCapabilities(
        supports_blobs=False,
        supports_dense_search=False,
        supports_sparse_search=supported,
        supports_metadata=True,
        supports_graph=False,
        supports_transactions=True,
        supports_health_checks=True,
    )
    storage.search_sparse = AsyncMock(return_value=results)
    return storage


@pytest.mark.anyio
async def test_sparse_preserves_filter_top_k_score_order_and_identity() -> None:
    chunks = (_chunk(1), _chunk(2), _chunk(3))
    scores = (4.25, 2.0, 0.75)
    backend = tuple(
        ScoredChunk(chunk=chunk, score=score, source="sqlite-fts5", rank=index)
        for index, (chunk, score) in enumerate(zip(chunks, scores, strict=True), start=1)
    )
    storage = _storage(backend)
    retriever = SparseRetriever(storage)
    filters = MetadataFilter(source_ids=(uuid4(),))

    results = await retriever.retrieve("duty action", (1.0,), filters, 3)

    storage.search_sparse.assert_awaited_once_with("duty action", filters, 3)
    assert tuple(result.chunk is chunk for result, chunk in zip(results, chunks, strict=True)) == (
        True,
        True,
        True,
    )
    assert tuple(result.score for result in results) == scores
    assert tuple(result.source for result in results) == ("sparse",) * 3
    assert tuple(result.rank for result in results) == (1, 2, 3)


@pytest.mark.anyio
async def test_sparse_empty_and_storage_failure_propagate() -> None:
    storage = _storage()
    retriever = SparseRetriever(storage)
    assert await retriever.retrieve("missing", None, MetadataFilter(), 5) == ()
    storage.search_sparse.side_effect = RuntimeError("sqlite failed")
    with pytest.raises(RuntimeError, match="sqlite failed"):
        await retriever.retrieve("duty", None, MetadataFilter(), 5)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("query", "filters", "top_k", "error"),
    [
        ("", MetadataFilter(), 1, ValueError),
        ("   ", MetadataFilter(), 1, ValueError),
        (1, MetadataFilter(), 1, TypeError),
        ("duty", object(), 1, TypeError),
        ("duty", MetadataFilter(), 0, ValueError),
        ("duty", MetadataFilter(), True, TypeError),
    ],
)
async def test_sparse_rejects_invalid_input(query, filters, top_k, error) -> None:
    with pytest.raises(error):
        await SparseRetriever(_storage()).retrieve(query, None, filters, top_k)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad",
    [
        [],
        (object(),),
        tuple(ScoredChunk(chunk=_chunk(1), score=1, source="x", rank=1) for _ in range(2)),
    ],
)
async def test_sparse_rejects_invalid_storage_results(bad) -> None:
    with pytest.raises(IntegrityError):
        await SparseRetriever(_storage(bad)).retrieve("duty", None, MetadataFilter(), 1)


def test_sparse_registry_capabilities_and_boundary() -> None:
    retriever = SparseRetriever(_storage())
    registry = PluginRegistry(core_version="0.20.1")

    class Plugin:
        name = "test-sparse"
        version = "0.20.1"
        core_version_range = ">=0.20.1"

        def capabilities(self):
            return ("retriever",)

        def register(self, target):
            target.register_retriever("sparse", retriever, priority=0)

    assert registry.load_plugins((Plugin(),))[0].loaded
    registry.freeze()
    assert registry.resolve_retriever("sparse") is retriever
    assert isinstance(retriever, RetrieverInterfaceV1)
    assert retriever.retrieval_mode == "sparse"
    assert retriever.capabilities().supports_metadata_filters


def test_sparse_rejects_invalid_or_incapable_storage() -> None:
    with pytest.raises(TypeError):
        SparseRetriever(object())  # type: ignore[arg-type]
    with pytest.raises(UnsupportedError):
        SparseRetriever(_storage(supported=False))


def test_sparse_has_no_backend_or_fusion_dependency() -> None:
    source = __import__("inspect").getsource(__import__("mnemo.retrieval.sparse", fromlist=["x"]))
    for forbidden in ("sqlite3", "SQLiteStore", "Qdrant", "RRF", "fusion"):
        assert forbidden not in source
