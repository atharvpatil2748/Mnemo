"""Read-only, mandatory build-completeness gate for one fresh isolated notebook."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo.phase85.isolated_v2_identity import IsolatedV2DatabaseIdentityVerifier
from mnemo.phase85.profiles import ModelProfileDocument
from mnemo.phase85.rebuild_runtime import resolve_governed_rebuild_runtime
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore

from mnemo_server.tools.isolated_activation import REQUIRED, assess_generation_set
from mnemo_server.tools.isolated_rebuild import VerifiedSource, inspect_isolated_ingestion
from mnemo_server.tools.source_manifest import verify_source_manifest


async def _active_alias(database: Path) -> tuple[tuple[UUID, ...] | None, str | None]:
    store = SQLiteV2ReadOnlyRuntimeStore(database)
    await store.open()
    try:
        return (
            await store.resolve_active_multilingual_v2_generation_set(),
            await store.resolve_active_multilingual_v2_alias_digest(),
        )
    finally:
        await store.close()


def verify_rebuild_integrity(
    *,
    workspace: Path,
    runtime: Path,
    source_manifest: Path,
    expected_count: int,
    selected_relative_paths: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Require source/IR/asset/derivation/vector/alias completeness; never repair."""
    root = workspace.resolve(strict=True)
    runtime = runtime.resolve(strict=True)
    status = resolve_governed_rebuild_runtime(workspace=root, runtime=runtime)
    recorded = json.loads(source_manifest.read_text(encoding="utf-8"))
    if not isinstance(recorded, dict):
        raise ValueError("rebuild source manifest is invalid")
    manifest = verify_source_manifest(
        manifest=source_manifest, corpus=Path(recorded["corpus_root"])
    )
    manifest_sources = manifest["sources"]
    if len(manifest_sources) != expected_count:
        raise ValueError("rebuild source count differs from the governed manifest")
    expected_sources = manifest_sources
    if selected_relative_paths is not None:
        selected = set(selected_relative_paths)
        if len(selected) != len(selected_relative_paths):
            raise ValueError("duplicate canary source selection")
        expected_sources = [item for item in manifest_sources if item["relative_path"] in selected]
        if len(expected_sources) != len(selected):
            raise ValueError("canary source selection is outside the governed manifest")
    expected = Counter(
        (item["relative_path"], item["sha256"], item["byte_size"]) for item in expected_sources
    )
    actual = Counter(
        (item["relative_path"], item["sha256"], item["byte_size"]) for item in status["sources"]
    )
    if actual != expected:
        raise ValueError("rebuild source set differs from the governed manifest")
    owner = status.get("rebuild_owner")
    if (
        not isinstance(owner, dict)
        or owner.get("input_identity") != manifest["notebook_input_identity"]
        or owner.get("label") != manifest["label"]
    ):
        raise ValueError("rebuild source manifest does not match runtime owner")
    database = runtime / "mnemo.db"
    sources = tuple(VerifiedSource(**item) for item in status["sources"])
    ingestion = inspect_isolated_ingestion(
        database=database,
        files=runtime / "files",
        notebook_id=status["notebook_id"],
        sources=sources,
    )
    if ingestion["counts"]["sources"] != len(sources):
        raise ValueError("rebuild source membership count is incomplete")
    complete = json.loads((runtime / "complete-rebuild-status.json").read_text(encoding="utf-8"))
    multilingual = json.loads((runtime / "multilingual-stage.json").read_text(encoding="utf-8"))
    decision = json.loads((runtime / "activation-decision.json").read_text(encoding="utf-8"))
    serving = json.loads((runtime / "full-v2-serving.json").read_text(encoding="utf-8"))
    required_stages = (
        "canonical_ingestion",
        "paddleocr",
        "vision",
        "visual",
        "projections",
        "multilingual",
    )
    if (
        complete.get("notebook_id") != status["notebook_id"]
        or complete.get("activation")
        not in {"complete_v2_build_ready", "complete_v2_retrieval_ready"}
        or any(complete.get("stages", {}).get(stage) != "complete" for stage in required_stages)
    ):
        raise ValueError("rebuild stage report is incomplete or points to another notebook")
    generation_ids = {name: UUID(value) for name, value in complete["generations"].items()}
    component = (
        ModelProfileDocument.from_file(
            root / "config/model_profiles/full_multilingual_v2_profiles.toml"
        )
        .select("full_multilingual_v2_local_prebuild")
        .models["multilingual_embedding"]
    )
    coverage = assess_generation_set(
        database=database,
        notebook_id=UUID(status["notebook_id"]),
        generation_ids=generation_ids,
        vector_space=multilingual["vector_space"],
        embedding_model_identity=f"{component.model}@{component.revision}",
    )
    if not coverage["eligible_for_activation"] or not decision.get("active"):
        raise ValueError("rebuild generation coverage or activation is incomplete")
    if set(generation_ids) != set(REQUIRED):
        raise ValueError("rebuild generation set is incomplete")
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        active_rows = connection.execute(
            "SELECT a.generation_id,g.capability FROM active_index_generations a "
            "JOIN index_generations g ON g.generation_id=a.generation_id"
        ).fetchall()
        active_ids = {UUID(str(row[0])) for row in active_rows if row[1] != "structured_table"}
        if active_ids != set(generation_ids.values()):
            raise ValueError("rebuild active generation set differs from built generations")
        expected_tables: dict[tuple[str, int], int] = {}
        for version_id in (item["version_id"] for item in ingestion["sources"]):
            ir_path = runtime / "files" / "parsed" / version_id[:8] / f"{version_id}.ir.json"
            parsed = json.loads(ir_path.read_text(encoding="utf-8"))
            for block in parsed["blocks"]:
                if block["type"] == "table" and block["header_row_count"] > 0:
                    expected_tables[(version_id, block["ordinal"])] = (
                        len(block["rows"]) - block["header_row_count"]
                    )
        projected = connection.execute(
            "SELECT p.version_id,p.block_ordinal,p.row_count,g.state,a.generation_id "
            "FROM structured_table_projections p "
            "JOIN index_generations g ON g.generation_id=p.generation_id "
            "LEFT JOIN active_index_generations a ON a.generation_id=p.generation_id"
        ).fetchall()
        observed_tables = {(str(row[0]), int(row[1])): int(row[2]) for row in projected}
        if (
            observed_tables != expected_tables
            or len(projected) != len(expected_tables)
            or any(row[3] != "ready" or row[4] is None for row in projected)
        ):
            raise ValueError("rebuild structured-table projection coverage is incomplete")
        occurrence_rows = connection.execute(
            "SELECT o.occurrence_id,o.document_id,o.version_id,o.asset_id,"
            "a.content_hash FROM asset_occurrences o "
            "JOIN asset_catalog a ON a.asset_id=o.asset_id"
        ).fetchall()
        versions = {item["version_id"] for item in ingestion["sources"]}
        if any(str(row[2]) not in versions for row in occurrence_rows):
            raise ValueError("asset occurrence points outside the rebuilt versions")
    finally:
        connection.close()
    verifier = IsolatedV2DatabaseIdentityVerifier(workspace_root=root, runtime=runtime)
    artifact = verifier.artifact
    verifier.verify(expected_database_identity=artifact.database_identity)
    active_alias, alias_digest = asyncio.run(_active_alias(database))
    if (
        active_alias != artifact.generation_ids
        or alias_digest is None
        or serving.get("state") != "active_internal_only"
        or serving.get("alias_set_digest") != alias_digest
        or serving.get("notebook_id") != status["notebook_id"]
        or serving.get("generation_ids") != [str(item) for item in artifact.generation_ids]
        or complete.get("full_v2_serving", {}).get("alias_set_digest") != alias_digest
    ):
        raise ValueError("Full V2 serving composition is missing or stale")
    return {
        "schema": "mnemo.rebuild-integrity/1",
        "notebook_id": status["notebook_id"],
        "source_count": len(sources),
        "ir_and_chunk_ancestry": "pass",
        "asset_occurrences": len(occurrence_rows),
        "structured_table_projections": len(expected_tables),
        "representation_coverage": coverage["expected"],
        "multilingual_embedding_counts": coverage["embedding_counts"],
        "active_generations": {name: str(value) for name, value in generation_ids.items()},
        "full_v2_alias_digest": alias_digest,
        "status": "pass",
    }
