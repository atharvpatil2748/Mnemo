"""Diagnostic-only policy replay of frozen six-case ranked traces.

This cannot certify a new policy: the source manifest's comparison gate requires
more independent documents and notebooks than this trace cohort contains.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "scratch/module_894_disposable/dere-trace-20261107-02"
MANIFEST = ROOT / "evaluation/module_894_dere/manifest.v2.json"
KEYS = ("notebook_id", "source_id", "document_id", "version_id", "evidence_id")


def identity(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[key]) for key in KEYS)


def score(rows: list[dict[str, Any]], targets: set[tuple[str, ...]]) -> dict[str, float]:
    seen: set[tuple[str, ...]] = set()
    ranks: list[int] = []
    for rank, row in enumerate(rows[:10], 1):
        key = identity(row)
        if key in targets and key not in seen:
            ranks.append(rank)
            seen.add(key)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(targets), 10) + 1))
    return {
        "recall_at_10": len(seen) / len(targets),
        "mrr": 1 / min(ranks) if ranks else 0.0,
        "ndcg_at_10": sum(1 / math.log2(rank + 1) for rank in ranks) / ideal,
        "distinct_evidence_at_10": float(len({identity(row) for row in rows[:10]})),
    }


def unique(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = identity(row)
        if key not in seen:
            seen.add(key)
            selected.append(row)
        if len(selected) == 10:
            break
    return selected


def round_robin(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["representation"]), []).append(row)
    selected: list[dict[str, Any]] = []
    while any(groups.values()) and len(selected) < 10:
        for group in groups.values():
            if group:
                selected.append(group.pop(0))
            if len(selected) == 10:
                break
    return selected


def main() -> int:
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        raise ValueError("production selector changed")
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    result = json.loads((TRACE / "result.json").read_text())
    if result["manifest_sha256"] != hashlib.sha256(manifest_bytes).hexdigest():
        raise ValueError("frozen trace and QREL manifest mismatch")
    cases = {case["case_id"]: case for case in manifest["cases"]}
    out: list[dict[str, Any]] = []
    for receipt in result["cases"]:
        case = cases[receipt["case_id"]]
        with gzip.open(TRACE / receipt["trace"], "rt", encoding="utf-8") as stream:
            trace = json.load(stream)
        targets = {identity(target) for target in case["targets"]}
        pool = trace["advanced_before_output_bounds"]
        policies = {
            "current": trace["advanced_selected"],
            "same_pool_unique_evidence": unique(pool),
            "same_pool_representation_round_robin": round_robin(pool),
            "depth_5_unique": unique(pool[:5]),
            "depth_20_unique": unique(pool[:20]),
        }
        out.append(
            {
                "case_id": case["case_id"],
                "pool_count": len(pool),
                "policies": {name: score(rows, targets) for name, rows in policies.items()},
            }
        )
    print(json.dumps({"status": "DIAGNOSTIC_ONLY_GATE_UNMET", "cases": out}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
