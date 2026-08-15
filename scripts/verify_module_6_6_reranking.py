"""Validate ADR-0042 with real Module 6.5 evidence and the pinned model."""

from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from mnemo import __version__
from mnemo.config import RerankerConfig
from mnemo.embeddings.cached import CachedEmbeddingProvider
from mnemo.embeddings.ollama import OllamaEmbedder
from mnemo.interfaces import (
    EmbeddingProviderV1,
    FusionRerankerCapabilities,
    IntegrityError,
    StorageInterfaceV1,
)
from mnemo.models import (
    MetadataFilter,
    RerankFallbackReason,
    RerankPolicy,
    RetrievalFusionResult,
    RetrievalIntent,
    RetrievalMode,
    RetrievalPlan,
    RetrievalRerankResult,
    SubQuery,
    stable_sigmoid,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import MultiSourceRetriever
from mnemo.retrieval.reranker import (
    MODEL_ID,
    MODEL_REVISION,
    CrossEncoderReranker,
    CrossEncoderRerankerPlugin,
    RerankingModule,
)
from mnemo.storage.cache import SQLiteEmbeddingCache
from verify_module_6_5_fusion import (
    EXPECTED_SHA256,
    ROOT,
    _builtins,
    _config,
    _retrieval_registry,
)

DATASET = ROOT / "goldenDataset" / "Bhagavad-gita-As-It-Is.pdf"
M65_EVIDENCE = ROOT / "docs" / "milestone-evidence" / "module-6.5-fusion.json"
EVIDENCE = ROOT / "docs" / "milestone-evidence" / "module-6.6-reranking.json"


class _FailureProvider:
    def capabilities(self) -> FusionRerankerCapabilities:
        return FusionRerankerCapabilities(
            supports_cross_encoder=True,
            supports_batch=True,
            preserves_fusion_evidence=True,
            max_candidates=100,
            model_id="acceptance/failure",
            model_revision="controlled-v1",
        )

    async def rerank_fused(
        self, query: str, fusion_result: RetrievalFusionResult
    ) -> RetrievalRerankResult:
        del query, fusion_result
        raise IntegrityError("controlled registered-provider failure")


class _FailurePlugin:
    name = "mnemo-module-6-6-failure-check"
    version = __version__
    core_version_range = ">=0.20.1"

    def capabilities(self) -> tuple[str, ...]:
        return ("fusion_reranker",)

    def register(self, registry: PluginRegistry) -> None:
        registry.register_fusion_reranker("primary", _FailureProvider(), priority=0)


def _run_id(evidence: dict[str, object]) -> str:
    database = Path(cast(str, evidence["sqlite_database"]))
    return database.parent.name


def _plan(evidence: dict[str, object]) -> RetrievalPlan:
    raw = cast(list[dict[str, object]], evidence["subqueries"])
    subqueries = tuple(
        SubQuery(
            query_text=cast(str, item["query_text"]),
            retrieval_mode=RetrievalMode(cast(str, item["retrieval_mode"])),
            filters=MetadataFilter.model_validate(item["filters"]),
            max_results=cast(int, item["max_results"]),
        )
        for item in raw
    )
    return RetrievalPlan(
        intent=RetrievalIntent.FACTUAL,
        sub_queries=subqueries,
        requires_multi_hop=False,
        requires_multi_doc=False,
    )


async def _real_fusion(
    evidence: dict[str, object],
) -> tuple[RetrievalFusionResult, StorageInterfaceV1, OllamaEmbedder, PluginRegistry]:
    config = _config(_run_id(evidence))
    builtins = _builtins(config)
    storage = builtins.resolve_storage("primary")
    if storage is None:
        raise AssertionError("historical Module 6.5 storage is unavailable")
    await storage.open()
    await builtins.execute_startup_hooks()
    provider = builtins.resolve_embedding_provider("primary")
    if not isinstance(provider, OllamaEmbedder):
        raise AssertionError("real Ollama provider is unavailable")
    cache = SQLiteEmbeddingCache(config.storage.sqlite.path.parent / "embedding-cache.db")
    await cache.initialize()
    cached: EmbeddingProviderV1 = CachedEmbeddingProvider(provider, cache)
    orchestrator = MultiSourceRetriever(
        _retrieval_registry(storage),
        cached,
        max_concurrency=4,
    )
    fusion = await orchestrator.execute(_plan(evidence), global_limit=10)
    return fusion, storage, provider, builtins


async def _run() -> dict[str, object]:
    digest = sha256(DATASET.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise AssertionError(f"golden corpus hash mismatch: {digest}")
    m65 = cast(dict[str, object], json.loads(M65_EVIDENCE.read_text(encoding="utf-8")))
    started = time.perf_counter()
    fusion, storage, ollama, builtins = await _real_fusion(m65)
    reranker = CrossEncoderReranker(
        RerankerConfig(provider="sentence-transformers", model=MODEL_ID)
    )
    registry = PluginRegistry(core_version=__version__)
    registry.load_plugin(CrossEncoderRerankerPlugin(reranker))
    try:
        model_started = time.perf_counter()
        await registry.execute_startup_hooks()
        model_startup_seconds = time.perf_counter() - model_started
        registry.freeze()
        module = RerankingModule(registry)
        query = cast(str, m65["query"])
        first_started = time.perf_counter()
        first = await module.execute(query, fusion)
        first_seconds = time.perf_counter() - first_started
        second_started = time.perf_counter()
        second = await module.execute(query, fusion)
        second_seconds = time.perf_counter() - second_started

        if first != second:
            raise AssertionError("pinned-model reranking repeat was nondeterministic")
        if first.policy is not RerankPolicy.CROSS_ENCODER:
            raise AssertionError("registered provider did not use cross-encoder policy")
        if len(first.results) != len(fusion.results):
            raise AssertionError("reranking changed candidate cardinality")
        original_by_id = {item.chunk.id: item for item in fusion.results}
        for result in first.results:
            original = original_by_id[result.fused_result.chunk.id]
            if result.fused_result is not original:
                raise AssertionError("reranking replaced fused provenance")
            evidence = result.rerank_evidence
            if evidence is None or not math.isfinite(evidence.raw_logit):
                raise AssertionError("cross-encoder evidence is missing or non-finite")
            if evidence.relevance_score != stable_sigmoid(evidence.raw_logit):
                raise AssertionError("cross-encoder sigmoid changed")
            if evidence.below_relevance_threshold is not (evidence.relevance_score < 0.4):
                raise AssertionError("cross-encoder threshold flag changed")
            if result.fused_result.rrf_score != original.rrf_score:
                raise AssertionError("reranking changed RRF evidence")
            if result.fused_result.global_rank != original.global_rank:
                raise AssertionError("reranking changed original global rank")

        fallback_registry = PluginRegistry(core_version=__version__)
        fallback_registry.freeze()
        fallback = await RerankingModule(fallback_registry).execute(query, fusion)
        if (
            fallback.policy is not RerankPolicy.RRF_FALLBACK
            or fallback.fallback_reason is not RerankFallbackReason.PROVIDER_UNAVAILABLE
            or tuple(item.fused_result for item in fallback.results) != fusion.results
        ):
            raise AssertionError("typed provider-unavailable fallback changed")

        failure_registry = PluginRegistry(core_version=__version__)
        failure_registry.load_plugin(_FailurePlugin())
        failure_registry.freeze()
        try:
            await RerankingModule(failure_registry).execute(query, fusion)
        except IntegrityError as error:
            if str(error) != "controlled registered-provider failure":
                raise
        else:
            raise AssertionError("registered provider failure silently fell back")

        scores = tuple(
            item.rerank_evidence.relevance_score
            for item in first.results
            if item.rerank_evidence is not None
        )
        return {
            "verdict": "PASS",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": digest,
            "module_6_5_evidence": str(M65_EVIDENCE.relative_to(ROOT)).replace("\\", "/"),
            "module_6_5_collection": m65["qdrant_collection"],
            "module_6_5_points": m65["qdrant_points"],
            "query": query,
            "candidate_count_before": len(fusion.results),
            "candidate_count_after": len(first.results),
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "device": "cpu",
            "model_startup_seconds": model_startup_seconds,
            "first_rerank_seconds": first_seconds,
            "second_rerank_seconds": second_seconds,
            "total_acceptance_seconds": time.perf_counter() - started,
            "score_min": min(scores),
            "score_max": max(scores),
            "score_mean": math.fsum(scores) / len(scores),
            "below_threshold_count": sum(score < 0.4 for score in scores),
            "reranked_results": [
                {
                    "chunk_id": item.fused_result.chunk.id,
                    "reranked_rank": item.reranked_rank,
                    "original_global_rank": item.fused_result.global_rank,
                    "rrf_score": item.fused_result.rrf_score,
                    "raw_logit": item.rerank_evidence.raw_logit,
                    "relevance_score": item.rerank_evidence.relevance_score,
                    "below_relevance_threshold": (item.rerank_evidence.below_relevance_threshold),
                    "evidence_count": len(item.fused_result.evidence),
                }
                for item in first.results
                if item.rerank_evidence is not None
            ],
            "deterministic_repeat": True,
            "provenance_preserved": True,
            "candidate_cardinality_preserved": True,
            "fallback_verified": True,
            "provider_failure_propagation_verified": True,
            "retrieval_or_refill_performed_by_module_6_6": False,
        }
    finally:
        await registry.execute_shutdown_hooks()
        await ollama._client.aclose()
        await storage.close()
        del builtins


def main() -> int:
    result = asyncio.run(_run())
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
