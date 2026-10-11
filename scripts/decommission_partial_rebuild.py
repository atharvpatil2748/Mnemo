"""Retire only the explicitly pinned, owner-verified c976 partial index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from decommission_pre_phase89 import OUT, _inventory, _preconditions, _sha256, _target, _write_json
from mnemo_server.tools.legacy_decommission import execute_full_store

ALLOWLIST = Path("config/decommission/partial_c976b97b_target.json")


def _entry(root: Path) -> dict[str, Any]:
    entry = cast(dict[str, Any], json.loads((root / ALLOWLIST).read_text(encoding="utf-8")))
    if entry.get("schema") != "mnemo.legacy-partial-rebuild-target/1":
        raise ValueError("partial rebuild allowlist schema mismatch")
    owner_path = (root / str(entry["owner_manifest"])).resolve(strict=True)
    if not owner_path.is_relative_to(root) or _sha256(owner_path) != entry["owner_manifest_sha256"]:
        raise ValueError("partial rebuild owner evidence changed")
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    for name, expected in (
        ("run_id", entry["run_id"]),
        ("pair_id", entry["pair_id"]),
        ("notebook_id", entry["notebook_ids"][0]),
        ("input_identity", entry["source_input_identity"]),
        ("label", "personal_44"),
    ):
        if owner.get(name) != expected:
            raise ValueError("partial rebuild ownership is inconsistent")
    status_path = owner_path.with_name("rebuild-status.json")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("notebook_id") != owner["notebook_id"] or status.get("activation") != "inactive":
        raise ValueError("partial rebuild is not the approved inactive notebook")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve(strict=True)
    entry = _entry(root)
    before = _preconditions(root)
    inventory = _inventory(root, entry, None)
    if inventory["wal_sha256"] != entry["expected_wal_sha256"]:
        raise ValueError("approved partial rebuild WAL fingerprint changed")
    report = root / OUT / "partial-rebuild-dry-run.json"
    if not args.execute:
        _write_json(
            report,
            {
                "schema": "mnemo.legacy-partial-rebuild-preflight/1",
                "allowlist_sha256": _sha256(root / ALLOWLIST),
                "preconditions": before,
                "inventory": inventory,
            },
        )
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_COMPLETE",
                    "report": str(report),
                    "rows": sum(cast(dict[str, int], inventory["counts"]).values()),
                },
                indent=2,
            )
        )
        return
    recorded = json.loads(report.read_text(encoding="utf-8"))
    if (
        recorded.get("allowlist_sha256") != _sha256(root / ALLOWLIST)
        or recorded.get("preconditions") != before
        or {k: v for k, v in recorded["inventory"].items() if k != "sidecars"}
        != {k: v for k, v in inventory.items() if k != "sidecars"}
    ):
        raise ValueError("partial rebuild changed since dry run")
    receipt = execute_full_store(workspace=root, target=_target(root, entry, registry_sha=None))
    after = _preconditions(root)
    output = root / OUT / "partial-rebuild-execution.json"
    _write_json(
        output,
        {
            "schema": "mnemo.legacy-partial-rebuild-execution/1",
            "before": before,
            "after": after,
            "receipt": receipt,
        },
    )
    print(json.dumps({"status": receipt["status"], "report": str(output)}, indent=2))


if __name__ == "__main__":
    main()
