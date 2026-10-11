"""Guarded isolated rebuild from immutable corpus bytes into a fresh notebook."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from mnemo.phase85.profiles import ModelProfileDocument

from mnemo_server.tools.isolated_activation import (
    REQUIRED,
    activate_isolated_generation_set,
)
from mnemo_server.tools.source_manifest import verify_source_manifest


@dataclass(frozen=True, slots=True)
class VerifiedSource:
    relative_path: str
    sha256: str
    byte_size: int
    prior_document_id: str | None
    prior_version_id: str | None


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _embedding_model_identity(workspace: Path) -> str:
    component = (
        ModelProfileDocument.from_file(
            workspace / "config/model_profiles/full_multilingual_v2_profiles.toml"
        )
        .select("full_multilingual_v2_local_prebuild")
        .models["multilingual_embedding"]
    )
    return f"{component.model}@{component.revision}"


def _progress(message: str) -> None:
    print(f"[{datetime.now(UTC).isoformat()}] {message}", file=sys.stderr, flush=True)


def _run_logged_command(
    command: list[str],
    *,
    workspace: Path,
    runtime: Path,
    stage: str,
    timeout_seconds: int,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Stream every child line to the terminal and a durable stage log."""
    logs = runtime / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{stage}.log"
    _progress(f"START {stage}; log={log_path}")
    timed_out = threading.Event()
    tail: deque[str] = deque(maxlen=80)
    environment = {**environment, "PYTHONUNBUFFERED": "1"}
    if stage in {"paddleocr_inference", "vision_and_visual_inference"}:
        environment["MNEMO_REBUILD_LIVE_PROGRESS"] = "1"
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n=== START {stage} {datetime.now(UTC).isoformat()} ===\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        def stop_on_timeout() -> None:
            if process.poll() is None:
                timed_out.set()
                process.kill()

        timer = threading.Timer(timeout_seconds, stop_on_timeout)
        timer.daemon = True
        timer.start()
        try:
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
                tail.append(line)
                print(f"[{stage}] {line}", end="", file=sys.stderr, flush=True)
            code = process.wait()
            log.write(f"=== END {stage} exit={code} timeout={timed_out.is_set()} ===\n")
            log.flush()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
    if timed_out.is_set():
        raise RuntimeError(f"{stage} timed out after {timeout_seconds}s; log={log_path}")
    _progress(f"{'DONE' if code == 0 else 'FAILED'} {stage}; exit={code}; log={log_path}")
    return subprocess.CompletedProcess(command, code, stdout="".join(tail)[-3000:], stderr="")


def verify_sources(
    *,
    corpus: Path,
    includes: tuple[str, ...],
    source_database: Path | None = None,
    source_manifest: Path | None = None,
) -> tuple[VerifiedSource, ...]:
    """Verify selected originals against a manifest or the legacy evaluation index."""
    corpus = corpus.resolve(strict=True)
    if (source_database is None) == (source_manifest is None):
        raise ValueError("exactly one source authority is required")
    if not includes or len(set(includes)) != len(includes):
        raise ValueError("source selection must be nonempty and unique")
    if source_manifest is not None:
        manifest = verify_source_manifest(manifest=source_manifest, corpus=corpus)
        by_path = {item["relative_path"]: item for item in manifest["sources"]}
        if not set(includes) <= set(by_path):
            raise ValueError("selected source is absent from the manifest")
        return tuple(
            VerifiedSource(
                relative_path=relative,
                sha256=by_path[relative]["sha256"],
                byte_size=by_path[relative]["byte_size"],
                prior_document_id=None,
                prior_version_id=None,
            )
            for relative in includes
        )
    assert source_database is not None
    source_database = source_database.resolve(strict=True)
    connection = sqlite3.connect(f"file:{source_database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        verified: list[VerifiedSource] = []
        for relative in includes:
            candidate = corpus / relative
            path = candidate.resolve(strict=True)
            if candidate.is_symlink() or not path.is_file() or not path.is_relative_to(corpus):
                raise ValueError("source must be a regular file inside the corpus")
            digest = _digest(path)
            rows = connection.execute(
                "SELECT document_id,current_version_id FROM documents WHERE current_hash=?",
                (digest,),
            ).fetchall()
            if len(rows) != 1:
                raise ValueError("source hash is absent or ambiguous in the evaluation index")
            verified.append(
                VerifiedSource(
                    relative_path=path.relative_to(corpus).as_posix(),
                    sha256=digest,
                    byte_size=path.stat().st_size,
                    prior_document_id=str(rows[0][0]),
                    prior_version_id=str(rows[0][1]),
                )
            )
        return tuple(verified)
    finally:
        connection.close()


def inspect_isolated_ingestion(
    *, database: Path, files: Path, notebook_id: str, sources: tuple[VerifiedSource, ...]
) -> dict[str, Any]:
    """Read-only post-ingest census; failure never authorizes activation."""
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        notebooks = connection.execute("SELECT notebook_id FROM notebooks").fetchall()
        if notebooks != [(notebook_id,)]:
            raise RuntimeError("isolated notebook identity mismatch")
        source_evidence: list[dict[str, Any]] = []
        for source in sources:
            row = connection.execute(
                "SELECT document_id,current_version_id FROM documents WHERE current_hash=?",
                (source.sha256,),
            ).fetchone()
            if row is None:
                raise RuntimeError("verified source missing after ingestion")
            document_id, version_id = str(row[0]), str(row[1])
            if source.prior_document_id is not None and (document_id, version_id) != (
                source.prior_document_id,
                source.prior_version_id,
            ):
                raise RuntimeError("source document/version identity changed unexpectedly")
            membership = connection.execute(
                "SELECT COUNT(*) FROM sources WHERE notebook_id=? AND document_id=?",
                (notebook_id, document_id),
            ).fetchone()
            if membership is None or membership[0] != 1:
                raise RuntimeError("isolated source membership is missing")
            original = connection.execute(
                "SELECT r.byte_size,a.content_hash FROM document_binary_references r "
                "JOIN asset_catalog a ON a.asset_id=r.asset_id "
                "WHERE r.version_id=? AND r.role='original'",
                (version_id,),
            ).fetchone()
            if original != (source.byte_size, source.sha256):
                raise RuntimeError("original binary reference differs from source truth")
            raw_dir = files / source.sha256[:2] / source.sha256[2:]
            raw_files = tuple(raw_dir.glob("raw.*"))
            if len(raw_files) != 1 or _digest(raw_files[0]) != source.sha256:
                raise RuntimeError("stored original bytes differ from source truth")
            ir_path = files / "parsed" / version_id[:8] / f"{version_id}.ir.json"
            parsed = json.loads(ir_path.read_text(encoding="utf-8"))
            blocks = parsed["blocks"]
            if parsed["metadata"]["content_hash"] != source.sha256 or [
                block["ordinal"] for block in blocks
            ] != list(range(len(blocks))):
                raise RuntimeError("persisted IR hash or block ordering is invalid")
            spans = connection.execute(
                "SELECT source_start_ordinal,source_end_ordinal FROM chunks "
                "WHERE version_id=? ORDER BY position_chunk_index",
                (version_id,),
            ).fetchall()
            if any(start < 0 or end < start or end >= len(blocks) for start, end in spans):
                raise RuntimeError("canonical chunk references an impossible block ordinal")
            source_evidence.append(
                {
                    "relative_path": source.relative_path,
                    "document_id": document_id,
                    "version_id": version_id,
                    "blocks": len(blocks),
                    "chunks": len(spans),
                    "original_sha256_verified": True,
                    "block_ordinals_contiguous": True,
                }
            )
        tables = (
            "documents",
            "document_versions",
            "sources",
            "chunks",
            "asset_occurrences",
            "ocr_results",
            "vision_results",
            "visual_embeddings",
            "ocr_projection_rows",
            "vision_text_projection_rows",
            "visual_vector_projection_rows",
            "multilingual_embeddings_v2",
            "active_index_generations",
        )
        available = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            if table in available
            else 0
            for table in tables
        }
        if counts["documents"] != len(sources) or counts["document_versions"] != len(sources):
            raise RuntimeError("isolated source/version count mismatch")
        return {"counts": counts, "sources": source_evidence, "database_sha256": _digest(database)}
    finally:
        connection.close()


def assess_canary_coverage(database: Path) -> dict[str, Any]:
    """Report missing governed inputs without creating or promoting generations."""
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        eligible = {
            str(row[0])
            for row in connection.execute(
                "SELECT o.occurrence_id FROM asset_occurrences o "
                "JOIN asset_catalog a ON a.asset_id=o.asset_id "
                "WHERE a.mime_type LIKE 'image/%' AND a.mime_type != 'image/svg+xml'"
            )
        }
        source_tables = {
            "ocr": "ocr_results",
            "vision": "vision_results",
            "visual": "visual_embeddings",
            "ocr_projection": "ocr_projection_rows",
            "vision_projection": "vision_text_projection_rows",
            "visual_projection": "visual_vector_projection_rows",
        }
        present = {
            name: {
                str(row[0])
                for row in connection.execute(f"SELECT DISTINCT occurrence_id FROM {table}")
            }
            for name, table in source_tables.items()
        }
        missing = {name: sorted(eligible - values) for name, values in present.items()}
        canonical_chunks = int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        multilingual_embeddings = int(
            connection.execute("SELECT COUNT(*) FROM multilingual_embeddings_v2").fetchone()[0]
        )
        generation_states = [
            {"capability": str(row[0]), "state": str(row[1]), "active": bool(row[2])}
            for row in connection.execute(
                "SELECT g.capability,g.state,a.generation_id IS NOT NULL "
                "FROM index_generations g LEFT JOIN active_index_generations a "
                "ON a.generation_id=g.generation_id ORDER BY g.capability"
            )
        ]
        blockers = [name for name, ids in missing.items() if ids]
        if canonical_chunks and multilingual_embeddings < canonical_chunks:
            blockers.append("canonical_multilingual_embeddings")
        if eligible and multilingual_embeddings < len(eligible) * 2:
            blockers.append("ocr_vision_multilingual_embeddings")
        if not generation_states:
            blockers.append("governed_generations_absent")
        if any(item["state"] != "ready" for item in generation_states):
            blockers.append("generation_not_ready")
        structural_coverage_complete = not blockers
        # Counts alone cannot certify source-version ancestry, model compatibility,
        # full multilingual coverage, or a controlled atomic promotion. Until that
        # coordinator exists, never turn this diagnostic into activation authority.
        blockers.append("governed_activation_coordinator_not_integrated")
        return {
            "expected_raster_occurrences": len(eligible),
            "present_occurrences": {name: len(values) for name, values in present.items()},
            "missing_occurrences": missing,
            "canonical_chunks": canonical_chunks,
            "multilingual_embeddings": multilingual_embeddings,
            "generations": generation_states,
            "structural_coverage_complete": structural_coverage_complete,
            "eligible_for_activation": False,
            "blockers": blockers,
        }
    finally:
        connection.close()


def run_canary(
    *,
    workspace: Path,
    corpus: Path,
    includes: tuple[str, ...],
    source_database: Path | None = None,
    source_manifest: Path | None = None,
    canonical_device: str = "cpu",
    evaluation_rebuild: bool = False,
    stream_logs: bool = False,
    rebuild_owner: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the real ingestion path in a never-reused disposable runtime."""
    workspace = workspace.resolve(strict=True)
    corpus = corpus.resolve(strict=True)
    sources = verify_sources(
        corpus=corpus,
        source_database=source_database,
        source_manifest=source_manifest,
        includes=includes,
    )
    if canonical_device not in {"cpu", "cuda"}:
        raise ValueError("canonical embedding device must be cpu or cuda")
    run_id = uuid4().hex
    notebook_key = (
        f"evaluation-rebuild:{run_id}"
        if evaluation_rebuild
        else f"isolated-rebuild-canary:{run_id}"
    )
    notebook_id = str(uuid5(NAMESPACE_URL, f"mnemo:{notebook_key}"))
    runtime = (
        workspace
        / "scratch"
        / ("two_corpus_rebuilds" if evaluation_rebuild else "isolated_rebuilds")
        / run_id
    )
    if runtime.exists():
        raise RuntimeError("isolated runtime identity collision")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(workspace / "scripts" / "phase8_5_11_ingest.py"),
        "--corpus",
        str(corpus),
        "--runtime",
        str(runtime),
        "--config",
        str(workspace / "mnemo.toml"),
        "--notebook-key",
        notebook_key,
        "--notebook-title",
        f"Evaluation rebuild {run_id}"
        if evaluation_rebuild
        else f"Isolated rebuild canary {run_id}",
        "--notebook-description",
        "Isolated governed evaluation index"
        if evaluation_rebuild
        else "Disposable, non-serving engineering warm-up",
    ]
    for source in sources:
        command.extend(("--include", source.relative_path))
    report: dict[str, Any] = {
        "schema": "mnemo.isolated-rebuild-canary/1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "notebook_id": notebook_id,
        "runtime": str(runtime),
        "sources": [asdict(source) for source in sources],
        "canonical_embedding_device": canonical_device,
        "stages": {
            "canonical_ingestion": "running",
            "paddleocr": "not_run",
            "vision": "not_run",
            "multilingual": "not_run",
            "visual": "not_run",
            "projections": "not_run",
        },
        "activation": "inactive",
    }
    if rebuild_owner is not None:
        report["rebuild_owner"] = rebuild_owner.copy()
    if rebuild_owner is not None and (
        not evaluation_rebuild or set(rebuild_owner) != {"pair_id", "label", "input_identity"}
    ):
        raise ValueError("two-corpus rebuild ownership is invalid")
    runtime.mkdir(parents=True)
    if rebuild_owner is not None:
        (runtime / "rebuild-owner.json").write_text(
            json.dumps(
                {
                    "schema": "mnemo.two-corpus-rebuild-owner/1",
                    **rebuild_owner,
                    "run_id": run_id,
                    "notebook_id": notebook_id,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    if stream_logs:
        report["log_directory"] = str(runtime / "logs")
    try:
        environment = {**os.environ, "MNEMO_EMBEDDING_DEVICE": canonical_device}
        completed = (
            _run_logged_command(
                command,
                workspace=workspace,
                runtime=runtime,
                stage="canonical_ingestion",
                timeout_seconds=max(900, len(sources) * 300),
                environment=environment,
            )
            if stream_logs
            else subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                check=False,
                timeout=max(900, len(sources) * 300),
                env=environment,
            )
        )
        report["ingestion_exit_code"] = completed.returncode
        if completed.returncode != 0:
            report["stages"]["canonical_ingestion"] = "failed"
            report["failure"] = (
                "production ingestion runner failed; inspect isolated ingestion evidence"
            )
            report["failure_detail"] = (completed.stderr or completed.stdout)[-3000:]
        else:
            if canonical_device == "cuda":
                attestation = json.loads(
                    (runtime / "ingestion-evidence.json").read_text(encoding="utf-8")
                )
                actual = attestation["configuration"].get("embedding_execution_device")
                if not isinstance(actual, str) or not actual.startswith("cuda"):
                    raise RuntimeError("canonical embedding GPU execution was not attested")
                report["canonical_execution_device"] = actual
            report["ingestion"] = inspect_isolated_ingestion(
                database=runtime / "mnemo.db",
                files=runtime / "files",
                notebook_id=notebook_id,
                sources=sources,
            )
            report["stages"]["canonical_ingestion"] = "complete"
            report["coverage"] = assess_canary_coverage(runtime / "mnemo.db")
            report["blockers"] = [
                "Approved local PaddleOCR package and exact model trees are not provisioned",
                "Vision, visual, and derived multilingual generations have not been built",
                "Complete projection/embedding coverage and governed activation remain required",
            ]
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as error:
        report["stages"]["canonical_ingestion"] = "failed"
        report["failure"] = type(error).__name__
        report["failure_detail"] = str(error)[-3000:]
    (runtime / "rebuild-status.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _run_stage(
    command: list[str],
    *,
    workspace: Path,
    stage: str,
    timeout_seconds: int = 1200,
    log_runtime: Path | None = None,
) -> None:
    environment = os.environ.copy()
    if stage == "paddleocr_inference":
        environment.update(
            PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="True",
            OMP_NUM_THREADS="1",
            PYTHONIOENCODING="utf-8",
        )
    completed = (
        _run_logged_command(
            command,
            workspace=workspace,
            runtime=log_runtime,
            stage=stage,
            timeout_seconds=timeout_seconds,
            environment=environment,
        )
        if log_runtime is not None
        else subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
            env=environment,
        )
    )
    if completed.returncode:
        tail = (completed.stderr or completed.stdout)[-3000:]
        raise RuntimeError(f"{stage} failed with exit {completed.returncode}: {tail}")


def _verify_vision_gpu(*, model: str, revision: str) -> dict[str, Any]:
    """Require the exact Ollama runner to be wholly GPU-resident after inference."""
    try:
        response = httpx.get("http://127.0.0.1:11434/api/ps", timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError("Vision GPU telemetry is unavailable") from error
    runners = response.json().get("models", [])
    matching = [
        item for item in runners if item.get("name") == model and item.get("digest") == revision
    ]
    if len(matching) != 1:
        raise RuntimeError("exact Vision model is not resident after inference")
    runner = matching[0]
    size, vram = runner.get("size"), runner.get("size_vram")
    if not isinstance(size, int) or size < 1 or vram != size:
        raise RuntimeError("Vision model did not execute wholly on GPU")
    return {"model": model, "revision": revision, "size_bytes": size, "gpu_bytes": vram}


def _probe_v2_retrieval(
    *,
    workspace: Path,
    runtime: Path,
    query: str,
    model_cache: Path,
    clip_snapshot: Path,
    log_runtime: Path | None = None,
) -> dict[str, Any]:
    if log_runtime is not None:
        _progress(f"START v2_retrieval_probe; log={log_runtime / 'logs' / 'v2_probe.stderr.log'}")
    completed = subprocess.run(
        [
            sys.executable,
            str(workspace / "scripts/verify_isolated_rebuild_query.py"),
            "--runtime",
            str(runtime),
            "--query",
            query,
            "--cache-folder",
            str(model_cache),
            "--clip-snapshot",
            str(clip_snapshot),
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    if log_runtime is not None:
        logs = log_runtime / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "v2_probe.stdout.json").write_text(completed.stdout, encoding="utf-8")
        (logs / "v2_probe.stderr.log").write_text(completed.stderr, encoding="utf-8")
        state = "DONE" if completed.returncode == 0 else "FAILED"
        _progress(f"{state} v2_retrieval_probe; exit={completed.returncode}")
    if completed.returncode:
        raise RuntimeError(
            "isolated V2 retrieval probe failed"
            + (f"; log={log_runtime / 'logs' / 'v2_probe.stderr.log'}" if log_runtime else "")
        )
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise RuntimeError("isolated V2 retrieval probe returned an invalid response")
    return result


def run_complete_canary(
    *,
    workspace: Path,
    corpus: Path,
    source_database: Path | None = None,
    source_manifest: Path | None = None,
    includes: tuple[str, ...],
    paddle_detection_dir: Path,
    paddle_recognition_dir: Path,
    paddle_detection_sha256: str,
    paddle_recognition_sha256: str,
    paddle_language: str,
    vision_model: str,
    vision_revision: str,
    clip_snapshot: Path,
    visual_model: str,
    visual_revision: str,
    bge_cache: Path,
    paddle_device: str = "cpu",
    visual_device: str = "cpu",
    bge_device: str = "cpu",
    paddle_python: Path | None = None,
    probe_query: str = "Chip thickness",
    require_ocr_probe_hit: bool = True,
    perform_v2_probe: bool = True,
    evaluation_rebuild: bool = False,
    rebuild_owner: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run every production builder against one fresh disposable notebook."""
    workspace = workspace.resolve(strict=True)
    corpus = corpus.resolve(strict=True)
    report = run_canary(
        workspace=workspace,
        corpus=corpus,
        source_database=source_database,
        source_manifest=source_manifest,
        includes=includes,
        canonical_device=bge_device,
        evaluation_rebuild=evaluation_rebuild,
        stream_logs=evaluation_rebuild,
        rebuild_owner=rebuild_owner,
    )
    if report["stages"]["canonical_ingestion"] != "complete":
        return report
    runtime = Path(report["runtime"]).resolve(strict=True)
    stage_timeout = max(1200, len(report["sources"]) * 600)
    database = runtime / "mnemo.db"
    files = runtime / "files"
    report["schema"] = "mnemo.isolated-complete-rebuild/1"
    report["activation"] = "inactive"
    try:
        if paddle_language not in {"en", "hi", "mr"}:
            raise ValueError("OCR language is not supported by the governed provider")
        ocr_version = "PP-OCRv5" if "PP-OCRv5" in paddle_recognition_dir.name else "PP-OCRv3"
        ocr_python = (
            str(paddle_python.resolve(strict=True)) if paddle_python is not None else sys.executable
        )
        _run_stage(
            [
                ocr_python,
                str(workspace / "scripts/phase8_5_11_derived_pipeline.py"),
                "--database",
                str(database),
                "--blobs",
                str(files),
                "--operations",
                "ocr",
                "--ocr-provider",
                "paddleocr",
                "--paddle-package-version",
                "3.4.1",
                "--paddle-model-identity",
                f"{paddle_detection_dir.name}+{paddle_recognition_dir.name}",
                "--paddle-model-revision",
                (f"det-{paddle_detection_sha256}+rec-{paddle_recognition_sha256}"),
                "--paddle-detection-dir",
                str(paddle_detection_dir.resolve(strict=True)),
                "--paddle-recognition-dir",
                str(paddle_recognition_dir.resolve(strict=True)),
                "--paddle-detection-sha256",
                paddle_detection_sha256,
                "--paddle-recognition-sha256",
                paddle_recognition_sha256,
                "--paddle-language",
                paddle_language,
                "--paddle-ocr-version",
                ocr_version,
                "--paddle-device",
                paddle_device,
                "--run-id",
                str(report["run_id"]),
                "--all-assets",
                "--compact-output",
                "--output",
                str(runtime / "ocr-stage.json"),
            ],
            workspace=workspace,
            stage="paddleocr_inference",
            timeout_seconds=stage_timeout,
            log_runtime=runtime if evaluation_rebuild else None,
        )
        _run_stage(
            [
                sys.executable,
                str(workspace / "scripts/phase8_5_11_derived_pipeline.py"),
                "--database",
                str(database),
                "--blobs",
                str(files),
                "--operations",
                "vision_analysis",
                "visual_embedding",
                "--vision-model",
                vision_model,
                "--vision-revision",
                vision_revision,
                "--clip",
                str(clip_snapshot.resolve(strict=True)),
                "--visual-model",
                visual_model,
                "--visual-revision",
                visual_revision,
                "--visual-dimensions",
                "768",
                "--visual-device",
                visual_device,
                "--run-id",
                str(report["run_id"]),
                "--all-assets",
                "--compact-output",
                "--output",
                str(runtime / "derived-stage.json"),
            ],
            workspace=workspace,
            stage="vision_and_visual_inference",
            timeout_seconds=stage_timeout,
            log_runtime=runtime if evaluation_rebuild else None,
        )
        derived = json.loads((runtime / "derived-stage.json").read_text(encoding="utf-8"))
        ocr_stage = json.loads((runtime / "ocr-stage.json").read_text(encoding="utf-8"))
        if (
            paddle_device.startswith("gpu:")
            and ocr_stage.get("execution", {}).get("paddleocr", {}).get("actual_device")
            != paddle_device
        ):
            raise RuntimeError("PaddleOCR GPU execution evidence is missing")
        if visual_device == "cuda" and not str(
            derived.get("execution", {}).get("clip", {}).get("actual_device", "")
        ).startswith("cuda"):
            raise RuntimeError("CLIP GPU execution evidence is missing")
        if paddle_device.startswith("gpu:") and visual_device == "cuda" and bge_device == "cuda":
            report["vision_gpu"] = _verify_vision_gpu(model=vision_model, revision=vision_revision)
        for table in ("ocr_results", "vision_results", "visual_embeddings"):
            if derived["counts"][table] < 1:
                raise RuntimeError(f"required real inference did not persist {table}")
        report["stages"].update(paddleocr="complete", vision="complete", visual="complete")
        _run_stage(
            [
                sys.executable,
                str(workspace / "scripts/phase8_5_16_prepare_evaluation.py"),
                "--database",
                str(database),
                "--files",
                str(files),
                "--config",
                str(workspace / "mnemo.toml"),
                "--source-checksum",
                _digest(database),
                "--build-only",
                "--output",
                str(runtime / "projection-stage.json"),
            ],
            workspace=workspace,
            stage="text_and_visual_projections",
            timeout_seconds=stage_timeout,
            log_runtime=runtime if evaluation_rebuild else None,
        )
        projection = json.loads((runtime / "projection-stage.json").read_text(encoding="utf-8"))
        generation_ids: dict[str, UUID] = {}
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            for status in projection["statuses"]:
                if "generation_id" not in status:
                    continue
                identifier = UUID(status["generation_id"])
                row = connection.execute(
                    "SELECT capability FROM index_generations WHERE generation_id=?",
                    (str(identifier),),
                ).fetchone()
                if row is None or str(row[0]) in generation_ids:
                    raise RuntimeError("projection report has missing or duplicated generation")
                generation_ids[str(row[0])] = identifier
        finally:
            connection.close()
        report["stages"]["projections"] = "complete"
        _run_stage(
            [
                sys.executable,
                str(workspace / "scripts/isolated_multilingual_build.py"),
                "--workspace",
                str(workspace),
                "--runtime",
                str(runtime),
                "--notebook-id",
                str(report["notebook_id"]),
                "--cache-folder",
                str(bge_cache.resolve(strict=True)),
                "--device",
                bge_device,
                "--output",
                str(runtime / "multilingual-stage.json"),
            ],
            workspace=workspace,
            stage="multilingual_embeddings",
            timeout_seconds=stage_timeout,
            log_runtime=runtime if evaluation_rebuild else None,
        )
        multilingual = json.loads((runtime / "multilingual-stage.json").read_text(encoding="utf-8"))
        if bge_device == "cuda" and multilingual.get("execution_device") != "cuda":
            raise RuntimeError("BGE-M3 GPU execution evidence is missing")
        generation_ids.update(
            {name: UUID(value) for name, value in multilingual["generations"].items()}
        )
        report["stages"]["multilingual"] = "complete"
        if set(generation_ids) != set(REQUIRED):
            raise RuntimeError("rebuild did not produce the complete generation set")
        if evaluation_rebuild:
            _progress("START governed_generation_activation")
        decision = asyncio.run(
            activate_isolated_generation_set(
                database=database,
                notebook_id=UUID(report["notebook_id"]),
                generation_ids=generation_ids,
                vector_space=multilingual["vector_space"],
                embedding_model_identity=_embedding_model_identity(workspace),
                report_path=runtime / "activation-decision.json",
            )
        )
        report["coverage"] = decision
        if evaluation_rebuild:
            _progress(
                "DONE governed_generation_activation"
                if decision.get("active")
                else "FAILED governed_generation_activation"
            )
        if not decision.get("active"):
            raise RuntimeError("unified generation activation gate denied the rebuild")
        for source in report["sources"]:
            original = (corpus / source["relative_path"]).resolve(strict=True)
            if _digest(original) != source["sha256"]:
                raise RuntimeError("immutable source bytes changed during isolated rebuild")
        report["activation"] = "index_aliases_active_in_isolated_runtime_only"
        report["generations"] = {name: str(value) for name, value in generation_ids.items()}
        from mnemo_server.tools.isolated_activation import compose_isolated_full_v2_alias

        if evaluation_rebuild:
            _progress("START full_v2_serving_composition")
        report["full_v2_serving"] = asyncio.run(
            compose_isolated_full_v2_alias(workspace=workspace, runtime=runtime)
        )
        if evaluation_rebuild:
            _progress("DONE full_v2_serving_composition")
        report["blockers"] = []
        if perform_v2_probe:
            probe = _probe_v2_retrieval(
                workspace=workspace,
                runtime=runtime,
                query=probe_query,
                model_cache=bge_cache,
                clip_snapshot=clip_snapshot,
                log_runtime=runtime if evaluation_rebuild else None,
            )
            report["v2_probe"] = probe
            decisions = {
                item["representation"]: item["status"] for item in probe["representation_decisions"]
            }
            required = ("canonical_text", "ocr_text", "vision_analysis", "multilingual_text")
            unavailable = [name for name in required if decisions.get(name) != "searched"]
            if unavailable:
                raise RuntimeError(
                    "V2 normal-query runtime did not compose complete ready sources: "
                    + ",".join(unavailable)
                )
            if require_ocr_probe_hit and not any(
                item["representation"] == "ocr_text" for item in probe["evidence"]
            ):
                raise RuntimeError("V2 normal query did not retrieve OCR-derived evidence")
            report["activation"] = "complete_v2_retrieval_ready"
        else:
            report["activation"] = "complete_v2_build_ready"
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        report["failure"] = str(error)[-3000:]
        report["blockers"] = [type(error).__name__]
    (runtime / "complete-rebuild-status.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    authority = parser.add_mutually_exclusive_group(required=True)
    authority.add_argument("--source-database", type=Path)
    authority.add_argument("--source-manifest", type=Path)
    parser.add_argument("--include", action="append", required=True)
    args = parser.parse_args()
    report = run_canary(
        workspace=args.workspace,
        corpus=args.corpus,
        source_database=args.source_database,
        source_manifest=args.source_manifest,
        includes=tuple(args.include),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["stages"]["canonical_ingestion"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
