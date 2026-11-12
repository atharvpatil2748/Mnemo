"""Read-only engineering evaluation preflight; not semantic adjudication."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_module_894_dere.py"
SPEC = importlib.util.spec_from_file_location("module_894_dere", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_dere_manifest_does_not_claim_human_judgment() -> None:
    manifest = json.loads(
        (ROOT / "evaluation" / "module_894_dere" / "manifest.v1.json").read_text(encoding="utf-8")
    )
    assert manifest["human_adjudication_claimed"] is False
    assert manifest["status"] == "PROVENANCE_PREFLIGHT_ONLY"
    assert manifest["case_id_conflict"]["disposition"] == "DISTINCT_DERE_ID_NO_GRADE_TRANSFER"
    assert len({item["case_id"] for item in manifest["cases"]}) == len(manifest["cases"])
    assert all(item["judgment_provenance"] for item in manifest["cases"])


def test_dere_preflight_rejects_non_evaluation_snapshot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit isolated evaluation snapshot"):
        MODULE.verify(ROOT / "evaluation" / "module_894_dere" / "manifest.v1.json", tmp_path)


@pytest.mark.local_database
def test_dere_snapshot_ancestry_is_receipt_bound_and_not_ranked() -> None:
    snapshot = ROOT / "scratch" / "phase8_5_11" / "eval-20260825-02"
    if not (snapshot / "mnemo.db").is_file():
        pytest.skip("isolated local evaluation snapshot is unavailable")
    result = MODULE.verify(ROOT / "evaluation" / "module_894_dere" / "manifest.v1.json", snapshot)
    assert result["cases"] == [{"case_id": "DERE-894-ENMR-CANONICAL-001", "ancestry": "PASS"}]
    assert result["source_receipt"] == "PASS"
    assert result["source_bytes"] == "NOT_VERIFIED"
    assert result["ranking_metrics"] == "NOT_RUN"
    assert result["human_semantic_relevance"] == "NOT_ADJUDICATED"


@pytest.mark.local_database
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source_id", "00000000-0000-0000-0000-000000000000"),
        ("version_id", "00000000-0000-0000-0000-000000000000"),
        ("evidence_content_sha256", "0" * 64),
        (
            "negative_evidence_ids",
            ["523c5c88b522ce818212ffc42241706b731a767bb4dc5045ffa1a99e3392a0ca"],
        ),
    ],
)
def test_dere_rejects_identity_tampering(tmp_path: Path, field: str, replacement: object) -> None:
    snapshot = ROOT / "scratch" / "phase8_5_11" / "eval-20260825-02"
    if not (snapshot / "mnemo.db").is_file():
        pytest.skip("isolated local evaluation snapshot is unavailable")
    manifest = json.loads(
        (ROOT / "evaluation" / "module_894_dere" / "manifest.v1.json").read_text(encoding="utf-8")
    )
    manifest["cases"][0][field] = replacement
    candidate = tmp_path / "tampered-manifest.json"
    candidate.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=r"mismatch|not outside exact scope"):
        MODULE.verify(candidate, snapshot)
