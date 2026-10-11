"""Fail-closed whole-notebook gate for an isolated multimodal rebuild.

The gate never selects generations by recency or activates a partial modality.
Only exact generation IDs returned by the builders can be admitted.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from mnemo.phase85.isolated_v2_identity import IsolatedV2DatabaseIdentityVerifier
from mnemo.phase85.v2_activation_authorization import first_v2_deactivation_recovery_digest
from mnemo.storage.sqlite import SQLiteStore

REQUIRED = (
    "ocr_text",
    "vision_text",
    "visual_vector",
    "representation_derivation_v2",
    "language_text_v2",
    "multilingual_embedding_v2",
    "multilingual_vector_v2",
)
_SERVING_AUTHORITY = UUID("32055a3d-5b4f-5562-a82f-6bf44afe94b7")


def assess_generation_set(
    *,
    database: Path,
    notebook_id: UUID,
    generation_ids: dict[str, UUID],
    vector_space: str,
    embedding_model_identity: str,
) -> dict[str, Any]:
    """Verify selected persisted records and ancestry without writing aliases."""
    blockers: list[str] = []
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        notebooks = connection.execute("SELECT notebook_id FROM notebooks").fetchall()
        if notebooks != [(str(notebook_id),)]:
            blockers.append("isolated_notebook_identity_mismatch")
        versions = {
            str(row[0])
            for row in connection.execute(
                "SELECT v.version_id FROM document_versions v JOIN sources s "
                "ON s.document_id=v.document_id WHERE s.notebook_id=?",
                (str(notebook_id),),
            )
        }
        if not versions:
            blockers.append("source_versions_absent")
        occurrences = {
            str(row[0])
            for row in connection.execute(
                "SELECT o.occurrence_id FROM asset_occurrences o JOIN sources s "
                "ON s.document_id=o.document_id JOIN asset_catalog a ON a.asset_id=o.asset_id "
                "WHERE s.notebook_id=? AND a.mime_type LIKE 'image/%' "
                "AND a.mime_type<>'image/svg+xml'",
                (str(notebook_id),),
            )
        }
        derivation_occurrences: dict[str, set[str]] = {}
        for family, table in (
            ("ocr", "ocr_results"),
            ("vision", "vision_results"),
            ("visual", "visual_embeddings"),
        ):
            completeness = " WHERE completeness='complete'" if family != "visual" else ""
            rows = connection.execute(
                f"SELECT occurrence_id,document_id,version_id FROM {table}{completeness}"
            ).fetchall()
            observed = {str(row[0]) for row in rows}
            derivation_occurrences[family] = observed
            if observed != occurrences or len(rows) != len(occurrences):
                blockers.append(f"{family}:applicable_occurrence_coverage_incomplete")
            if any(str(row[2]) not in versions for row in rows):
                blockers.append(f"{family}:source_version_ancestry_invalid")
        ocr_text_occurrences = {
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT o.occurrence_id FROM ocr_regions r "
                "JOIN ocr_results o USING(derivation_id) "
                "WHERE o.completeness='complete' AND length(trim(r.text))>0"
            )
        }
        if set(generation_ids) != set(REQUIRED) or len(set(generation_ids.values())) != len(
            REQUIRED
        ):
            blockers.append("generation_set_incomplete_or_duplicated")
        generation_status: dict[str, dict[str, object]] = {}
        for capability in REQUIRED:
            identifier = generation_ids.get(capability)
            if identifier is None:
                continue
            row = connection.execute(
                "SELECT g.capability,g.state,g.item_count,g.checksum,g.model_identity,g.dimensions,"
                "c.expected_count,c.succeeded_count,c.failed_count,c.skipped_count,c.completeness "
                "FROM index_generations g LEFT JOIN index_generation_coverage c "
                "USING(generation_id) WHERE g.generation_id=?",
                (str(identifier),),
            ).fetchone()
            if row is None or row[0] != capability:
                blockers.append(f"{capability}:generation_missing_or_wrong_capability")
                continue
            generation_status[capability] = {
                "generation_id": str(identifier),
                "state": row[1],
                "item_count": row[2],
                "coverage_expected": row[6],
                "coverage_succeeded": row[7],
                "coverage_failed": row[8],
            }
            if (
                row[1] != "ready"
                or row[3] is None
                or row[6] is None
                or row[6] != row[7]
                or row[7] != row[2]
                or row[8] != 0
                or row[9] != 0
                or row[10] != "complete"
            ):
                blockers.append(f"{capability}:not_complete_ready")
            source_versions = {
                str(source[0])
                for source in connection.execute(
                    "SELECT source_id FROM index_generation_sources "
                    "WHERE generation_id=? AND source_kind='version'",
                    (str(identifier),),
                )
            }
            if not source_versions or not source_versions.issubset(versions):
                blockers.append(f"{capability}:source_version_ancestry_invalid")
            if capability in {"multilingual_embedding_v2", "multilingual_vector_v2"} and (
                row[4] != embedding_model_identity or row[5] != 1024
            ):
                blockers.append(f"{capability}:embedding_model_incompatible")
            if capability in {
                "representation_derivation_v2",
                "language_text_v2",
                "multilingual_embedding_v2",
                "multilingual_vector_v2",
            }:
                try:
                    manifest = connection.execute(
                        "SELECT capability,expected_count,succeeded_count,failed_count,"
                        "skipped_count,provenance_complete,authorization_compatible,"
                        "payload,payload_hash FROM multilingual_coverage_manifests_v2 "
                        "WHERE generation_id=?",
                        (str(identifier),),
                    ).fetchone()
                except sqlite3.OperationalError:
                    manifest = None
                if (
                    manifest is None
                    or manifest[0] != capability
                    or manifest[1:5] != (row[6], row[7], row[8], row[9])
                    or manifest[5] != 1
                    or manifest[6] != 1
                    or hashlib.sha256(str(manifest[7]).encode("utf-8")).hexdigest() != manifest[8]
                ):
                    blockers.append(f"{capability}:coverage_manifest_invalid")
        expected = {
            "canonical": int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]),
            "ocr": int(
                connection.execute(
                    "SELECT COUNT(*) FROM ocr_regions r JOIN ocr_results o USING(derivation_id) "
                    "WHERE o.completeness='complete'"
                ).fetchone()[0]
            ),
            "vision": int(
                connection.execute(
                    "SELECT COUNT(*) FROM vision_results WHERE completeness='complete'"
                ).fetchone()[0]
            ),
            "visual": int(
                connection.execute("SELECT COUNT(*) FROM visual_embeddings").fetchone()[0]
            ),
        }
        for capability, table, parent, expected_key in (
            ("ocr_text", "ocr_projection_rows", "ocr_results", "ocr"),
            ("vision_text", "vision_text_projection_rows", "vision_results", "vision"),
            ("visual_vector", "visual_vector_projection_rows", "visual_embeddings", "visual"),
        ):
            identifier = generation_ids.get(capability)
            if identifier is None:
                continue
            rows = connection.execute(
                f"SELECT occurrence_id,document_id,version_id FROM {table} WHERE generation_id=?",
                (str(identifier),),
            ).fetchall()
            required_occurrences = ocr_text_occurrences if capability == "ocr_text" else occurrences
            if (
                len(rows) != expected[expected_key]
                or {str(row[0]) for row in rows} != required_occurrences
            ):
                blockers.append(f"{capability}:projection_coverage_incomplete")
            if any(str(row[2]) not in versions for row in rows):
                blockers.append(f"{capability}:projection_version_ancestry_invalid")
            ancestry = connection.execute(
                f"SELECT p.derivation_id,p.occurrence_id,p.document_id,p.version_id,"
                f"d.occurrence_id,d.document_id,d.version_id FROM {table} p "
                f"LEFT JOIN {parent} d ON d.derivation_id=p.derivation_id "
                "WHERE p.generation_id=?",
                (str(identifier),),
            ).fetchall()
            if any(row[4] is None or tuple(row[1:4]) != tuple(row[4:7]) for row in ancestry):
                blockers.append(f"{capability}:projection_derivation_ancestry_invalid")
            if (
                capability == "ocr_text"
                and connection.execute(
                    "SELECT 1 FROM ocr_projection_rows p LEFT JOIN ocr_regions r "
                    "ON r.region_id=p.region_id AND r.derivation_id=p.derivation_id "
                    "WHERE p.generation_id=? AND r.region_id IS NULL LIMIT 1",
                    (str(identifier),),
                ).fetchone()
                is not None
            ):
                blockers.append("ocr_text:projection_region_ancestry_invalid")
        embedding_id = generation_ids.get("multilingual_embedding_v2")
        embedding_counts: dict[str, int] = {}
        if embedding_id is not None:
            rows = connection.execute(
                "SELECT notebook_id,document_id,version_id,occurrence_id,derivation_id,"
                "representation_type,vector_space FROM multilingual_embeddings_v2 "
                "WHERE generation_id=?",
                (str(embedding_id),),
            ).fetchall()
            for row in rows:
                embedding_counts[str(row[5])] = embedding_counts.get(str(row[5]), 0) + 1
                if (
                    str(row[0]) != str(notebook_id)
                    or str(row[2]) not in versions
                    or str(row[6]) != vector_space
                ):
                    blockers.append("multilingual_embedding_v2:scope_or_space_mismatch")
                if row[5] != "unicode_semantic_text" and (
                    row[3] is None or row[4] is None or str(row[3]) not in occurrences
                ):
                    blockers.append("multilingual_embedding_v2:derived_ancestry_missing")
            for representation, key in (
                ("unicode_semantic_text", "canonical"),
                ("ocr_text", "ocr"),
                ("vision_text", "vision"),
            ):
                if embedding_counts.get(representation, 0) != expected[key]:
                    blockers.append(
                        f"multilingual_embedding_v2:{representation}_coverage_incomplete"
                    )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            blockers.append("sqlite_integrity_failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            blockers.append("foreign_key_integrity_failed")
        return {
            "schema": "mnemo.isolated-generation-activation/1",
            "checked_at_utc": datetime.now(UTC).isoformat(),
            "notebook_id": str(notebook_id),
            "expected": expected,
            "raster_occurrences": len(occurrences),
            "embedding_counts": embedding_counts,
            "generations": generation_status,
            "vector_space": vector_space,
            "eligible_for_activation": not blockers,
            "blockers": sorted(set(blockers)),
        }
    finally:
        connection.close()


async def activate_isolated_generation_set(
    *,
    database: Path,
    notebook_id: UUID,
    generation_ids: dict[str, UUID],
    vector_space: str,
    embedding_model_identity: str,
    report_path: Path,
) -> dict[str, Any]:
    report = assess_generation_set(
        database=database,
        notebook_id=notebook_id,
        generation_ids=generation_ids,
        vector_space=vector_space,
        embedding_model_identity=embedding_model_identity,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not report["eligible_for_activation"]:
        return report
    store = SQLiteStore(database)
    await store.open()
    try:
        promoted = await store.promote_index_generation_set(
            tuple(generation_ids[capability] for capability in REQUIRED)
        )
    finally:
        await store.close()
    report["active"] = promoted
    if not promoted:
        report["blockers"] = ["generation_changed_before_atomic_promotion"]
        report["eligible_for_activation"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


async def compose_isolated_full_v2_alias(*, workspace: Path, runtime: Path) -> dict[str, Any]:
    """Promote the existing four-generation alias only after whole-canary admission."""
    verifier = IsolatedV2DatabaseIdentityVerifier(workspace_root=workspace, runtime=runtime)
    artifact = verifier.artifact
    decision = json.loads((runtime / "activation-decision.json").read_text(encoding="utf-8"))
    if decision.get("notebook_id") != str(artifact.notebook_id) or not decision.get("active"):
        raise ValueError("isolated whole-notebook activation is absent")
    expected = {
        item["generation_id"]
        for name, item in decision["generations"].items()
        if name.endswith("_v2")
    }
    if expected != {str(item) for item in artifact.generation_ids}:
        raise ValueError("isolated Full V2 generations differ from whole-notebook decision")
    verifier.verify(expected_database_identity=artifact.database_identity)
    authority = {
        "schema": "mnemo.isolated-full-v2-serving-authorization/1",
        "decision_reference": "owner-authorized-disposable-canary-serving-2026-10-07",
        "notebook_id": str(artifact.notebook_id),
        "run_id": str(artifact.build_run_id),
        "database_identity": artifact.database_identity,
        "profile_fingerprint": artifact.profile_fingerprint,
        "vector_space": artifact.vector_space_identity,
        "generation_ids": [str(item) for item in artifact.generation_ids],
        "recovery_mode": "deactivate_v2_alias_set",
    }
    authorization_digest = hashlib.sha256(
        json.dumps(authority, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    authorization_id = uuid5(_SERVING_AUTHORITY, authorization_digest)
    store = SQLiteStore(runtime / "mnemo.db")
    await store.open()
    try:
        active = await store.resolve_active_multilingual_v2_generation_set()
        if active is None:
            alias_digest = await store.promote_multilingual_v2_alias_set(
                profile_fingerprint=artifact.profile_fingerprint,
                generation_ids=artifact.generation_ids,
                rollback_alias_set_digest=first_v2_deactivation_recovery_digest(
                    profile_fingerprint=artifact.profile_fingerprint
                ),
                rollback_generation_ids=(),
                expected_active_alias_set_digest=None,
                activation_mode="first_v2_activation",
                recovery_mode="deactivate_v2_alias_set",
                authorization_id=authorization_id,
                authorization_digest=authorization_digest,
            )
        elif active == artifact.generation_ids:
            existing_digest = await store.resolve_active_multilingual_v2_alias_digest()
            if existing_digest is None:
                raise RuntimeError("Full V2 active alias digest is missing")
            with sqlite3.connect(
                f"file:{(runtime / 'mnemo.db').as_posix()}?mode=ro&immutable=1", uri=True
            ) as connection:
                record = connection.execute(
                    "SELECT activation_mode,recovery_mode,authorization_id,"
                    "authorization_digest FROM multilingual_v2_activation_records "
                    "WHERE alias_set_digest=?",
                    (existing_digest,),
                ).fetchone()
            if record != (
                "first_v2_activation",
                "deactivate_v2_alias_set",
                str(authorization_id),
                authorization_digest,
            ):
                raise ValueError("existing Full V2 alias lacks this serving authorization")
            alias_digest = existing_digest
        else:
            raise ValueError("another Full V2 generation set is already active")
        if await store.resolve_active_multilingual_v2_generation_set() != artifact.generation_ids:
            raise RuntimeError("Full V2 alias resolver disagrees with serving authorization")
    finally:
        await store.close()
    report = {
        **authority,
        "authorization_id": str(authorization_id),
        "authorization_digest": authorization_digest,
        "alias_set_digest": alias_digest,
        "state": "active_internal_only",
    }
    (runtime / "full-v2-serving.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
