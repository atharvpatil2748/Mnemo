"""Focused acceptance tests for ADR-0042 fusion-aware reranking."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from mnemo import CapabilityKind, PluginRegistry, PluginValidationError
from mnemo.config import RerankerConfig
from mnemo.interfaces import (
    ContractValidationError,
    DependencyUnavailableError,
    FusionRerankerCapabilities,
    FusionRerankingInterfaceV1,
    IntegrityError,
    LifecycleError,
    PluginError,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    CrossEncoderEvidence,
    FusedChunkResult,
    FusionEvidence,
    MetadataFilter,
    RerankedChunkResult,
    RerankFallbackReason,
    RerankPolicy,
    RetrievalFusionResult,
    RetrievalIntent,
    RetrievalInvocationTrace,
    RetrievalMode,
    RetrievalPlan,
    RetrievalRerankResult,
    ScoredChunk,
    SubQuery,
    stable_sigmoid,
)
from mnemo.registry import RegistryFrozenError
from mnemo.retrieval.reranker import (
    MAX_PAIR_TOKENS,
    MAX_RERANK_CANDIDATES,
    MODEL_ID,
    MODEL_REVISION,
    RERANK_BATCH_SIZE,
    CrossEncoderReranker,
    CrossEncoderRerankerPlugin,
    RerankingModule,
    _CrossEncoderRuntime,
    _validate_snapshot,
)

pytestmark = pytest.mark.anyio

_DOCUMENT_ID = UUID("10000000-0000-4000-8000-000000000001")
_VERSION_ID = UUID("10000000-0000-4000-8000-000000000002")


def _chunk(index: int, *, text: str | None = None) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        text=text or f"candidate text {index}",
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Chapter",),
    )


def _fusion(count: int = 3) -> RetrievalFusionResult:
    subqueries = (
        SubQuery(
            query_text="dense question",
            retrieval_mode=RetrievalMode.DENSE,
            filters=MetadataFilter(),
            max_results=max(1, count),
        ),
        SubQuery(
            query_text="sparse question",
            retrieval_mode=RetrievalMode.SPARSE,
            filters=MetadataFilter(),
            max_results=max(1, count),
        ),
    )
    plan = RetrievalPlan(
        intent=RetrievalIntent.FACTUAL,
        sub_queries=subqueries,
        requires_multi_hop=False,
        requires_multi_doc=True,
    )
    if count == 0:
        return RetrievalFusionResult(plan=plan, invocations=(), results=())
    dense = tuple(
        ScoredChunk(chunk=_chunk(i), score=1.0 - i / 100, source="dense", rank=i)
        for i in range(1, count + 1)
    )
    sparse = tuple(
        ScoredChunk(chunk=_chunk(i), score=-float(i), source="sparse", rank=i)
        for i in range(1, count + 1)
    )
    traces = (
        RetrievalInvocationTrace(
            invocation_id="sq-1:dense",
            subquery_index=1,
            declared_mode=RetrievalMode.DENSE,
            effective_mode=RetrievalMode.DENSE,
            query_text="dense question",
            filters=MetadataFilter(),
            requested_top_k=max(1, count),
            raw_results=dense,
            promoted_results=dense,
        ),
        RetrievalInvocationTrace(
            invocation_id="sq-2:sparse",
            subquery_index=2,
            declared_mode=RetrievalMode.SPARSE,
            effective_mode=RetrievalMode.SPARSE,
            query_text="sparse question",
            filters=MetadataFilter(),
            requested_top_k=max(1, count),
            raw_results=sparse,
            promoted_results=sparse,
        ),
    )
    results = tuple(
        FusedChunkResult(
            chunk=_chunk(i),
            rrf_score=2.0 / (60 + i),
            global_rank=i,
            evidence=(
                FusionEvidence(
                    invocation_id="sq-1:dense",
                    subquery_index=1,
                    declared_mode=RetrievalMode.DENSE,
                    effective_mode=RetrievalMode.DENSE,
                    result=dense[i - 1],
                    identity_introduced_by_parent_promotion=i == 1,
                ),
                FusionEvidence(
                    invocation_id="sq-2:sparse",
                    subquery_index=2,
                    declared_mode=RetrievalMode.SPARSE,
                    effective_mode=RetrievalMode.SPARSE,
                    result=sparse[i - 1],
                    identity_introduced_by_parent_promotion=False,
                ),
            ),
        )
        for i in range(1, count + 1)
    )
    return RetrievalFusionResult(plan=plan, invocations=traces, results=results)


def _evidence(chunk: Chunk, logit: float) -> CrossEncoderEvidence:
    relevance = stable_sigmoid(logit)
    return CrossEncoderEvidence(
        chunk_id=chunk.id,
        raw_logit=logit,
        relevance_score=relevance,
        below_relevance_threshold=relevance < 0.4,
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
    )


def _result(
    query: str, fusion: RetrievalFusionResult, logits: tuple[float, ...]
) -> RetrievalRerankResult:
    records = [
        RerankedChunkResult(
            fused_result=fused,
            rerank_evidence=_evidence(fused.chunk, logit),
            reranked_rank=1,
        )
        for fused, logit in zip(fusion.results, logits, strict=True)
    ]
    records.sort(
        key=lambda item: (
            -cast(CrossEncoderEvidence, item.rerank_evidence).relevance_score,
            item.fused_result.global_rank,
            item.fused_result.chunk.id,
        )
    )
    records = [replace(item, reranked_rank=rank) for rank, item in enumerate(records, 1)]
    return RetrievalRerankResult(
        query=query,
        fusion_result=fusion,
        policy=RerankPolicy.CROSS_ENCODER,
        results=tuple(records),
    )


class _Provider:
    def __init__(self, logits: tuple[float, ...]) -> None:
        self.logits = logits
        self.calls: list[tuple[str, RetrievalFusionResult]] = []
        self.failure: BaseException | None = None
        self.override: object | None = None

    def capabilities(self) -> FusionRerankerCapabilities:
        return FusionRerankerCapabilities(
            supports_cross_encoder=True,
            supports_batch=True,
            preserves_fusion_evidence=True,
            max_candidates=100,
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
        )

    async def rerank_fused(
        self,
        query: str,
        fusion_result: RetrievalFusionResult,
    ) -> RetrievalRerankResult:
        self.calls.append((query, fusion_result))
        if self.failure is not None:
            raise self.failure
        if self.override is not None:
            return cast(RetrievalRerankResult, self.override)
        return _result(query, fusion_result, self.logits)


@dataclass(slots=True)
class _Plugin:
    name: str
    callback: Callable[[PluginRegistry], None]
    version: str = "1.0.0"
    core_version_range: str = ">=0.20.1"

    def capabilities(self) -> tuple[str, ...]:
        return ("fusion_reranker",)

    def register(self, registry: PluginRegistry) -> None:
        self.callback(registry)


def _register_provider(
    registry: PluginRegistry,
    provider: _Provider,
    *,
    name: str,
    priority: int,
) -> None:
    registry.load_plugin(
        _Plugin(
            name=name,
            callback=lambda target: target.register_fusion_reranker(
                "primary", provider, priority=priority
            ),
        )
    )


def _module(provider: _Provider | None = None) -> RerankingModule:
    registry = PluginRegistry(core_version="0.20.1")
    if provider is not None:
        _register_provider(registry, provider, name="provider", priority=1)
    registry.freeze()
    return RerankingModule(registry)


def test_contract_models_are_immutable_runtime_checkable_and_validate_sigmoid() -> None:
    fusion = _fusion(1)
    provider = _Provider((0.0,))
    assert isinstance(provider, FusionRerankingInterfaceV1)
    evidence = _evidence(fusion.results[0].chunk, 0.0)
    assert evidence.relevance_score == 0.5
    with pytest.raises(FrozenInstanceError):
        evidence.raw_logit = 1.0  # type: ignore[misc]
    assert stable_sigmoid(1000.0) == 1.0
    assert stable_sigmoid(-100.0) > 0.0
    with pytest.raises(ValueError, match="finite"):
        _evidence(fusion.results[0].chunk, math.inf)
    with pytest.raises(ValueError, match="sigmoid"):
        replace(evidence, relevance_score=0.6)


def test_threshold_is_strict_at_exact_point_four() -> None:
    chunk = _chunk(1)
    logit = math.log(0.4 / 0.6)
    exact = _evidence(chunk, logit)
    assert math.isclose(exact.relevance_score, 0.4, rel_tol=1e-15)
    assert exact.below_relevance_threshold is False
    assert _evidence(chunk, logit - 0.01).below_relevance_threshold is True
    assert _evidence(chunk, logit + 0.01).below_relevance_threshold is False
    with pytest.raises(ValueError, match="threshold"):
        replace(exact, below_relevance_threshold=True)


async def test_empty_input_normalizes_query_without_resolving_provider() -> None:
    provider = _Provider(())
    result = await _module(provider).execute("  original\n query  ", _fusion(0))
    assert result.query == "original query"
    assert result.policy is RerankPolicy.UNCHANGED_EMPTY
    assert result.results == ()
    assert provider.calls == []


async def test_empty_query_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="empty"):
        await _module().execute(" \n ", _fusion(0))


async def test_missing_provider_returns_typed_rrf_fallback_without_loss() -> None:
    fusion = _fusion(3)
    result = await _module().execute("question", fusion)
    assert result.policy is RerankPolicy.RRF_FALLBACK
    assert result.fallback_reason is RerankFallbackReason.PROVIDER_UNAVAILABLE
    assert tuple(item.fused_result for item in result.results) == fusion.results
    assert tuple(item.reranked_rank for item in result.results) == (1, 2, 3)
    assert all(item.rerank_evidence is None for item in result.results)


async def test_module_uses_only_explicit_original_query_and_preserves_provenance() -> None:
    fusion = _fusion(3)
    provider = _Provider((-1.0, 3.0, 0.0))
    result = await _module(provider).execute("  What is duty? ", fusion)
    assert provider.calls == [("What is duty?", fusion)]
    assert all(call[0] not in {"dense question", "sparse question"} for call in provider.calls)
    assert result.fusion_result is fusion
    assert tuple(item.fused_result for item in result.results) == (
        fusion.results[1],
        fusion.results[2],
        fusion.results[0],
    )
    assert all(
        item.fused_result
        is next(
            original
            for original in fusion.results
            if original.chunk.id == item.fused_result.chunk.id
        )
        for item in result.results
    )
    assert result.fusion_result.invocations is fusion.invocations
    assert result.fusion_result.results[0].evidence is fusion.results[0].evidence


async def test_equal_scores_use_global_rank_then_chunk_id_and_keep_global_rank() -> None:
    fusion = _fusion(3)
    result = await _module(_Provider((1.0, 1.0, 1.0))).execute("query", fusion)
    assert tuple(item.fused_result.global_rank for item in result.results) == (1, 2, 3)
    assert tuple(item.reranked_rank for item in result.results) == (1, 2, 3)


@pytest.mark.parametrize("count", [1, 3, 100])
async def test_candidate_cardinality_never_changes(count: int) -> None:
    fusion = _fusion(count)
    logits = tuple((i % 11 - 5) / 2 for i in range(count))
    result = await _module(_Provider(logits)).execute("query", fusion)
    assert len(result.results) == count
    assert {item.fused_result.chunk.id for item in result.results} == {
        item.chunk.id for item in fusion.results
    }


async def test_registered_failures_never_fall_back() -> None:
    provider = _Provider((0.0,))
    provider.failure = IntegrityError("bad output")
    with pytest.raises(IntegrityError, match="bad output"):
        await _module(provider).execute("query", _fusion(1))
    provider.failure = RuntimeError("backend exploded")
    with pytest.raises(PluginError) as caught:
        await _module(provider).execute("query", _fusion(1))
    assert isinstance(caught.value.__cause__, RuntimeError)


async def test_malformed_provider_result_is_rejected() -> None:
    fusion = _fusion(1)
    provider = _Provider((0.0,))
    provider.override = object()
    with pytest.raises(IntegrityError, match="invalid result type"):
        await _module(provider).execute("query", fusion)
    provider.override = _result("different", fusion, (0.0,))
    with pytest.raises(IntegrityError, match="changed query"):
        await _module(provider).execute("query", fusion)


class _Runtime:
    def __init__(self, logits: tuple[float, ...], *, delay: float = 0.0) -> None:
        self.logits = logits
        self.delay = delay
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def predict_logits(self, query: str, texts: tuple[str, ...]) -> tuple[float, ...]:
        self.calls.append((query, texts))
        if self.delay:
            time.sleep(self.delay)
        return self.logits


class _TestCrossEncoder(CrossEncoderReranker):
    def __init__(self, runtime: _Runtime) -> None:
        super().__init__(RerankerConfig(provider="sentence-transformers", model=MODEL_ID))
        self.runtime = runtime
        self.loads = 0

    def _load_runtime(self) -> Any:
        self.loads += 1
        return self.runtime


async def test_reference_provider_lifecycle_alignment_and_repeatability() -> None:
    runtime = _Runtime((2.0, -1.0, 0.5))
    provider = _TestCrossEncoder(runtime)
    assert provider.capabilities().model_id == MODEL_ID
    assert provider.capabilities().model_revision == MODEL_REVISION
    with pytest.raises(LifecycleError, match="startup"):
        await provider.rerank_fused("query", _fusion(3))
    await provider.initialize()
    await provider.initialize()
    first = await provider.rerank_fused("query", _fusion(3))
    second = await provider.rerank_fused("query", _fusion(3))
    assert provider.loads == 1
    assert first == second
    assert runtime.calls[0] == (
        "query",
        tuple(item.chunk.text for item in _fusion(3).results),
    )
    await provider.close()
    await provider.close()
    with pytest.raises(LifecycleError):
        await provider.rerank_fused("query", _fusion(3))


@pytest.mark.parametrize(
    "logits",
    [(), (0.0, 1.0), (math.nan,)],
)
async def test_reference_provider_rejects_missing_extra_and_nonfinite_scores(
    logits: tuple[float, ...],
) -> None:
    provider = _TestCrossEncoder(_Runtime(logits))
    await provider.initialize()
    with pytest.raises(IntegrityError):
        await provider.rerank_fused("query", _fusion(1))
    await provider.close()


async def test_reference_provider_cancellation_discards_result() -> None:
    provider = _TestCrossEncoder(_Runtime((0.0,), delay=0.05))
    await provider.initialize()
    task = asyncio.create_task(provider.rerank_fused("query", _fusion(1)))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.06)
    await provider.close()


def test_reference_runtime_uses_only_second_512_and_batches_sixteen() -> None:
    batches: list[dict[str, Any]] = []

    class _Tensor:
        def to(self, _: str) -> _Tensor:
            return self

        def reshape(self, _: int) -> _Tensor:
            return self

        def detach(self) -> _Tensor:
            return self

        def cpu(self) -> _Tensor:
            return self

        def tolist(self) -> list[float]:
            return [0.0] * batches[-1]["size"]

    class _Tokenizer:
        def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if len(args) == 1:
                return {"input_ids": [1, 2]}
            batches.append(
                {
                    "size": len(args[0]),
                    "truncation": kwargs["truncation"],
                    "max_length": kwargs["max_length"],
                }
            )
            return {"input_ids": _Tensor()}

    class _ModelBody:
        def __call__(self, **_: Any) -> Any:
            return type("Output", (), {"logits": _Tensor()})()

    class _Model:
        tokenizer = _Tokenizer()
        model = _ModelBody()

    class _Inference:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_: Any) -> None:
            return None

    torch = type("Torch", (), {"inference_mode": staticmethod(_Inference)})()
    runtime = _CrossEncoderRuntime(model=_Model(), torch=torch)
    assert len(runtime.predict_logits("query", tuple(str(i) for i in range(33)))) == 33
    assert [item["size"] for item in batches] == [16, 16, 1]
    assert all(item["truncation"] == "only_second" for item in batches)
    assert all(item["max_length"] == 512 for item in batches)
    assert RERANK_BATCH_SIZE == 16
    assert MAX_PAIR_TOKENS == 512
    assert MAX_RERANK_CANDIDATES == 100


def test_reference_runtime_rejects_query_that_cannot_fit() -> None:
    class _Tokenizer:
        def __call__(self, *_: Any, **__: Any) -> dict[str, list[int]]:
            return {"input_ids": [1] * 510}

    model = type("Model", (), {"tokenizer": _Tokenizer()})()
    runtime = _CrossEncoderRuntime(model=model, torch=object())
    with pytest.raises(ContractValidationError, match="without truncation"):
        runtime.predict_logits("long", ("candidate",))


async def test_registry_capability_priority_conflict_freeze_and_shutdown() -> None:
    registry = PluginRegistry(core_version="0.20.1")
    low = _Provider((0.0,))
    high = _Provider((1.0,))
    _register_provider(registry, low, name="low", priority=1)
    _register_provider(registry, high, name="high", priority=2)
    assert registry.resolve_fusion_reranker("primary") is high
    records = registry.list_registrations(CapabilityKind.FUSION_RERANKER)
    assert [item.priority for item in records] == [2, 1]
    with pytest.raises(PluginValidationError, match="registration failed"):
        _register_provider(registry, _Provider((2.0,)), name="conflict", priority=2)
    order: list[str] = []

    async def first() -> None:
        order.append("first")

    async def second() -> None:
        order.append("second")
        raise RuntimeError("shutdown")

    registry.register_shutdown_hook(first)
    registry.register_shutdown_hook(second)
    registry.freeze()
    with pytest.raises(RegistryFrozenError):
        registry.register_fusion_reranker("other", low, priority=1)
    with pytest.raises(RuntimeError, match="shutdown"):
        await registry.execute_shutdown_hooks()
    assert order == ["second", "first"]


async def test_plugin_registers_explicit_legacy_and_fusion_capabilities() -> None:
    provider = _TestCrossEncoder(_Runtime((0.0,)))
    plugin = CrossEncoderRerankerPlugin(provider)
    registry = PluginRegistry(core_version="0.20.1")
    descriptor = registry.load_plugin(plugin)
    assert descriptor.name == plugin.name
    assert registry.resolve_fusion_reranker("primary") is provider
    legacy = registry.resolve_reranker("primary")
    assert legacy is not None
    assert legacy is not provider
    assert registry.resolve_fusion_reranker("legacy-only") is None
    await registry.execute_startup_hooks()
    registry.freeze()
    await registry.execute_shutdown_hooks()


def test_cross_encoder_config_is_exact_and_construction_is_inert() -> None:
    provider = CrossEncoderReranker(
        RerankerConfig(provider="sentence-transformers", model=MODEL_ID)
    )
    assert provider.capabilities().model_revision == MODEL_REVISION
    with pytest.raises(ValueError, match="provider"):
        CrossEncoderReranker(RerankerConfig(provider="other", model=MODEL_ID))
    with pytest.raises(ValueError, match="model"):
        CrossEncoderReranker(
            RerankerConfig(provider="sentence-transformers", model="floating/model")
        )


def _snapshot(tmp_path: Path, **config_changes: object) -> Path:
    config: dict[str, object] = {
        "max_position_embeddings": 512,
        "id2label": {"0": "LABEL_0"},
        "sbert_ce_default_activation_function": "torch.nn.modules.linear.Identity",
    }
    config.update(config_changes)
    for name in ("tokenizer.json", "tokenizer_config.json", "model.safetensors"):
        (tmp_path / name).write_text("fixture", encoding="utf-8")
    (tmp_path / "config.json").write_text(__import__("json").dumps(config), encoding="utf-8")
    (tmp_path / "README.md").write_text("---\nlicense: apache-2.0\n---\n", encoding="utf-8")
    return tmp_path


def test_snapshot_validation_accepts_only_exact_artifacts(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    _validate_snapshot(snapshot)
    (snapshot / "model.safetensors").unlink()
    with pytest.raises(DependencyUnavailableError, match="incomplete"):
        _validate_snapshot(snapshot)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"max_position_embeddings": 511}, "512 positions"),
        ({"id2label": {"0": "A", "1": "B"}}, "single-logit"),
        ({"sbert_ce_default_activation_function": "Sigmoid"}, "identity"),
    ],
)
def test_snapshot_validation_rejects_incompatible_model_metadata(
    tmp_path: Path,
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(IntegrityError, match=message):
        _validate_snapshot(_snapshot(tmp_path, **changes))


def test_snapshot_validation_requires_license_metadata(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    (snapshot / "README.md").write_text("license: unknown", encoding="utf-8")
    with pytest.raises(IntegrityError, match="license"):
        _validate_snapshot(snapshot)


async def test_legacy_adapter_preserves_raw_scores_and_respects_top_k() -> None:
    provider = _TestCrossEncoder(_Runtime((-2.0, 3.0, 0.0)))
    plugin = CrossEncoderRerankerPlugin(provider)
    registry = PluginRegistry(core_version="0.20.1")
    registry.load_plugin(plugin)
    await registry.execute_startup_hooks()
    legacy = registry.resolve_reranker("primary")
    assert legacy is not None
    candidates = tuple(
        ScoredChunk(chunk=_chunk(i), score=float(i), source="dense", rank=i) for i in range(1, 4)
    )
    reranked = await legacy.rerank(" query ", candidates, 2)
    assert tuple(item.chunk.id for item in reranked) == (
        candidates[1].chunk.id,
        candidates[2].chunk.id,
    )
    assert tuple(item.score for item in reranked) == (2.0, 3.0)
    assert tuple(item.rank for item in reranked) == (1, 2)
    await registry.execute_shutdown_hooks()


async def test_provider_validates_candidate_and_bound_contracts() -> None:
    provider = _TestCrossEncoder(_Runtime((0.0,)))
    await provider.initialize()
    candidate = ScoredChunk(chunk=_chunk(1), score=1.0, source="dense", rank=1)
    with pytest.raises(TypeError, match="tuple"):
        await provider.rerank("query", cast(Any, [candidate]), 1)
    with pytest.raises(TypeError, match="integer"):
        await provider.rerank("query", (candidate,), cast(Any, True))
    with pytest.raises(ValueError, match="from 1"):
        await provider.rerank("query", (candidate,), 101)
    with pytest.raises(IntegrityError, match="unique"):
        await provider._score_chunks("query", (_chunk(1), _chunk(1)))
    await provider.close()


@pytest.mark.parametrize(
    "logits",
    [cast(Any, [0.0]), cast(Any, (1,)), cast(Any, (True,))],
)
async def test_provider_rejects_malformed_score_sequences(logits: Any) -> None:
    provider = _TestCrossEncoder(_Runtime(cast(Any, logits)))
    await provider.initialize()
    with pytest.raises(IntegrityError, match="score"):
        await provider.rerank_fused("query", _fusion(1))
    await provider.close()


def test_reranking_module_requires_frozen_registry() -> None:
    with pytest.raises(TypeError, match="PluginRegistry"):
        RerankingModule(cast(Any, object()))
    with pytest.raises(ValueError, match="frozen"):
        RerankingModule(PluginRegistry(core_version="0.20.1"))


def test_plugin_requires_reference_provider() -> None:
    with pytest.raises(TypeError, match="CrossEncoderReranker"):
        CrossEncoderRerankerPlugin(cast(Any, object()))
