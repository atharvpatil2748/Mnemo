"""Run Module 6.3 against the real golden PDF and an isolated SQLite index."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from mnemo import __version__
from mnemo.chunkers import BookChunker, ChunkerDispatcher
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion import DocumentCanonicalizer
from mnemo.interfaces import ChunkingContext, ChunkingOptions
from mnemo.interfaces.parser_models import ParseResult
from mnemo.models import (
    DocType,
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    MetadataFilter,
    Notebook,
    Source,
)
from mnemo.parsers import ParserRouter, PDFParser
from mnemo.registry import PluginRegistry
from mnemo.retrieval import SparseRetriever
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.retrieval_projection import RetrievalMetadataProjection
from mnemo.storage.sqlite import SQLiteStore
from mnemo.tokenizers import O200KBaseTokenCounter

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "goldenDataset" / "Bhagavad-gita-As-It-Is.pdf"
EXPECTED_SHA256 = "ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583"
TOKENIZER = (
    Path.home()
    / "AppData"
    / "Local"
    / "Mnemo"
    / "tokenizers"
    / "o200k_base"
    / "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
    / "o200k_base.tiktoken"
)


class _GoldenPlugin:
    name = "mnemo-module-6-3-golden"
    version = __version__
    core_version_range = ">=0.20.1"

    def capabilities(self) -> tuple[str, ...]:
        return ("parser", "chunker")

    def register(self, registry: PluginRegistry) -> None:
        parser = PDFParser()
        registry.register_parser(".pdf", parser, priority=0)
        registry.register_parser("application/pdf", parser, priority=0)
        registry.register_chunker_v2(DocType.BOOK, BookChunker(), priority=0)


async def _run() -> dict[str, object]:
    payload = DATASET.read_bytes()
    if sha256(payload).hexdigest() != EXPECTED_SHA256:
        raise AssertionError("golden corpus hash mismatch")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "data" / "module-6.3-acceptance" / run_id
    sqlite = SQLiteStore(run_dir / "mnemo.db")
    blobs = FilesystemBlobStore(run_dir / "files")
    await sqlite.open()
    await blobs.open()
    try:
        registry = PluginRegistry(core_version=__version__)
        result = registry.load_plugins((_GoldenPlugin(),))[0]
        if not result.loaded:
            raise AssertionError(result.error_message)
        registry.freeze()

        started = time.perf_counter()
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
        await blobs.put_parsed_document(version_id, canonical)
        chunks = ChunkerDispatcher(registry, O200KBaseTokenCounter(TOKENIZER)).dispatch(
            canonical,
            ChunkingContext(
                document_version=version,
                options=ChunkingOptions(target_tokens=400, max_tokens=500),
            ),
        )
        await sqlite._upsert_chunks_with_projection(
            chunks,
            RetrievalMetadataProjection(
                doc_type=canonical.doc_type,
                publication_date=version.metadata.publication_date,
            ),
        )
        notebook_id = uuid5(NAMESPACE_URL, "mnemo-module-6.3-notebook")
        source_id = uuid5(NAMESPACE_URL, "mnemo-module-6.3-source")
        await sqlite.upsert_notebook(
            Notebook(
                notebook_id=notebook_id,
                title="Module 6.3 golden acceptance",
                created_at=created,
                updated_at=created,
            )
        )
        await sqlite.upsert_source(
            Source(
                source_id=source_id,
                notebook_id=notebook_id,
                document_id=document_id,
                created_at=created,
            )
        )
        retriever = SparseRetriever(sqlite)
        query = "What does the Bhagavad Gita teach about duty?"
        unfiltered = await retriever.retrieve(query, None, MetadataFilter(), 5)
        filtered = await retriever.retrieve(
            query,
            None,
            MetadataFilter(
                notebook_id=notebook_id,
                source_ids=(source_id,),
                doc_types=(DocType.BOOK,),
            ),
            5,
        )
        if len(unfiltered) != 5 or len(filtered) != 5:
            raise AssertionError("golden sparse search did not honor top_k=5")
        if tuple(item.chunk.id for item in unfiltered) != tuple(item.chunk.id for item in filtered):
            raise AssertionError("eligible golden filter changed the candidate identity")
        if any(item.chunk.document_id != document_id for item in filtered):
            raise AssertionError("filtered result escaped the golden document")
        scores = tuple(item.score for item in filtered)
        if scores != tuple(sorted(scores, reverse=True)):
            raise AssertionError("sparse results are not descending by score")
        indexed = len(chunks)
        await sqlite.delete_chunks_for_document(document_id, version_id)
        if await retriever.retrieve("duty", None, MetadataFilter(), 5):
            raise AssertionError("deleted FTS rows remained searchable")
        await sqlite._upsert_chunks_with_projection(
            chunks,
            RetrievalMetadataProjection(
                doc_type=canonical.doc_type,
                publication_date=version.metadata.publication_date,
            ),
        )
        if not await retriever.retrieve("duty", None, MetadataFilter(), 1):
            raise AssertionError("reindexed chunks were not searchable")
        return {
            "verdict": "PASS",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "database": str((run_dir / "mnemo.db").relative_to(ROOT)).replace("\\", "/"),
            "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": EXPECTED_SHA256,
            "document_type": canonical.doc_type.value,
            "chunk_count": indexed,
            "query": query,
            "top_k": 5,
            "returned_chunk_ids": [item.chunk.id for item in filtered],
            "returned_scores": list(scores),
            "filters": ["notebook_id", "source_ids", "doc_types"],
            "delete_reindex": "PASS",
            "elapsed_seconds": time.perf_counter() - started,
        }
    finally:
        await blobs.close()
        await sqlite.close()


def main() -> int:
    result = asyncio.run(_run())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
