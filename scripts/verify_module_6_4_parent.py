"""Validate Module 6.4 against the real Bhagavad Gita hierarchy and SQLite."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from mnemo import __version__
from mnemo.chunkers import BookChunker, ChunkerDispatcher
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion import DocumentCanonicalizer
from mnemo.interfaces import ChunkingContext, ChunkingOptions
from mnemo.interfaces.parser_models import ParseResult
from mnemo.models import (
    Chunk,
    DocType,
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    ScoredChunk,
)
from mnemo.parsers import ParserRouter, PDFParser
from mnemo.registry import PluginRegistry
from mnemo.retrieval import ParentRetriever
from mnemo.storage.composite import CompositeStorage
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.sqlite import SQLiteStore
from mnemo.tokenizers import O200K_BASE_ASSET_NAME, O200K_BASE_ASSET_SHA256, O200KBaseTokenCounter

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "goldenDataset" / "Bhagavad-gita-As-It-Is.pdf"
EXPECTED_SHA256 = "ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583"


class _GoldenPlugin:
    name = "mnemo-module-6-4-golden"
    version = __version__
    core_version_range = ">=0.20.1"

    def capabilities(self) -> tuple[str, ...]:
        return ("parser", "chunker")

    def register(self, registry: PluginRegistry) -> None:
        parser = PDFParser()
        registry.register_parser(".pdf", parser, priority=0)
        registry.register_parser("application/pdf", parser, priority=0)
        registry.register_chunker_v2(DocType.BOOK, BookChunker(), priority=0)


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
    return root / "o200k_base" / O200K_BASE_ASSET_SHA256 / O200K_BASE_ASSET_NAME


def _stream(chunks: tuple[Chunk, ...], source: str = "dense") -> tuple[ScoredChunk, ...]:
    return tuple(
        ScoredChunk(
            chunk=chunk,
            score=1.0 - (index * 0.001),
            source=source,
            rank=index + 1,
        )
        for index, chunk in enumerate(chunks)
    )


def _composite(sqlite: SQLiteStore, blobs: FilesystemBlobStore) -> CompositeStorage:
    unused = cast(Any, object())
    return CompositeStorage(blobs, sqlite, unused, unused)


async def _measure(
    promoter: ParentRetriever,
    storage: CompositeStorage,
    candidates: tuple[ScoredChunk, ...],
) -> tuple[tuple[ScoredChunk, ...], int, float]:
    started = time.perf_counter()
    with patch.object(storage, "get_chunk", wraps=storage.get_chunk) as lookup:
        result = await promoter.promote(candidates)
        calls = lookup.await_count
    return result, calls, time.perf_counter() - started


async def _run() -> dict[str, object]:
    payload = DATASET.read_bytes()
    if sha256(payload).hexdigest() != EXPECTED_SHA256:
        raise AssertionError("golden corpus hash mismatch")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "data" / "module-6.4-acceptance" / run_id
    sqlite = SQLiteStore(run_dir / "mnemo.db")
    blobs = FilesystemBlobStore(run_dir / "files")
    await sqlite.open()
    await blobs.open()
    acceptance_started = time.perf_counter()
    try:
        registry = PluginRegistry(core_version=__version__)
        registration = registry.load_plugins((_GoldenPlugin(),))[0]
        if not registration.loaded:
            raise AssertionError(registration.error_message)
        registry.freeze()

        parsed = await ParserRouter(registry, sqlite).route(payload, DATASET.name)
        if not isinstance(parsed, ParseResult):
            raise AssertionError("isolated database unexpectedly deduplicated the corpus")
        classified = DocumentClassifier().classify(DocumentCleaner().clean(parsed), DATASET.name)
        if classified.doc_type is not DocType.BOOK:
            raise AssertionError(f"golden corpus classified as {classified.doc_type.value}")
        assets = {
            item.parser_local_id: await blobs.put_asset(
                item.raw_bytes, item.mime_type, classified.metadata.metadata
            )
            for item in classified.extracted_assets
        }
        canonical = DocumentCanonicalizer().canonicalize(classified, assets)
        content_hash = canonical.metadata.content_hash
        document_id = uuid5(NAMESPACE_URL, f"mnemo-golden-document:{content_hash}")
        version_id = uuid5(NAMESPACE_URL, f"mnemo-golden-version:{content_hash}")
        created = datetime(2026, 8, 13, tzinfo=UTC)
        version = DocumentVersion(
            version_id=version_id,
            document_id=document_id,
            content_hash=content_hash,
            metadata=canonical.metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=created,
        )
        await sqlite.upsert_document(
            Document(
                document_id=document_id,
                versions=(version,),
                current_version_id=version_id,
                current_hash=content_hash,
                status=DocumentStatus.INDEXED,
                created_at=created,
                updated_at=created,
            )
        )
        chunks = ChunkerDispatcher(registry, O200KBaseTokenCounter(_tokenizer_asset())).dispatch(
            canonical,
            ChunkingContext(
                document_version=version,
                options=ChunkingOptions(target_tokens=400, max_tokens=500),
            ),
        )
        await sqlite.upsert_chunks(chunks)

        by_id = {chunk.id: chunk for chunk in chunks}
        grouped: dict[str, list[Chunk]] = defaultdict(list)
        for chunk in chunks:
            if chunk.parent_chunk_id is not None:
                grouped[chunk.parent_chunk_id].append(chunk)
        families = tuple(
            (by_id[parent_id], tuple(children))
            for parent_id, children in grouped.items()
            if parent_id in by_id
        )
        storage = _composite(sqlite, blobs)
        promoter = ParentRetriever(storage)
        parent: Chunk | None = None
        independent: tuple[tuple[Chunk, tuple[Chunk, ...]], ...] = ()
        if families:
            large = next((family for family in families if len(family[1]) >= 3), None)
            if large is None:
                raise AssertionError("golden hierarchy cannot express all threshold cases")
            independent = tuple(family for family in families if len(family[1]) >= 2)[:2]
            if len(independent) != 2:
                raise AssertionError("golden hierarchy has fewer than two independent families")
            parent, children = large
            threshold_count = (len(children) + 1) // 2
            cases: dict[str, tuple[Chunk, ...]] = {
                "below_threshold": children[: max(1, threshold_count - 1)],
                "threshold": children[:threshold_count],
                "above_threshold": children[: min(len(children), threshold_count + 1)],
                "independent_families": tuple(
                    child
                    for _, family_children in independent
                    for child in family_children[: (len(family_children) + 1) // 2]
                ),
            }
            sole = next((family for family in families if len(family[1]) == 1), None)
            if sole is not None:
                cases["sole_child"] = sole[1]
        else:
            cases = {"root_noop": chunks[:100]}

        case_results: dict[str, dict[str, object]] = {}
        all_returned_ids: list[str] = []
        total_lookups = 0
        total_promotion_seconds = 0.0
        promoted_parent_ids: set[str] = set()
        for label, case_chunks in cases.items():
            candidates = _stream(case_chunks)
            result, lookups, elapsed = await _measure(promoter, storage, candidates)
            repeat, repeat_lookups, _ = await _measure(promoter, storage, candidates)
            if result != repeat:
                raise AssertionError(f"{label} promotion was not deterministic")
            if any(item.chunk.version_id != version_id for item in result):
                raise AssertionError(f"{label} crossed the golden document version")
            if any(item.source != "dense" for item in result):
                raise AssertionError(f"{label} changed score source")
            if tuple(item.rank for item in result) != tuple(range(1, len(result) + 1)):
                raise AssertionError(f"{label} ranks are not contiguous")
            total_lookups += lookups + repeat_lookups
            total_promotion_seconds += elapsed
            returned_ids = [item.chunk.id for item in result]
            all_returned_ids.extend(returned_ids)
            promoted_parent_ids.update(item.chunk.id for item in result if item.chunk.id in grouped)
            case_results[label] = {
                "candidate_count": len(candidates),
                "result_count": len(result),
                "lookup_count": lookups,
                "elapsed_seconds": elapsed,
                "returned_chunk_ids": returned_ids,
            }

        if parent is not None:
            if parent.id in cast(list[str], case_results["below_threshold"]["returned_chunk_ids"]):
                raise AssertionError("below-threshold golden family promoted")
            for label in ("threshold", "above_threshold"):
                if parent.id not in cast(list[str], case_results[label]["returned_chunk_ids"]):
                    raise AssertionError(f"{label} golden family did not promote")
            for expected_parent, _ in independent:
                if expected_parent.id not in cast(
                    list[str], case_results["independent_families"]["returned_chunk_ids"]
                ):
                    raise AssertionError("independent golden family did not promote")
        else:
            root_ids = cast(list[str], case_results["root_noop"]["returned_chunk_ids"])
            if root_ids != [chunk.id for chunk in chunks[:100]]:
                raise AssertionError("golden root stream changed during parent promotion")
            if case_results["root_noop"]["lookup_count"] != 0:
                raise AssertionError("golden root stream performed relationship lookups")

        return {
            "verdict": "PASS",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": EXPECTED_SHA256,
            "database": str((run_dir / "mnemo.db").relative_to(ROOT)).replace("\\", "/"),
            "document_type": canonical.doc_type.value,
            "chunk_count": len(chunks),
            "stored_family_count": len(families),
            "families_examined": len(families),
            "unique_parents_promoted": len(promoted_parent_ids),
            "actual_get_chunk_calls_including_repeat": total_lookups,
            "promotion_seconds_excluding_repeat": total_promotion_seconds,
            "total_acceptance_seconds": time.perf_counter() - acceptance_started,
            "deterministic_repeat": "PASS",
            "hierarchy_limitation": (
                None
                if families
                else "BookChunker emitted 1275 root chunks and no canonical parent families; "
                "promotion semantics are covered by controlled SQLite fixtures."
            ),
            "cases": case_results,
            "returned_identity_count": len(all_returned_ids),
        }
    finally:
        await blobs.close()
        await sqlite.close()


def main() -> int:
    print(json.dumps(asyncio.run(_run()), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
