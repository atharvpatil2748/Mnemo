"""Verify an offline disposable benchmark and print its portable metric summary."""

from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from run_module_894_disposable_bge import ROOT, RUNTIME
from run_module_894_rank_benchmark import (
    MANIFEST,
    checked_trace,
    key,
    metrics,
    provenance,
    sha,
)


def summarize(directory: Path) -> dict[str, Any]:
    directory = directory.resolve(strict=True)
    if directory.parent != RUNTIME.parent or not directory.name.startswith("dere-trace-"):
        raise ValueError("expected a disposable trace run")
    manifest = json.loads(MANIFEST.read_bytes())
    inventory_file = (
        ROOT
        / "docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack"
        / "V2_GOVERNED_CASE_INVENTORY.proposed.json"
    )
    inventory = {
        c["case_id"]: c
        for cohort in json.loads(inventory_file.read_bytes())["directional_cohorts"].values()
        for c in cohort["cases"]
    }
    allowed = provenance(directory, manifest)
    result = json.loads((directory / "result.json").read_bytes())
    digest = sha(MANIFEST.read_bytes())
    if result["manifest_sha256"] != digest:
        raise ValueError("run consumed another manifest")
    out = []
    for case, row in zip(manifest["cases"], result["cases"], strict=True):
        origins = [inventory[i] for i in case["inventory_ids"]]
        if case["query"] != " ".join(c["query_text"] for c in origins):
            raise ValueError("predeclared query does not match origin")
        for target, origin in zip(case["targets"], origins, strict=True):
            (old,) = origin["target_evidence"]
            if (
                any(
                    target[k] != old[k]
                    for k in (
                        "notebook_id",
                        "document_id",
                        "version_id",
                        "evidence_id",
                        "evidence_kind",
                    )
                )
                or target["evidence_content_sha256"] != old["source_content_hash"]
            ):
                raise ValueError("predeclared target does not match origin")
        path = (directory / row["trace"]).resolve(strict=True)
        if path.parent != directory:
            raise ValueError("invalid trace path")
        data = path.read_bytes()
        trace = json.loads(gzip.decompress(data))
        if (
            trace["case_id"] != case["case_id"]
            or row["case_id"] != case["case_id"]
            or trace["manifest_sha256"] != digest
            or trace["alias"] != manifest["active_alias"]
        ):
            raise ValueError("unbound trace")
        checked_trace(trace, allowed)
        if not all(
            math.isclose(sum(v["contributions"].values()), v["score"], rel_tol=1e-12)
            for v in trace["full_v2_rrf_before_limits"]
        ):
            raise ValueError("RRF contributions do not reconstruct score")
        targets = {key(t) for t in case["targets"]}
        calculated = {s: metrics(trace[s], targets, 10) for s in row["metrics"]}
        if calculated != row["metrics"]:
            raise ValueError("metric mismatch")
        if [key(r) for r in trace["advanced_selected"]] != [key(r) for r in trace["final"]]:
            raise ValueError("unexpected change in one-notebook delivery")
        canonical = [
            v for v in trace["advanced_before_dedup"] if v["representation"] == "canonical_text"
        ]
        calculated["canonical_source_page"] = metrics(canonical, targets, 10)
        out.append(
            {
                "case_id": case["case_id"],
                "type": case["case_type"],
                "direction": case["query_language"] + "->" + case["target_language"],
                "document_id": case["targets"][0]["document_id"],
                "target_count": len(targets),
                "metrics_at_10": calculated,
                "stage_counts": {
                    s: len(v) for s, v in trace.items() if isinstance(v, list) and s != "omissions"
                },
                "trace": row["trace"],
                "trace_sha256": sha(data),
                "observed_ms": row["observed_ms"],
                "deadline_ms": row["deadline_ms"],
                "budgets": trace["budgets"],
                "cut_reason": trace["advanced_cut_reason"],
                "requested_k": row["requested_k"],
                "representation_exposure": row["representation_exposure"],
                "stable_output_equal": row["output_equal"],
                "acl_revision": trace["acl_revision"],
            }
        )
    singles = [v for v in out if v["type"] == "single_target"]
    aggregate = {
        stage: {
            metric: mean(v["metrics_at_10"][stage][metric] for v in singles)
            for metric in ("recall", "precision", "rr", "ndcg")
        }
        for stage in singles[0]["metrics_at_10"]
    }
    return {
        "schema": "mnemo.dere-ranking-observation/2",
        "run": directory.name,
        "manifest_sha256": digest,
        "alias": result["alias"],
        "judgment": "DETERMINISTIC_ENGINEERING",
        "human_adjudicated": False,
        "verified_notebook_identities": len(allowed),
        "negative_controls": result["negative_controls"],
        "cases": out,
        "macro_single_target_only": aggregate,
        "single_target_count": len(singles),
        "macro_interpretation": (
            "Descriptive per-query macro for these five fixtures, "
            "not independent document samples or population estimates."
        ),
        "offline_policy_comparison": (
            "INSUFFICIENT independent document/language and notebook coverage"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(json.dumps(summarize(parser.parse_args().directory), indent=2, sort_keys=True))
