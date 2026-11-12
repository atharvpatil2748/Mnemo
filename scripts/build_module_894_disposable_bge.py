"""Build real Full V2 BGE-M3 projections in one named disposable evaluation copy.

This is not a production rebuild or alias activation. The isolated builder owns
all generation writes; this wrapper only binds the evaluation path and receipts.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import UUID

from mnemo.phase85.isolated_multilingual import _items, build_isolated_multilingual

ROOT = Path(__file__).resolve().parents[1]
DISPOSABLE = ROOT / "scratch/module_894_disposable/eval-20261106-04"
NOTEBOOK = UUID("df9c20cf-85fe-529c-902e-2e9e68193fbe")
CACHE = Path("D:/Mnemo/phase8.5.11-models/huggingface/hub")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run() -> dict[str, object]:
    target = DISPOSABLE.resolve(strict=True)
    if target != DISPOSABLE or target.is_symlink():
        raise ValueError("unexpected disposable target")
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        raise ValueError("production selector changed")
    database = target / "mnemo.db"
    original = ROOT / "scratch/module_894_disposable/eval-20261106-01/mnemo.db"
    if _sha(database) != _sha(original):
        raise ValueError("disposable database is not an unchanged copy of eval-20261106-01")
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        source_versions = {
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT v.version_id FROM document_versions v "
                "JOIN sources s ON s.document_id=v.document_id WHERE s.notebook_id=?",
                (str(NOTEBOOK),),
            )
        }
    finally:
        connection.close()
    items = _items(database, NOTEBOOK)
    covered = {str(item.source.version_id) for item in items}
    exclusions = sorted(source_versions - covered)
    if not covered or covered | set(exclusions) != source_versions:
        raise ValueError("version census is inconsistent")
    parsed = list((target / "files/parsed").rglob("*.ir.json"))
    if len(parsed) != len(source_versions):
        raise ValueError("parsed IR coverage differs from source versions")
    prebuild = {
        "schema": "mnemo.module-894-disposable-bge-census/1",
        "database_sha256": _sha(database),
        "original_database_sha256": _sha(original),
        "notebook_id": str(NOTEBOOK),
        "source_version_count": len(source_versions),
        "embedding_eligible_version_ids": sorted(covered),
        "no_searchable_evidence_version_ids": exclusions,
        "evidence_item_count": len(items),
        "parsed_ir_count": len(parsed),
        "model_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "production_selector": "UNINDEXED",
    }
    # The frozen snapshot predates two columns now required by the existing
    # Full V2 manifest schema. Its table has no rows. Reconcile only this
    # copied evaluation database, never a source snapshot or production store.
    with sqlite3.connect(database) as writable:
        columns = {
            str(row[1])
            for row in writable.execute("PRAGMA table_info(multilingual_coverage_manifests_v2)")
        }
        count = int(
            writable.execute("SELECT COUNT(*) FROM multilingual_coverage_manifests_v2").fetchone()[
                0
            ]
        )
        if count or columns & {"capability", "item_identity_digest"}:
            raise ValueError("unexpected legacy manifest shape; do not migrate automatically")
        writable.execute(
            "ALTER TABLE multilingual_coverage_manifests_v2 "
            "ADD COLUMN capability TEXT NOT NULL DEFAULT ''"
        )
        writable.execute(
            "ALTER TABLE multilingual_coverage_manifests_v2 "
            "ADD COLUMN item_identity_digest TEXT NOT NULL DEFAULT ''"
        )
    prebuild["disposable_schema_reconciliation"] = ["capability", "item_identity_digest"]
    (target / "bge-prebuild-census.json").open("x", encoding="utf-8").write(
        json.dumps(prebuild, indent=2, sort_keys=True) + "\n"
    )
    result = await build_isolated_multilingual(
        database=database,
        notebook_id=NOTEBOOK,
        profile_file=ROOT / "config/model_profiles/full_multilingual_v2_profiles.toml",
        cache_folder=CACHE.resolve(strict=True),
        device="cuda",
        language_capability_file=ROOT / "config/rebuild/multilingual_embedding_capability.json",
    )
    result["prebuild_census"] = prebuild
    (target / "bge-build-result.json").open("x", encoding="utf-8").write(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(asyncio.run(run()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
