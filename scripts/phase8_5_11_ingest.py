"""Reproducible isolated production-ingestion runner for Phase 8.5.11."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import os
import sqlite3
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from mnemo.config import MnemoConfig
from mnemo.engine import KnowledgeEngine
from mnemo.models import Notebook
from mnemo.tokenizers import O200KBaseTokenCounter
from mnemo_server.services.ingestion import IngestionService  # type: ignore[import-untyped]
from mnemo_server.tokenizer_provisioning import provision_tokenizer  # type: ignore[import-untyped]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("mnemo.toml"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--notebook-key", default="phase-8.5.11:evaluation-notebook")
    parser.add_argument("--notebook-title", default="Phase 8.5 Evaluation Corpus")
    parser.add_argument(
        "--notebook-description", default="Isolated production-pipeline evaluation notebook"
    )
    return parser.parse_args()


def _inventory(corpus: Path, includes: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    selected = sorted(item for item in corpus.rglob("*") if item.is_file())
    if includes:
        allowed = frozenset(includes)
        selected = [path for path in selected if path.relative_to(corpus).as_posix() in allowed]
        missing = sorted(allowed - {path.relative_to(corpus).as_posix() for path in selected})
        if missing:
            raise FileNotFoundError(f"included corpus files are absent: {missing}")
    for path in selected:
        content = path.read_bytes()
        result.append(
            {
                "filename": path.name,
                "relative_path": path.relative_to(corpus).as_posix(),
                "extension": path.suffix.casefold(),
                "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "byte_size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return result


def _database_evidence(database: Path, ingestions: list[dict[str, Any]]) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:

        def scalar(sql: str, values: tuple[object, ...] = ()) -> int:
            row = connection.execute(sql, values).fetchone()
            assert row is not None
            return int(row[0])

        by_document: list[dict[str, Any]] = []
        for item in ingestions:
            if item.get("status") != "indexed":
                continue
            document_id = item["document_id"]
            version_id = item["version_id"]
            by_document.append(
                {
                    "filename": item["filename"],
                    "document_id": document_id,
                    "version_id": version_id,
                    "chunks": scalar(
                        "SELECT COUNT(*) FROM chunks WHERE document_id=?", (document_id,)
                    ),
                    "fts": scalar(
                        "SELECT COUNT(*) FROM fts_chunks WHERE document_id=?", (document_id,)
                    ),
                    "titles": scalar(
                        "SELECT COUNT(*) FROM fts_chunk_titles "
                        "WHERE document_id=? AND version_id=?",
                        (document_id, version_id),
                    ),
                }
            )
        return {
            "schema_version": scalar("SELECT MAX(version) FROM schema_versions"),
            "notebooks": scalar("SELECT COUNT(*) FROM notebooks"),
            "documents": scalar("SELECT COUNT(*) FROM documents"),
            "versions": scalar("SELECT COUNT(*) FROM document_versions"),
            "sources": scalar("SELECT COUNT(*) FROM sources"),
            "chunks": scalar("SELECT COUNT(*) FROM chunks"),
            "fts_rows": scalar("SELECT COUNT(*) FROM fts_chunks"),
            "title_rows": scalar("SELECT COUNT(*) FROM fts_chunk_titles"),
            "assets": scalar("SELECT COUNT(*) FROM asset_catalog"),
            "binary_references": scalar("SELECT COUNT(*) FROM document_binary_references"),
            "occurrences": scalar("SELECT COUNT(*) FROM asset_occurrences"),
            "duplicate_chunk_ids": scalar(
                "SELECT COUNT(*) FROM (SELECT id FROM chunks GROUP BY id HAVING COUNT(*) > 1)"
            ),
            "orphan_chunks": scalar(
                "SELECT COUNT(*) FROM chunks c LEFT JOIN documents d "
                "ON d.document_id=c.document_id "
                "LEFT JOIN document_versions v ON v.version_id=c.version_id "
                "WHERE d.document_id IS NULL OR v.version_id IS NULL"
            ),
            "orphan_versions": scalar(
                "SELECT COUNT(*) FROM document_versions v LEFT JOIN documents d "
                "ON d.document_id=v.document_id WHERE d.document_id IS NULL"
            ),
            "orphan_occurrences": scalar(
                "SELECT COUNT(*) FROM asset_occurrences o LEFT JOIN asset_catalog a "
                "ON a.asset_id=o.asset_id "
                "LEFT JOIN document_versions v ON v.version_id=o.version_id "
                "WHERE a.asset_id IS NULL OR v.version_id IS NULL"
            ),
            "stale_fts_rows": scalar(
                "SELECT COUNT(*) FROM fts_chunks f LEFT JOIN chunks c ON c.rowid=f.rowid "
                "WHERE c.id IS NULL"
            ),
            "missing_fts_rows": scalar(
                "SELECT COUNT(*) FROM chunks c LEFT JOIN fts_chunks f ON f.rowid=c.rowid "
                "WHERE f.rowid IS NULL"
            ),
            "orphan_title_rows": scalar(
                "SELECT COUNT(*) FROM fts_chunk_titles t LEFT JOIN chunks c ON c.id=t.chunk_id "
                "WHERE c.id IS NULL"
            ),
            "by_document": by_document,
        }
    finally:
        connection.close()


async def _run(args: argparse.Namespace) -> int:
    corpus = args.corpus.resolve(strict=True)
    runtime = args.runtime.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    blob_root = runtime / "files"
    blob_root.mkdir(parents=True, exist_ok=True)
    database = runtime / "mnemo.db"
    if database.exists() and not args.resume:
        raise RuntimeError(f"evaluation database must start absent: {database}")

    os.environ["MNEMO_STORAGE_SQLITE_PATH"] = str(database)
    os.environ["MNEMO_STORAGE_FILESYSTEM_ROOT"] = str(blob_root)
    config = MnemoConfig.from_file(args.config)
    engine = KnowledgeEngine(config)
    await engine.initialize()
    notebook_id = uuid5(NAMESPACE_URL, f"mnemo:{args.notebook_key}")
    now = datetime.now(UTC)
    await engine.storage.upsert_notebook(
        Notebook(
            notebook_id=notebook_id,
            title=args.notebook_title,
            description=args.notebook_description,
            created_at=now,
            updated_at=now,
        )
    )
    token_counter = O200KBaseTokenCounter(provision_tokenizer())
    service = IngestionService(engine, token_counter, max_asset_bytes=100 * 1024 * 1024)
    inventory = _inventory(corpus, tuple(args.include))
    ingestions: list[dict[str, Any]] = []
    try:
        for position, source in enumerate(inventory, start=1):
            path = corpus / source["relative_path"]
            started = time.perf_counter()
            record: dict[str, Any] = {"filename": path.name, "position": position}
            try:
                existing = await engine.storage.get_document_by_content_hash(source["sha256"])
                if existing is not None and existing.status.value == "failed":
                    await engine.storage.delete_document_cascade(existing.document_id)
                    existing = None
                if existing is not None:
                    parsed = await engine.storage.get_parsed_document(existing.current_version_id)
                    assert parsed is not None
                    source_record = await service._find_source_in_notebook(
                        notebook_id, existing.document_id
                    )
                    assert source_record is not None
                    occurrences = await engine.asset_catalog.list_asset_occurrences(
                        existing.current_version_id
                    )
                    record.update(
                        {
                            "status": existing.status.value,
                            "document_id": str(existing.document_id),
                            "version_id": str(existing.current_version_id),
                            "source_id": str(source_record.source_id),
                            "doc_type": parsed.doc_type.value,
                            "title": parsed.metadata.title,
                            "language": parsed.language,
                            "blocks": len(parsed.blocks),
                            "block_types": dict(
                                Counter(type(block).__name__ for block in parsed.blocks)
                            ),
                            "occurrences": len(occurrences),
                            "occurrence_parsers": dict(
                                Counter(
                                    occurrence.extraction_provenance.parser_id
                                    for occurrence in occurrences
                                )
                            ),
                            "resumed": True,
                        }
                    )
                    print(f"[{position}/{len(inventory)}] retained {path.name}", flush=True)
                    record["duration_seconds"] = round(time.perf_counter() - started, 3)
                    ingestions.append(record)
                    continue
                response = await service.ingest_source(
                    notebook_id=notebook_id,
                    filename=path.name,
                    data=path.read_bytes(),
                )
                document = await engine.storage.get_document(response.document_id)
                assert document is not None
                parsed = await engine.storage.get_parsed_document(document.current_version_id)
                assert parsed is not None
                occurrences = await engine.asset_catalog.list_asset_occurrences(
                    document.current_version_id
                )
                record.update(
                    {
                        "status": response.status,
                        "document_id": str(response.document_id),
                        "version_id": str(document.current_version_id),
                        "source_id": str(response.source_id),
                        "doc_type": response.doc_type,
                        "title": parsed.metadata.title,
                        "language": parsed.language,
                        "blocks": len(parsed.blocks),
                        "block_types": dict(
                            Counter(type(block).__name__ for block in parsed.blocks)
                        ),
                        "occurrences": len(occurrences),
                        "occurrence_parsers": dict(
                            Counter(
                                occurrence.extraction_provenance.parser_id
                                for occurrence in occurrences
                            )
                        ),
                    }
                )
                print(f"[{position}/{len(inventory)}] indexed {path.name}", flush=True)
            except Exception as error:
                record.update(
                    {
                        "status": "failed",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
                print(
                    f"[{position}/{len(inventory)}] FAILED {path.name}: "
                    f"{type(error).__name__}: {error}",
                    flush=True,
                )
            record["duration_seconds"] = round(time.perf_counter() - started, 3)
            ingestions.append(record)
        phase8_5_models = {
            "vision": engine.phase85.profile_status("vision").model,
            "multilingual_embedding": engine.phase85.profile_status("multilingual_embedding").model,
            "multilingual_reranker": engine.phase85.profile_status("multilingual_reranker").model,
            "visual_embedding": engine.phase85.profile_status("visual_embedding").model,
        }
    finally:
        await engine.shutdown()

    evidence = {
        "created_at": datetime.now(UTC).isoformat(),
        "corpus_root": str(corpus),
        "runtime_root": str(runtime),
        "notebook_id": str(notebook_id),
        "configuration": {
            "embedding_provider": config.embedding.provider,
            "embedding_model": config.embedding.model,
            "embedding_dimensions": config.embedding.dimensions,
            "reranker_provider": config.reranker.provider,
            "reranker_model": config.reranker.model,
            "phase8_5_models": phase8_5_models,
            "llm_models": {
                role: getattr(config.llm, role).model
                for role in ("planner", "synthesizer", "extractor", "classifier")
            },
            "qdrant_enabled": config.storage.qdrant.enabled,
        },
        "inventory": inventory,
        "ingestions": ingestions,
        "database": _database_evidence(database, ingestions),
    }
    output = runtime / "ingestion-evidence.json"
    output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)
    return 0 if all(item["status"] == "indexed" for item in ingestions) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_arguments())))
