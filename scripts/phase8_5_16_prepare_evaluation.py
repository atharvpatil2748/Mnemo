"""Prepare an isolated WP-16 database from already-persisted evidence.

This command never ingests source documents and never invokes a model provider.
It projects canonical table IR and persisted OCR, Vision, and visual-embedding
derivations through the governed Phase 8.5 generation lifecycle.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from mnemo.config import MnemoConfig
from mnemo.models import IndexGeneration, IndexGenerationState
from mnemo.phase85.profiles import ModelProfileRegistry
from mnemo.phase85.projections import (
    DerivedProjectionCoordinator,
    OCRTextProjectionBuilder,
    ProjectionCoverage,
    ProjectionGenerationSpec,
    VisionTextProjectionBuilder,
    VisualVectorProjectionBuilder,
)
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.sqlite import SQLiteStore


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows(database: Path, query: str) -> tuple[tuple[str, ...], ...]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        return tuple(tuple(str(value) for value in row) for row in connection.execute(query))
    finally:
        connection.close()


def _spec(
    *,
    capability: str,
    profile_id: str,
    profile_fingerprint: str,
    input_scope: str,
    source_versions: tuple[UUID, ...],
    source_generations: tuple[UUID, ...],
    provider: str | None,
    model: str | None,
    revision: str | None,
    dimensions: int | None = None,
) -> ProjectionGenerationSpec:
    return ProjectionGenerationSpec(
        capability=capability,
        profile_id=profile_id,
        schema_version=1,
        input_scope=input_scope,
        provider_identity=provider,
        model_identity=model,
        model_revision=revision,
        configuration_fingerprint=profile_fingerprint,
        source_version_ids=source_versions,
        source_generation_ids=source_generations,
        dimensions=dimensions,
    )


def _status_payload(status: Any) -> dict[str, Any]:
    coverage = status.coverage
    return {
        "generation_id": str(status.generation_id),
        "state": status.state.value,
        "active": status.active,
        "compatible": status.compatible,
        "eligible_for_activation": status.eligible_for_activation,
        "reason_code": status.reason_code,
        "coverage": (
            None
            if coverage is None
            else {
                "expected_count": coverage.expected_count,
                "succeeded_count": coverage.succeeded_count,
                "failed_count": coverage.failed_count,
                "skipped_count": coverage.skipped_count,
                "completeness": coverage.completeness.value,
                "checksum": coverage.checksum,
            }
        ),
    }


async def _build_source_projection(
    *,
    store: SQLiteStore,
    capability: str,
    profile_id: str,
    provider: str,
    model: str,
    revision: str,
    configuration_digest: str,
    dimensions: int | None,
    input_scope: str,
    source_versions: tuple[UUID, ...],
    source_generations: tuple[UUID, ...],
    builder: Any,
) -> dict[str, Any]:
    """Run the existing immutable generation/store lifecycle for source-bound builders."""
    identity = json.dumps(
        {
            "capability": capability,
            "configuration_digest": configuration_digest,
            "dimensions": dimensions,
            "input_scope": input_scope,
            "model": model,
            "profile_id": profile_id,
            "provider": provider,
            "revision": revision,
            "source_generations": sorted(str(item) for item in source_generations),
            "source_versions": sorted(str(item) for item in source_versions),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    generation_id = uuid5(NAMESPACE_URL, f"urn:mnemo:phase8.5:wp16:{identity}")
    now = datetime.now(UTC)
    created = await store.create_index_generation(
        IndexGeneration(
            generation_id=generation_id,
            capability=capability,
            profile=profile_id,
            schema_version=1,
            input_scope=input_scope,
            provider_identity=provider,
            model_identity=f"{model}@{revision}",
            configuration_digest=configuration_digest,
            dimensions=dimensions,
            state=IndexGenerationState.BUILDING,
            item_count=0,
            checksum=None,
            created_at=now,
            updated_at=now,
        )
    )
    if not created:
        existing = await store.get_index_generation(generation_id)
        if existing is None or existing.state is not IndexGenerationState.READY:
            raise RuntimeError("deterministic projection generation is not resumable")
        if not await store.promote_index_generation(generation_id):
            raise RuntimeError("ready projection generation could not be promoted")
        coverage = await store.get_index_generation_coverage(generation_id)
    else:
        await store.put_index_generation_sources(
            generation_id=generation_id,
            source_generation_ids=source_generations,
            source_version_ids=source_versions,
        )
        result = await builder.build(generation_id)
        coverage = ProjectionCoverage.from_result(
            generation_id, result, updated_at=datetime.now(UTC)
        )
        await store.put_index_generation_coverage(coverage)
        if result.completeness.value != "complete":
            await store.transition_index_generation(
                generation_id,
                IndexGenerationState.BUILDING,
                IndexGenerationState.FAILED,
            )
            raise RuntimeError(f"{capability} projection was incomplete")
        if not await store.transition_index_generation(
            generation_id,
            IndexGenerationState.BUILDING,
            IndexGenerationState.READY,
            item_count=result.succeeded_count,
            checksum=result.checksum,
        ):
            raise RuntimeError("projection generation lifecycle changed before READY")
        if not await store.promote_index_generation(generation_id):
            raise RuntimeError("ready projection generation could not be promoted")
    if coverage is None:
        raise RuntimeError("active projection generation lacks coverage")
    return {
        "generation_id": str(generation_id),
        "state": "ready",
        "active": True,
        "compatible": True,
        "eligible_for_activation": True,
        "reason_code": "generation_active",
        "coverage": {
            "expected_count": coverage.expected_count,
            "succeeded_count": coverage.succeeded_count,
            "failed_count": coverage.failed_count,
            "skipped_count": coverage.skipped_count,
            "completeness": coverage.completeness.value,
            "checksum": coverage.checksum,
        },
    }


async def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    database = args.database.resolve(strict=True)
    files = args.files.resolve(strict=True)
    config_path = args.config.resolve(strict=True)
    initial_hash = _sha256(database)
    if initial_hash.casefold() != args.source_checksum.casefold():
        raise ValueError("isolated database does not match the recorded source checksum")

    config = MnemoConfig.from_file(config_path)
    profile_fingerprint = ModelProfileRegistry(config).active.fingerprint
    input_scope = f"wp16-isolated:{initial_hash}"
    version_ids = tuple(
        UUID(row[0])
        for row in _rows(database, "SELECT version_id FROM document_versions ORDER BY version_id")
    )
    source_counts = {
        table: int(_rows(database, f"SELECT COUNT(*) FROM {table}")[0][0])
        for table in (
            "documents",
            "document_versions",
            "chunks",
            "asset_occurrences",
            "ocr_results",
            "vision_results",
            "visual_embeddings",
        )
    }

    store = SQLiteStore(database)
    blobs = FilesystemBlobStore(files)
    await store.open()
    await blobs.open()
    statuses: list[dict[str, Any]] = []
    missing_ir: list[str] = []
    try:
        structured_changed = 0
        for version_id in version_ids:
            document = await blobs.get_parsed_document(version_id)
            if document is None:
                missing_ir.append(str(version_id))
                continue
            structured_changed += int(await store.project_structured_document(version_id, document))
        statuses.append(
            {
                "capability": "structured_table",
                "source_versions": len(version_ids),
                "missing_ir": len(missing_ir),
                "generations_created": structured_changed,
            }
        )

        coordinator = DerivedProjectionCoordinator(store)
        ocr_refs = _rows(
            database,
            """SELECT r.derivation_id,MIN(s.notebook_id) FROM ocr_results r
               JOIN sources s ON s.document_id=r.document_id
               GROUP BY r.derivation_id ORDER BY r.derivation_id""",
        )
        loaded_ocr = []
        for derivation_id, notebook_id in ocr_refs:
            result = await store.get_authorized_ocr_result(
                notebook_id=UUID(notebook_id), derivation_id=UUID(derivation_id)
            )
            if result is not None:
                loaded_ocr.append(result)
        ocr_results = tuple(loaded_ocr)
        if ocr_results:
            first = ocr_results[0]
            statuses.append(
                await _build_source_projection(
                    store=store,
                    capability="ocr_text",
                    profile_id=first.provider.profile_id,
                    provider=first.provider.provider_identity,
                    model=first.provider.model_identity,
                    revision=first.provider.model_revision,
                    configuration_digest=first.preprocessing_digest,
                    dimensions=None,
                    input_scope=input_scope,
                    source_versions=tuple(
                        sorted({item.version_id for item in ocr_results}, key=str)
                    ),
                    source_generations=tuple(
                        sorted({item.generation_id for item in ocr_results}, key=str)
                    ),
                    builder=OCRTextProjectionBuilder(store=store, results=ocr_results),
                )
            )

        vision_generations = tuple(
            UUID(row[0])
            for row in _rows(
                database, "SELECT DISTINCT generation_id FROM vision_results ORDER BY generation_id"
            )
        )
        if vision_generations:
            vision_versions = tuple(
                UUID(row[0])
                for row in _rows(
                    database, "SELECT DISTINCT version_id FROM vision_results ORDER BY version_id"
                )
            )
            spec = _spec(
                capability="vision_text",
                profile_id="phase8_5_local_v1:vision_text",
                profile_fingerprint=profile_fingerprint,
                input_scope=input_scope,
                source_versions=vision_versions,
                source_generations=vision_generations,
                provider="ollama",
                model="qwen2.5vl",
                revision="persisted-mixed",
            )
            status = await coordinator.build_and_activate(
                spec,
                VisionTextProjectionBuilder(store=store, source_generation_ids=vision_generations),
            )
            statuses.append(_status_payload(status))

        visual_refs = _rows(
            database,
            """SELECT e.derivation_id,MIN(s.notebook_id) FROM visual_embeddings e
               JOIN sources s ON s.document_id=e.document_id
               GROUP BY e.derivation_id ORDER BY e.derivation_id""",
        )
        visual_by_profile: dict[str, list[Any]] = defaultdict(list)
        for derivation_id, notebook_id in visual_refs:
            embedding = await store.get_authorized_visual_embedding(
                notebook_id=UUID(notebook_id), derivation_id=UUID(derivation_id)
            )
            if embedding is not None:
                visual_by_profile[embedding.provider.profile_id].append(embedding)
        for profile_id in sorted(visual_by_profile):
            embeddings = tuple(visual_by_profile[profile_id])
            first = embeddings[0]
            visual_contract = hashlib.sha256(
                json.dumps(
                    {
                        "preprocessing_digest": first.preprocessing_digest,
                        "metric": first.metric.value,
                        "normalization": first.normalization.value,
                        "shared_space_id": first.shared_space_id,
                        "dimensions": first.dimensions,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            statuses.append(
                await _build_source_projection(
                    store=store,
                    capability="visual_vector",
                    profile_id=profile_id,
                    provider=first.provider.provider_identity,
                    model=first.provider.model_identity,
                    revision=first.provider.model_revision,
                    configuration_digest=visual_contract,
                    dimensions=first.dimensions,
                    input_scope=input_scope,
                    source_versions=tuple(
                        sorted({item.version_id for item in embeddings}, key=str)
                    ),
                    source_generations=tuple(
                        sorted({item.generation_id for item in embeddings}, key=str)
                    ),
                    builder=VisualVectorProjectionBuilder(store=store, embeddings=embeddings),
                )
            )
    finally:
        await blobs.close()
        await store.close()

    generation_counts = {
        "index_generations": int(_rows(database, "SELECT COUNT(*) FROM index_generations")[0][0]),
        "active_index_generations": int(
            _rows(database, "SELECT COUNT(*) FROM active_index_generations")[0][0]
        ),
        "structured_table_projections": int(
            _rows(database, "SELECT COUNT(*) FROM structured_table_projections")[0][0]
        ),
        "ocr_projection_rows": int(
            _rows(database, "SELECT COUNT(*) FROM ocr_projection_rows")[0][0]
        ),
        "vision_text_projection_rows": int(
            _rows(database, "SELECT COUNT(*) FROM vision_text_projection_rows")[0][0]
        ),
        "visual_vector_projection_rows": int(
            _rows(database, "SELECT COUNT(*) FROM visual_vector_projection_rows")[0][0]
        ),
        "language_text_projection_rows": int(
            _rows(database, "SELECT COUNT(*) FROM language_text_projection_rows")[0][0]
        ),
        "multilingual_embeddings": int(
            _rows(database, "SELECT COUNT(*) FROM multilingual_embeddings")[0][0]
        ),
    }
    return {
        "schema": "mnemo.phase8.5.wp16-isolated-preparation/1",
        "database": database.name,
        "source_checksum": initial_hash,
        "prepared_checksum": _sha256(database),
        "profile_id": ModelProfileRegistry(config).active.profile_id,
        "profile_fingerprint": profile_fingerprint,
        "source_counts": source_counts,
        "generation_counts": generation_counts,
        "missing_parsed_ir": missing_ir,
        "statuses": statuses,
        "provider_calls": 0,
        "ingestion_runs": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--files", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source-checksum", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = asyncio.run(_prepare(args))
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
