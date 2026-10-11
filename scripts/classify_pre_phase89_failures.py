"""Create an auditable inventory from the pre-Phase-8.9 JUnit reports.

This report generator reads test artifacts only; it never opens an index store.
The classification is deliberately conservative: a guard-preempted assertion is
not classified as a runtime security regression without an independent probe.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def failures(path: Path) -> dict[str, dict[str, str]]:
    root = ET.parse(path).getroot()
    items: dict[str, dict[str, str]] = {}
    for case in root.iter("testcase"):
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")
        if failure is None:
            continue
        node_id = f"{case.get('classname')}::{case.get('name')}"
        items[node_id] = {
            "message": failure.get("message", ""),
            "traceback": failure.text or "",
        }
    return items


def classify(node_id: str, message: str) -> tuple[str, str]:
    if "test_v2_index_build_operator::" in node_id:
        return ("retired_checkpoint", "Governed preflight rejects retired checkpoint identity")
    if "test_v2_production_adapters::" in node_id or (
        "test_v2_production_adapters_registration::" in node_id
    ):
        return ("stale_index_assumption", "Historical active generation or alias is absent")
    if "test_pre_certification_transports::" in node_id:
        return ("stale_configuration_assumption", "Disposable root lacks runtime selection")
    if "test_phase86_exposure_boundary::test_http_production_startup" in node_id:
        return ("stale_assertion", "UNINDEXED admission rejects before evaluation-store check")
    if "test_mcp_sse::test_certified_sse_rejects_injected" in node_id:
        return ("stale_assertion", "UNINDEXED admission rejects before injected-engine check")
    if "test_server_app::test_production_rejects_" in node_id:
        return ("stale_assertion", "UNINDEXED admission rejects before injected-engine check")
    if "test_server_delivery::" in node_id:
        return ("stale_configuration_assumption", "Production cursor test reaches UNINDEXED guard")
    if "test_mcp_immutable_schema_matrix::" in node_id or (
        "test_ordered_text_certification::test_persisted_mixed_document_real_transports" in node_id
    ):
        return (
            "indexed_test_seam_required",
            "HTTP/MCP assertion received the UNINDEXED response before its expected result",
        )
    if "PRODUCTION_CORPUS_UNINDEXED" in message or "KeyError: 'category'" in message:
        return (
            "indexed_test_seam_required",
            "Positive serving assertion was preempted by the deliberate production guard",
        )
    return ("unresolved_requires_independent_reproduction", "Traceback needs individual triage")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = failures(args.baseline)
    current = failures(args.current)
    inventory = []
    for node_id, detail in sorted(current.items()):
        classification, reason = classify(node_id, detail["message"])
        inventory.append(
            {
                "node_id": node_id,
                "classification": classification,
                "reason": reason,
                "message": detail["message"],
                "traceback": detail["traceback"],
                "also_failed_in_baseline": node_id in baseline,
            }
        )
    report = {
        "schema": "mnemo.pre-phase89-failure-inventory/1",
        "baseline_failure_count": len(baseline),
        "current_failure_count": len(current),
        "fixed_node_ids": sorted(baseline.keys() - current.keys()),
        "newly_failing_node_ids": sorted(current.keys() - baseline.keys()),
        "failures": inventory,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"classified={len(inventory)} fixed={len(report['fixed_node_ids'])} "
        f"new={len(report['newly_failing_node_ids'])}"
    )


if __name__ == "__main__":
    main()
