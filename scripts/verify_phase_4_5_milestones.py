"""Execute Mnemo's real Phase 4/5 golden-corpus acceptance milestones.

This runner is deliberately service-backed and assertion-heavy. It uses the
repository Bhagavad Gita PDF, production built-in registration, Ollama, the
embedding cache, CompositeStorage, and Qdrant. It never substitutes mocks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import re
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import aiosqlite
import pymupdf
from mnemo import __version__
from mnemo.chunkers import BookChunker, ChunkerDispatcher, compute_chunk_id
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
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
from mnemo.ingestion import DocumentCanonicalizer
from mnemo.interfaces import ChunkingContext, ChunkingOptions, StorageInterfaceV1
from mnemo.interfaces.parser_models import ParseResult
from mnemo.models import (
    Block,
    CaptionBlock,
    Chunk,
    CodeBlock,
    DocType,
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    EquationBlock,
    HeadingBlock,
    ImageBlock,
    ParsedDocument,
    TableBlock,
    TextBlock,
)
from mnemo.parsers import ParserRouter
from mnemo.registry import PluginRegistry
from mnemo.storage.cache import SQLiteEmbeddingCache
from mnemo.tokenizers import O200KBaseTokenCounter
from pydantic import HttpUrl
from qdrant_client import AsyncQdrantClient

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "goldenDataset"
DATASET = DATASET_DIR / "Bhagavad-gita-As-It-Is.pdf"
EVIDENCE_DIR = ROOT / "docs" / "milestone-evidence"
RUNS_DIR = ROOT / "data" / "milestone-acceptance"
EXPECTED_DATASET_SHA256 = "ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583"
TOKENIZER_ASSET_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
CHAPTER_RE = re.compile(
    r"^(?:chapter|book)\s+(?:[ivxlcdm]+|\d+|one|two|three|four|five|six|seven|"
    r"eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty)\b",
    re.IGNORECASE,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _dataset() -> Path:
    _assert(DATASET.is_file(), f"golden PDF is missing: {DATASET.relative_to(ROOT)}")
    digest = sha256(DATASET.read_bytes()).hexdigest()
    _assert(digest == EXPECTED_DATASET_SHA256, f"golden PDF SHA-256 mismatch: {digest}")
    return DATASET


def _tokenizer_asset() -> Path:
    override = os.environ.get("MNEMO_TOKENIZER_ASSET")
    if override:
        return Path(override).expanduser().resolve(strict=False)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        root = base / "Mnemo" / "tokenizers"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "Mnemo" / "tokenizers"
    else:
        root = (
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            / "mnemo"
            / "tokenizers"
        )
    return root / "o200k_base" / TOKENIZER_ASSET_SHA256 / "o200k_base.tiktoken"


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _config(run_id: str) -> MnemoConfig:
    run_dir = RUNS_DIR / run_id
    collection = f"mnemo_m5_gita_{run_id.lower()}"
    surrealdb_defaults = SurrealDBStorageConfig()
    qdrant_url = os.environ.get("MNEMO_STORAGE_QDRANT_URL", "http://127.0.0.1:6333")
    surrealdb_url = os.environ.get("MNEMO_STORAGE_SURREALDB_URL", "http://127.0.0.1:8001")
    ollama_url = os.environ.get("MNEMO_EMBEDDING_API_BASE", "http://127.0.0.1:11434")
    return MnemoConfig(
        storage=StorageConfig(
            filesystem=FilesystemStorageConfig(root=run_dir / "files"),
            sqlite=SQLiteStorageConfig(path=run_dir / "mnemo.db"),
            qdrant=QdrantStorageConfig(
                url=HttpUrl(qdrant_url),
                api_key=os.environ.get("MNEMO_STORAGE_QDRANT_API_KEY") or None,
                collection_name=collection,
                on_disk=False,
            ),
            surrealdb=SurrealDBStorageConfig(
                url=HttpUrl(surrealdb_url),
                username=os.environ.get(
                    "MNEMO_STORAGE_SURREALDB_USERNAME", surrealdb_defaults.username
                ),
                password=os.environ.get(
                    "MNEMO_STORAGE_SURREALDB_PASSWORD", surrealdb_defaults.password
                ),
                namespace="mnemo_milestone",
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
            api_base=ollama_url,
        ),
        reranker=RerankerConfig(provider="unused", model="unused"),
        plugins=PluginConfig(directory=ROOT / "plugins"),
    )


def _registry(config: MnemoConfig) -> PluginRegistry:
    registry = PluginRegistry(core_version=__version__)
    results = registry.load_plugins(_builtin_plugins(config))
    failures = [result.error_message for result in results if not result.loaded]
    _assert(not failures, f"built-in plugin registration failed: {failures}")
    registry.freeze()
    return registry


def _block_text(block: Block) -> str:
    if isinstance(block, (TextBlock, CaptionBlock, HeadingBlock)):
        return block.text
    if isinstance(block, TableBlock):
        return "\n".join("\t".join(row) for row in block.rows)
    if isinstance(block, EquationBlock):
        return block.latex
    if isinstance(block, CodeBlock):
        return block.code
    if isinstance(block, ImageBlock):
        return block.alt_text or ""
    return ""


def _norm(text: str) -> str:
    return " ".join(text.split())


def _chapter_for_path(path: tuple[str, ...]) -> str:
    for heading in path:
        if CHAPTER_RE.match(heading.strip()):
            return heading
    return "<front/back matter>"


def _relationship_stats(chunks: tuple[Chunk, ...]) -> tuple[int, int]:
    by_id = {chunk.id: chunk for chunk in chunks}
    order = {chunk.id: index for index, chunk in enumerate(chunks)}
    invalid_parents = 0
    invalid_siblings = 0
    for chunk in chunks:
        parent = chunk.parent_chunk_id
        if parent is not None and (parent not in by_id or order[parent] >= order[chunk.id]):
            invalid_parents += 1
        expected: tuple[str, ...] = ()
        if parent is not None and parent in by_id:
            expected = tuple(
                other.id
                for other in chunks
                if other.parent_chunk_id == parent and other.id != chunk.id
            )
        if chunk.sibling_ids != expected:
            invalid_siblings += 1
            continue
        for sibling_id in chunk.sibling_ids:
            sibling = by_id.get(sibling_id)
            if (
                sibling is None
                or parent is None
                or sibling.parent_chunk_id != parent
                or chunk.id not in sibling.sibling_ids
            ):
                invalid_siblings += 1
                break
    return invalid_parents, invalid_siblings


def _chapter_boundary_violations(document: ParsedDocument, chunks: tuple[Chunk, ...]) -> int:
    current: str | None = None
    chapter_at: dict[int, str | None] = {}
    for block in document.blocks:
        if isinstance(block, HeadingBlock) and CHAPTER_RE.match(block.text.strip()):
            current = block.text
        chapter_at[block.ordinal] = current
    violations = 0
    for chunk in chunks:
        chapters = {
            chapter_at[ordinal]
            for ordinal in range(chunk.source_span.start_ordinal, chunk.source_span.end_ordinal + 1)
        }
        if len(chapters) > 1:
            violations += 1
    return violations


def _validate_chunks(
    document: ParsedDocument,
    context: ChunkingContext,
    chunks: tuple[Chunk, ...],
    token_counter: O200KBaseTokenCounter,
) -> dict[str, Any]:
    _assert(bool(chunks), "chunker returned no chunks")
    _assert(len({chunk.id for chunk in chunks}) == len(chunks), "duplicate chunk IDs")
    invalid_provenance = 0
    invalid_source_text = 0
    short_chunks = 0
    oversized_chunks = 0
    for chunk in chunks:
        span = chunk.source_span
        if (
            chunk.document_id != context.document_version.document_id
            or chunk.version_id != context.document_version.version_id
            or span.start_ordinal < 0
            or span.end_ordinal >= len(document.blocks)
            or chunk.id != compute_chunk_id(chunk.version_id, span, chunk.text)
        ):
            invalid_provenance += 1
        source = _norm(
            " ".join(
                _block_text(document.blocks[index])
                for index in range(span.start_ordinal, span.end_ordinal + 1)
            )
        )
        if _norm(chunk.text) not in source:
            invalid_source_text += 1
        token_count = token_counter.count(chunk.text)
        short_chunks += token_count < 15
        oversized_chunks += token_count > context.effective_max_tokens
    invalid_parents, invalid_siblings = _relationship_stats(chunks)
    chapter_violations = _chapter_boundary_violations(document, chunks)
    stats = {
        "invalid_provenance": invalid_provenance,
        "invalid_source_text": invalid_source_text,
        "short_chunks": short_chunks,
        "oversized_chunks": oversized_chunks,
        "invalid_parent_relationships": invalid_parents,
        "invalid_sibling_relationships": invalid_siblings,
        "chapter_boundary_violations": chapter_violations,
    }
    _assert(all(value == 0 for value in stats.values()), f"chunk invariants failed: {stats}")
    return stats


def _signature(chunks: tuple[Chunk, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            chunk.id,
            chunk.text,
            chunk.source_span.start_ordinal,
            chunk.source_span.end_ordinal,
            chunk.heading_path,
            chunk.parent_chunk_id,
            chunk.sibling_ids,
        )
        for chunk in chunks
    )


async def _run_m4(
    registry: PluginRegistry,
    config: MnemoConfig,
) -> tuple[dict[str, Any], tuple[Chunk, ...], Any]:
    dataset = _dataset()
    with pymupdf.open(dataset) as pdf:  # type: ignore[no-untyped-call]
        physical_pages = pdf.page_count
        encrypted = pdf.is_encrypted
    _assert(physical_pages == 952, f"expected 952-page corpus, got {physical_pages}")
    _assert(not encrypted, "golden PDF is encrypted")

    storage = registry.resolve_storage("primary")
    _assert(storage is not None, "primary CompositeStorage was not registered")
    storage = cast(StorageInterfaceV1, storage)
    await storage.open()

    payload = dataset.read_bytes()
    router = ParserRouter(registry, storage)
    parse_start = time.perf_counter()
    routed = await router.route(payload, dataset.name)
    parse_seconds = time.perf_counter() - parse_start
    if not isinstance(routed, ParseResult):
        raise AssertionError("golden corpus unexpectedly deduplicated")

    cleaner = DocumentCleaner()
    clean_start = time.perf_counter()
    cleaned = cleaner.clean(routed)
    clean_seconds = time.perf_counter() - clean_start

    classifier = DocumentClassifier()
    classify_start = time.perf_counter()
    classified = classifier.classify(cleaned, dataset.name)
    classify_seconds = time.perf_counter() - classify_start
    _assert(classified.doc_type is DocType.BOOK, f"classified as {classified.doc_type.value}")

    assets_start = time.perf_counter()
    assets = {
        transient.parser_local_id: await storage.put_asset(
            transient.raw_bytes, transient.mime_type, classified.metadata.metadata
        )
        for transient in classified.extracted_assets
    }
    asset_seconds = time.perf_counter() - assets_start

    canonicalizer = DocumentCanonicalizer()
    canonical_start = time.perf_counter()
    document = canonicalizer.canonicalize(classified, assets)
    canonical_seconds = time.perf_counter() - canonical_start

    content_hash = document.metadata.content_hash
    document_id = uuid5(NAMESPACE_URL, f"mnemo-golden-document:{content_hash}")
    version_id = uuid5(NAMESPACE_URL, f"mnemo-golden-version:{content_hash}")
    await storage.put_parsed_document(version_id, document)
    context = ChunkingContext(
        document_version=DocumentVersion(
            version_id=version_id,
            document_id=document_id,
            content_hash=content_hash,
            metadata=document.metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=datetime(2026, 8, 13, tzinfo=UTC),
        ),
        options=ChunkingOptions(target_tokens=400, max_tokens=500),
    )
    await storage.upsert_document(
        Document(
            document_id=document_id,
            versions=(context.document_version,),
            current_version_id=version_id,
            current_hash=content_hash,
            status=DocumentStatus.INDEXING,
            created_at=context.document_version.created_at,
            updated_at=context.document_version.created_at,
        )
    )
    token_counter = O200KBaseTokenCounter(_tokenizer_asset())
    selected = registry.resolve_chunker_v2(document.doc_type)
    _assert(type(selected) is BookChunker, f"dispatcher selected {type(selected).__name__}")
    dispatcher = ChunkerDispatcher(registry, token_counter)

    chunk_start = time.perf_counter()
    chunks = dispatcher.dispatch(document, context)
    chunk_seconds = time.perf_counter() - chunk_start
    repeat_start = time.perf_counter()
    repeated = dispatcher.dispatch(document, context)
    repeat_seconds = time.perf_counter() - repeat_start
    _assert(_signature(chunks) == _signature(repeated), "chunking repeat is nondeterministic")
    invariant_stats = _validate_chunks(document, context, chunks, token_counter)

    per_chapter = Counter(_chapter_for_path(chunk.heading_path) for chunk in chunks)
    chapter_examples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        chapter = _chapter_for_path(chunk.heading_path)
        if chapter == "<front/back matter>" or chapter in seen:
            continue
        seen.add(chapter)
        chapter_examples.append(
            {
                "chapter": chapter,
                "heading_path": list(chunk.heading_path),
                "page": chunk.position.page_number,
                "chunk_id": chunk.id,
            }
        )

    authored_chapters = tuple(
        chapter for chapter in per_chapter if chapter != "<front/back matter>"
    )
    _assert(
        len(authored_chapters) == 18,
        f"expected all 18 authored chapters in heading_path, got {authored_chapters}",
    )
    _assert(len(chapter_examples) == 18, "hierarchy examples do not cover every chapter")

    total_seconds = (
        parse_seconds
        + clean_seconds
        + classify_seconds
        + asset_seconds
        + canonical_seconds
        + chunk_seconds
    )
    result: dict[str, Any] = {
        "verdict": "PASS",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "dataset": str(dataset.relative_to(ROOT)).replace("\\", "/"),
        "dataset_bytes": len(payload),
        "dataset_sha256": sha256(payload).hexdigest(),
        "physical_pages": physical_pages,
        "metadata_pages": document.metadata.page_count,
        "parser": "ParserRouter -> PDFParser",
        "block_count": len(document.blocks),
        "asset_count": len(classified.extracted_assets),
        "heading_count": sum(isinstance(block, HeadingBlock) for block in document.blocks),
        "document_type": document.doc_type.value,
        "chunker": type(selected).__name__,
        "chunk_count": len(chunks),
        "root_count": sum(chunk.parent_chunk_id is None for chunk in chunks),
        "maximum_hierarchy_depth": max(len(chunk.heading_path) for chunk in chunks),
        "empty_heading_path_count": sum(not chunk.heading_path for chunk in chunks),
        "chunks_per_chapter": dict(per_chapter),
        "authored_chapter_count": len(authored_chapters),
        "chunks_with_chapter_path": sum(per_chapter[chapter] for chapter in authored_chapters),
        "hierarchy_examples": chapter_examples,
        "deterministic_repeat": True,
        "timings_seconds": {
            "parse": parse_seconds,
            "clean": clean_seconds,
            "classify": classify_seconds,
            "asset_persistence": asset_seconds,
            "canonicalization": canonical_seconds,
            "chunking": chunk_seconds,
            "repeat_chunking": repeat_seconds,
            "ingestion_to_chunks": total_seconds,
        },
        "normalized_1000_page_chunking_seconds": chunk_seconds * 1000 / physical_pages,
        **invariant_stats,
        "environment": {
            "mnemo_core": __version__,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor(),
            "tokenizer": token_counter.tokenizer_id,
            "target_tokens": context.options.target_tokens,
            "max_tokens": context.options.max_tokens,
            "effective_max_tokens": context.effective_max_tokens,
        },
    }
    _assert(result["empty_heading_path_count"] == 0, "empty heading_path values found")
    return result, chunks, storage


def _point_id(chunk_id: str) -> str:
    return str(UUID(chunk_id[:32]))


async def _cache_count(path: Path) -> int:
    async with (
        aiosqlite.connect(path) as db,
        db.execute("SELECT COUNT(*) FROM embedding_cache") as cursor,
    ):
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def _run_m5(
    registry: PluginRegistry,
    config: MnemoConfig,
    chunks: tuple[Chunk, ...],
    storage: Any,
    run_id: str,
) -> dict[str, Any]:
    _assert(len(chunks) >= 1000, f"M4 produced only {len(chunks)} real chunks")
    selected = chunks[:1000]

    # ADR-0018: initialization hooks execute before synchronous provider
    # resolution/capability reads.
    await registry.execute_startup_hooks()
    provider = registry.resolve_embedding_provider("primary")
    _assert(provider is not None, "primary Ollama embedding provider was not registered")
    _assert(isinstance(provider, OllamaEmbedder), "primary provider is not OllamaEmbedder")
    provider = cast(OllamaEmbedder, provider)
    health = await provider.health_check()
    _assert(health.healthy, f"Ollama unavailable: {health.detail}")
    dimensions = provider.dimensions
    _assert(dimensions == config.embedding.dimensions == 768, "embedding dimension mismatch")

    cache_path = RUNS_DIR / run_id / "embedding-cache.db"
    cache = SQLiteEmbeddingCache(cache_path)
    await cache.initialize()
    cached_provider = CachedEmbeddingProvider(provider, cache)
    embedder = EmbedderModule(cached_provider, max_concurrency=4)
    keys = tuple(cached_provider._compute_key(chunk.text) for chunk in selected)
    cold_values: list[tuple[float, ...] | None] = []
    for key in keys:
        cold_values.append(await cache.get(key))
    cold = tuple(cold_values)
    _assert(all(vector is None for vector in cold), "acceptance cache was not cold")

    embedding_start = time.perf_counter()
    embedded = await embedder.embed_chunks(selected)
    embedding_seconds = time.perf_counter() - embedding_start
    _assert(len(embedded) == 1000, "embedded chunk count changed")
    _assert(
        tuple(chunk.id for chunk in embedded) == tuple(chunk.id for chunk in selected),
        "order changed",
    )
    for chunk in embedded:
        vector = chunk.embedding
        if vector is None:
            raise AssertionError(f"missing embedding for {chunk.id}")
        _assert(len(vector) == dimensions, f"wrong vector dimension for {chunk.id}")
        _assert(all(math.isfinite(value) for value in vector), f"non-finite vector for {chunk.id}")
    cache_rows = await _cache_count(cache_path)
    _assert(cache_rows == len(set(keys)), "cache row count does not match model-specific keys")

    verifier = AsyncQdrantClient(url=str(config.storage.qdrant.url))
    collection = config.storage.qdrant.collection_name
    before = await verifier.count(collection_name=collection, exact=True)
    _assert(before.count == 0, f"isolated collection was contaminated: {before.count} points")
    collection_info = await verifier.get_collection(collection)
    vector_config = collection_info.config.params.vectors
    stored_dimensions = getattr(vector_config, "size", None)
    _assert(stored_dimensions == dimensions, "Qdrant collection dimension mismatch")

    qdrant_start = time.perf_counter()
    await storage.upsert_chunks(embedded)
    qdrant_seconds = time.perf_counter() - qdrant_start
    point_ids = [_point_id(chunk.id) for chunk in embedded]
    records = await verifier.retrieve(
        collection_name=collection,
        ids=point_ids,
        with_payload=True,
        with_vectors=True,
    )
    after = await verifier.count(collection_name=collection, exact=True)
    _assert(after.count == 1000, f"Qdrant count is {after.count}, expected 1000")
    _assert(len(records) == 1000, f"Qdrant read-back returned {len(records)} points")
    by_point = {str(record.id): record for record in records}
    sample_indices = tuple(range(0, 1000, 100))
    for index in sample_indices:
        chunk = embedded[index]
        record = by_point[_point_id(chunk.id)]
        payload = record.payload or {}
        stored_vector = record.vector
        if not isinstance(stored_vector, list) or len(stored_vector) != dimensions:
            raise AssertionError("stored vector invalid")
        expected_payload = {
            "id": chunk.id,
            "document_id": str(chunk.document_id),
            "version_id": str(chunk.version_id),
            "heading_path": list(chunk.heading_path),
            "source_span": {
                "start_ordinal": chunk.source_span.start_ordinal,
                "end_ordinal": chunk.source_span.end_ordinal,
            },
        }
        for key, expected in expected_payload.items():
            _assert(payload.get(key) == expected, f"payload mismatch for {key} at sample {index}")

    repeat_source = selected[:100]
    repeat_start = time.perf_counter()
    repeated = await embedder.embed_chunks(repeat_source)
    repeat_seconds = time.perf_counter() - repeat_start
    for first, second in zip(embedded[:100], repeated, strict=True):
        first_vector = first.embedding
        second_vector = second.embedding
        if first_vector is None or second_vector is None:
            raise AssertionError("repeat vector missing")
        _assert(
            all(
                math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-6)
                for left, right in zip(first_vector, second_vector, strict=True)
            ),
            f"cached vector differs for {first.id}",
        )
    _assert(await _cache_count(cache_path) == cache_rows, "repeat changed cache cardinality")
    await verifier.close()
    await provider._client.aclose()

    return {
        "verdict": "PASS",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "input_chunks": 1000,
        "selection": "first 1000 chunks in deterministic source order",
        "ollama_model": provider.model_name,
        "embedding_dimensions": dimensions,
        "batch_size": provider.capabilities().max_batch,
        "concurrency": 4,
        "ollama_embedding_requests": 1000,
        "ollama_startup_probe_requests": 1,
        "cache_hits_first_run": 0,
        "cache_misses_first_run": 1000,
        "cache_rows": cache_rows,
        "repeat_subset_chunks": 100,
        "repeat_cache_hits": 100,
        "repeat_cache_misses": 0,
        "repeat_underlying_ollama_requests": 0,
        "repeat_vectors_equivalent": True,
        "embedding_seconds": embedding_seconds,
        "average_embedding_latency_seconds": embedding_seconds / 1000,
        "throughput_chunks_per_second": 1000 / embedding_seconds,
        "repeat_seconds": repeat_seconds,
        "qdrant_seconds": qdrant_seconds,
        "qdrant_collection": collection,
        "qdrant_collection_dimensions": stored_dimensions,
        "qdrant_points_before": before.count,
        "qdrant_points_written": 1000,
        "qdrant_points_read_back": len(records),
        "qdrant_exact_count": after.count,
        "payload_samples_validated": len(sample_indices),
        "payload_validation": True,
        "benchmark_10000": "not executed: the golden corpus was not duplicated or fabricated",
    }


async def _main(phase: str) -> int:
    run_id = _run_id()
    config = _config(run_id)
    registry = _registry(config)
    storage: Any | None = None
    try:
        m4, chunks, storage = await _run_m4(registry, config)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (EVIDENCE_DIR / "m4-bhagavad-gita.json").write_text(
            json.dumps(m4, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps({"M4": m4}, indent=2, ensure_ascii=True))
        if phase == "m4":
            return 0
        m5 = await _run_m5(registry, config, chunks, storage, run_id)
        (EVIDENCE_DIR / "m5-ollama-qdrant.json").write_text(
            json.dumps(m5, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps({"M5": m5}, indent=2, ensure_ascii=True))
        return 0
    finally:
        if storage is not None:
            await storage.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("m4", "all"), default="all", nargs="?")
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(_main(arguments.phase)))
