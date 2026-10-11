"""Read-only, fail-closed inventory for a proposed legacy notebook index reset.

This is deliberately not a delete command. Serving retirement and a complete
dependency-ordered, transactional executor are separate prerequisites.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tomllib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


@dataclass(frozen=True, slots=True)
class LegacyResetTarget:
    database: Path
    notebook_ids: tuple[UUID, ...]
    expected_sha256: str

    def __post_init__(self) -> None:
        if not self.notebook_ids or len(set(self.notebook_ids)) != len(self.notebook_ids):
            raise ValueError("target notebook allowlist is empty or duplicated")
        if len(self.expected_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.expected_sha256
        ):
            raise ValueError("database fingerprint must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class LegacyResetInventory:
    database: str
    sha256: str
    notebook_ids: tuple[str, ...]
    counts: dict[str, int]
    cross_target_shared_documents: int
    blockers: tuple[str, ...]


_COUNT_TABLES = (
    "notebooks",
    "sources",
    "documents",
    "document_versions",
    "chunks",
    "asset_catalog",
    "asset_occurrences",
    "asset_derivations",
    "document_binary_references",
    "ocr_results",
    "ocr_regions",
    "ocr_projection_rows",
    "vision_results",
    "vision_text_projection_rows",
    "visual_embeddings",
    "visual_vector_projection_rows",
    "multilingual_embeddings",
    "multilingual_embeddings_v2",
    "language_text_projection_rows_v2",
    "structured_table_projections",
    "structured_table_cells",
    "index_generations",
    "active_index_generations",
    "multilingual_v2_alias_sets",
    "active_multilingual_v2_alias_set",
    "final_qa_v2_executions",
    "notes",
    "sessions",
    "citations",
)


def _configured_authority_references(workspace: Path, database: Path) -> list[str]:
    """Check known active configuration; absence is not proof of no consumers."""
    references: list[str] = []
    production = workspace / "config/production/full_multilingual_v2.production.json"
    if production.is_file():
        raw = json.loads(production.read_text(encoding="utf-8"))
        value = raw.get("corpus", {}).get("database_path")
        if isinstance(value, str) and (workspace / value).resolve() == database:
            references.append("production_manifest")
    core_config = workspace / "mnemo.toml"
    if core_config.is_file():
        with core_config.open("rb") as stream:
            raw_core = tomllib.load(stream)
        value = raw_core.get("storage", {}).get("sqlite", {}).get("path")
        if isinstance(value, str) and (workspace / value).resolve() == database:
            references.append("core_runtime_config")
    registry = workspace / "scratch/evaluation_notebooks/registry.json"
    if registry.is_file():
        raw = json.loads(registry.read_text(encoding="utf-8"))
        entries = raw.get("notebooks", {})
        if isinstance(entries, dict):
            for alias, entry in entries.items():
                if not isinstance(entry, dict):
                    continue
                store = entry.get("store")
                if (
                    isinstance(store, str)
                    and (workspace / store / "mnemo.db").resolve() == database
                ):
                    references.append(f"evaluation_registry:{alias}")
    return references


def inspect_legacy_reset_target(
    *, workspace: Path, target: LegacyResetTarget
) -> LegacyResetInventory:
    """Inspect exact allowlisted target without opening SQLite for write.

    Immutable mode is used only when there is no WAL. A WAL-bearing store is
    read through SQLite's read-only WAL-aware connection; its sidecar remains
    a blocker for mutation until a consistent snapshot is established.
    """
    root = workspace.resolve(strict=True)
    raw_path = target.database if target.database.is_absolute() else root / target.database
    if _linked(root) or any(_linked(parent) for parent in (raw_path, *raw_path.parents)):
        raise ValueError("linked reset target or ancestor is not allowed")
    database = raw_path.resolve(strict=True)
    if not database.is_file() or database.suffix != ".db":
        raise ValueError("reset target is not a regular SQLite database")
    relative = database.relative_to(root)
    if not relative.parts or relative.parts[0] not in {"data", "scratch"}:
        raise ValueError("reset target is outside governed index roots")
    actual_hash = _sha256(database)
    blockers: list[str] = []
    if actual_hash != target.expected_sha256:
        blockers.append("database_fingerprint_changed")
    wal_present = False
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.exists() and sidecar.stat().st_size > 0:
            blockers.append(f"nonempty_{suffix[1:]}")
            if suffix == "-wal":
                wal_present = True
    query = "?mode=ro" if wal_present else "?mode=ro&immutable=1"
    connection = sqlite3.connect(database.as_uri() + query, uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"notebooks", "sources", "documents", "document_versions"} <= tables:
            raise ValueError("target does not expose the expected Mnemo index schema")
        actual_ids = tuple(
            str(row[0])
            for row in connection.execute("SELECT notebook_id FROM notebooks ORDER BY 1")
        )
        expected_ids = tuple(sorted(str(value) for value in target.notebook_ids))
        if actual_ids != expected_ids:
            blockers.append("notebook_allowlist_does_not_cover_store")
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _COUNT_TABLES
            if table in tables
        }
        shared = int(
            connection.execute(
                "SELECT COUNT(*) FROM (SELECT document_id FROM sources "
                "GROUP BY document_id HAVING COUNT(DISTINCT notebook_id)>1)"
            ).fetchone()[0]
        )
        orphaned = int(
            connection.execute(
                "SELECT COUNT(*) FROM documents d WHERE NOT EXISTS "
                "(SELECT 1 FROM sources s WHERE s.document_id=d.document_id)"
            ).fetchone()[0]
        )
        if orphaned:
            blockers.append("unowned_global_documents")
        for family in (
            "notes",
            "sessions",
            "citations",
            "final_qa_v2_executions",
            "active_index_generations",
            "active_multilingual_v2_alias_set",
        ):
            if counts.get(family, 0):
                blockers.append(f"retained_or_active:{family}")
    finally:
        connection.close()
    blockers.extend(_configured_authority_references(root, database))
    blockers.append("live_consumer_quiescence_not_established")
    return LegacyResetInventory(
        database=str(database),
        sha256=actual_hash,
        notebook_ids=actual_ids,
        counts=counts,
        cross_target_shared_documents=shared,
        blockers=tuple(sorted(set(blockers))),
    )
