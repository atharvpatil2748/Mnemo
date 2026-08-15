"""Focused tests for ADR-0041 multi-source retrieval orchestration."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from mnemo.embeddings.cached import CachedEmbeddingProvider
from mnemo.interfaces import (
    DependencyUnavailableError,
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingProviderV1,
    EmbeddingVector,
    HealthStatus,
    IntegrityError,
    MultiSourceRetrievalInterfaceV1,
    ParentPromotionCapabilities,
    ParentPromotionInterfaceV1,
    PluginError,
    RetrieverCapabilities,
    RetrieverInterfaceV1,
    StorageError,
    UnsupportedError,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    FusedChunkResult,
    FusionEvidence,
    MetadataFilter,
    RetrievalFusionResult,
    RetrievalIntent,
    RetrievalInvocationTrace,
    RetrievalMode,
    RetrievalPlan,
    ScoredChunk,
    SubQuery,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import MultiSourceRetriever
from mnemo.storage.cache import SQLiteEmbeddingCache

pytestmark = pytest.mark.anyio

_DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000001")
_VERSION_ID = UUID("00000000-0000-4000-8000-000000000002")


def _chunk(index: int, *, text: str | None = None) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        text=text or f"chunk {index}",
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Chapter",),
    )


def _scored(index: int, score: float, source: str, rank: int) -> ScoredChunk:
    return ScoredChunk(chunk=_chunk(index), score=score, source=source, rank=rank)


def _subquery(
    text: str,
    mode: RetrievalMode,
    *,
    max_results: int = 10,
    filters: MetadataFilter | None = None,
) -> SubQuery:
    return SubQuery(
        query_text=text,
        retrieval_mode=mode,
        filters=filters or MetadataFilter(),
        max_results=max_results,
    )


def _plan(
    *subqueries: SubQuery,
    intent: RetrievalIntent = RetrievalIntent.FACTUAL,
    multi_hop: bool = False,
    multi_doc: bool = False,
) -> RetrievalPlan:
    return RetrievalPlan(
        intent=intent,
        sub_queries=tuple(subqueries),
        requires_multi_hop=multi_hop,
        requires_multi_doc=multi_doc,
    )


class _Provider:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.calls = 0
        self.failure: Exception | None = None

    @property
    def model_name(self) -> str:
        return "test/model"

    @property
    def dimensions(self) -> int:
        return 2

    @property
    def max_tokens(self) -> int:
        return 512

    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            dimensions=2,
            supports_batch=True,
            max_batch=8,
            multilingual=True,
            supports_normalization=False,
        )

    async def embed(self, text: str) -> EmbeddingVector:
        self.calls += 1
        self.texts.append(text)
        if self.failure is not None:
            raise self.failure
        value = float(sum(text.encode("utf-8")))
        return (value, value + 1.0)

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        vectors = tuple([await self.embed(text) for text in texts])
        return EmbeddingBatch(
            vectors=vectors,
            model_name=self.model_name,
            dimensions=self.dimensions,
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            healthy=True,
            component="test-provider",
            checked_at=datetime.now(UTC),
        )


class _Retriever:
    def __init__(self, mode: str) -> None:
        self._mode = mode
        self.results: dict[str, tuple[ScoredChunk, ...]] = {}
        self.failures: dict[str, Exception] = {}
        self.delays: dict[str, float] = {}
        self.calls: list[tuple[str, EmbeddingVector | None, MetadataFilter, int]] = []
        self.active = 0
        self.max_active = 0
        self.cancelled = 0
        self.cleaned = 0
        self.started = asyncio.Event()

    @property
    def retrieval_mode(self) -> str:
        return self._mode

    def capabilities(self) -> RetrieverCapabilities:
        return RetrieverCapabilities(
            supports_hybrid=False,
            supports_metadata_filters=True,
            supports_parent_child=False,
            supports_reranking=False,
        )

    async def retrieve(
        self,
        query: str,
        query_embedding: EmbeddingVector | None,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        self.calls.append((query, query_embedding, filters, top_k))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.started.set()
        try:
            await asyncio.sleep(self.delays.get(query, 0))
            if query in self.failures:
                raise self.failures[query]
            return self.results.get(query, ())
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.active -= 1
            self.cleaned += 1


class _Promoter:
    def __init__(self) -> None:
        self.calls: list[tuple[ScoredChunk, ...]] = []
        self.transform: Callable[[tuple[ScoredChunk, ...]], tuple[ScoredChunk, ...]] = (
            lambda values: values
        )
        self.failure: Exception | None = None

    @property
    def promotion_mode(self) -> str:
        return "parent"

    def capabilities(self) -> ParentPromotionCapabilities:
        return ParentPromotionCapabilities(
            source_local=True,
            single_pass=True,
            preserves_raw_scores=True,
            validates_exact_version=True,
        )

    async def promote(
        self,
        candidates: tuple[ScoredChunk, ...],
    ) -> tuple[ScoredChunk, ...]:
        self.calls.append(candidates)
        if self.failure is not None:
            raise self.failure
        return self.transform(candidates)


class _Plugin:
    name = "retrieval-test"
    version = "1.0.0"
    core_version_range = ">=0.20.1"

    def __init__(
        self,
        dense: RetrieverInterfaceV1 | None,
        sparse: RetrieverInterfaceV1 | None,
        promoter: ParentPromotionInterfaceV1 | None,
    ) -> None:
        self._dense = dense
        self._sparse = sparse
        self._promoter = promoter

    def capabilities(self) -> tuple[str, ...]:
        return ("retriever", "parent_promotion")

    def register(self, registry: PluginRegistry) -> None:
        if self._dense is not None:
            registry.register_retriever("dense", self._dense, priority=0)
        if self._sparse is not None:
            registry.register_retriever("sparse", self._sparse, priority=0)
        if self._promoter is not None:
            registry.register_parent_promoter("default", self._promoter, priority=0)


def _orchestrator(
    *,
    dense: _Retriever | None = None,
    sparse: _Retriever | None = None,
    promoter: _Promoter | None = None,
    provider: EmbeddingProviderV1 | None = None,
    max_concurrency: int = 4,
) -> tuple[MultiSourceRetriever, _Provider, _Retriever, _Retriever, _Promoter]:
    actual_dense = dense or _Retriever("dense")
    actual_sparse = sparse or _Retriever("sparse")
    actual_promoter = promoter or _Promoter()
    actual_provider = provider or _Provider()
    registry = PluginRegistry(core_version="0.20.1")
    registry.load_plugin(_Plugin(actual_dense, actual_sparse, actual_promoter))
    registry.freeze()
    return (
        MultiSourceRetriever(
            registry,
            actual_provider,
            max_concurrency=max_concurrency,
        ),
        cast(_Provider, actual_provider),
        actual_dense,
        actual_sparse,
        actual_promoter,
    )


async def test_runtime_interface_and_single_dense_sparse_dispatch() -> None:
    orchestrator, provider, dense, sparse, promoter = _orchestrator()
    assert isinstance(orchestrator, MultiSourceRetrievalInterfaceV1)
    dense.results["dense text"] = (_scored(1, 0.9, "dense", 1),)
    sparse.results["sparse text"] = (_scored(2, 4.0, "sparse", 1),)
    plan = _plan(
        _subquery("dense text", RetrievalMode.DENSE, max_results=3),
        _subquery("sparse text", RetrievalMode.SPARSE, max_results=4),
    )

    result = await orchestrator.execute(plan, global_limit=10)

    assert provider.texts == ["dense text"]
    assert dense.calls[0][0::3] == ("dense text", 3)
    assert sparse.calls == [("sparse text", None, MetadataFilter(), 4)]
    assert [trace.invocation_id for trace in result.invocations] == [
        "sq-1:dense",
        "sq-2:sparse",
    ]
    assert len(promoter.calls) == 2
    assert [item.chunk.id for item in result.results] == [_chunk(1).id, _chunk(2).id]


async def test_hybrid_expands_dense_then_sparse_with_exact_embedding_mapping() -> None:
    orchestrator, provider, dense, sparse, promoter = _orchestrator()
    dense.results["hybrid one"] = (_scored(1, 0.7, "dense", 1),)
    sparse.results["hybrid one"] = (_scored(2, 7.0, "sparse", 1),)
    dense.results["dense two"] = (_scored(3, 0.6, "dense", 1),)

    result = await orchestrator.execute(
        _plan(
            _subquery("hybrid one", RetrievalMode.HYBRID),
            _subquery("dense two", RetrievalMode.DENSE),
        ),
        global_limit=10,
    )

    assert [trace.invocation_id for trace in result.invocations] == [
        "sq-1:dense",
        "sq-1:sparse",
        "sq-2:dense",
    ]
    assert provider.texts == ["hybrid one", "dense two"]
    assert dense.calls[0][1] != dense.calls[1][1]
    assert sparse.calls[0][1] is None
    assert promoter.calls == [
        dense.results["hybrid one"],
        sparse.results["hybrid one"],
        dense.results["dense two"],
    ]


@pytest.mark.parametrize("mode", [RetrievalMode.GRAPH, RetrievalMode.PARENT])
async def test_unsupported_modes_fail_before_any_task(mode: RetrievalMode) -> None:
    orchestrator, provider, dense, sparse, promoter = _orchestrator()
    with pytest.raises(UnsupportedError):
        await orchestrator.execute(_plan(_subquery("unsupported", mode)), global_limit=5)
    assert provider.calls == 0
    assert dense.calls == []
    assert sparse.calls == []
    assert promoter.calls == []


@pytest.mark.parametrize("missing", ["dense", "sparse", "promoter"])
async def test_missing_capability_fails_preflight(missing: str) -> None:
    dense = _Retriever("dense")
    sparse = _Retriever("sparse")
    promoter = _Promoter()
    registry = PluginRegistry(core_version="0.20.1")
    registry.load_plugin(
        _Plugin(
            None if missing == "dense" else dense,
            None if missing == "sparse" else sparse,
            None if missing == "promoter" else promoter,
        )
    )
    registry.freeze()
    orchestrator = MultiSourceRetriever(registry, _Provider())
    plan = _plan(_subquery("both", RetrievalMode.HYBRID))
    with pytest.raises(DependencyUnavailableError):
        await orchestrator.execute(plan, global_limit=5)
    assert dense.calls == []
    assert sparse.calls == []
    assert promoter.calls == []


async def test_empty_stream_is_promoted_once_and_retained_in_trace() -> None:
    orchestrator, _, dense, _, promoter = _orchestrator()
    result = await orchestrator.execute(
        _plan(_subquery("empty", RetrievalMode.DENSE)),
        global_limit=5,
    )
    assert dense.calls
    assert promoter.calls == [()]
    assert result.invocations[0].raw_results == ()
    assert result.invocations[0].promoted_results == ()
    assert result.results == ()


async def test_parent_promotion_precedes_fusion_and_marks_introduced_identity() -> None:
    orchestrator, _, dense, sparse, promoter = _orchestrator()
    child_dense = _scored(1, 0.9, "dense", 1)
    child_sparse = _scored(2, 9.0, "sparse", 1)
    parent = _chunk(99)
    dense.results["q"] = (child_dense,)
    sparse.results["q"] = (child_sparse,)

    def promote(values: tuple[ScoredChunk, ...]) -> tuple[ScoredChunk, ...]:
        value = values[0]
        return (ScoredChunk(chunk=parent, score=value.score, source=value.source, rank=1),)

    promoter.transform = promote
    result = await orchestrator.execute(
        _plan(_subquery("q", RetrievalMode.HYBRID)),
        global_limit=5,
    )

    assert len(result.results) == 1
    assert result.results[0].chunk.id == parent.id
    assert len(result.results[0].evidence) == 2
    assert all(item.identity_introduced_by_parent_promotion for item in result.results[0].evidence)
    assert result.results[0].rrf_score == math.fsum((1 / 61, 1 / 61))


async def test_rrf_dedup_preserves_raw_evidence_and_exact_global_order() -> None:
    orchestrator, _, dense, sparse, _ = _orchestrator()
    common_dense = _scored(1, -1000.0, "dense", 2)
    common_sparse = _scored(1, 1000000.0, "sparse", 1)
    dense.results["d"] = (_scored(2, 0.9, "dense", 1), common_dense)
    sparse.results["s"] = (common_sparse, _scored(3, 10.0, "sparse", 2))

    result = await orchestrator.execute(
        _plan(
            _subquery("d", RetrievalMode.DENSE),
            _subquery("s", RetrievalMode.SPARSE),
        ),
        global_limit=100,
    )

    fused = result.results[0]
    assert fused.chunk.id == _chunk(1).id
    assert fused.rrf_score == math.fsum((1 / 62, 1 / 61))
    assert [(item.result.score, item.result.source) for item in fused.evidence] == [
        (-1000.0, "dense"),
        (1000000.0, "sparse"),
    ]
    assert [item.global_rank for item in result.results] == [1, 2, 3]


async def test_rrf_tie_uses_chunk_id_and_limit_applies_after_complete_fusion() -> None:
    orchestrator, _, dense, sparse, _ = _orchestrator()
    dense.results["d"] = (_scored(2, 100.0, "dense", 1),)
    sparse.results["s"] = (_scored(1, -100.0, "sparse", 1),)
    result = await orchestrator.execute(
        _plan(
            _subquery("d", RetrievalMode.DENSE),
            _subquery("s", RetrievalMode.SPARSE),
        ),
        global_limit=1,
    )
    assert len(result.results) == 1
    assert result.results[0].chunk.id == _chunk(1).id
    assert result.results[0].global_rank == 1


async def test_duplicate_within_invocation_and_conflicting_snapshot_fail() -> None:
    orchestrator, _, dense, sparse, _ = _orchestrator()
    duplicate = _scored(1, 0.9, "dense", 1)
    dense.results["duplicate"] = (
        duplicate,
        ScoredChunk(chunk=duplicate.chunk, score=0.8, source="dense", rank=2),
    )
    with pytest.raises(IntegrityError, match="duplicate"):
        await orchestrator.execute(
            _plan(_subquery("duplicate", RetrievalMode.DENSE)),
            global_limit=5,
        )

    dense.results["dense"] = (_scored(1, 0.9, "dense", 1),)
    conflict = replace(_chunk(1), text="conflicting canonical snapshot")
    sparse.results["sparse"] = (ScoredChunk(chunk=conflict, score=9.0, source="sparse", rank=1),)
    with pytest.raises(IntegrityError, match="conflicting"):
        await orchestrator.execute(
            _plan(
                _subquery("dense", RetrievalMode.DENSE),
                _subquery("sparse", RetrievalMode.SPARSE),
            ),
            global_limit=5,
        )


@pytest.mark.parametrize("value", [True, 0, 101, 1.5, "5"])
async def test_invalid_global_limit(value: object) -> None:
    orchestrator, *_ = _orchestrator()
    error = TypeError if isinstance(value, (bool, float, str)) else ValueError
    with pytest.raises(error):
        await orchestrator.execute(
            _plan(_subquery("q", RetrievalMode.DENSE)),
            global_limit=cast(int, value),
        )


@pytest.mark.parametrize("value", [True, 0, 33, 1.5, "4"])
def test_invalid_concurrency_and_unfrozen_registry(value: object) -> None:
    registry = PluginRegistry(core_version="0.20.1")
    registry.load_plugin(_Plugin(_Retriever("dense"), _Retriever("sparse"), _Promoter()))
    registry.freeze()
    error = TypeError if isinstance(value, (bool, float, str)) else ValueError
    with pytest.raises(error):
        MultiSourceRetriever(registry, _Provider(), max_concurrency=cast(int, value))

    unfrozen = PluginRegistry(core_version="0.20.1")
    with pytest.raises(ValueError, match="frozen"):
        MultiSourceRetriever(unfrozen, _Provider())


@pytest.mark.parametrize("limit", [1, 4, 32])
async def test_concurrency_bound_and_completion_order_independence(limit: int) -> None:
    orchestrator, _, dense, _, _ = _orchestrator(max_concurrency=limit)
    subqueries = tuple(_subquery(f"q{index}", RetrievalMode.DENSE) for index in range(1, 7))
    for index in range(1, 7):
        dense.results[f"q{index}"] = (_scored(index, 1.0, "dense", 1),)
        dense.delays[f"q{index}"] = (7 - index) * 0.002

    first = await orchestrator.execute(_plan(*subqueries), global_limit=10)
    for index in range(1, 7):
        dense.delays[f"q{index}"] = index * 0.002
    second = await orchestrator.execute(_plan(*subqueries), global_limit=10)

    assert dense.max_active <= limit
    assert first == second
    assert [trace.invocation_id for trace in first.invocations] == [
        f"sq-{index}:dense" for index in range(1, 7)
    ]


async def test_fail_fast_cancels_and_awaits_peer_cleanup() -> None:
    orchestrator, _, dense, _, _ = _orchestrator(max_concurrency=2)
    dense.failures["fail"] = StorageError("storage failed")
    dense.delays["slow"] = 30
    with pytest.raises(StorageError, match="storage failed"):
        await orchestrator.execute(
            _plan(
                _subquery("fail", RetrievalMode.DENSE),
                _subquery("slow", RetrievalMode.DENSE),
            ),
            global_limit=5,
        )
    assert dense.cancelled == 1
    assert dense.active == 0
    assert dense.cleaned == 2


async def test_simultaneous_failures_choose_lowest_invocation_order() -> None:
    orchestrator, _, dense, sparse, _ = _orchestrator(max_concurrency=2)
    dense.failures["q"] = StorageError("dense wins")
    sparse.failures["q"] = IntegrityError("sparse loses")
    with pytest.raises(StorageError, match="dense wins"):
        await orchestrator.execute(
            _plan(_subquery("q", RetrievalMode.HYBRID)),
            global_limit=5,
        )


async def test_unexpected_plugin_failure_is_wrapped_with_invocation_id() -> None:
    orchestrator, _, dense, _, _ = _orchestrator()
    dense.failures["q"] = RuntimeError("vendor leaked")
    with pytest.raises(PluginError) as caught:
        await orchestrator.execute(
            _plan(_subquery("q", RetrievalMode.DENSE)),
            global_limit=5,
        )
    assert caught.value.details["retrieval.invocation_id"] == "sq-1:dense"


async def test_caller_cancellation_cleans_up_invocations() -> None:
    orchestrator, _, dense, _, _ = _orchestrator(max_concurrency=2)
    dense.delays["q1"] = dense.delays["q2"] = 30
    task = asyncio.create_task(
        orchestrator.execute(
            _plan(
                _subquery("q1", RetrievalMode.DENSE),
                _subquery("q2", RetrievalMode.DENSE),
            ),
            global_limit=5,
        )
    )
    await dense.started.wait()
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert dense.active == 0
    assert dense.cancelled >= 1


async def test_multi_hop_and_multi_doc_flags_and_filters_are_preserved() -> None:
    source_id = UUID("00000000-0000-4000-8000-000000000003")
    notebook_id = UUID("00000000-0000-4000-8000-000000000004")
    filters = MetadataFilter(notebook_id=notebook_id, source_ids=(source_id,))
    orchestrator, _, dense, _, _ = _orchestrator()
    plan = _plan(
        _subquery("q", RetrievalMode.DENSE, filters=filters),
        multi_hop=True,
        multi_doc=True,
    )
    result = await orchestrator.execute(plan, global_limit=5)
    assert result.plan is plan
    assert result.plan.requires_multi_hop is True
    assert result.plan.requires_multi_doc is True
    assert dense.calls[0][2] is filters
    assert result.invocations[0].filters is filters


@pytest.mark.parametrize("intent", tuple(RetrievalIntent))
async def test_all_planner_intents_have_identical_dispatch(intent: RetrievalIntent) -> None:
    orchestrator, _, dense, _, _ = _orchestrator()
    result = await orchestrator.execute(
        _plan(_subquery("q", RetrievalMode.DENSE), intent=intent),
        global_limit=5,
    )
    assert result.plan.intent is intent
    assert len(dense.calls) == 1


async def test_cached_provider_interaction_remains_provider_owned(tmp_path: Path) -> None:
    underlying = _Provider()
    cache = SQLiteEmbeddingCache(tmp_path / "fusion-cache.db")
    await cache.initialize()
    cached = CachedEmbeddingProvider(underlying, cache)
    orchestrator, _, dense, _, _ = _orchestrator(provider=cached)
    dense.results["same text"] = (_scored(1, 0.9, "dense", 1),)
    plan = _plan(_subquery("same text", RetrievalMode.DENSE, filters=MetadataFilter()))

    await orchestrator.execute(plan, global_limit=5)
    await orchestrator.execute(plan, global_limit=5)

    assert underlying.calls == 1
    assert len(dense.calls) == 2


async def test_mixed_zero_and_nonzero_streams_and_evidence_are_bounded() -> None:
    orchestrator, _, dense, sparse, promoter = _orchestrator()
    dense.results["hit"] = tuple(
        _scored(index, float(101 - index), "dense", index) for index in range(1, 101)
    )
    result = await orchestrator.execute(
        _plan(
            _subquery("hit", RetrievalMode.DENSE, max_results=100),
            _subquery("miss", RetrievalMode.SPARSE, max_results=100),
        ),
        global_limit=100,
    )
    assert len(result.results) == 100
    assert sparse.calls
    assert promoter.calls[-1] == ()
    assert sum(len(item.evidence) for item in result.results) == 100


async def test_malformed_streams_and_promoter_failures_propagate() -> None:
    orchestrator, _, dense, _, promoter = _orchestrator()
    dense.results["bad-source"] = (_scored(1, 0.9, "sparse", 1),)
    with pytest.raises(IntegrityError, match="wrong source"):
        await orchestrator.execute(
            _plan(_subquery("bad-source", RetrievalMode.DENSE)),
            global_limit=5,
        )

    dense.results["promotion"] = (_scored(1, 0.9, "dense", 1),)
    promoter.failure = StorageError("parent lookup failed")
    with pytest.raises(StorageError, match="parent lookup failed"):
        await orchestrator.execute(
            _plan(_subquery("promotion", RetrievalMode.DENSE)),
            global_limit=5,
        )


async def test_provider_failure_propagates_unchanged() -> None:
    provider = _Provider()
    provider.failure = StorageError("embedding unavailable")
    orchestrator, *_ = _orchestrator(provider=provider)
    with pytest.raises(StorageError, match="embedding unavailable"):
        await orchestrator.execute(
            _plan(_subquery("q", RetrievalMode.DENSE)),
            global_limit=5,
        )


async def test_constructor_and_execute_type_boundaries() -> None:
    registry = PluginRegistry(core_version="0.20.1")
    registry.freeze()
    with pytest.raises(TypeError, match="registry"):
        MultiSourceRetriever(cast(PluginRegistry, object()), _Provider())
    with pytest.raises(TypeError, match="embedding_provider"):
        MultiSourceRetriever(registry, cast(EmbeddingProviderV1, object()))

    orchestrator, *_ = _orchestrator()
    with pytest.raises(TypeError, match="plan"):
        await orchestrator.execute(cast(RetrievalPlan, object()), global_limit=5)


async def test_registered_retriever_must_report_matching_mode() -> None:
    wrong = _Retriever("sparse")
    registry = PluginRegistry(core_version="0.20.1")
    registry.load_plugin(_Plugin(wrong, _Retriever("sparse"), _Promoter()))
    registry.freeze()
    orchestrator = MultiSourceRetriever(registry, _Provider())
    with pytest.raises(IntegrityError, match="wrong mode"):
        await orchestrator.execute(
            _plan(_subquery("q", RetrievalMode.DENSE)),
            global_limit=5,
        )


@pytest.mark.parametrize(
    "vector",
    [
        [1.0, 2.0],
        (1.0,),
        (),
        (1.0, float("nan")),
        (1.0, True),
    ],
)
async def test_malformed_embedding_vectors_fail_closed(vector: object) -> None:
    class BadProvider(_Provider):
        async def embed(self, text: str) -> EmbeddingVector:
            del text
            return cast(EmbeddingVector, vector)

    orchestrator, *_ = _orchestrator(provider=BadProvider())
    with pytest.raises(IntegrityError, match="embedding"):
        await orchestrator.execute(
            _plan(_subquery("q", RetrievalMode.DENSE)),
            global_limit=5,
        )


@pytest.mark.parametrize(
    ("bad_stream", "message"),
    [
        (["not-a-tuple"], "non-tuple"),
        (("not-scored",), "invalid result"),
        ((_scored(1, 0.9, "dense", 2),), "ranks"),
        (
            (
                _scored(1, 0.8, "dense", 1),
                _scored(2, 0.9, "dense", 2),
            ),
            "ordering",
        ),
    ],
)
async def test_other_malformed_retriever_streams_fail(
    bad_stream: object,
    message: str,
) -> None:
    orchestrator, _, dense, _, _ = _orchestrator()
    dense.results["q"] = cast(tuple[ScoredChunk, ...], bad_stream)
    with pytest.raises(IntegrityError, match=message):
        await orchestrator.execute(
            _plan(_subquery("q", RetrievalMode.DENSE)),
            global_limit=5,
        )


async def test_retriever_and_promoter_top_k_and_non_expansion_are_enforced() -> None:
    orchestrator, _, dense, _, promoter = _orchestrator()
    dense.results["too-many"] = (
        _scored(1, 0.9, "dense", 1),
        _scored(2, 0.8, "dense", 2),
    )
    with pytest.raises(IntegrityError, match="top_k"):
        await orchestrator.execute(
            _plan(_subquery("too-many", RetrievalMode.DENSE, max_results=1)),
            global_limit=5,
        )

    dense.results["expand"] = (_scored(1, 0.9, "dense", 1),)
    promoter.transform = lambda values: (
        values[0],
        _scored(2, 0.8, "dense", 2),
    )
    with pytest.raises(IntegrityError, match="expand"):
        await orchestrator.execute(
            _plan(_subquery("expand", RetrievalMode.DENSE, max_results=2)),
            global_limit=5,
        )


async def test_unexpected_promoter_failure_is_wrapped() -> None:
    orchestrator, _, dense, _, promoter = _orchestrator()
    dense.results["q"] = (_scored(1, 0.9, "dense", 1),)
    promoter.failure = RuntimeError("plugin leaked")
    with pytest.raises(PluginError) as caught:
        await orchestrator.execute(
            _plan(_subquery("q", RetrievalMode.DENSE)),
            global_limit=5,
        )
    assert caught.value.details["retrieval.invocation_id"] == "sq-1:dense"


def _valid_fusion_records() -> tuple[
    RetrievalPlan,
    RetrievalInvocationTrace,
    FusionEvidence,
    FusedChunkResult,
    RetrievalFusionResult,
]:
    plan = _plan(_subquery("q", RetrievalMode.DENSE))
    scored = _scored(1, 0.9, "dense", 1)
    trace = RetrievalInvocationTrace(
        invocation_id="sq-1:dense",
        subquery_index=1,
        declared_mode=RetrievalMode.DENSE,
        effective_mode=RetrievalMode.DENSE,
        query_text="q",
        filters=MetadataFilter(),
        requested_top_k=10,
        raw_results=(scored,),
        promoted_results=(scored,),
    )
    evidence = FusionEvidence(
        invocation_id="sq-1:dense",
        subquery_index=1,
        declared_mode=RetrievalMode.DENSE,
        effective_mode=RetrievalMode.DENSE,
        result=scored,
        identity_introduced_by_parent_promotion=False,
    )
    fused = FusedChunkResult(
        chunk=scored.chunk,
        rrf_score=1 / 61,
        global_rank=1,
        evidence=(evidence,),
    )
    result = RetrievalFusionResult(plan=plan, invocations=(trace,), results=(fused,))
    return plan, trace, evidence, fused, result


def _unsafe_replace(value: object, changes: dict[str, object]) -> object:
    """Exercise runtime dataclass validation with intentionally invalid types."""
    return cast(object, replace(cast(Any, value), **changes))


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"subquery_index": True}, TypeError),
        ({"subquery_index": 0}, ValueError),
        ({"declared_mode": "dense"}, TypeError),
        ({"effective_mode": RetrievalMode.HYBRID}, ValueError),
        ({"invocation_id": "wrong"}, ValueError),
        ({"filters": object()}, TypeError),
        ({"requested_top_k": True}, TypeError),
        ({"requested_top_k": 101}, ValueError),
        ({"raw_results": []}, TypeError),
        ({"raw_results": tuple(_scored(i, 1.0, "dense", i) for i in range(1, 12))}, ValueError),
        ({"raw_results": (object(),)}, TypeError),
    ],
)
def test_invocation_trace_validation(changes: dict[str, object], error: type[Exception]) -> None:
    _, trace, *_ = _valid_fusion_records()
    with pytest.raises(error):
        _unsafe_replace(trace, changes)


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"subquery_index": True}, TypeError),
        ({"subquery_index": 17}, ValueError),
        ({"declared_mode": "dense"}, TypeError),
        ({"effective_mode": RetrievalMode.HYBRID}, ValueError),
        ({"invocation_id": "wrong"}, ValueError),
        ({"result": object()}, TypeError),
        ({"identity_introduced_by_parent_promotion": 1}, TypeError),
    ],
)
def test_fusion_evidence_validation(changes: dict[str, object], error: type[Exception]) -> None:
    _, _, evidence, *_ = _valid_fusion_records()
    with pytest.raises(error):
        _unsafe_replace(evidence, changes)


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"chunk": object()}, TypeError),
        ({"rrf_score": 0.0}, ValueError),
        ({"global_rank": True}, TypeError),
        ({"global_rank": 0}, ValueError),
        ({"evidence": []}, TypeError),
        ({"evidence": ()}, ValueError),
        ({"evidence": (object(),)}, TypeError),
    ],
)
def test_fused_result_validation(changes: dict[str, object], error: type[Exception]) -> None:
    _, _, _, fused, _ = _valid_fusion_records()
    with pytest.raises(error):
        _unsafe_replace(fused, changes)


def test_fused_result_rejects_mismatched_evidence_identity() -> None:
    _, _, evidence, fused, _ = _valid_fusion_records()
    other = replace(evidence, result=_scored(2, 0.8, "dense", 1))
    with pytest.raises(ValueError, match="identity"):
        replace(fused, evidence=(other,))


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"plan": object()}, TypeError),
        ({"invocations": []}, TypeError),
        ({"invocations": (object(),)}, TypeError),
        ({"results": []}, TypeError),
        ({"results": (object(),)}, TypeError),
    ],
)
def test_retrieval_fusion_result_validation(
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    *_, result = _valid_fusion_records()
    with pytest.raises(error):
        _unsafe_replace(result, changes)


def test_retrieval_fusion_result_rejects_duplicate_invocations_and_bad_ranks() -> None:
    _, trace, _, fused, result = _valid_fusion_records()
    with pytest.raises(ValueError, match="unique"):
        replace(result, invocations=(trace, trace))
    with pytest.raises(ValueError, match="ranks"):
        replace(result, results=(replace(fused, global_rank=2),))
