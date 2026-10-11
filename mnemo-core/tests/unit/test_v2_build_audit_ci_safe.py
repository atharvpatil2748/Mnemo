"""Run the governed build audit against a disposable, identity-shaped store."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest
from mnemo.interfaces.errors import IntegrityError
from mnemo.phase85.projections import ProjectionGenerationSpec
from mnemo.phase85.v2_index_build import FullMultilingualV2IndexBuildOperator, V2BuildArtifacts

PROPOSALS = (
    Path(__file__).resolve().parents[3]
    / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
)

EXPECTED_COUNTS = {
    "documents": 44,
    "document_versions": 44,
    "chunks": 2658,
    "ocr_regions": 402,
    "vision_results": 463,
    "language_observations_v2": 3523,
    "script_observations_v1": 3523,
    "representation_observations_v1": 3523,
    "v2_build_exclusions": 504,
    "language_text_projection_rows_v2": 3019,
    "multilingual_embeddings_v2": 3019,
    "multilingual_coverage_manifests_v2": 4,
    "multilingual_v2_alias_sets": 0,
    "active_multilingual_v2_alias_set": 0,
}


def _ready_audit_fixture(tmp_path: Path) -> tuple[Path, tuple[ProjectionGenerationSpec, ...]]:
    database = tmp_path / "isolated-audit.db"
    artifacts = V2BuildArtifacts.load(PROPOSALS)
    specs = tuple(
        ProjectionGenerationSpec.from_manifest_payload(item)
        for item in cast(list[dict[str, Any]], artifacts.build["generation_specifications"])
    )
    with closing(sqlite3.connect(database)) as connection, connection:
        for table, count in EXPECTED_COUNTS.items():
            connection.execute(f"CREATE TABLE {table}(value INTEGER)")
            connection.executemany(
                f"INSERT INTO {table} VALUES(?)", ((index,) for index in range(count))
            )
        connection.execute(
            "CREATE TABLE index_generations("
            "generation_id TEXT, capability TEXT, state TEXT, item_count INTEGER, checksum TEXT)"
        )
        connection.execute(
            "CREATE TABLE index_generation_coverage("
            "generation_id TEXT, expected_count INTEGER, succeeded_count INTEGER,"
            "failed_count INTEGER, skipped_count INTEGER, completeness TEXT)"
        )
        connection.execute("CREATE TABLE active_index_generations(capability TEXT)")
        for spec in specs:
            connection.execute(
                "INSERT INTO index_generations VALUES(?,?,?,?,?)",
                (str(spec.generation_id), spec.capability, "ready", 1, "checksum"),
            )
            connection.execute(
                "INSERT INTO index_generation_coverage VALUES(?,?,?,?,?,?)",
                (str(spec.generation_id), 1, 1, 0, 0, "complete"),
            )
    return database, specs


def test_governed_build_audit_accepts_only_complete_inactive_disposable_state(
    tmp_path: Path,
) -> None:
    database, specs = _ready_audit_fixture(tmp_path)
    operator = object.__new__(FullMultilingualV2IndexBuildOperator)
    before = database.read_bytes()
    report = operator._audit(database, specs)
    assert report["counts"] == EXPECTED_COUNTS
    assert len(cast(list[object], report["generations"])) == 4
    assert report["foreign_key_errors"] == []
    assert report["integrity_check"] == "ok"
    assert report["active_v2_aliases"] == 0
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing-row", "row counts do not reconcile"),
        ("not-ready", "not READY"),
        ("incomplete", "coverage is incomplete"),
        ("active", "alias was promoted"),
        ("orphan", "integrity audit failed"),
    ],
)
def test_governed_build_audit_rejects_partial_or_promoted_disposable_state(
    tmp_path: Path, mutation: str, message: str
) -> None:
    database, specs = _ready_audit_fixture(tmp_path)
    with closing(sqlite3.connect(database)) as connection, connection:
        if mutation == "missing-row":
            connection.execute("DELETE FROM chunks WHERE value=0")
        elif mutation == "not-ready":
            connection.execute("UPDATE index_generations SET state='building' WHERE rowid=1")
        elif mutation == "incomplete":
            connection.execute(
                "UPDATE index_generation_coverage SET completeness='partial' WHERE rowid=1"
            )
        elif mutation == "active":
            connection.execute("INSERT INTO active_index_generations VALUES('language_text_v2')")
        else:
            connection.executescript(
                "CREATE TABLE audit_parent(id INTEGER PRIMARY KEY);"
                "CREATE TABLE audit_child(parent_id INTEGER REFERENCES audit_parent(id));"
                "INSERT INTO audit_child VALUES(999);"
            )
    with pytest.raises(IntegrityError, match=message):
        object.__new__(FullMultilingualV2IndexBuildOperator)._audit(database, specs)
