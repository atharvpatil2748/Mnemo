"""Exact four-store pre-Phase-8.9 retirement; never scans for deletion targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import psutil  # type: ignore[import-untyped]
from mnemo_server.services.production_runtime_selection import (
    resolve_production_runtime_selection,
)
from mnemo_server.tools.legacy_decommission import (
    FullStoreTarget,
    _tables,
    dry_run_full_store,
    execute_full_store,
)
from mnemo_server.tools.source_manifest import verify_source_manifest
from mnemo_server.tools.windows_open_handles import processes_using_files

TARGETS = Path("config/decommission/pre_phase_8_9_targets.json")
REGISTRY = Path("scratch/evaluation_notebooks/registry.json")
CREDENTIALS = Path("scratch/phase8_5_full_multilingual_v2/operational/credentials.json")
OUT = Path("scratch/phase8_9_decommission/2026-10-10")
REVOKED_GENERATION = "fc85192e-f672-4cc0-9539-b4b063bb8f41"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_prefix(root: Path, path: Path) -> Path:
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("decommission target escaped workspace")
    return resolved


def _preconditions(root: Path) -> dict[str, object]:
    selection = resolve_production_runtime_selection(root)
    if selection.state != "UNINDEXED":
        raise RuntimeError("production selection is not UNINDEXED")
    credential = json.loads(_safe_prefix(root, CREDENTIALS).read_text(encoding="utf-8"))
    generations = credential.get("generations")
    if (
        credential.get("active_generation_id") is not None
        or not isinstance(generations, list)
        or not any(
            isinstance(item, dict)
            and item.get("generation_id") == REVOKED_GENERATION
            and item.get("state") == "REVOKED"
            for item in generations
        )
    ):
        raise RuntimeError("historical serving credential is not retired")
    tunnel = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            details = process.info
            command = " ".join(details.get("cmdline") or ())
            if "certified-tunnel-stdio" in command or "certified-tunnel-stdio" in str(
                details.get("name") or ""
            ):
                tunnel.append(int(details["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            raise RuntimeError("could not prove tunnel process quiescence") from None
    if tunnel:
        raise RuntimeError("historical tunnel is still active")
    personal = verify_source_manifest(
        manifest=root / "config/rebuild/personal_44.sources.json",
        corpus=root / "goldenDataset/Phase 8.5 Evaluation Corpus",
    )
    format_diverse = verify_source_manifest(
        manifest=root / "config/rebuild/codex_downloaded_24.sources.json",
        corpus=root / "evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus",
    )
    if len(personal["sources"]) != 44 or len(format_diverse["sources"]) != 24:
        raise RuntimeError("protected source membership changed")
    return {
        "production_state": "UNINDEXED",
        "credential_generation": REVOKED_GENERATION,
        "credential_state": "REVOKED",
        "tunnel_processes": tunnel,
        "source_counts": [44, 24],
        "source_manifest_sha256": [
            _sha256(root / "config/rebuild/personal_44.sources.json"),
            _sha256(root / "config/rebuild/codex_downloaded_24.sources.json"),
        ],
    }


def _target(root: Path, entry: dict[str, Any], *, registry_sha: str | None) -> FullStoreTarget:
    database = _safe_prefix(root, Path(str(entry["database"])))
    if _sha256(database) != entry["expected_sha256"]:
        raise ValueError("approved database fingerprint changed")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        tables = _tables(connection)
        ids = (
            tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT generation_id FROM index_generations ORDER BY 1"
                )
            )
            if "index_generations" in tables
            else ()
        )
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
    finally:
        connection.close()
    digest = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()
    if len(ids) != entry["generation_count"] or digest != entry["generation_inventory_sha256"]:
        raise ValueError("approved generation inventory changed")
    if aliases != tuple(entry["alias_digests"]):
        raise ValueError("approved alias inventory changed")
    alias = entry["registry_alias"]
    wal = Path(str(database) + "-wal")
    return FullStoreTarget(
        database=database,
        expected_sha256=str(entry["expected_sha256"]),
        notebook_ids=tuple(str(item) for item in entry["notebook_ids"]),
        generation_ids=ids,
        alias_digests=aliases,
        snapshot=root / OUT / "snapshots" / (str(entry["label"]) + ".db"),
        registry=root / REGISTRY if alias else None,
        registry_aliases=(str(alias),) if alias else (),
        expected_registry_sha256=registry_sha if alias else None,
        expected_wal_sha256=_sha256(wal) if wal.is_file() and wal.stat().st_size else None,
    )


def _record_keys(connection: sqlite3.Connection, table: str) -> list[list[object]]:
    keys = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")') if row[5]]
    if not keys:
        keys = ["rowid"]
    selected = ",".join(f'"{key}"' for key in keys)
    return [list(row) for row in connection.execute(f'SELECT {selected} FROM "{table}"')]


def _inventory(root: Path, entry: dict[str, Any], registry_sha: str | None) -> dict[str, object]:
    target = _target(root, entry, registry_sha=registry_sha)
    plan = dry_run_full_store(workspace=root, target=target)
    sidecars = {}
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(plan.database) + suffix)
        sidecars[suffix] = (
            {"bytes": sidecar.stat().st_size, "sha256": _sha256(sidecar)}
            if sidecar.is_file()
            else None
        )
    files = tuple(
        path
        for path in (plan.database, *(Path(str(plan.database) + s) for s in ("-wal", "-shm")))
        if path.exists()
    )
    consumers = processes_using_files(files)
    if consumers:
        raise RuntimeError("target index still has file consumers")
    db = sqlite3.connect(plan.database.as_uri() + "?mode=ro", uri=True)
    try:
        identities = {
            table: _record_keys(db, table) for table, count in plan.counts.items() if count
        }
        documents = [
            list(row)
            for row in db.execute(
                "SELECT document_id,current_version_id,current_hash FROM documents ORDER BY 1"
            )
        ]
        versions = [
            list(row)
            for row in db.execute(
                "SELECT version_id,document_id,content_hash FROM document_versions ORDER BY 1"
            )
        ]
        memberships = [
            list(row)
            for row in db.execute(
                "SELECT source_id,notebook_id,document_id FROM sources ORDER BY 1"
            )
        ]
    finally:
        db.close()
    return {
        "label": entry["label"],
        "database": entry["database"],
        "before_sha256": plan.before_sha256,
        "wal_sha256": plan.wal_sha256,
        "sidecars": sidecars,
        "registry_sha256": plan.registry_sha256,
        "notebook_ids": list(plan.notebook_ids),
        "generation_ids": list(plan.generation_ids),
        "alias_digests": list(plan.alias_digests),
        "registry_aliases": list(plan.registry_aliases),
        "counts": plan.counts,
        "record_keys": identities,
        "memberships": memberships,
        "documents_and_stored_hashes": documents,
        "versions_and_stored_hashes": versions,
        "snapshot": str(plan.snapshot.relative_to(root)),
        "consumers": list(consumers),
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve(strict=True)
    pinned = json.loads((root / TARGETS).read_text(encoding="utf-8"))
    if (
        pinned.get("schema") != "mnemo.legacy-full-store-targets/1"
        or len(pinned.get("targets", [])) != 4
    ):
        raise ValueError("unexpected decommission allowlist")
    before = _preconditions(root)
    registry_sha = _sha256(root / REGISTRY)
    if not args.execute:
        targets = [_inventory(root, entry, registry_sha) for entry in pinned["targets"]]
        manifest = {
            "schema": "mnemo.pre-phase-8-9-full-store-preflight/1",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "allowlist_sha256": _sha256(root / TARGETS),
            "preconditions": before,
            "targets": targets,
        }
        report = root / OUT / "full-store-dry-run.json"
        _write_json(report, manifest)
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_COMPLETE",
                    "report": str(report),
                    "counts": [
                        {
                            "label": item["label"],
                            "rows": sum(cast(dict[str, int], item["counts"]).values()),
                        }
                        for item in targets
                    ],
                },
                indent=2,
            )
        )
        return
    report = root / OUT / "full-store-dry-run.json"
    manifest = json.loads(report.read_text(encoding="utf-8"))
    if manifest.get("allowlist_sha256") != _sha256(root / TARGETS):
        raise ValueError("decommission allowlist changed after dry run")
    if manifest.get("preconditions") != before:
        raise ValueError("protected preconditions changed after dry run")
    actual = [_inventory(root, entry, registry_sha) for entry in pinned["targets"]]
    for recorded, current in zip(manifest["targets"], actual, strict=True):
        comparable = {key: value for key, value in recorded.items() if key != "sidecars"}
        current_comparable = {key: value for key, value in current.items() if key != "sidecars"}
        if comparable != current_comparable:
            raise ValueError("index inventory changed after dry run")
    receipts: list[dict[str, object]] = []
    for entry in pinned["targets"]:
        _preconditions(root)
        current_registry_sha = _sha256(root / REGISTRY)
        target = _target(root, entry, registry_sha=current_registry_sha)
        receipt = execute_full_store(workspace=root, target=target)
        receipts.append({"label": entry["label"], **receipt})
        _write_json(root / OUT / "execution-progress.json", receipts)
    after = _preconditions(root)
    result = {
        "schema": "mnemo.pre-phase-8-9-full-store-execution/1",
        "status": "COMPLETE",
        "before": before,
        "after": after,
        "receipts": receipts,
    }
    output = root / OUT / "full-store-execution.json"
    _write_json(output, result)
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "report": str(output),
                "stores": [item["label"] for item in receipts],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
