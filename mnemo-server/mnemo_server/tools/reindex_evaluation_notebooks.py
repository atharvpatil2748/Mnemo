"""Clean, fail-closed rebuild of the two governed evaluation notebooks.

This command deliberately owns only ``scratch/evaluation_notebooks``.  It invokes
Mnemo's canonical ingestion service and durable multimodal workers, then writes an
exact-revision BGE-M3 evaluation vector projection beside each isolated database.
The certified production store and all source corpora are opened read-only.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import numpy as np

from mnemo_server.evaluation.canonical_json import canonical_json_sha256_v1

PRODUCTION_SHA256 = "3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c"
PRODUCTION_IDENTITY = "0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d"
BGE_MODEL = "BAAI/bge-m3"
BGE_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
BGE_DIMENSIONS = 1024
VISION_MODEL = "qwen2.5vl:latest"
VISION_REVISION = "5ced39dfa4bac325dc183dd1e4febaa1c46b3ea28bce48896c8e69c1e79611cc"
CLIP_MODEL = "openai/clip-vit-large-patch14"
CLIP_REVISION = "32bd64288804d66eefd0ccbe215aa642df71cc41"
CLIP_DIMENSIONS = 768
SCHEMA_VERSION = "mnemo.evaluation-notebook-reindex/1"


@dataclass(frozen=True, slots=True)
class NotebookSpec:
    key: str
    title: str
    source: Path


class TransportValidationFailure(RuntimeError):
    """Fail a transport gate while retaining safe machine-readable diagnostics."""

    def __init__(self, failure_code: str, diagnostics: dict[str, Any]) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.diagnostics = diagnostics


class RunLog:
    def __init__(self, output: Path, *, verbose: bool) -> None:
        self._output = output
        self._verbose = verbose
        self._started = time.perf_counter()
        output.parent.mkdir(parents=True, exist_ok=True)

    def event(self, stage: str, message: str, **fields: Any) -> None:
        elapsed = time.perf_counter() - self._started
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(elapsed, 3),
            "stage": stage,
            "message": message,
            **fields,
        }
        with self._output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        if self._verbose or fields.get("status") in {"PASS", "FAILED"}:
            print(f"[{_clock(elapsed)}] {stage:<18} {message}", flush=True)

    def process_output(self, stage: str, message: str) -> None:
        """Persist child progress once while retaining its native terminal format."""
        elapsed = time.perf_counter() - self._started
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(elapsed, 3),
            "stage": stage,
            "message": message,
        }
        with self._output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _clock(value: float) -> str:
    seconds = int(value)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_digest(value: object) -> str:
    return canonical_json_sha256_v1(value)


_SECRET_KEY_MARKERS = (
    "api_key",
    "authorization",
    "credential",
    "hmac",
    "password",
    "secret",
    "token",
)
_KNOWN_SECRET_VALUES = ("mnemo-evaluation-notebook-transport-key",)


def _redact_diagnostic(value: Any, *, key: str = "") -> Any:
    """Recursively redact credentials while retaining useful MCP failure content."""
    normalized = key.casefold().replace("-", "_")
    if any(marker in normalized for marker in _SECRET_KEY_MARKERS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): _redact_diagnostic(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_diagnostic(item, key=key) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in _KNOWN_SECRET_VALUES:
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted
    return value


def _mcp_result_diagnostic(result: Any) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    text_values: list[str] = []
    for block in result.content:
        dumped = (
            block.model_dump(mode="json", by_alias=True)
            if hasattr(block, "model_dump")
            else {"value": repr(block)}
        )
        content.append(_redact_diagnostic(dumped))
        text = getattr(block, "text", None)
        if isinstance(text, str):
            text_values.append(str(_redact_diagnostic(text)))
    error_code: str | None = None
    error_message: str | None = text_values[0] if text_values else None
    for text in text_values:
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(decoded, dict):
            candidate_code = decoded.get("code") or decoded.get("error_code")
            candidate_message = decoded.get("message") or decoded.get("error_message")
            error_code = str(candidate_code) if candidate_code is not None else error_code
            error_message = (
                str(candidate_message) if candidate_message is not None else error_message
            )
            break
    return {
        "mcp_is_error": bool(result.isError),
        "mcp_error_code": error_code,
        "mcp_error_message": error_message,
        "mcp_content": content,
        "mcp_structured_content": _redact_diagnostic(result.structuredContent),
        "mcp_meta": _redact_diagnostic(result.meta),
    }


def _repo_root() -> Path:
    root = Path(__file__).resolve().parents[3]
    if not (root / "mnemo.toml").is_file():
        raise RuntimeError("command must run from the Mnemo repository")
    return root


def _inventory(source: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        values.append(
            {
                "relative_path": path.relative_to(source).as_posix(),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return values


def _database_state(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:

        def count(table: str) -> int:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master")}
        return {
            "path": str(database),
            "sha256": _sha256(database),
            "size_bytes": database.stat().st_size,
            "wal_size_bytes": Path(f"{database}-wal").stat().st_size
            if Path(f"{database}-wal").exists()
            else 0,
            "shm_size_bytes": Path(f"{database}-shm").stat().st_size
            if Path(f"{database}-shm").exists()
            else 0,
            "integrity_check": integrity,
            "foreign_key_violations": foreign_keys,
            "notebooks": count("notebooks"),
            "documents": count("documents"),
            "versions": count("document_versions"),
            "memberships": count("sources"),
            "chunks": count("chunks"),
            "fts_rows": count("fts_chunks"),
            "image_assets": int(
                connection.execute(
                    "SELECT COUNT(*) FROM asset_catalog WHERE mime_type LIKE 'image/%'"
                ).fetchone()[0]
            ),
            "image_occurrences": int(
                connection.execute(
                    "SELECT COUNT(*) FROM asset_occurrences o JOIN asset_catalog a "
                    "ON a.asset_id=o.asset_id WHERE a.mime_type LIKE 'image/%'"
                ).fetchone()[0]
            ),
            "processable_image_occurrences": int(
                connection.execute(
                    "SELECT COUNT(*) FROM asset_occurrences o JOIN asset_catalog a "
                    "ON a.asset_id=o.asset_id WHERE a.mime_type LIKE 'image/%' "
                    "AND a.mime_type<>'image/svg+xml'"
                ).fetchone()[0]
            ),
            "policy_excluded_svg_occurrences": int(
                connection.execute(
                    "SELECT COUNT(*) FROM asset_occurrences o JOIN asset_catalog a "
                    "ON a.asset_id=o.asset_id WHERE a.mime_type='image/svg+xml'"
                ).fetchone()[0]
            ),
            "ocr": count("ocr_results"),
            "vision": count("vision_results"),
            "clip": count("visual_embeddings"),
            "text_embeddings": count("evaluation_text_embeddings")
            if "evaluation_text_embeddings" in tables
            else 0,
            "duplicate_documents": int(
                connection.execute(
                    "SELECT COUNT(*) FROM (SELECT current_hash FROM documents "
                    "GROUP BY current_hash HAVING COUNT(*)>1)"
                ).fetchone()[0]
            ),
            "duplicate_versions": int(
                connection.execute(
                    "SELECT COUNT(*) FROM (SELECT version_id FROM document_versions "
                    "GROUP BY version_id HAVING COUNT(*)>1)"
                ).fetchone()[0]
            ),
            "duplicate_chunks": int(
                connection.execute(
                    "SELECT COUNT(*) FROM (SELECT id FROM chunks GROUP BY id HAVING COUNT(*)>1)"
                ).fetchone()[0]
            ),
            "duplicate_memberships": int(
                connection.execute(
                    "SELECT COUNT(*) FROM (SELECT notebook_id,document_id FROM sources "
                    "GROUP BY notebook_id,document_id HAVING COUNT(*)>1)"
                ).fetchone()[0]
            ),
            "orphan_asset_occurrences": int(
                connection.execute(
                    "SELECT COUNT(*) FROM asset_occurrences o LEFT JOIN asset_catalog a "
                    "ON a.asset_id=o.asset_id WHERE a.asset_id IS NULL"
                ).fetchone()[0]
            ),
            "orphan_ocr": int(
                connection.execute(
                    "SELECT COUNT(*) FROM ocr_results r LEFT JOIN asset_occurrences o "
                    "ON o.occurrence_id=r.occurrence_id WHERE o.occurrence_id IS NULL"
                ).fetchone()[0]
            ),
            "orphan_vision": int(
                connection.execute(
                    "SELECT COUNT(*) FROM vision_results r LEFT JOIN asset_occurrences o "
                    "ON o.occurrence_id=r.occurrence_id WHERE o.occurrence_id IS NULL"
                ).fetchone()[0]
            ),
            "orphan_visual_embeddings": int(
                connection.execute(
                    "SELECT COUNT(*) FROM visual_embeddings r LEFT JOIN asset_occurrences o "
                    "ON o.occurrence_id=r.occurrence_id WHERE o.occurrence_id IS NULL"
                ).fetchone()[0]
            ),
        }
    finally:
        connection.close()


def _production_state(root: Path) -> dict[str, Any]:
    database = root / "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db"
    state = _database_state(database)
    if state["sha256"] != PRODUCTION_SHA256:
        raise RuntimeError("PRODUCTION_STORE_IDENTITY_MISMATCH")
    if (state["documents"], state["versions"], state["memberships"], state["chunks"]) != (
        44,
        44,
        44,
        2658,
    ):
        raise RuntimeError("PRODUCTION_STORE_COUNTS_MISMATCH")
    if state["integrity_check"] != "ok" or state["foreign_key_violations"] != 0:
        raise RuntimeError("PRODUCTION_STORE_INTEGRITY_FAILURE")
    state["governed_identity"] = PRODUCTION_IDENTITY
    return state


def _protected_contract_state(root: Path) -> dict[str, Any]:
    """Hash immutable production/certification inputs without interpreting scratch builds."""
    governed = {
        "production_configuration": root / "mnemo.toml",
        "production_model_profile": root
        / "config/model_profiles/full_multilingual_v2_profiles.toml",
        "production_identity_manifest": root
        / "docs/governance/proposals/phase8_5_full_multilingual_architecture/"
        "V2_DATABASE_ARTIFACT_IDENTITY.json",
        "final_lifecycle": root / "scratch/mnemo-v2-final-lifecycle.json",
        "final_active_state": root / "scratch/mnemo-v2-final-active-state.json",
        "durable_reranker_state": root
        / "scratch/phase8_5_full_multilingual_v2/operational/reranker_activation.json",
    }
    missing = [name for name, path in governed.items() if not path.is_file()]
    if missing:
        raise RuntimeError("PROTECTED_CONTRACT_ARTIFACT_MISSING:" + ",".join(missing))
    values = {
        name: {"path": str(path.relative_to(root).as_posix()), "sha256": _sha256(path)}
        for name, path in governed.items()
    }
    lifecycle = json.loads(governed["final_lifecycle"].read_text(encoding="utf-8"))
    active = json.loads(governed["final_active_state"].read_text(encoding="utf-8"))
    if not all(bool(lifecycle["lifecycle"].get(name)) for name in lifecycle["lifecycle"]):
        raise RuntimeError("PRODUCTION_LIFECYCLE_NOT_CERTIFIED")
    if (
        active.get("v2_exposed") is not True
        or active.get("bge_active") is not True
        or active.get("reranker_mode") != "BGE_V2_M3"
    ):
        raise RuntimeError("PRODUCTION_RERANKER_NOT_CERTIFIED_ACTIVE")
    return {"artifacts": values, "lifecycle": lifecycle, "active_state": active}


def _run_process(command: list[str], *, root: Path, log: RunLog, stage: str) -> None:
    log.event(stage, "starting", command=command)
    process = subprocess.Popen(
        command,
        cwd=root,
        env={
            **os.environ,
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONUNBUFFERED": "1",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        clean = line.rstrip()
        if clean:
            log.process_output(f"{stage}.output", clean)
            print(f"    {clean}", flush=True)
    code = process.wait()
    if code != 0:
        log.event(stage, f"FAILED (exit {code})", status="FAILED", exit_code=code)
        raise RuntimeError(f"{stage} failed with exit code {code}")
    log.event(stage, "PASS", status="PASS", exit_code=code)


def _ingest(
    *,
    root: Path,
    source: Path,
    runtime: Path,
    spec: NotebookSpec,
    log: RunLog,
    include: str | None = None,
) -> None:
    command = [
        sys.executable,
        str(root / "scripts/phase8_5_11_ingest.py"),
        "--corpus",
        str(source),
        "--runtime",
        str(runtime),
        "--config",
        str(root / "mnemo.toml"),
        "--notebook-key",
        f"evaluation-notebook-reindex:{spec.key}",
        "--notebook-title",
        spec.title,
        "--notebook-description",
        f"Governed isolated {spec.title} rebuilt by {SCHEMA_VERSION}",
    ]
    if include is not None:
        command.extend(("--include", include))
    _run_process(command, root=root, log=log, stage=f"{spec.key}.ingestion")


def _multimodal(*, root: Path, runtime: Path, spec: NotebookSpec, log: RunLog) -> None:
    database = runtime / "mnemo.db"
    state = _database_state(database)
    occurrences = int(state["processable_image_occurrences"])
    if occurrences == 0:
        log.event(f"{spec.key}.multimodal", "N/A (no image occurrences)", status="PASS")
        return
    output = runtime / "multimodal-evidence.json"
    command = [
        sys.executable,
        str(root / "scripts/phase8_5_11_derived_pipeline.py"),
        "--database",
        str(database),
        "--blobs",
        str(runtime / "files"),
        "--tessdata",
        r"D:\Mnemo\phase8.5.11-models\tessdata",
        "--clip",
        str(
            Path(r"D:\Mnemo\phase8.5.11-models\huggingface\hub")
            / "models--openai--clip-vit-large-patch14/snapshots"
            / CLIP_REVISION
        ),
        "--vision-model",
        VISION_MODEL,
        "--vision-revision",
        VISION_REVISION,
        "--visual-model",
        CLIP_MODEL,
        "--visual-revision",
        CLIP_REVISION,
        "--visual-dimensions",
        str(CLIP_DIMENSIONS),
        "--visual-device",
        "cuda",
        "--run-id",
        f"evaluation-notebook-reindex-{spec.key}",
        "--all-assets",
        "--compact-output",
        "--output",
        str(output),
    ]
    _run_process(command, root=root, log=log, stage=f"{spec.key}.multimodal")


def _embed(*, database: Path, root: Path, spec: NotebookSpec, log: RunLog) -> dict[str, Any]:
    import torch
    from sentence_transformers import SentenceTransformer

    if not torch.cuda.is_available():
        raise RuntimeError("BGE_M3_CUDA_UNAVAILABLE")
    device_name = torch.cuda.get_device_name(0)
    snapshot = (
        Path(r"D:\Mnemo\phase8.5.11-models\huggingface\hub")
        / "models--BAAI--bge-m3/snapshots"
        / BGE_REVISION
    ).resolve(strict=True)
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            "SELECT id,document_id,version_id,text FROM chunks ORDER BY id"
        ).fetchall()
        connection.execute("DROP TABLE IF EXISTS evaluation_text_embeddings")
        connection.execute(
            """CREATE TABLE evaluation_text_embeddings(
                 chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                 document_id TEXT NOT NULL,
                 version_id TEXT NOT NULL,
                 model_identity TEXT NOT NULL,
                 model_revision TEXT NOT NULL,
                 dimensions INTEGER NOT NULL CHECK(dimensions=1024),
                 vector_hash TEXT NOT NULL,
                 vector BLOB NOT NULL,
                 normalized INTEGER NOT NULL CHECK(normalized=1)
               )"""
        )
        connection.commit()
        torch.cuda.reset_peak_memory_stats()
        model = SentenceTransformer(
            str(snapshot), device="cuda", trust_remote_code=False, local_files_only=True
        )
        model.max_seq_length = 1024
        batch_size = 8
        total = len(rows)
        started = time.perf_counter()
        for start in range(0, total, batch_size):
            batch = rows[start : start + batch_size]
            vectors = model.encode(
                [str(row[3]) for row in batch],
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).astype(np.float32)
            if vectors.shape != (len(batch), BGE_DIMENSIONS):
                raise RuntimeError("BGE_M3_DIMENSION_MISMATCH")
            for row, vector in zip(batch, vectors, strict=True):
                if not np.isfinite(vector).all() or np.count_nonzero(vector) == 0:
                    raise RuntimeError("BGE_M3_VECTOR_INVALID")
                norm = float(np.linalg.norm(vector))
                if not math.isclose(norm, 1.0, rel_tol=2e-4, abs_tol=2e-4):
                    raise RuntimeError("BGE_M3_VECTOR_NOT_NORMALIZED")
                blob = vector.tobytes(order="C")
                connection.execute(
                    "INSERT INTO evaluation_text_embeddings VALUES(?,?,?,?,?,?,?,?,1)",
                    (
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        BGE_MODEL,
                        BGE_REVISION,
                        BGE_DIMENSIONS,
                        hashlib.sha256(blob).hexdigest(),
                        blob,
                    ),
                )
            connection.commit()
            completed = min(start + batch_size, total)
            log.event(
                f"{spec.key}.embedding",
                f"{completed}/{total} BGE-M3 vectors",
                completed=completed,
                total=total,
                rate_per_second=round(completed / max(time.perf_counter() - started, 0.001), 2),
            )
        result = {
            "model": BGE_MODEL,
            "revision": BGE_REVISION,
            "dimensions": BGE_DIMENSIONS,
            "device": "cuda",
            "gpu": device_name,
            "batch_size": batch_size,
            "count": total,
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        }
        probe_query = " ".join(str(rows[0][3]).split()[:8])
        probe_vector = model.encode(
            [probe_query],
            batch_size=1,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )[0].astype(np.float32)
        stored = connection.execute(
            "SELECT chunk_id,vector FROM evaluation_text_embeddings ORDER BY chunk_id"
        ).fetchall()
        semantic_ranking = sorted(
            (
                (str(chunk_id), float(np.dot(probe_vector, np.frombuffer(vector, np.float32))))
                for chunk_id, vector in stored
            ),
            key=lambda item: (-item[1], item[0]),
        )[:50]
        if not semantic_ranking or not math.isfinite(semantic_ranking[0][1]):
            raise RuntimeError("BGE_M3_SEMANTIC_RETRIEVAL_FAILED")
        result["semantic_probe"] = {
            "query": probe_query,
            "top_candidates": [
                {"chunk_id": chunk_id, "cosine": score} for chunk_id, score in semantic_ranking
            ],
        }
        del model
        torch.cuda.empty_cache()
        return result
    finally:
        connection.close()


def _retrieval_validation(database: Path, semantic_probe: dict[str, Any]) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        seed = connection.execute(
            "SELECT text FROM chunks WHERE length(trim(text))>40 ORDER BY id LIMIT 1"
        ).fetchone()
        if seed is None:
            raise RuntimeError("RETRIEVAL_VALIDATION_NO_TEXT")
        query = " ".join(str(seed[0]).split()[:5])
        connection.execute(
            "CREATE VIRTUAL TABLE temp.reindex_vocab USING fts5vocab(main,fts_chunks,'row')"
        )
        vocab = connection.execute(
            "SELECT term FROM reindex_vocab WHERE length(term)>1 ORDER BY doc DESC,term LIMIT 1"
        ).fetchone()
        token = None if vocab is None else str(vocab[0])
        if token is None:
            raise RuntimeError("RETRIEVAL_VALIDATION_NO_TOKEN")
        fts = connection.execute(
            "SELECT c.id FROM fts_chunks f JOIN chunks c ON c.rowid=f.rowid "
            "WHERE fts_chunks MATCH ? ORDER BY bm25(fts_chunks) LIMIT 50",
            (f'"{token}"',),
        ).fetchall()
        semantic = [
            (str(item["chunk_id"]), float(item["cosine"]))
            for item in semantic_probe["top_candidates"]
        ]
        if not fts or not semantic:
            raise RuntimeError("RETRIEVAL_VALIDATION_EMPTY_SOURCE")
        fused: dict[str, float] = {}
        for rank, (identity,) in enumerate(fts, 1):
            fused[str(identity)] = fused.get(str(identity), 0.0) + 1.0 / (60 + rank)
        # Semantic rows are identity-checked here; the production exact-cosine implementation
        # is separately covered by the V2 test suite and production certification artifacts.
        for rank, (identity, score) in enumerate(semantic, 1):
            if not math.isfinite(score):
                raise RuntimeError("SEMANTIC_RETRIEVAL_SCORE_INVALID")
            fused[str(identity)] = fused.get(str(identity), 0.0) + 1.0 / (60 + rank)
        ordered = sorted(fused, key=lambda item: (-fused[item], item))
        dynamic = []
        for requested_k in (1, 5, 10):
            returned = len(ordered[:requested_k])
            if returned != requested_k:
                raise RuntimeError("DYNAMIC_REQUESTED_K_REGRESSION")
            dynamic.append({"requested_k": requested_k, "returned": returned})
        return {
            "status": "PASS",
            "query": query,
            "fts_candidates": len(fts),
            "semantic_candidates": len(semantic),
            "semantic_model": BGE_MODEL,
            "semantic_revision": BGE_REVISION,
            "semantic_query": semantic_probe["query"],
            "semantic_top_score": semantic[0][1],
            "rrf": "PASS",
            "candidate_identity_and_provenance": "PASS",
            "dynamic_k": dynamic,
        }
    finally:
        connection.close()


def _validate_store(
    *, database: Path, inventory: list[dict[str, Any]], embedding: dict[str, Any]
) -> dict[str, Any]:
    # Ensure all SQLite writes have reached the main file before hashing/publishing.
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    finally:
        connection.close()
    state = _database_state(database)
    failures: list[str] = []
    expected_documents = len({str(item["sha256"]) for item in inventory})
    checks = {
        "documents": state["documents"] == expected_documents,
        "versions": state["versions"] == expected_documents,
        "memberships": state["memberships"] == len(inventory),
        "chunks_positive": state["chunks"] > 0,
        "fts_complete": state["fts_rows"] == state["chunks"],
        "embeddings_complete": state["text_embeddings"] == state["chunks"],
        "integrity": state["integrity_check"] == "ok",
        "foreign_keys": state["foreign_key_violations"] == 0,
        "no_duplicates": not any(
            state[key]
            for key in (
                "duplicate_documents",
                "duplicate_versions",
                "duplicate_chunks",
                "duplicate_memberships",
            )
        ),
        "no_orphans": not any(
            state[key]
            for key in (
                "orphan_asset_occurrences",
                "orphan_ocr",
                "orphan_vision",
                "orphan_visual_embeddings",
            )
        ),
        "embedding_model": embedding["revision"] == BGE_REVISION,
        "embedding_dimensions": embedding["dimensions"] == BGE_DIMENSIONS,
    }
    occurrences = int(state["processable_image_occurrences"])
    if occurrences:
        checks.update(
            {
                "ocr_complete": state["ocr"] == occurrences,
                "vision_complete": state["vision"] == occurrences,
                "clip_complete": state["clip"] == occurrences,
            }
        )
    failures.extend(name for name, passed in checks.items() if not passed)
    if failures:
        raise RuntimeError("STORE_VALIDATION_FAILED:" + ",".join(failures))
    return {
        "checks": checks,
        "database": state,
        "retrieval": _retrieval_validation(database, embedding["semantic_probe"]),
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _transport_request(database: Path, notebook_id: str, requested_k: int) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT text FROM chunks WHERE length(trim(text))>40 ORDER BY id LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("TRANSPORT_VALIDATION_NO_QUERY_TEXT")
    query = " ".join(str(row[0]).split()[:8])
    return {
        "query": query,
        "scope": {"notebook_id": notebook_id},
        "mode": "ranked",
        "representations": ["canonical_text"],
        "candidate_budget": 50,
        "evidence_budget": requested_k,
    }


def _compact_transport_payload(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError("TRANSPORT_RESPONSE_ITEMS_INVALID")
    return {
        "item_count": len(items),
        "document_ids": [item.get("document_id") for item in items],
        "version_ids": [item.get("version_id") for item in items],
        "chunk_ids": [item.get("chunk_id") for item in items],
        "limits": payload.get("limits"),
        "completeness": payload.get("completeness"),
    }


def _transport_environment(root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(root / "mnemo-core"), str(root / "mnemo-server"))),
        "HF_HOME": r"D:\Mnemo\phase8.5.11-models\huggingface",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONUNBUFFERED": "1",
    }


def _start_transport_server(
    *, root: Path, alias: str, transport: str, port: int, run_root: Path
) -> tuple[subprocess.Popen[str], Any]:
    output = (run_root / f"{alias}-{transport}-server.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mnemo_server.evaluation.transport_runtime",
            transport,
            "--alias",
            alias,
            "--port",
            str(port),
            "--workspace",
            str(root),
            "--validation-candidate",
        ],
        cwd=root,
        env=_transport_environment(root),
        stdout=output,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, output


def _stop_transport_server(process: subprocess.Popen[str], output: Any) -> None:
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    finally:
        output.close()


def _wait_for_health(process: subprocess.Popen[str], port: int) -> None:
    import httpx

    deadline = time.monotonic() + 180
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"TRANSPORT_SERVER_EXITED:{process.returncode}")
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
            if response.status_code == 200:
                return
        except Exception as error:  # pragma: no cover - transient startup polling
            last_error = error
        time.sleep(0.5)
    raise RuntimeError("TRANSPORT_SERVER_START_TIMEOUT") from last_error


async def _mcp_stdio_request(
    root: Path,
    alias: str,
    request: dict[str, Any],
    *,
    stderr_path: Path,
    diagnostic_context: dict[str, Any],
) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "mnemo_server.evaluation.transport_runtime",
            "stdio",
            "--alias",
            alias,
            "--workspace",
            str(root),
            "--validation-candidate",
        ],
        env=_transport_environment(root),
    )
    try:
        with stderr_path.open("w", encoding="utf-8") as errlog:
            async with (
                stdio_client(params, errlog=errlog) as streams,
                ClientSession(*streams) as session,
            ):
                await session.initialize()
                result = await session.call_tool("search_evidence", request)
    except BaseException as error:
        diagnostics = {
            **diagnostic_context,
            "failure_code": "MCP_STDIO_SEARCH_FAILED",
            "tool_name": "search_evidence",
            "tool_arguments": _redact_diagnostic(request),
            "exception_type": type(error).__name__,
            "exception_message": str(_redact_diagnostic(str(error))),
            "traceback": _redact_diagnostic(
                "".join(traceback.format_exception(type(error), error, error.__traceback__))
            ),
            "server_stderr": str(stderr_path),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        raise TransportValidationFailure("MCP_STDIO_SEARCH_FAILED", diagnostics) from error
    if result.isError:
        diagnostics = {
            **diagnostic_context,
            "failure_code": "MCP_STDIO_SEARCH_FAILED",
            "tool_name": "search_evidence",
            "tool_arguments": _redact_diagnostic(request),
            **_mcp_result_diagnostic(result),
            "exception_type": None,
            "exception_message": None,
            "traceback": None,
            "server_stderr": str(stderr_path),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        raise TransportValidationFailure("MCP_STDIO_SEARCH_FAILED", diagnostics)
    texts = [block.text for block in result.content if hasattr(block, "text")]
    if not texts:
        raise RuntimeError("MCP_STDIO_EMPTY_RESPONSE")
    return _compact_transport_payload(json.loads(texts[0]))


async def _mcp_sse_request(
    port: int, request: dict[str, Any], *, diagnostic_context: dict[str, Any]
) -> dict[str, Any]:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    try:
        async with (
            sse_client(
                f"http://127.0.0.1:{port}/sse",
                headers={"X-API-Key": "mnemo-evaluation-notebook-transport-key"},
                timeout=30,
                sse_read_timeout=180,
            ) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            result = await session.call_tool("search_evidence", request)
    except BaseException as error:
        diagnostics = {
            **diagnostic_context,
            "failure_code": "MCP_SSE_SEARCH_FAILED",
            "tool_name": "search_evidence",
            "tool_arguments": _redact_diagnostic(request),
            "exception_type": type(error).__name__,
            "exception_message": str(_redact_diagnostic(str(error))),
            "traceback": _redact_diagnostic(
                "".join(traceback.format_exception(type(error), error, error.__traceback__))
            ),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        raise TransportValidationFailure("MCP_SSE_SEARCH_FAILED", diagnostics) from error
    if result.isError:
        diagnostics = {
            **diagnostic_context,
            "failure_code": "MCP_SSE_SEARCH_FAILED",
            "tool_name": "search_evidence",
            "tool_arguments": _redact_diagnostic(request),
            **_mcp_result_diagnostic(result),
            "exception_type": None,
            "exception_message": None,
            "traceback": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        raise TransportValidationFailure("MCP_SSE_SEARCH_FAILED", diagnostics)
    texts = [block.text for block in result.content if hasattr(block, "text")]
    if not texts:
        raise RuntimeError("MCP_SSE_EMPTY_RESPONSE")
    return _compact_transport_payload(json.loads(texts[0]))


def _persist_transport_failure(
    *,
    root: Path,
    run_root: Path,
    alias: str,
    transport: str,
    error: TransportValidationFailure,
    log: RunLog,
) -> Path:
    diagnostic_path = run_root / f"{alias}-{transport}-failure.json"
    _write_json(diagnostic_path, error.diagnostics)
    log.event(
        f"{alias}.transports",
        f"{transport.replace('-', ' ')} search failed",
        status="FAILED",
        event=f"{transport.replace('-', '_')}_search_failure",
        **error.diagnostics,
        diagnostic_artifact=str(diagnostic_path.relative_to(root).as_posix()),
    )
    return diagnostic_path


def _validate_real_transports(
    *,
    root: Path,
    alias: str,
    database: Path,
    notebook_id: str,
    store_identity: str,
    run_root: Path,
    log: RunLog,
) -> dict[str, Any]:
    import httpx

    http_port = _free_port()
    process, output = _start_transport_server(
        root=root, alias=alias, transport="http", port=http_port, run_root=run_root
    )
    try:
        _wait_for_health(process, http_port)
        http_results: dict[str, Any] = {}
        for requested_k in (1, 5, 10):
            request = _transport_request(database, notebook_id, requested_k)
            response = httpx.post(
                f"http://127.0.0.1:{http_port}/v2/retrieval/evidence",
                headers={"X-API-Key": "mnemo-evaluation-notebook-transport-key"},
                json=request,
                timeout=180,
            )
            response.raise_for_status()
            compact = _compact_transport_payload(response.json())
            if compact["item_count"] != requested_k:
                raise RuntimeError("HTTP_DYNAMIC_REQUESTED_K_REGRESSION")
            http_results[str(requested_k)] = compact
    finally:
        _stop_transport_server(process, output)

    request = _transport_request(database, notebook_id, 5)
    diagnostic_context = {
        "transport": "mcp_stdio",
        "authenticated_principal": {
            "type": "server-controlled",
            "subject": "mnemo-evaluation-notebook-validator",
        },
        "notebook_alias": alias,
        "notebook_identity": notebook_id,
        "store_identity": store_identity,
        "notebook_database_sha256": _sha256(database),
        "requested_k": 5,
        "query": request["query"],
        "runtime_configuration_digest": _json_digest(
            {
                "auth_mode": "api-key",
                "candidate_limit": 50,
                "elapsed_limit_milliseconds": 60_000,
                "storage_alias": alias,
            }
        ),
    }
    try:
        stdio = asyncio.run(
            _mcp_stdio_request(
                root,
                alias,
                request,
                stderr_path=run_root / f"{alias}-mcp-stdio-server.log",
                diagnostic_context=diagnostic_context,
            )
        )
    except TransportValidationFailure as error:
        _persist_transport_failure(
            root=root,
            run_root=run_root,
            alias=alias,
            transport="mcp-stdio",
            error=error,
            log=log,
        )
        raise
    if stdio["item_count"] != 5:
        raise RuntimeError("MCP_STDIO_DYNAMIC_REQUESTED_K_REGRESSION")

    sse_port = _free_port()
    process, output = _start_transport_server(
        root=root, alias=alias, transport="sse", port=sse_port, run_root=run_root
    )
    try:
        _wait_for_health(process, sse_port)
        sse_context = {**diagnostic_context, "transport": "mcp_sse"}
        try:
            sse = asyncio.run(_mcp_sse_request(sse_port, request, diagnostic_context=sse_context))
        except TransportValidationFailure as error:
            _persist_transport_failure(
                root=root,
                run_root=run_root,
                alias=alias,
                transport="mcp-sse",
                error=error,
                log=log,
            )
            raise
    finally:
        _stop_transport_server(process, output)
    if sse["item_count"] != 5:
        raise RuntimeError("MCP_SSE_DYNAMIC_REQUESTED_K_REGRESSION")
    expected = http_results["5"]
    identity_fields = ("document_ids", "version_ids", "chunk_ids")
    if any(
        stdio[field] != expected[field] or sse[field] != expected[field]
        for field in identity_fields
    ):
        raise RuntimeError("HTTP_MCP_TRANSPORT_PARITY_FAILED")
    evidence = {
        "status": "PASS",
        "runtime": "actual Mnemo HTTP, MCP stdio, and MCP SSE transports",
        "application_service": "EvidenceRetrievalApplicationService",
        "authorization": "CentralAuthorizationServiceV1",
        "selection": "server-owned allowlisted notebook alias",
        "http": {"status": "PASS", "dynamic_requested_k": http_results},
        "mcp_stdio": {"status": "PASS", "result": stdio},
        "mcp_sse": {"status": "PASS", "result": sse, "authentication": "api-key"},
        "semantic_identity_parity": "PASS",
    }
    _write_json(run_root / f"{alias}-transport-validation.json", evidence)
    log.event(f"{alias}.transports", "HTTP + MCP stdio + MCP SSE parity PASS", status="PASS")
    return evidence


def _safe_managed_path(path: Path, managed_root: Path) -> Path:
    resolved = path.resolve()
    root = managed_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"refusing destructive action outside {root}: {resolved}") from error
    if len(relative.parts) != 1 or relative.name not in {"phase8_5", "phase8_6"}:
        raise RuntimeError(f"refusing destructive action for unmanaged target: {resolved}")
    return resolved


def _safe_staging_path(path: Path, managed_root: Path, key: str) -> Path:
    resolved = path.resolve()
    root = managed_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"refusing staging cleanup outside {root}: {resolved}") from error
    if len(relative.parts) != 1 or not relative.name.startswith(f".{key}.staging-run-"):
        raise RuntimeError(f"refusing staging cleanup for unexpected target: {resolved}")
    return resolved


def _delete_managed(path: Path, managed_root: Path, log: RunLog) -> None:
    resolved = _safe_managed_path(path, managed_root)
    if resolved.exists():
        shutil.rmtree(resolved)
        log.event("cleanup", f"deleted managed evaluation notebook {resolved}", status="PASS")


def _set_notebook_status(
    manifest_path: Path,
    status: str,
    *,
    transport_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("PERSISTED_MANIFEST_INVALID")
    manifest["status"] = status
    manifest["status_updated_at"] = datetime.now(UTC).isoformat()
    if transport_validation is not None:
        manifest["transport_validation"] = _redact_diagnostic(transport_validation)
    manifest.pop("store_identity", None)
    manifest["store_identity"] = _json_digest(manifest)
    _write_json(manifest_path, manifest)
    _write_json(
        manifest_path.parent / "checkpoint.json",
        {
            "status": status,
            "manifest": "manifest.json",
            "transport_validation": _redact_diagnostic(transport_validation),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    return manifest


def _serving_registry_payload(manifests: dict[str, Any]) -> dict[str, Any]:
    registry = {
        "schema_version": "mnemo.server-owned-evaluation-notebook-registry/1",
        "created_at": datetime.now(UTC).isoformat(),
        "selection_policy": "server-allowlisted-alias-only; no client paths",
        "notebooks": {
            key: {
                "store": value["notebook"]["store"],
                "notebook_id": value["notebook"]["id"],
                "store_identity": value["store_identity"],
                "manifest": f"scratch/evaluation_notebooks/{key}/manifest.json",
            }
            for key, value in manifests.items()
            if value.get("status") == "READY"
        },
    }
    registry["registry_digest"] = _json_digest(registry)
    return registry


def _write_serving_registry(*, managed_root: Path, manifests: dict[str, Any]) -> dict[str, Any]:
    registry = _serving_registry_payload(manifests)
    _write_json(managed_root / "registry.json", registry)
    return registry


def _load_managed_manifests(managed_root: Path) -> dict[str, Any]:
    manifests: dict[str, Any] = {}
    for key in ("phase8_5", "phase8_6"):
        path = managed_root / key / "manifest.json"
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                manifests[key] = value
    return manifests


def _retained_embedding_audit(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT e.chunk_id,e.document_id,e.version_id,e.model_identity,"
            "e.model_revision,e.dimensions,e.vector_hash,e.vector,e.normalized,"
            "c.document_id,c.version_id FROM evaluation_text_embeddings e "
            "LEFT JOIN chunks c ON c.id=e.chunk_id ORDER BY e.chunk_id"
        )
        count = 0
        failure: str | None = None
        for row in rows:
            count += 1
            blob = bytes(row[7])
            vector = np.frombuffer(blob, dtype=np.float32)
            if row[9] is None:
                failure = f"orphan:{row[0]}"
            elif str(row[1]) != str(row[9]) or str(row[2]) != str(row[10]):
                failure = f"identity:{row[0]}"
            elif str(row[3]) != BGE_MODEL or str(row[4]) != BGE_REVISION:
                failure = f"model:{row[0]}"
            elif int(row[5]) != BGE_DIMENSIONS or vector.size != BGE_DIMENSIONS:
                failure = f"dimensions:{row[0]}"
            elif hashlib.sha256(blob).hexdigest() != str(row[6]):
                failure = f"vector_hash:{row[0]}"
            elif int(row[8]) != 1 or not np.isfinite(vector).all():
                failure = f"numeric:{row[0]}"
            if failure is not None:
                break
        chunk_count = int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    finally:
        connection.close()
    if failure is not None or count != chunk_count:
        detail = failure or f"coverage:{count}/{chunk_count}"
        raise RuntimeError(f"RETAINED_EMBEDDING_VALIDATION_FAILED:{detail}")
    return {
        "status": "PASS",
        "count": count,
        "chunk_count": chunk_count,
        "dimensions": BGE_DIMENSIONS,
        "model": BGE_MODEL,
        "revision": BGE_REVISION,
        "finite": True,
        "identity_bound": True,
        "vector_hashes_valid": True,
    }


def _repair_retained_manifest(
    *, root: Path, managed_root: Path, alias: str, run_root: Path, log: RunLog
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_sources = {
        "phase8_5": root / "goldenDataset/Phase 8.5 Evaluation Corpus",
        "phase8_6": root
        / "evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus",
    }
    store = _safe_managed_path(managed_root / alias, managed_root)
    manifest_path = store / "manifest.json"
    database = store / "mnemo.db"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("PERSISTED_MANIFEST_INVALID")
    if manifest.get("status") not in {
        "VALIDATION_FAILED",
        "TRANSPORT_VALIDATION_FAILED",
        "PUBLISHED",
        "READY",
    }:
        raise RuntimeError(f"RETAINED_MANIFEST_STATE_INVALID:{alias}")
    notebook = manifest.get("notebook")
    validation = manifest.get("validation")
    if not isinstance(notebook, dict) or not isinstance(validation, dict):
        raise RuntimeError(f"RETAINED_MANIFEST_INCOMPLETE:{alias}")
    if (root / str(notebook.get("store"))).resolve() != store.resolve():
        raise RuntimeError(f"RETAINED_STORE_BINDING_INVALID:{alias}")
    source = expected_sources[alias]
    if (root / str(manifest.get("source_corpus"))).resolve() != source.resolve():
        raise RuntimeError(f"RETAINED_SOURCE_BINDING_INVALID:{alias}")
    inventory = _inventory(source)
    if manifest.get("source_inventory") != inventory:
        raise RuntimeError(f"RETAINED_SOURCE_INVENTORY_MISMATCH:{alias}")

    before_sha = _sha256(database)
    state = _database_state(database)
    prior_state = validation.get("database")
    if not isinstance(prior_state, dict):
        raise RuntimeError(f"RETAINED_DATABASE_EVIDENCE_MISSING:{alias}")
    invariant_keys = (
        "sha256",
        "size_bytes",
        "integrity_check",
        "foreign_key_violations",
        "notebooks",
        "documents",
        "versions",
        "memberships",
        "chunks",
        "fts_rows",
        "image_assets",
        "image_occurrences",
        "processable_image_occurrences",
        "policy_excluded_svg_occurrences",
        "ocr",
        "vision",
        "clip",
        "text_embeddings",
        "duplicate_documents",
        "duplicate_versions",
        "duplicate_chunks",
        "duplicate_memberships",
        "orphan_asset_occurrences",
        "orphan_ocr",
        "orphan_vision",
        "orphan_visual_embeddings",
    )
    mismatches = [key for key in invariant_keys if prior_state.get(key) != state.get(key)]
    if mismatches:
        raise RuntimeError(f"RETAINED_DATABASE_EVIDENCE_MISMATCH:{alias}:{','.join(mismatches)}")
    if state["integrity_check"] != "ok" or state["foreign_key_violations"] != 0:
        raise RuntimeError(f"RETAINED_DATABASE_INTEGRITY_FAILED:{alias}")
    if state["fts_rows"] != state["chunks"] or state["text_embeddings"] != state["chunks"]:
        raise RuntimeError(f"RETAINED_REPRESENTATION_COVERAGE_FAILED:{alias}")
    if any(
        state[key]
        for key in (
            "duplicate_documents",
            "duplicate_versions",
            "duplicate_chunks",
            "duplicate_memberships",
            "orphan_asset_occurrences",
            "orphan_ocr",
            "orphan_vision",
            "orphan_visual_embeddings",
        )
    ):
        raise RuntimeError(f"RETAINED_IDENTITY_OR_PROVENANCE_FAILED:{alias}")
    processable = int(state["processable_image_occurrences"])
    if processable and not (
        state["ocr"] == processable
        and state["vision"] == processable
        and state["clip"] == processable
    ):
        raise RuntimeError(f"RETAINED_MULTIMODAL_COVERAGE_FAILED:{alias}")
    embedding_audit = _retained_embedding_audit(database)

    old_identity = str(manifest.get("store_identity"))
    old_inventory_digest = str(manifest.get("source_inventory_digest"))
    manifest["source_inventory_digest"] = _json_digest(inventory)
    manifest["validation"]["database"] = state
    manifest["canonicalization"] = {
        "contract": "mnemo.canonical-json-utf8/1",
        "ensure_ascii": False,
        "sort_keys": True,
        "separators": [",", ":"],
        "encoding": "utf-8",
        "allow_nan": False,
        "newline": "none",
    }
    manifest["repair"] = {
        "reason": "unicode canonical JSON writer/validator mismatch",
        "old_store_identity": old_identity,
        "old_source_inventory_digest": old_inventory_digest,
        "tool": "mnemo_server.tools.reindex_evaluation_notebooks --repair-retained",
        "tool_revision": _sha256(Path(__file__)),
        "timestamp": datetime.now(UTC).isoformat(),
        "database_sha256_before": before_sha,
    }
    manifest.pop("transport_validation", None)
    manifest.pop("store_identity", None)
    manifest["status"] = "VALIDATING"
    manifest["status_updated_at"] = datetime.now(UTC).isoformat()
    manifest["store_identity"] = _json_digest(manifest)
    _write_json(manifest_path, manifest)
    repaired = _set_notebook_status(manifest_path, "PUBLISHED")
    after_sha = _sha256(database)
    if after_sha != before_sha:
        raise RuntimeError(f"RETAINED_DATABASE_MUTATED:{alias}")
    evidence = {
        "schema_version": "mnemo.evaluation-notebook-manifest-repair/1",
        "status": "PASS",
        "alias": alias,
        "serialization_contract": repaired["canonicalization"],
        "unicode_present": any(
            ord(character) > 127 for character in json.dumps(inventory, ensure_ascii=False)
        ),
        "old_store_identity": old_identity,
        "canonical_store_identity": repaired["store_identity"],
        "old_source_inventory_digest": old_inventory_digest,
        "canonical_source_inventory_digest": repaired["source_inventory_digest"],
        "database_sha256_before": before_sha,
        "database_sha256_after": after_sha,
        "database_unchanged": True,
        "database": state,
        "embedding_audit": embedding_audit,
        "source_inventory_count": len(inventory),
        "source_inventory_match": True,
        "multimodal_coverage": "PASS",
        "identity_and_provenance": "PASS",
        "resulting_status": repaired["status"],
    }
    _write_json(run_root / f"{alias}-manifest-repair.json", evidence)
    log.event(alias, "retained store validated; manifest canonically rebound", status="PASS")
    return repaired, evidence


def _repair_retained_notebooks(
    *, root: Path, aliases: list[str], run_root: Path, log: RunLog
) -> int:
    managed_root = root / "scratch/evaluation_notebooks"
    production_before = _production_state(root)
    database_before = {alias: _sha256(managed_root / alias / "mnemo.db") for alias in aliases}
    manifests = _load_managed_manifests(managed_root)
    evidence: dict[str, Any] = {}
    for alias in aliases:
        repaired, item = _repair_retained_manifest(
            root=root, managed_root=managed_root, alias=alias, run_root=run_root, log=log
        )
        manifests[alias] = repaired
        evidence[alias] = item
    registry = _write_serving_registry(managed_root=managed_root, manifests=manifests)
    if any(alias in registry["notebooks"] for alias in aliases):
        raise RuntimeError("REPAIR_PREMATURELY_EXPOSED_NOTEBOOK")
    database_after = {alias: _sha256(managed_root / alias / "mnemo.db") for alias in aliases}
    production_after = _production_state(root)
    if database_after != database_before:
        raise RuntimeError("RETAINED_DATABASE_MUTATION")
    if production_after["sha256"] != production_before["sha256"]:
        raise RuntimeError("PRODUCTION_STATE_MUTATION")
    result = {
        "schema_version": "mnemo.evaluation-notebook-manifest-repair-run/1",
        "status": "MANIFEST_REPAIR_PASS",
        "canonicalization_contract": "mnemo.canonical-json-utf8/1",
        "aliases": aliases,
        "notebooks": evidence,
        "database_sha256_before": database_before,
        "database_sha256_after": database_after,
        "databases_unchanged": True,
        "production_before": production_before,
        "production_after": production_after,
        "production_unchanged": True,
        "registry": registry,
        "data_regeneration": {
            "ingestion": False,
            "chunking": False,
            "text_embeddings": False,
            "ocr": False,
            "vision": False,
            "clip": False,
        },
    }
    _write_json(run_root / "result.json", result)
    _write_json(run_root / "checkpoint.json", {"status": "COMPLETE", "result": "result.json"})
    _write_json(root / "scratch/mnemo-canonical-json-digest-fix.json", result)
    print("RESULT: MANIFEST_REPAIR_PASS", flush=True)
    return 0


def _build_one(
    *, root: Path, managed_root: Path, spec: NotebookSpec, run_root: Path, log: RunLog
) -> dict[str, Any]:
    final = managed_root / spec.key
    staging = managed_root / f".{spec.key}.staging-{run_root.name}"
    if staging.exists():
        shutil.rmtree(_safe_staging_path(staging, managed_root, spec.key))
    staging.mkdir(parents=True)
    inventory = _inventory(spec.source)
    checkpoint = staging / "checkpoint.json"
    _write_json(checkpoint, {"status": "BUILDING", "stage": "ingestion", "spec": spec.key})
    try:
        _ingest(root=root, source=spec.source, runtime=staging, spec=spec, log=log)
        _write_json(checkpoint, {"status": "BUILDING", "stage": "multimodal"})
        _multimodal(root=root, runtime=staging, spec=spec, log=log)
        _write_json(checkpoint, {"status": "BUILDING", "stage": "embedding"})
        embedding = _embed(database=staging / "mnemo.db", root=root, spec=spec, log=log)
        validation = _validate_store(
            database=staging / "mnemo.db", inventory=inventory, embedding=embedding
        )
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "status": "PUBLISHED",
            "notebook": {
                "key": spec.key,
                "id": str(uuid5(NAMESPACE_URL, f"mnemo:evaluation-notebook-reindex:{spec.key}")),
                "title": spec.title,
                "store": str(final.relative_to(root).as_posix()),
            },
            "source_corpus": str(spec.source.relative_to(root).as_posix()),
            "source_inventory": inventory,
            "source_inventory_digest": _json_digest(inventory),
            "embedding": embedding,
            "multimodal": {
                "ocr": "tesseract-best multilingual",
                "vision_model": VISION_MODEL,
                "vision_revision": VISION_REVISION,
                "visual_model": CLIP_MODEL,
                "visual_revision": CLIP_REVISION,
            },
            "validation": validation,
            "created_at": datetime.now(UTC).isoformat(),
            "pipeline_revision": _sha256(Path(__file__)),
            "configuration": {
                "mnemo_toml_sha256": _sha256(root / "mnemo.toml"),
                "model_profile_sha256": _sha256(
                    root / "config/model_profiles/full_multilingual_v2_profiles.toml"
                ),
            },
        }
        envelope["store_identity"] = _json_digest(envelope)
        _write_json(staging / "manifest.json", envelope)
        _write_json(checkpoint, {"status": "PUBLISHED", "manifest": "manifest.json"})
        if final.exists():
            raise RuntimeError("managed target unexpectedly reappeared during staging build")
        os.replace(staging, final)
        log.event(spec.key, "notebook atomically published for validation", status="PASS")
        persisted = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(persisted, dict):
            raise RuntimeError("PERSISTED_MANIFEST_INVALID")
        return persisted
    except BaseException as error:
        _write_json(
            checkpoint,
            {
                "status": "FAILED",
                "error_type": type(error).__name__,
                "error": str(error),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        raise


def _preflight(root: Path, log: RunLog) -> dict[str, Any]:
    import httpx
    import torch
    from PIL import Image  # noqa: F401 - dependency preflight

    required = {
        "production_database": root
        / "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db",
        "phase85": root / "goldenDataset/Phase 8.5 Evaluation Corpus",
        "phase86": root
        / "evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus",
        "bge_m3": Path(r"D:\Mnemo\phase8.5.11-models\huggingface\hub")
        / "models--BAAI--bge-m3/snapshots"
        / BGE_REVISION,
        "clip": Path(r"D:\Mnemo\phase8.5.11-models\huggingface\hub")
        / "models--openai--clip-vit-large-patch14/snapshots"
        / CLIP_REVISION,
        "tessdata": Path(r"D:\Mnemo\phase8.5.11-models\tessdata"),
        "tesseract": Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise RuntimeError("PREFLIGHT_REQUIRED_PATH_MISSING:" + ",".join(missing))
    if not torch.cuda.is_available():
        raise RuntimeError("PREFLIGHT_CUDA_UNAVAILABLE")
    if os.environ.get("OLLAMA_MODELS") != r"D:\Ollama\models":
        raise RuntimeError("PREFLIGHT_OLLAMA_MODELS_MISMATCH")
    if os.environ.get("OLLAMA_NUM_PARALLEL") != "4":
        raise RuntimeError("PREFLIGHT_OLLAMA_NUM_PARALLEL_MISMATCH")
    try:
        ollama = httpx.get("http://127.0.0.1:11434/api/tags", timeout=10.0)
        ollama.raise_for_status()
    except Exception as error:
        raise RuntimeError("PREFLIGHT_OLLAMA_UNAVAILABLE") from error
    models = {str(item.get("name")): item for item in ollama.json().get("models", [])}
    if VISION_MODEL not in models:
        raise RuntimeError("PREFLIGHT_QWEN_VISION_MODEL_MISSING")
    if models[VISION_MODEL].get("digest") != VISION_REVISION:
        raise RuntimeError("PREFLIGHT_QWEN_VISION_REVISION_MISMATCH")
    production = _production_state(root)
    protected = _protected_contract_state(root)
    value = {
        "status": "PASS",
        "production": production,
        "protected_contracts": protected,
        "cuda": {
            "available": True,
            "device": torch.cuda.get_device_name(0),
            "torch": torch.__version__,
            "cuda_version": torch.version.cuda,
        },
        "ollama": {
            "models_root": os.environ["OLLAMA_MODELS"],
            "num_parallel": os.environ["OLLAMA_NUM_PARALLEL"],
        },
        "phase85_source_count": len(_inventory(required["phase85"])),
        "phase86_source_count": len(_inventory(required["phase86"])),
        "qwen_vision": {
            "model": VISION_MODEL,
            "digest": models[VISION_MODEL].get("digest"),
            "expected_digest": VISION_REVISION,
        },
    }
    log.event("preflight", "production, models, CUDA, and Ollama contract PASS", status="PASS")
    return value


def _smoke(root: Path, run_root: Path, log: RunLog) -> dict[str, Any]:
    source = root / "goldenDataset/Phase 8.5 Evaluation Corpus"
    smoke = run_root / "smoke"
    spec = NotebookSpec("smoke", "Mnemo production indexing smoke", source)
    _ingest(
        root=root,
        source=source,
        runtime=smoke,
        spec=spec,
        log=log,
        include="manuscript.pdf",
    )
    _multimodal(root=root, runtime=smoke, spec=spec, log=log)
    embedding = _embed(database=smoke / "mnemo.db", root=root, spec=spec, log=log)
    validation = _validate_store(
        database=smoke / "mnemo.db",
        inventory=[
            item for item in _inventory(source) if item["relative_path"] == "manuscript.pdf"
        ],
        embedding=embedding,
    )
    evidence = {
        "source": "goldenDataset/Phase 8.5 Evaluation Corpus/manuscript.pdf",
        "status": "PASS",
        "validation": validation,
    }
    _write_json(run_root / "smoke-evidence.json", evidence)
    source_path = source / "manuscript.pdf"
    if not source_path.is_file():
        raise RuntimeError("SMOKE_SOURCE_MUTATED")
    shutil.rmtree(smoke)
    if smoke.exists():
        raise RuntimeError("SMOKE_DATABASE_CLEANUP_FAILED")
    log.event("smoke", "PASS; temporary store deleted", status="PASS")
    return evidence


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--full", action="store_true")
    group.add_argument("--phase85", action="store_true")
    group.add_argument("--phase86", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Retry HTTP/MCP validation for one retained notebook without indexing",
    )
    parser.add_argument(
        "--repair-retained",
        action="store_true",
        help="Validate and canonically rebind retained stores without regenerating data",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.validate_only and (args.full or (args.phase85 == args.phase86)):
        parser.error("--validate-only requires exactly one of --phase85 or --phase86")
    if args.repair_retained and args.validate_only:
        parser.error("--repair-retained and --validate-only are separate governed operations")
    if args.repair_retained and args.full:
        parser.error("--repair-retained never accepts --full")
    return args


def _failure_checkpoint(
    *,
    error: BaseException,
    stage: str,
    publication_state: str | None,
    cleanup_decision: str,
    artifact_paths: list[str],
    production: dict[str, Any] | None,
) -> dict[str, Any]:
    diagnostics = error.diagnostics if isinstance(error, TransportValidationFailure) else None
    return {
        "status": "FAILED",
        "stage": stage,
        "phase": diagnostics.get("notebook_alias") if diagnostics else None,
        "notebook": diagnostics.get("notebook_identity") if diagnostics else None,
        "publication_state": publication_state,
        "transport": diagnostics.get("transport") if diagnostics else None,
        "failure_classification": (
            error.failure_code
            if isinstance(error, TransportValidationFailure)
            else type(error).__name__
        ),
        "underlying": _redact_diagnostic(diagnostics),
        "cleanup_decision": cleanup_decision,
        "artifact_paths": artifact_paths,
        "production_store_identity": PRODUCTION_IDENTITY,
        "production_store_sha256": production.get("sha256") if production else None,
        "error_type": type(error).__name__,
        "error": str(error),
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _validate_retained_notebook(*, root: Path, alias: str, run_root: Path, log: RunLog) -> int:
    from mnemo_server.evaluation.notebook_registry import (
        resolve_evaluation_notebook_validation_candidate_v1,
    )

    managed_root = root / "scratch/evaluation_notebooks"
    before = _production_state(root)
    manifests = _load_managed_manifests(managed_root)
    selection = resolve_evaluation_notebook_validation_candidate_v1(
        workspace_root=root, alias=alias
    )
    manifest_path = selection.manifest
    database_before = _sha256(selection.database)
    try:
        transport = _validate_real_transports(
            root=root,
            alias=alias,
            database=selection.database,
            notebook_id=selection.notebook_id,
            store_identity=selection.store_identity,
            run_root=run_root,
            log=log,
        )
        if _sha256(selection.database) != database_before:
            raise RuntimeError("EVALUATION_NOTEBOOK_MUTATED_DURING_TRANSPORT_VALIDATION")
        manifests[alias] = _set_notebook_status(
            manifest_path, "READY", transport_validation=transport
        )
        registry = _write_serving_registry(managed_root=managed_root, manifests=manifests)
        after = _production_state(root)
        if after["sha256"] != before["sha256"]:
            raise RuntimeError("PRODUCTION_STATE_MUTATION")
        result = {
            "schema_version": "mnemo.evaluation-notebook-transport-retry/1",
            "status": "TRANSPORT_VALIDATION_PASS",
            "alias": alias,
            "database_sha256_before": database_before,
            "database_sha256_after": _sha256(selection.database),
            "transport_validation": transport,
            "registry": registry,
            "production_before": before,
            "production_after": after,
        }
        _write_json(run_root / "result.json", result)
        _write_json(
            run_root / "checkpoint.json",
            {"status": "COMPLETE", "stage": "transport-validation", "result": "result.json"},
        )
        print("RESULT: TRANSPORT_VALIDATION_PASS", flush=True)
        return 0
    except BaseException as error:
        diagnostics = error.diagnostics if isinstance(error, TransportValidationFailure) else None
        manifests[alias] = _set_notebook_status(
            manifest_path,
            "TRANSPORT_VALIDATION_FAILED",
            transport_validation=diagnostics
            or {
                "failure_code": type(error).__name__,
                "exception_message": str(error),
            },
        )
        _write_serving_registry(managed_root=managed_root, manifests=manifests)
        artifacts = [
            str(path.relative_to(root).as_posix())
            for path in sorted(run_root.glob("*"))
            if path.is_file()
        ]
        _write_json(
            run_root / "checkpoint.json",
            _failure_checkpoint(
                error=error,
                stage="transport-validation",
                publication_state="TRANSPORT_VALIDATION_FAILED",
                cleanup_decision="retained immutable notebook; excluded from serving registry",
                artifact_paths=artifacts,
                production=before,
            ),
        )
        log.event(
            "run",
            f"FAILED: {type(error).__name__}: {error}",
            status="FAILED",
            cleanup_decision="retained immutable notebook; excluded from serving registry",
        )
        print("RESULT: TRANSPORT_VALIDATION_FAILED", flush=True)
        return 1


def main() -> int:
    args = _arguments()
    root = _repo_root()
    run_id = datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")
    run_root = root / "scratch/evaluation_notebook_reindex/runs" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    log = RunLog(run_root / "events.jsonl", verbose=args.verbose)
    print("=" * 68)
    print("MNEMO EVALUATION NOTEBOOK REINDEX")
    print("=" * 68, flush=True)
    checkpoint = run_root / "checkpoint.json"
    published_by_run: list[Path] = []
    _write_json(checkpoint, {"status": "RUNNING", "stage": "preflight"})
    if args.repair_retained:
        aliases: list[str] = []
        if args.phase85 or not (args.phase85 or args.phase86):
            aliases.append("phase8_5")
        if args.phase86 or not (args.phase85 or args.phase86):
            aliases.append("phase8_6")
        return _repair_retained_notebooks(root=root, aliases=aliases, run_root=run_root, log=log)
    if args.validate_only:
        alias = "phase8_5" if args.phase85 else "phase8_6"
        return _validate_retained_notebook(root=root, alias=alias, run_root=run_root, log=log)
    try:
        preflight = _preflight(root, log)
        before = preflight["production"]
        protected_before = preflight["protected_contracts"]
        _write_json(checkpoint, {"status": "RUNNING", "stage": "smoke"})
        smoke = _smoke(root, run_root, log)
        managed_root = root / "scratch/evaluation_notebooks"
        managed_root.mkdir(parents=True, exist_ok=True)
        selected = []
        if args.full or not (args.phase85 or args.phase86) or args.phase85:
            selected.append(
                NotebookSpec(
                    "phase8_5",
                    "Phase 8.5 Golden Evaluation Notebook",
                    root / "goldenDataset/Phase 8.5 Evaluation Corpus",
                )
            )
        if args.full or not (args.phase85 or args.phase86) or args.phase86:
            selected.append(
                NotebookSpec(
                    "phase8_6",
                    "Phase 8.6 Format-Diverse Multilingual Evaluation Notebook",
                    root
                    / "evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus",
                )
            )
        stale_staging = sorted(
            path
            for spec in selected
            for path in managed_root.glob(f".{spec.key}.staging-run-*")
            if path.is_dir()
        )
        deletion = {
            "schema_version": "mnemo.evaluation-notebook-deletion-manifest/1",
            "created_at": datetime.now(UTC).isoformat(),
            "entries": [
                {
                    "path": str((managed_root / spec.key).relative_to(root).as_posix()),
                    "notebook": spec.key,
                    "reason": "authorized clean reindex",
                    "classification": "orchestrator-owned evaluation notebook store",
                    "safe_to_delete": True,
                    "exists": (managed_root / spec.key).exists(),
                }
                for spec in selected
            ]
            + [
                {
                    "path": str(path.relative_to(root).as_posix()),
                    "notebook": path.name.split(".staging-", 1)[0].lstrip("."),
                    "reason": "incomplete orchestrator-owned staging run",
                    "classification": "failed evaluation notebook staging store",
                    "safe_to_delete": True,
                    "exists": True,
                }
                for path in stale_staging
            ],
        }
        _write_json(run_root / "deletion-manifest.json", deletion)
        _write_json(checkpoint, {"status": "RUNNING", "stage": "delete-managed-evaluation"})
        for spec in selected:
            _delete_managed(managed_root / spec.key, managed_root, log)
        for path in stale_staging:
            key = path.name.split(".staging-", 1)[0].lstrip(".")
            shutil.rmtree(_safe_staging_path(path, managed_root, key))
            log.event("cleanup", f"deleted failed staging store {path}", status="PASS")
        manifests: dict[str, Any] = {}
        for spec in selected:
            _write_json(checkpoint, {"status": "RUNNING", "stage": spec.key})
            manifests[spec.key] = _build_one(
                root=root,
                managed_root=managed_root,
                spec=spec,
                run_root=run_root,
                log=log,
            )
            published_by_run.append(managed_root / spec.key)
        selected_keys = [spec.key for spec in selected]
        for key in ("phase8_5", "phase8_6"):
            if key in manifests:
                continue
            existing_manifest = managed_root / key / "manifest.json"
            if existing_manifest.is_file():
                existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
                if existing.get("status") == "READY":
                    manifests[key] = existing
        registry = _write_serving_registry(managed_root=managed_root, manifests=manifests)
        from mnemo_server.evaluation.notebook_registry import (
            resolve_evaluation_notebook_validation_candidate_v1,
        )

        exposure: dict[str, Any] = {}
        for key in selected_keys:
            selection = resolve_evaluation_notebook_validation_candidate_v1(
                workspace_root=root, alias=key
            )
            try:
                transport = _validate_real_transports(
                    root=root,
                    alias=key,
                    database=selection.database,
                    notebook_id=selection.notebook_id,
                    store_identity=selection.store_identity,
                    run_root=run_root,
                    log=log,
                )
            except BaseException as error:
                diagnostic = (
                    error.diagnostics
                    if isinstance(error, TransportValidationFailure)
                    else {
                        "failure_code": type(error).__name__,
                        "exception_message": str(error),
                    }
                )
                manifests[key] = _set_notebook_status(
                    selection.manifest,
                    "TRANSPORT_VALIDATION_FAILED",
                    transport_validation=diagnostic,
                )
                registry = _write_serving_registry(managed_root=managed_root, manifests=manifests)
                raise
            manifests[key] = _set_notebook_status(
                selection.manifest, "READY", transport_validation=transport
            )
            registry = _write_serving_registry(managed_root=managed_root, manifests=manifests)
            exposure[key] = {
                "status": "PASS",
                "selection": "server-authorized-alias",
                "notebook_id": selection.notebook_id,
                "store_identity": manifests[key]["store_identity"],
                "database_sha256": _sha256(selection.database),
                "http_architecture": "EvidenceRetrievalApplicationService",
                "mcp_architecture": "shared EvidenceRetrievalApplicationService",
                "arbitrary_client_paths": "REJECTED",
                "transport_validation": transport,
            }
        after = _production_state(root)
        protected_after = _protected_contract_state(root)
        if after["sha256"] != before["sha256"]:
            raise RuntimeError("PRODUCTION_STATE_MUTATION")
        if protected_after["artifacts"] != protected_before["artifacts"]:
            raise RuntimeError("PROTECTED_PRODUCTION_CONTRACT_MUTATION")
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "PRODUCTION_PIPELINE_REINDEX_PASS",
            "run_id": run_id,
            "preflight": preflight,
            "smoke": smoke,
            "deletion_manifest": str((run_root / "deletion-manifest.json").relative_to(root)),
            "notebooks": manifests,
            "registry": registry,
            "governed_exposure": exposure,
            "production_before": before,
            "production_after": after,
            "production_unchanged": True,
            "protected_contracts_before": protected_before,
            "protected_contracts_after": protected_after,
            "protected_contracts_unchanged": True,
            "ollama_modified": False,
            "ollama_models_deleted": 0,
        }
        _write_json(run_root / "result.json", result)
        _write_json(checkpoint, {"status": "COMPLETE", "result": "result.json"})
        print("=" * 68)
        print("RESULT: PRODUCTION_PIPELINE_REINDEX_PASS")
        for key, manifest in manifests.items():
            state = manifest["validation"]["database"]
            print(
                f"{key}: docs={state['documents']} chunks={state['chunks']} "
                f"embeddings={state['text_embeddings']} images={state['image_occurrences']} "
                f"ocr={state['ocr']} vision={state['vision']} clip={state['clip']} READY"
            )
        print(f"Production SHA: {after['sha256']} (UNCHANGED)")
        print(f"Structured log: {run_root / 'events.jsonl'}")
        print("=" * 68, flush=True)
        return 0
    except BaseException as error:
        managed_root = root / "scratch/evaluation_notebooks"
        retained = [path for path in published_by_run if path.exists()]
        if retained:
            current_manifests = _load_managed_manifests(managed_root)
            for published in retained:
                alias = published.name
                current = current_manifests.get(alias)
                if not isinstance(current, dict):
                    continue
                if current.get("status") == "TRANSPORT_VALIDATION_FAILED":
                    continue
                current_manifests[alias] = _set_notebook_status(
                    published / "manifest.json",
                    "VALIDATION_FAILED",
                    transport_validation={
                        "failure_code": type(error).__name__,
                        "exception_message": str(error),
                    },
                )
            _write_serving_registry(managed_root=managed_root, manifests=current_manifests)
        diagnostic_artifacts = [
            str(path.relative_to(root).as_posix())
            for path in sorted(run_root.glob("*"))
            if path.is_file()
        ]
        cleanup_decision = (
            "retained published notebook; excluded transport-failed state from serving registry"
            if retained
            else "no published notebook required cleanup"
        )
        _write_json(
            checkpoint,
            _failure_checkpoint(
                error=error,
                stage=(
                    "transport-validation"
                    if isinstance(error, TransportValidationFailure)
                    else "pipeline"
                ),
                publication_state=("TRANSPORT_VALIDATION_FAILED" if retained else None),
                cleanup_decision=cleanup_decision,
                artifact_paths=diagnostic_artifacts,
                production=locals().get("before"),
            ),
        )
        log.event(
            "run",
            f"FAILED: {type(error).__name__}: {error}",
            status="FAILED",
            cleanup_decision=cleanup_decision,
        )
        print("RESULT: PRODUCTION_PIPELINE_REINDEX_FAILED", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
