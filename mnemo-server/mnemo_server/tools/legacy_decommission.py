"""Bounded full-store retirement for obsolete Mnemo notebook indexes.

Only a store whose *entire* notebook/generation/alias inventory is allowlisted
can be cleared. Partial-store retirement is deliberately refused; it needs a
separate reference-aware implementation. Original blobs and source files are
never touched. Registry unpublication precedes database mutation and remains
retired if a later step fails, which is the safe partial-failure direction.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mnemo_server.evaluation.canonical_json import canonical_json_sha256_v1

from .windows_open_handles import processes_using_files

_VIRTUAL_FTS = frozenset(
    {
        "fts_chunks",
        "fts_chunk_titles",
        "fts_notes",
        "ocr_fts",
        "vision_text_fts",
        "language_text_fts",
        "language_text_fts_v2",
    }
)
_EXTERNAL_FTS = frozenset({"fts_chunks", "fts_notes"})
_INDEX_TABLES = frozenset(
    """active_index_generations active_multilingual_v2_alias_set asset_catalog
    asset_derivations asset_gc_references asset_occurrences chunks citations
    document_binary_references document_versions documents evaluation_text_embeddings
    evidence_citations_v2
    final_qa_execution_snapshots final_qa_executions final_qa_v2_executions
    final_qa_v2_snapshots index_generation_coverage index_generation_sources
    index_generations insights language_derivations language_observations
    language_observations_v2 language_text_projection_rows
    language_text_projection_rows_v2 multilingual_coverage_manifests_v2
    multilingual_embeddings multilingual_embeddings_v2
    multilingual_v2_activation_records multilingual_v2_alias_sets notebooks
    notes ocr_failures ocr_language_observations ocr_projection_rows ocr_regions
    ocr_results processing_attempts processing_checkpoints processing_cost_ledger
    processing_jobs processing_progress_events processing_results
    representation_observations_v1 representation_transformations_v1
    retrieval_version_metadata script_observations_v1 sessions sources
    structured_table_cells structured_table_projections turns v2_build_checkpoints
    v2_build_exclusions v2_build_runs vision_results vision_text_projection_rows
    visual_embeddings visual_vector_projection_rows""".split()  # noqa: SIM905
)
_USER_DATA_TABLES = frozenset(
    {
        "notes",
        "sessions",
        "turns",
        "citations",
        "insights",
        "final_qa_executions",
        "final_qa_execution_snapshots",
        "final_qa_v2_executions",
        "final_qa_v2_snapshots",
        "evidence_citations_v2",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _inside(root: Path, path: Path) -> Path:
    base = root.resolve(strict=True)
    raw = path if path.is_absolute() else base / path
    if any(
        part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
        for part in (raw, *raw.parents)
        if part == base or part.is_relative_to(base)
    ):
        raise ValueError("decommission path contains a link or junction")
    resolved = raw.resolve(strict=False)
    if not resolved.is_relative_to(base):
        raise ValueError("decommission path escapes workspace")
    return resolved


def _tables(db: sqlite3.Connection) -> set[str]:
    names = {
        str(row[0])
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if not str(row[0]).startswith("sqlite_")
    }
    return {
        name for name in names if not any(name.startswith(prefix + "_") for prefix in _VIRTUAL_FTS)
    }


def _count(db: sqlite3.Connection, table: str) -> int:
    # Table names come only from sqlite_master and the fixed allowlist.
    return int(db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


@dataclass(frozen=True, slots=True)
class FullStoreTarget:
    database: Path
    expected_sha256: str
    notebook_ids: tuple[str, ...]
    generation_ids: tuple[str, ...]
    alias_digests: tuple[str, ...]
    snapshot: Path
    registry: Path | None = None
    registry_aliases: tuple[str, ...] = ()
    expected_registry_sha256: str | None = None
    expected_wal_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class FullStorePlan:
    database: Path
    snapshot: Path
    before_sha256: str
    wal_sha256: str | None
    counts: dict[str, int]
    notebook_ids: tuple[str, ...]
    generation_ids: tuple[str, ...]
    alias_digests: tuple[str, ...]
    registry: Path | None
    registry_aliases: tuple[str, ...]
    registry_sha256: str | None


def _registry_document(target: FullStoreTarget, root: Path) -> tuple[Path | None, str | None]:
    if target.registry is None:
        if target.registry_aliases or target.expected_registry_sha256 is not None:
            raise ValueError("registry allowlist is inconsistent")
        return None, None
    registry = _inside(root, target.registry)
    digest = _sha256(registry)
    if digest != target.expected_registry_sha256:
        raise ValueError("registry fingerprint changed")
    payload = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("notebooks"), dict):
        raise ValueError("registry is malformed")
    aliases = payload["notebooks"]
    for alias in target.registry_aliases:
        entry = aliases.get(alias)
        if not isinstance(entry, dict):
            raise ValueError("allowlisted registry alias is missing")
        if str(entry.get("notebook_id")) not in target.notebook_ids:
            raise ValueError("registry alias notebook is not allowlisted")
        store = _inside(root, Path(str(entry.get("store", ""))))
        if store / "mnemo.db" != _inside(root, target.database):
            raise ValueError("registry alias selects another store")
    if not target.registry_aliases:
        raise ValueError("registry target has no alias allowlist")
    return registry, digest


def dry_run_full_store(*, workspace: Path, target: FullStoreTarget) -> FullStorePlan:
    """WAL-aware logical inventory; no index rows are changed.

    SQLite read-only mode may touch SHM coordination sidecars. Capture their
    metadata separately and never treat a base-file hash as a WAL digest.
    """
    root = workspace.resolve(strict=True)
    database = _inside(root, target.database)
    snapshot = _inside(root, target.snapshot)
    if (
        not database.is_file()
        or database.suffix != ".db"
        or database == snapshot
        or snapshot.exists()
        or not snapshot.is_relative_to(root / "scratch")
    ):
        raise ValueError("decommission database or snapshot path is invalid")
    before = _sha256(database)
    if before != target.expected_sha256:
        raise ValueError("database fingerprint changed")
    wal = Path(str(database) + "-wal")
    wal_digest = _sha256(wal) if wal.is_file() and wal.stat().st_size else None
    if wal_digest != target.expected_wal_sha256:
        raise ValueError("WAL fingerprint changed or was not allowlisted")
    registry, registry_digest = _registry_document(target, root)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        tables = _tables(connection)
        if "schema_versions" not in tables or not {"notebooks", "sources", "documents"} <= tables:
            raise ValueError("not a supported Mnemo index schema")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("index database failed integrity check")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("index database has pre-existing foreign-key violations")
        unknown = tables - _INDEX_TABLES - _VIRTUAL_FTS - {"schema_versions"}
        if unknown:
            raise ValueError("unclassified index tables: " + ",".join(sorted(unknown)))
        counts = {name: _count(connection, name) for name in sorted(tables - {"schema_versions"})}
        if any(counts.get(name, 0) for name in _USER_DATA_TABLES):
            raise ValueError("retained user or execution data prevents full-store cleanup")
        notebooks = tuple(
            str(row[0])
            for row in connection.execute("SELECT notebook_id FROM notebooks ORDER BY 1")
        )
        if not notebooks or notebooks != tuple(sorted(target.notebook_ids)):
            raise ValueError("notebook allowlist does not exactly cover the store")
        generations = (
            tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT generation_id FROM index_generations ORDER BY 1"
                )
            )
            if "index_generations" in tables
            else ()
        )
        if generations != tuple(sorted(target.generation_ids)):
            raise ValueError("generation allowlist does not exactly cover the store")
        aliases = (
            tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT alias_set_digest FROM multilingual_v2_alias_sets ORDER BY 1"
                )
            )
            if "multilingual_v2_alias_sets" in tables
            else ()
        )
        if aliases != tuple(sorted(target.alias_digests)):
            raise ValueError("alias allowlist does not exactly cover the store")
        if "active_index_generations" in tables:
            active = {
                str(row[0])
                for row in connection.execute("SELECT generation_id FROM active_index_generations")
            }
            if not active.issubset(set(generations)):
                raise ValueError("active generation pointer is outside allowlist")
        if "sources" in tables:
            unowned = int(
                connection.execute(
                    "SELECT COUNT(*) FROM documents d WHERE NOT EXISTS "
                    "(SELECT 1 FROM sources s WHERE s.document_id=d.document_id)"
                ).fetchone()[0]
            )
            if unowned:
                raise ValueError("unowned global document requires separate reference analysis")
    finally:
        connection.close()
    return FullStorePlan(
        database,
        snapshot,
        before,
        wal_digest,
        counts,
        notebooks,
        generations,
        aliases,
        registry,
        target.registry_aliases,
        registry_digest,
    )


def _deletion_order(db: sqlite3.Connection, tables: set[str]) -> list[str]:
    remaining = set(tables)
    parents = {
        name: {
            str(row[2])
            for row in db.execute(f'PRAGMA foreign_key_list("{name}")')
            if str(row[2]) in tables and str(row[2]) != name
        }
        for name in tables
    }
    result: list[str] = []
    while remaining:
        candidates = sorted(
            name for name in remaining if not any(name in parents[other] for other in remaining)
        )
        if not candidates:
            raise ValueError("cyclic index dependency graph")
        selected = candidates[0]
        remaining.remove(selected)
        result.append(selected)
    return result


def _retire_registry(plan: FullStorePlan, root: Path) -> None:
    if plan.registry is None:
        return
    registry = plan.registry
    if _sha256(registry) != plan.registry_sha256:
        raise ValueError("registry changed after dry run")
    payload: dict[str, Any] = json.loads(registry.read_text(encoding="utf-8"))
    entries = payload["notebooks"]
    for alias in plan.registry_aliases:
        if alias not in entries:
            raise ValueError("registry alias disappeared")
        del entries[alias]
    unsigned = {key: value for key, value in payload.items() if key != "registry_digest"}
    payload["registry_digest"] = canonical_json_sha256_v1(unsigned)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".retiring-registry-", dir=registry.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if not registry.is_relative_to(root):
            raise ValueError("registry left workspace")
        os.replace(temporary, registry)
    finally:
        temporary.unlink(missing_ok=True)


def _receipt_path(snapshot: Path) -> Path:
    return Path(str(snapshot) + ".receipt.json")


def _completed_receipt(root: Path, target: FullStoreTarget) -> dict[str, object] | None:
    database = _inside(root, target.database)
    snapshot = _inside(root, target.snapshot)
    receipt_path = _receipt_path(snapshot)
    if not receipt_path.is_file():
        return None
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "COMPLETE"
        or payload.get("database") != str(database)
        or payload.get("before_sha256") != target.expected_sha256
        or payload.get("notebook_ids") != list(target.notebook_ids)
        or payload.get("generation_ids") != list(target.generation_ids)
        or payload.get("alias_digests") != list(target.alias_digests)
        or not snapshot.is_file()
        or payload.get("snapshot_sha256") != _sha256(snapshot)
    ):
        raise ValueError("decommission receipt or recovery snapshot is incompatible")
    if not database.is_file():
        raise ValueError("retired database disappeared")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        tables = _tables(connection)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("retired database integrity changed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("retired database has foreign-key violations")
        if any(_count(connection, name) for name in tables & (_INDEX_TABLES | _VIRTUAL_FTS)):
            raise ValueError("retired index has reappeared")
    finally:
        connection.close()
    if target.registry is not None:
        registry = _inside(root, target.registry)
        entries = json.loads(registry.read_text(encoding="utf-8")).get("notebooks", {})
        if any(alias in entries for alias in target.registry_aliases):
            raise ValueError("retired evaluation alias has reappeared")
    return {**payload, "status": "ALREADY_COMPLETE"}


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".retirement-receipt-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def execute_full_store(*, workspace: Path, target: FullStoreTarget) -> dict[str, object]:
    """Snapshot, unpublish, transactionally clear, and verify one exact store.

    Refuses partial allowlists, user data, unknown schema, changed fingerprints,
    and OS-reported file consumers. A failed transaction rolls back; a registry
    unpublication is deliberately not rolled back because re-exposure would
    be unsafe. The snapshot is the recovery evidence.
    """
    root = workspace.resolve(strict=True)
    completed = _completed_receipt(root, target)
    if completed is not None:
        return completed
    plan = dry_run_full_store(workspace=workspace, target=target)
    paths = tuple(
        path
        for path in (plan.database, *(Path(str(plan.database) + s) for s in ("-wal", "-shm")))
        if path.exists()
    )
    consumers = processes_using_files(paths)
    if consumers:
        raise RuntimeError("DECOMMISSION_CONSUMERS_ACTIVE:" + ",".join(map(str, consumers)))
    # A second preflight closes the time window between file-user inspection
    # and snapshot. BEGIN EXCLUSIVE below excludes concurrent SQLite users.
    if dry_run_full_store(workspace=workspace, target=target) != plan:
        raise ValueError("decommission inventory changed")
    plan.snapshot.parent.mkdir(parents=True, exist_ok=True)
    if plan.snapshot.exists():
        raise ValueError("snapshot already exists")
    source = sqlite3.connect(plan.database.as_uri() + "?mode=ro", uri=True)
    snapshot = sqlite3.connect(plan.snapshot)
    try:
        source.backup(snapshot)
        if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("snapshot integrity check failed")
    finally:
        snapshot.close()
        source.close()
    snapshot_digest = _sha256(plan.snapshot)
    if plan.registry is not None:
        registry_backup = Path(str(plan.snapshot) + ".registry.json")
        if registry_backup.exists():
            raise ValueError("registry snapshot already exists")
        registry_backup.write_bytes(plan.registry.read_bytes())
        if _sha256(registry_backup) != plan.registry_sha256:
            raise RuntimeError("registry snapshot fingerprint mismatch")
    _retire_registry(plan, workspace.resolve(strict=True))
    db = sqlite3.connect(plan.database, timeout=0)
    removed: dict[str, int] = {}
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN EXCLUSIVE")
        db.execute("PRAGMA defer_foreign_keys=ON")
        current_notebooks = tuple(
            str(row[0]) for row in db.execute("SELECT notebook_id FROM notebooks ORDER BY 1")
        )
        if current_notebooks != plan.notebook_ids:
            raise ValueError("notebook inventory changed before transaction")
        present = _tables(db)
        if {name: _count(db, name) for name in plan.counts} != plan.counts:
            raise ValueError("index row counts changed before transaction")
        for name in sorted((_VIRTUAL_FTS - _EXTERNAL_FTS) & present):
            removed[name] = db.execute(f'DELETE FROM "{name}"').rowcount
        for name in _deletion_order(db, (present & _INDEX_TABLES) - _VIRTUAL_FTS):
            removed[name] = db.execute(f'DELETE FROM "{name}"').rowcount
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("foreign-key violation during decommission")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity check failed during decommission")
        for name in sorted(present & _VIRTUAL_FTS):
            if _count(db, name):
                raise RuntimeError("stale FTS rows remain in " + name)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
    verify = sqlite3.connect(plan.database.as_uri() + "?mode=ro", uri=True)
    try:
        if verify.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("post-commit SQLite integrity check failed")
        if verify.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("post-commit foreign-key violation")
        if any(_count(verify, name) for name in present & (_INDEX_TABLES | _VIRTUAL_FTS)):
            raise RuntimeError("post-commit index rows remain")
    finally:
        verify.close()
    receipt: dict[str, object] = {
        "status": "COMPLETE",
        "database": str(plan.database),
        "before_sha256": plan.before_sha256,
        "after_sha256": _sha256(plan.database),
        "snapshot": str(plan.snapshot),
        "snapshot_sha256": snapshot_digest,
        "notebook_ids": list(plan.notebook_ids),
        "generation_ids": list(plan.generation_ids),
        "alias_digests": list(plan.alias_digests),
        "removed": removed,
    }
    _write_receipt(_receipt_path(plan.snapshot), receipt)
    return receipt
