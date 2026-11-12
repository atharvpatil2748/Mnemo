"""Independent read-only post-ingestion audit of the disposable four-notebook run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _read(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    suffix = "&immutable=1" if immutable else ""
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro{suffix}", uri=True)


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def validate_reused_document(
    original: sqlite3.Connection,
    current: sqlite3.Connection,
    *,
    content_hash: str,
    parsed_root: Path,
    model_revision: str,
) -> dict[str, object]:
    """Validate an immutable historical document before adding a membership.

    The snapshot is the frozen source of expected chunks and derivations.  The
    current copy must also satisfy structural/provenance checks independently;
    matching an incomplete snapshot is not sufficient.
    """
    errors: list[str] = []
    identity = original.execute(
        "SELECT d.document_id,d.current_version_id FROM documents d "
        "JOIN document_versions v ON v.version_id=d.current_version_id "
        "AND v.document_id=d.document_id "
        "JOIN sources s ON s.document_id=d.document_id "
        "WHERE d.current_hash=? AND v.content_hash=? AND d.status='indexed'",
        (content_hash, content_hash),
    ).fetchall()
    if len(identity) != 1:
        return {
            "status": "FAIL",
            "errors": ["historical source/document/version identity is not unique"],
        }
    document_id, version_id = identity[0]
    actual = current.execute(
        "SELECT d.document_id,d.current_version_id FROM documents d "
        "JOIN document_versions v ON v.version_id=d.current_version_id "
        "AND v.document_id=d.document_id "
        "WHERE d.current_hash=? AND v.content_hash=? AND d.status='indexed'",
        (content_hash, content_hash),
    ).fetchall()
    if actual != [(document_id, version_id)]:
        errors.append("document/version/hash identity differs from historical source")

    def rows(db: sqlite3.Connection, query: str, *params: str) -> list[tuple[Any, ...]]:
        return db.execute(query, params).fetchall()

    chunk_query = (
        "SELECT * FROM chunks WHERE document_id=? AND version_id=? "
        "ORDER BY position_section_index,position_chunk_index,id"
    )
    expected_chunks = rows(original, chunk_query, document_id, version_id)
    chunks = rows(current, chunk_query, document_id, version_id)
    if not chunks or chunks != expected_chunks:
        errors.append("required chunk rows or content hashes differ from snapshot")
    columns = [column[1] for column in current.execute("PRAGMA table_info(chunks)")]
    index = {
        name: columns.index(name)
        for name in (
            "id",
            "text",
            "position_section_index",
            "position_chunk_index",
            "source_start_ordinal",
            "source_end_ordinal",
        )
    }
    parsed = parsed_root / "parsed" / version_id[:8] / f"{version_id}.ir.json"
    if not parsed.is_file():
        errors.append("parsed representation missing")
        blocks: list[object] = []
    else:
        try:
            value = json.loads(parsed.read_text(encoding="utf-8"))
            blocks = value["blocks"]
            if not isinstance(blocks, list) or not blocks:
                raise ValueError("no parsed blocks")
        except (OSError, ValueError, KeyError, TypeError):
            blocks = []
            errors.append("parsed representation malformed")
    ids = [row[index["id"]] for row in chunks]
    positions = [
        (row[index["position_section_index"]], row[index["position_chunk_index"]]) for row in chunks
    ]
    if (
        len(ids) != len(set(ids))
        or len(positions) != len(set(positions))
        or positions != sorted(positions)
    ):
        errors.append("chunk identities or ordering invalid")
    for row in chunks:
        start, end = row[index["source_start_ordinal"]], row[index["source_end_ordinal"]]
        if (
            not isinstance(row[index["text"]], str)
            or not row[index["text"]].strip()
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not 0 <= start <= end < len(blocks)
        ):
            errors.append("empty chunk or invalid parsed-block boundaries")
            break
    embeddings = rows(
        current,
        "SELECT chunk_id,document_id,version_id,model_identity,model_revision,"
        "dimensions,normalized "
        "FROM evaluation_text_embeddings WHERE document_id=? AND version_id=?",
        document_id,
        version_id,
    )
    if {row[0] for row in embeddings} != set(ids) or any(
        row[1:] != (document_id, version_id, "BAAI/bge-m3", model_revision, 1024, 1)
        for row in embeddings
    ):
        errors.append("historical chunk embedding coverage/model/dimensions invalid")
    for table in ("evaluation_text_embeddings", "document_binary_references", "asset_occurrences"):
        query = f"SELECT * FROM {table} WHERE document_id=? AND version_id=? ORDER BY 1"
        if rows(current, query, document_id, version_id) != rows(
            original, query, document_id, version_id
        ):
            errors.append(f"{table} differs from snapshot")
    occurrences = rows(
        current,
        "SELECT occurrence_id,asset_id FROM asset_occurrences WHERE document_id=? AND version_id=?",
        document_id,
        version_id,
    )
    for occurrence_id, asset_id in occurrences:
        asset_query = "SELECT * FROM asset_catalog WHERE asset_id=?"
        if rows(current, asset_query, asset_id) != rows(
            original, asset_query, asset_id
        ) or not rows(current, asset_query, asset_id):
            errors.append(f"asset catalog identity differs for {occurrence_id}")
        for table in ("ocr_results", "vision_results", "visual_embeddings"):
            query = f"SELECT * FROM {table} WHERE occurrence_id=? ORDER BY 1"
            found = rows(current, query, occurrence_id)
            if len(found) != 1 or found != rows(original, query, occurrence_id):
                errors.append(f"{table} missing or changed for occurrence {occurrence_id}")
            columns = [column[1] for column in current.execute(f"PRAGMA table_info({table})")]
            if found and (
                found[0][columns.index("document_id")] != document_id
                or found[0][columns.index("version_id")] != version_id
                or found[0][columns.index("asset_id")] != asset_id
                or (
                    "completeness" in columns
                    and found[0][columns.index("completeness")] != "complete"
                )
                or (table == "visual_embeddings" and found[0][columns.index("dimensions")] != 768)
            ):
                errors.append(f"{table} provenance/completeness invalid for {occurrence_id}")
            if table == "ocr_results" and found:
                derivation_id = found[0][columns.index("derivation_id")]
                for child in ("ocr_regions", "ocr_language_observations"):
                    child_query = f"SELECT * FROM {child} WHERE derivation_id=? ORDER BY 1"
                    if rows(current, child_query, derivation_id) != rows(
                        original, child_query, derivation_id
                    ):
                        errors.append(f"{child} differs for {occurrence_id}")
        derivation_query = (
            "SELECT * FROM asset_derivations WHERE occurrence_id=? ORDER BY operation"
        )
        derivations = rows(current, derivation_query, occurrence_id)
        if derivations != rows(original, derivation_query, occurrence_id):
            errors.append(f"asset derivations differ for {occurrence_id}")
        derivation_columns = [
            column[1] for column in current.execute("PRAGMA table_info(asset_derivations)")
        ]
        if {row[derivation_columns.index("operation")] for row in derivations} != {
            "ocr",
            "vision_analysis",
            "visual_embedding",
        } or any(row[derivation_columns.index("status")] != "succeeded" for row in derivations):
            errors.append(f"required asset derivations incomplete for {occurrence_id}")
    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "document_id": document_id,
        "version_id": version_id,
        "chunk_count": len(chunks),
        "occurrence_count": len(occurrences),
    }


def audit(
    plan: dict[str, Any],
    records: dict[str, dict[str, Any]],
    runtime: Path,
    logs: Path,
    *,
    require_active_alias: bool = True,
    write_artifacts: bool = True,
) -> dict[str, object]:
    from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority

    from scripts.run_phase86_four_notebooks import (
        CAPABILITIES,
        MODEL_REVISION,
        digest,
        notebook_ids,
    )

    errors: list[str] = []
    warnings: list[str] = []
    file_rows: list[dict[str, object]] = []
    chunk_rows: list[dict[str, object]] = []
    old = plan["existing_notebook"]
    snapshot = ROOT / old["snapshot"]
    retired = ROOT / old["retired_store"]
    retained_files = ROOT / old["retained_files"]
    for source in retained_files.rglob("*"):
        if source.is_file():
            copied = runtime / "files" / source.relative_to(retained_files)
            if not copied.is_file() or _sha(source) != _sha(copied):
                errors.append(f"retained file copy differs: {source.name}")
    if digest(snapshot) != old["snapshot_sha256"] or digest(retired) != old["retired_store_sha256"]:
        errors.append("protected historical database changed")
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        errors.append("production selector changed")
    authority = SQLiteNotebookScopeAuthority(runtime / "acl.db")
    actor = UUID(str(plan["disposable_actor_id"]))
    ids = notebook_ids(plan)
    with _read(snapshot, immutable=True) as original, _read(runtime / "mnemo.db") as current:
        original_rows = original.execute(
            "SELECT source_id,notebook_id,document_id,created_at FROM sources "
            "WHERE notebook_id=? ORDER BY source_id",
            (old["id"],),
        ).fetchall()
        current_rows = current.execute(
            "SELECT source_id,notebook_id,document_id,created_at FROM sources "
            "WHERE notebook_id=? ORDER BY source_id",
            (old["id"],),
        ).fetchall()
        if original_rows != current_rows or len(original_rows) != 24:
            errors.append("existing notebook source memberships differ from protected snapshot")
        for table, fields in (
            ("documents", "document_id,current_hash,current_version_id,status,updated_at"),
            ("document_versions", "version_id,document_id,content_hash,status"),
            ("chunks", "id,document_id,version_id,text,position_chunk_index"),
        ):
            query = f"SELECT {fields} FROM {table} ORDER BY 1"
            if original.execute(query).fetchall() != current.execute(query).fetchall():
                errors.append(f"retained {table} changed from the recovery snapshot")
        if current.execute("SELECT COUNT(*) FROM notebooks").fetchone()[0] != 4:
            errors.append("disposable store does not contain exactly four notebooks")
        if (
            current.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            != original.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        ):
            errors.append("existing shared document population changed")
        for nb in (UUID(str(old["id"])), *ids.values()):
            if authority.active_role(actor, nb) != "owner" or authority.revision(nb) is None:
                errors.append(f"disposable owner/revision missing: {nb}")
        if authority.permits(UUID(int=0), UUID(str(old["id"]))) or any(
            authority.permits(UUID(int=0), nb) for nb in ids.values()
        ):
            errors.append("ungranted principal has notebook access")
        if current.execute(
            "SELECT COUNT(*) FROM (SELECT notebook_id,document_id,COUNT(*) n "
            "FROM sources GROUP BY notebook_id,document_id HAVING n>1)"
        ).fetchone()[0]:
            errors.append("duplicate notebook/document source association")
        if current.execute(
            "SELECT COUNT(*) FROM chunks c LEFT JOIN document_versions v USING(version_id) "
            "WHERE v.version_id IS NULL OR c.document_id!=v.document_id"
        ).fetchone()[0]:
            errors.append("orphan or cross-document chunk")
        if current.execute(
            "SELECT COUNT(*) FROM chunks c LEFT JOIN fts_chunks f ON f.rowid=c.rowid "
            "WHERE f.rowid IS NULL"
        ).fetchone()[0]:
            errors.append("missing canonical FTS rows")
        active = current.execute(
            "SELECT alias_set_digest FROM active_multilingual_v2_alias_set"
        ).fetchall()
        receipt_file = logs / "provider_activation.json"
        receipt = (
            json.loads(receipt_file.read_text(encoding="utf-8")) if receipt_file.exists() else {}
        )
        build_file = logs / "provider_results.json"
        build = json.loads(build_file.read_text(encoding="utf-8")) if build_file.exists() else {}
        if (
            build.get("model_revision") != MODEL_REVISION
            or build.get("model_identity") != "BAAI/bge-m3"
            or build.get("dimensions") != 1024
            or build.get("distance_metric") != "cosine"
            or build.get("normalized") is not True
            or build.get("embedding_count") != build.get("items")
        ):
            errors.append("BGE-M3 model revision or vector contract receipt differs")
        if require_active_alias:
            if len(active) != 1 or active[0][0] != receipt.get("alias_set_digest"):
                errors.append("disposable active alias does not match its activation receipt")
        elif active or receipt_file.exists():
            errors.append("pre-activation audit requires no active alias or activation receipt")
        all_generations = current.execute(
            "SELECT capability,generation_id,model_identity,dimensions,state,item_count "
            "FROM index_generations WHERE capability IN (?,?,?,?)",
            CAPABILITIES,
        ).fetchall()
        receipt_ids = set(
            receipt.get("generation_ids", ())
            if require_active_alias
            else (build.get("generations", {}).get(key) for key in CAPABILITIES)
        )
        generations = [row for row in all_generations if row[1] in receipt_ids]
        if any(row[4] == "failed" for row in all_generations if row[1] not in receipt_ids):
            warnings.append("superseded failed disposable generation retained for audit")
        if (require_active_alias and not active) or len({row[0] for row in generations}) != 4:
            errors.append("Full V2 alias or four-capability generation set missing")
        if {row[1] for row in generations} != receipt_ids or len(generations) != 4:
            errors.append("generation identities differ from the active alias receipt")
        if any(
            row[4] != "ready" or (row[0] in CAPABILITIES[2:] and row[3] != 1024)
            for row in generations
        ):
            errors.append("generation lifecycle or vector dimensions invalid")
        for capability, generation_id, *_ in generations:
            versions = {
                row[0]
                for row in current.execute(
                    "SELECT source_id FROM index_generation_sources "
                    "WHERE generation_id=? AND source_kind='version'",
                    (generation_id,),
                )
            }
            expected_versions = {
                row[0] for row in current.execute("SELECT version_id FROM document_versions")
            }
            if versions != expected_versions:
                errors.append(f"{capability}: source-version generation coverage differs")
            coverage = current.execute(
                "SELECT expected_count,succeeded_count,failed_count,skipped_count,"
                "provenance_complete,authorization_compatible "
                "FROM multilingual_coverage_manifests_v2 WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
            if (
                not coverage
                or coverage[0] != coverage[1]
                or coverage[2:4] != (0, 0)
                or coverage[4:] != (1, 1)
            ):
                errors.append(f"{capability}: incomplete or incompatible coverage receipt")
        for language, notebook_id in ids.items():
            wanted = plan["notebooks"][language]["files"]
            associations = current.execute(
                "SELECT COUNT(*) FROM sources WHERE notebook_id=?", (str(notebook_id),)
            ).fetchone()[0]
            if associations != len(wanted):
                errors.append(
                    f"{language}: expected {len(wanted)} sources, observed {associations}"
                )
            for filename in wanted:
                expected_hash = records[filename]["sha256"]
                file_path = (
                    ROOT
                    / "evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus"
                    / filename
                )
                if _sha(file_path) != expected_hash:
                    errors.append(f"source changed: {filename}")
                rows = current.execute(
                    "SELECT s.source_id,d.document_id,d.current_version_id,d.status,v.content_hash "
                    "FROM sources s JOIN documents d ON d.document_id=s.document_id "
                    "JOIN document_versions v ON v.version_id=d.current_version_id "
                    "WHERE s.notebook_id=? AND d.current_hash=?",
                    (str(notebook_id), expected_hash),
                ).fetchall()
                if len(rows) != 1 or rows[0][3] != "indexed" or rows[0][4] != expected_hash:
                    errors.append(f"association/version/hash invalid: {language}/{filename}")
                    file_rows.append({"language": language, "filename": filename, "status": "FAIL"})
                    continue
                source_id, document_id, version_id, _, _ = rows[0]
                complete = validate_reused_document(
                    original,
                    current,
                    content_hash=str(expected_hash),
                    parsed_root=runtime / "files",
                    model_revision=MODEL_REVISION,
                )
                if complete["status"] != "PASS":
                    errors.append(f"reused document incomplete: {filename}: {complete['errors']}")
                chunks = current.execute(
                    "SELECT id,text,position_chunk_index,source_start_ordinal,"
                    "source_end_ordinal FROM chunks "
                    "WHERE document_id=? AND version_id=? ORDER BY position_chunk_index",
                    (document_id, version_id),
                ).fetchall()
                if not chunks or any(not str(row[1]).strip() for row in chunks):
                    errors.append(f"no substantive persisted chunks: {filename}")
                duplicate = len({row[0] for row in chunks}) != len(chunks)
                if duplicate:
                    errors.append(f"duplicate chunk identity: {filename}")
                parsed_path = (
                    runtime / "files/parsed" / str(version_id)[:8] / f"{version_id}.ir.json"
                )
                languages: dict[str, int] = {}
                if parsed_path.is_file():
                    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
                    blocks = parsed.get("blocks", [])
                    for block in blocks:
                        label = str(block.get("language") or parsed.get("language") or "und")
                        languages[label] = languages.get(label, 0) + 1
                    if any(
                        row[3] is None or row[4] is None or not 0 <= row[3] <= row[4] < len(blocks)
                        for row in chunks
                    ):
                        errors.append(f"chunk source-block boundary invalid: {filename}")
                else:
                    errors.append(f"parsed IR is missing: {filename}")
                positions = current.execute(
                    "SELECT position_section_index,position_chunk_index FROM chunks "
                    "WHERE document_id=? AND version_id=? "
                    "ORDER BY position_section_index,position_chunk_index",
                    (document_id, version_id),
                ).fetchall()
                if len(positions) != len(set(positions)) or positions != sorted(positions):
                    errors.append(f"chunk position order or uniqueness invalid: {filename}")
                repeated_text = len(chunks) - len({str(row[1]) for row in chunks})
                if repeated_text:
                    warnings.append(f"{filename}: {repeated_text} repeated-text chunk positions")
                sample = [
                    {
                        "chunk_id": row[0],
                        "text_sha256": hashlib.sha256(str(row[1]).encode()).hexdigest(),
                        "characters": len(str(row[1])),
                        "position": row[2],
                    }
                    for row in (chunks[:1] + chunks[-1:] if len(chunks) > 1 else chunks)
                ]
                chunk_rows.append(
                    {
                        "language": language,
                        "filename": filename,
                        "source_id": source_id,
                        "document_id": document_id,
                        "version_id": version_id,
                        "chunk_count": len(chunks),
                        "parsed_language_labels": languages,
                        "repeated_text_positions": repeated_text,
                        "representative_chunks": sample,
                    }
                )
                file_rows.append(
                    {
                        "language": language,
                        "filename": filename,
                        "source_id": source_id,
                        "document_id": document_id,
                        "version_id": version_id,
                        "chunk_count": len(chunks),
                        "parsed_language_labels": languages,
                        "status": "PASS" if chunks and not duplicate else "FAIL",
                    }
                )
        if current.execute("SELECT COUNT(*) FROM sources").fetchone()[0] != 44:
            errors.append("global source count is not 24 retained + 20 new")
        with _read(runtime / "acl.db") as acl:
            source_states = acl.execute(
                "SELECT state,COUNT(*) FROM source_ingestion_intents GROUP BY state"
            ).fetchall()
            grants = set(
                acl.execute(
                    "SELECT actor_id,notebook_id,role,status FROM notebook_grants"
                ).fetchall()
            )
            expected_grants = {
                (str(actor), str(notebook), "owner", "active")
                for notebook in (UUID(str(old["id"])), *ids.values())
            }
            if grants != expected_grants:
                errors.append("disposable ACL has unexpected or missing grants")
            if acl.execute("SELECT COUNT(*) FROM notebook_create_intents").fetchone()[0]:
                errors.append("unrecovered notebook creation intent remains")
            if acl.execute("SELECT COUNT(*) FROM retired_notebook_ids").fetchone()[0]:
                errors.append("unexpected disposable notebook tombstone")
        if any(state != "published" for state, _count in source_states):
            errors.append("unfinished or quarantined source ingestion intent remains")
        publication_file = logs / "publication_states.json"
        publications = (
            json.loads(publication_file.read_text(encoding="utf-8"))
            if publication_file.exists()
            else {}
        )
        for language, notebook_id in ids.items():
            for filename in plan["notebooks"][language]["files"]:
                entry = publications.get(filename, {})
                association = current.execute(
                    "SELECT d.document_id,d.current_version_id,d.current_hash "
                    "FROM sources s JOIN documents d ON d.document_id=s.document_id "
                    "WHERE s.source_id=? AND s.notebook_id=?",
                    (entry.get("source_id"), str(notebook_id)),
                ).fetchall()
                if (
                    entry.get("state") != "PUBLISHED"
                    or entry.get("notebook_id") != str(notebook_id)
                    or entry.get("sha256") != records[filename]["sha256"]
                    or not entry.get("source_id")
                    or association
                    != [
                        (
                            entry.get("document_id"),
                            entry.get("version_id"),
                            records[filename]["sha256"],
                        )
                    ]
                ):
                    errors.append(f"publication state is not verified: {filename}")
        modality = {
            table: current.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "asset_occurrences",
                "ocr_results",
                "vision_results",
                "visual_embeddings",
            )
        }
        embedding_generation = next(
            (row[1] for row in generations if row[0] == "multilingual_embedding_v2"), None
        )
        modality["multilingual_embeddings_v2"] = current.execute(
            "SELECT COUNT(*) FROM multilingual_embeddings_v2 WHERE generation_id=?",
            (embedding_generation,),
        ).fetchone()[0]
        if modality["multilingual_embeddings_v2"] == 0:
            errors.append("real Full V2 embeddings were not persisted")
        if embedding_generation is not None:
            if current.execute(
                "SELECT COUNT(*) FROM multilingual_embeddings_v2 e "
                "LEFT JOIN sources s ON s.source_id=e.source_id AND s.notebook_id=e.notebook_id "
                "LEFT JOIN documents d ON d.document_id=e.document_id "
                "WHERE e.generation_id=? AND (s.source_id IS NULL "
                "OR s.document_id!=e.document_id OR d.current_version_id!=e.version_id)",
                (embedding_generation,),
            ).fetchone()[0]:
                errors.append("Full V2 embedding has orphaned or cross-version source ancestry")
            if current.execute(
                "SELECT COUNT(*) FROM sources s WHERE NOT EXISTS ("
                "SELECT 1 FROM multilingual_embeddings_v2 e WHERE e.generation_id=? "
                "AND e.notebook_id=s.notebook_id AND e.source_id=s.source_id "
                "AND e.document_id=s.document_id)",
                (embedding_generation,),
            ).fetchone()[0]:
                errors.append("Full V2 generation omits a notebook/source membership")
        if generations:
            expected_embeddings = next(
                (row[5] for row in generations if row[0] == "multilingual_embedding_v2"), None
            )
            if modality["multilingual_embeddings_v2"] != expected_embeddings:
                errors.append("persisted embedding count differs from generation receipt")
        if any(
            modality[table] != original.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("asset_occurrences", "ocr_results", "vision_results", "visual_embeddings")
        ):
            warnings.append("historical modality counts changed; inspect before claiming reuse")
    if write_artifacts:
        _write(logs / "file_audit.json", file_rows)
        _write(logs / "chunk_audit_manifest.json", chunk_rows)
    return {
        "schema": "mnemo.phase86-four-notebook-post-ingestion-audit/1",
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
        "existing_notebook_id": old["id"],
        "new_notebook_ids": {key: str(value) for key, value in ids.items()},
        "file_count": len(file_rows),
        "modality_counts": modality,
        "source_ingestion": "deduplicated governed associations over pre-existing parsed documents",
        "historical_ocr_vision_clip": "reused; not rerun",
        "production_selector": "UNINDEXED",
    }


def main() -> int:
    from scripts.run_phase86_four_notebooks import preflight, run_paths

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    plan, records = preflight()
    _, runtime, logs = run_paths(plan)
    if not runtime.is_dir() or not logs.is_dir():
        print("NOT_VERIFIABLE: ingestion run does not exist")
        return 2
    result = audit(plan, records, runtime, logs)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
