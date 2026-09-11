from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.services.v2_certification import (
    BGE_REVISION,
    PAIR_POLICY,
    STORE_IDENTITY,
    STORE_SHA256,
    WP17CertificationAuthorityV1,
    WP17EvidencePathsV1,
)


def _write(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _evidence(tmp_path: Path) -> WP17EvidencePathsV1:
    values: dict[str, dict[str, object]] = {
        "amendment": {
            "status": "ACCEPTED",
            "bindings": {
                "production_store_identity": STORE_IDENTITY,
                "production_store_sha256": STORE_SHA256,
                "bge_revision": BGE_REVISION,
                "pair_policy": PAIR_POLICY,
                "device": "cuda",
                "batch_size": 2,
                "cpu_fallback": False,
                "internal_candidate_k": 50,
            },
        },
        "approval": {"approval_type": "PROJECT_OWNER_GOVERNANCE_APPROVAL"},
        "qrels": {"status": "PASS"},
        "thresholds": {
            "status": "APPROVED_BEFORE_FRESH_CERTIFICATION_RUN",
            "floors": {
                "recall_at_1": 0.75,
                "recall_at_5": 0.85,
                "recall_at_10": 0.85,
                "mrr": 0.78,
                "ndcg_at_10": 0.8,
            },
        },
        "evaluation": {
            "status": "PRODUCTION_PARITY_EVALUATION_PASS",
            "metrics": {
                "recall_at_1": 0.8,
                "recall_at_5": 0.9,
                "recall_at_10": 0.9,
                "mrr": 0.82,
                "ndcg_at_10": 0.83,
            },
        },
        "wp16": {"status": "PASS"},
        "activation": {"status": "PASS"},
        "transport_parity": {"status": "PASS"},
        "security": {"status": "PASS"},
        "rollback": {"status": "PASS"},
        "final_active_state": {
            "status": "PASS",
            "bge_active": True,
            "reranker_mode": "BGE_V2_M3",
            "production_store_sha256": STORE_SHA256,
        },
    }
    paths = {name: _write(tmp_path / f"{name}.json", value) for name, value in values.items()}
    return WP17EvidencePathsV1(**paths)


def test_wp17_authority_certifies_only_complete_bound_evidence(tmp_path: Path) -> None:
    actor = uuid4()
    state = tmp_path / "certification.json"
    authority = WP17CertificationAuthorityV1(
        state_path=state,
        signing_key=b"w" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
    )
    result = authority.certify(
        principal=PrincipalContextV1(actor_id=actor, authenticated=True),
        evidence=_evidence(tmp_path),
    )
    assert result["status"] == "PRODUCTION_CERTIFICATION_PASS"
    assert result["lifecycle"]["CERTIFIED"] is True
    assert json.loads(state.read_text(encoding="utf-8"))["signature"] == result["signature"]


def test_wp17_authority_rejects_wrong_actor_and_failed_gate(tmp_path: Path) -> None:
    actor = uuid4()
    authority = WP17CertificationAuthorityV1(
        state_path=tmp_path / "certification.json",
        signing_key=b"w" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
    )
    evidence = _evidence(tmp_path)
    with pytest.raises(PermissionError):
        authority.certify(
            principal=PrincipalContextV1(actor_id=uuid4(), authenticated=True),
            evidence=evidence,
        )
    _write(evidence.security, {"status": "FAIL"})
    with pytest.raises(RuntimeError, match="WP17_EVIDENCE_GATE_FAILED:security"):
        authority.certify(
            principal=PrincipalContextV1(actor_id=actor, authenticated=True),
            evidence=evidence,
        )


def test_wp17_authority_rejects_threshold_failure_and_protected_path(tmp_path: Path) -> None:
    actor = uuid4()
    protected = tmp_path / "mnemo.db"
    with pytest.raises(ValueError, match="protected database"):
        WP17CertificationAuthorityV1(
            state_path=protected,
            signing_key=b"w" * 32,
            authorized_operator_actor_id=actor,
            prohibited_paths=(protected,),
        )
    authority = WP17CertificationAuthorityV1(
        state_path=tmp_path / "certification.json",
        signing_key=b"w" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(protected,),
    )
    evidence = _evidence(tmp_path)
    _write(
        evidence.evaluation,
        {
            "status": "PRODUCTION_PARITY_EVALUATION_PASS",
            "metrics": {
                "recall_at_1": 0.5,
                "recall_at_5": 0.9,
                "recall_at_10": 0.9,
                "mrr": 0.82,
                "ndcg_at_10": 0.83,
            },
        },
    )
    with pytest.raises(RuntimeError, match="WP17_THRESHOLD_FAILED:recall_at_1"):
        authority.certify(
            principal=PrincipalContextV1(actor_id=actor, authenticated=True),
            evidence=evidence,
        )
