"""Validate Module 6.5 against real golden data, Ollama, Qdrant, and SQLite."""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from mnemo import __version__
from mnemo.config import (
    EmbeddingConfig,
    FilesystemStorageConfig,
    LLMConfig,
    LLMRoleConfig,
    MnemoConfig,
    PluginConfig,
    QdrantStorageConfig,
    RerankerConfig,
    SQLiteStorageConfig,
    StorageConfig,
    SurrealDBStorageConfig,
)
from mnemo.embeddings.cached import CachedEmbeddingProvider
from mnemo.embeddings.embedder import EmbedderModule
from mnemo.embeddings.ollama import OllamaEmbedder
from mnemo.engine import _builtin_plugins
from mnemo.interfaces import EmbeddingProviderV1, StorageInterfaceV1
from mnemo.models import (
    DocType,
    MetadataFilter,
    Notebook,
    RetrievalIntent,
    RetrievalMode,
    RetrievalPlan,
    Source,
    SubQuery,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import DenseRetriever, MultiSourceRetriever, ParentRetriever, SparseRetriever
from mnemo.storage.cache import SQLiteEmbeddingCache
from pydantic import HttpUrl
from qdrant_client import AsyncQdrantClient
from verify_phase_4_5_milestones import _run_m4

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "goldenDataset" / "Bhagavad-gita-As-It-Is.pdf"
EXPECTED_SHA256 = "ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583"
RUNS_DIR = ROOT / "data" / "module-6.5-acceptance"
EVIDENCE = ROOT / "docs" / "milestone-evidence" / "module-6.5-fusion.json"


class _RetrievalPlugin:
    name = "mnemo-module-6-5-retrieval"
    version = __version__
    core_version_range = ">=0.20.1"

    def __init__(self, storage: StorageInterfaceV1) -> None:
        self._storage = storage

    def capabilities(self) -> tuple[str, ...]:
        return ("retriever", "parent_promotion")

    def register(self, registry: PluginRegistry) -> None:
        registry.register_retriever("dense", DenseRetriever(self._storage), priority=0)
        registry.register_retriever("sparse", SparseRetriever(self._storage), priority=0)
        registry.register_parent_promoter(
            "default",
            ParentRetriever(self._storage),
            priority=0,
        )


def _config(run_id: str) -> MnemoConfig:
    run_dir = RUNS_DIR / run_id
    defaults = SurrealDBStorageConfig()
    return MnemoConfig(
        storage=StorageConfig(
            filesystem=FilesystemStorageConfig(root=run_dir / "files"),
            sqlite=SQLiteStorageConfig(path=run_dir / "mnemo.db"),
            qdrant=QdrantStorageConfig(
                url=HttpUrl(os.environ.get("MNEMO_STORAGE_QDRANT_URL", "http://127.0.0.1:6333")),
                api_key=os.environ.get("MNEMO_STORAGE_QDRANT_API_KEY") or None,
                collection_name=f"mnemo_m6_5_gita_{run_id.lower()}",
                on_disk=False,
            ),
            surrealdb=SurrealDBStorageConfig(
                url=HttpUrl(os.environ.get("MNEMO_STORAGE_SURREALDB_URL", "http://127.0.0.1:8001")),
                username=os.environ.get("MNEMO_STORAGE_SURREALDB_USERNAME", defaults.username),
                password=os.environ.get("MNEMO_STORAGE_SURREALDB_PASSWORD", defaults.password),
                namespace="mnemo_module_6_5",
                database=f"gita_{run_id.lower()}",
            ),
        ),
        llm=LLMConfig(
            planner=LLMRoleConfig(provider="unused", model="unused", max_context_tokens=8192),
            synthesizer=LLMRoleConfig(provider="unused", model="unused", max_context_tokens=16384),
            extractor=LLMRoleConfig(provider="unused", model="unused", max_context_tokens=8192),
            classifier=LLMRoleConfig(provider="unused", model="unused", max_context_tokens=4096),
        ),
        embedding=EmbeddingConfig(
            provider="ollama",
            model="nomic-embed-text",
            dimensions=768,
            api_base=os.environ.get("MNEMO_EMBEDDING_API_BASE", "http://127.0.0.1:11434"),
        ),
        reranker=RerankerConfig(provider="unused", model="unused"),
        plugins=PluginConfig(directory=ROOT / "plugins"),
    )


def _builtins(config: MnemoConfig) -> PluginRegistry:
    registry = PluginRegistry(core_version=__version__)
    results = registry.load_plugins(_builtin_plugins(config))
    failures = tuple(result.error_message for result in results if not result.loaded)
    if failures:
        raise AssertionError(f"built-in registration failed: {failures}")
    registry.freeze()
    return registry


def _retrieval_registry(storage: StorageInterfaceV1) -> PluginRegistry:
    registry = PluginRegistry(core_version=__version__)
    result = registry.load_plugins((_RetrievalPlugin(storage),))[0]
    if not result.loaded:
        raise AssertionError(result.error_message)
    registry.freeze()
    return registry


async def _run() -> dict[str, object]:
    payload = DATASET.read_bytes()
    digest = sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise AssertionError(f"golden corpus hash mismatch: {digest}")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    config = _config(run_id)
    builtins = _builtins(config)
    storage: StorageInterfaceV1 | None = None
    verifier: AsyncQdrantClient | None = None
    provider: OllamaEmbedder | None = None
    acceptance_started = time.perf_counter()
    try:
        m4, chunks, opened_storage = await _run_m4(builtins, config)
        storage = cast(StorageInterfaceV1, opened_storage)
        if len(chunks) != 1275:
            raise AssertionError(f"expected 1275 real chunks, got {len(chunks)}")

        created = datetime.now(UTC)
        notebook = Notebook(
            notebook_id=uuid5(NAMESPACE_URL, f"mnemo-module-6.5-notebook:{run_id}"),
            title="Module 6.5 Bhagavad Gita acceptance",
            created_at=created,
            updated_at=created,
        )
        source = Source(
            source_id=uuid5(NAMESPACE_URL, f"mnemo-module-6.5-source:{run_id}"),
            notebook_id=notebook.notebook_id,
            document_id=chunks[0].document_id,
            created_at=created,
        )
        await storage.upsert_notebook(notebook)
        await storage.upsert_source(source)

        await builtins.execute_startup_hooks()
        resolved_provider = builtins.resolve_embedding_provider("primary")
        if not isinstance(resolved_provider, OllamaEmbedder):
            raise AssertionError("primary Ollama provider was not resolved")
        provider = resolved_provider
        health = await provider.health_check()
        if not health.healthy or provider.dimensions != 768:
            raise AssertionError(f"Ollama is unavailable or incompatible: {health.detail}")

        cache = SQLiteEmbeddingCache(RUNS_DIR / run_id / "embedding-cache.db")
        await cache.initialize()
        cached_provider: EmbeddingProviderV1 = CachedEmbeddingProvider(provider, cache)
        embedding_started = time.perf_counter()
        embedded = await EmbedderModule(cached_provider, max_concurrency=4).embed_chunks(chunks)
        embedding_seconds = time.perf_counter() - embedding_started
        if len(embedded) != len(chunks) or any(chunk.embedding is None for chunk in embedded):
            raise AssertionError("golden embedding changed count or lost vectors")

        indexing_started = time.perf_counter()
        await storage.upsert_chunks(embedded)
        indexing_seconds = time.perf_counter() - indexing_started

        verifier = AsyncQdrantClient(url=str(config.storage.qdrant.url))
        count = await verifier.count(
            collection_name=config.storage.qdrant.collection_name,
            exact=True,
        )
        if count.count != len(chunks):
            raise AssertionError(f"Qdrant count mismatch: {count.count}")

        orchestrator = MultiSourceRetriever(
            _retrieval_registry(storage),
            cached_provider,
            max_concurrency=4,
        )
        filters = MetadataFilter(
            notebook_id=notebook.notebook_id,
            source_ids=(source.source_id,),
            doc_types=(DocType.BOOK,),
        )
        query = "What does the Bhagavad Gita teach about duty?"
        plan = RetrievalPlan(
            intent=RetrievalIntent.FACTUAL,
            sub_queries=(
                SubQuery(
                    query_text=query,
                    retrieval_mode=RetrievalMode.HYBRID,
                    filters=filters,
                    max_results=8,
                ),
                SubQuery(
                    query_text=(
                        "Duty in the Bhagavad Gita is disciplined action performed without "
                        "attachment to personal reward."
                    ),
                    retrieval_mode=RetrievalMode.DENSE,
                    filters=filters,
                    max_results=8,
                ),
                SubQuery(
                    query_text="Bhagavad Gita duty action attachment reward",
                    retrieval_mode=RetrievalMode.SPARSE,
                    filters=filters,
                    max_results=8,
                ),
            ),
            requires_multi_hop=False,
            requires_multi_doc=False,
        )

        first_started = time.perf_counter()
        first = await orchestrator.execute(plan, global_limit=10)
        first_seconds = time.perf_counter() - first_started
        second_started = time.perf_counter()
        second = await orchestrator.execute(plan, global_limit=10)
        second_seconds = time.perf_counter() - second_started
        if first != second:
            raise AssertionError("golden orchestration repeat was nondeterministic")
        expected_invocations = (
            "sq-1:dense",
            "sq-1:sparse",
            "sq-2:dense",
            "sq-3:sparse",
        )
        if tuple(trace.invocation_id for trace in first.invocations) != expected_invocations:
            raise AssertionError("hybrid/source invocation expansion changed")
        if any(len(trace.raw_results) > trace.requested_top_k for trace in first.invocations):
            raise AssertionError("source-local top_k was exceeded")
        if any(len(trace.promoted_results) > len(trace.raw_results) for trace in first.invocations):
            raise AssertionError("parent promotion expanded a stream")
        if len(first.results) > 10:
            raise AssertionError("global_limit was exceeded")
        if tuple(item.global_rank for item in first.results) != tuple(
            range(1, len(first.results) + 1)
        ):
            raise AssertionError("global ranks are not contiguous")
        expected_order = tuple(
            sorted(first.results, key=lambda item: (-item.rrf_score, item.chunk.id))
        )
        if first.results != expected_order:
            raise AssertionError("global RRF ordering is incorrect")
        if any(item.chunk.document_id != chunks[0].document_id for item in first.results):
            raise AssertionError("golden result escaped canonical document identity")
        for item in first.results:
            expected_score = math.fsum(
                1.0 / (60 + evidence.result.rank) for evidence in item.evidence
            )
            if item.rrf_score != expected_score:
                raise AssertionError("RRF score differs from ADR-0041")

        raw_occurrences = sum(len(trace.promoted_results) for trace in first.invocations)
        promoted_count = sum(
            evidence.identity_introduced_by_parent_promotion
            for item in first.results
            for evidence in item.evidence
        )
        return {
            "verdict": "PASS",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": digest,
            "physical_pages": m4["physical_pages"],
            "chunk_count": len(chunks),
            "qdrant_collection": config.storage.qdrant.collection_name,
            "qdrant_points": count.count,
            "sqlite_database": str(config.storage.sqlite.path.relative_to(ROOT)).replace("\\", "/"),
            "ollama_model": provider.model_name,
            "embedding_dimensions": provider.dimensions,
            "embedding_seconds": embedding_seconds,
            "indexing_seconds": indexing_seconds,
            "query": query,
            "planner_input": "canonical validated RetrievalPlan (no live planner LLM plugin)",
            "subqueries": [subquery.model_dump(mode="json") for subquery in plan.sub_queries],
            "invocation_ids": list(expected_invocations),
            "raw_stream_counts": [len(trace.raw_results) for trace in first.invocations],
            "promoted_stream_counts": [len(trace.promoted_results) for trace in first.invocations],
            "source_local_occurrences": raw_occurrences,
            "parent_introduced_evidence": promoted_count,
            "golden_parent_limitation": (
                "The verified corpus contains 1275 canonical root chunks and no stored parent "
                "families; real ParentRetriever executed once per stream as a no-op. Controlled "
                "canonical family behavior remains validated by Module 6.4 storage fixtures and "
                "Module 6.5 promotion/fusion tests."
            ),
            "deduplicated_candidates": len(
                {
                    result.chunk.id
                    for trace in first.invocations
                    for result in trace.promoted_results
                }
            ),
            "final_result_count": len(first.results),
            "final_results": [
                {
                    "chunk_id": item.chunk.id,
                    "global_rank": item.global_rank,
                    "rrf_score": item.rrf_score,
                    "evidence": [
                        {
                            "invocation_id": evidence.invocation_id,
                            "source": evidence.result.source,
                            "local_rank": evidence.result.rank,
                            "raw_score": evidence.result.score,
                            "parent_introduced": (evidence.identity_introduced_by_parent_promotion),
                        }
                        for evidence in item.evidence
                    ],
                }
                for item in first.results
            ],
            "global_limit": 10,
            "configured_concurrency": 4,
            "first_orchestration_seconds": first_seconds,
            "cached_repeat_seconds": second_seconds,
            "deterministic_repeat": True,
            "total_acceptance_seconds": time.perf_counter() - acceptance_started,
        }
    finally:
        if verifier is not None:
            await verifier.close()
        if provider is not None:
            await provider._client.aclose()
        if storage is not None:
            await storage.close()


def main() -> int:
    result = asyncio.run(_run())
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
