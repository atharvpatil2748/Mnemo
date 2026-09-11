"""ADR-0076 typed, fail-closed WP-17 engineering certification authority."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo.interfaces import PrincipalContextV1

STORE_IDENTITY = "0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d"
STORE_SHA256 = "3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c"
BGE_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
PAIR_POLICY = "bge-reranker-v2-m3-pair-256-contextual-v1"


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, slots=True, kw_only=True)
class WP17EvidencePathsV1:
    amendment: Path
    approval: Path
    qrels: Path
    thresholds: Path
    evaluation: Path
    wp16: Path
    activation: Path
    transport_parity: Path
    security: Path
    rollback: Path
    final_active_state: Path


class WP17CertificationAuthorityV1:
    """Validate the complete evidence graph and atomically certify one snapshot."""

    def __init__(
        self,
        *,
        state_path: Path,
        signing_key: bytes,
        authorized_operator_actor_id: UUID,
        prohibited_paths: tuple[Path, ...],
    ) -> None:
        resolved = state_path.resolve()
        if any(resolved == item.resolve() for item in prohibited_paths):
            raise ValueError("certification state path is a protected database")
        if len(signing_key) < 32:
            raise ValueError("certification signing key must contain at least 32 bytes")
        self._path = resolved
        self._key = signing_key
        self._actor = authorized_operator_actor_id

    def certify(
        self,
        *,
        principal: PrincipalContextV1,
        evidence: WP17EvidencePathsV1,
    ) -> dict[str, Any]:
        if not principal.authenticated or principal.actor_id != self._actor:
            raise PermissionError("authorized WP-17 operator principal is required")
        evidence_paths = {item.name: getattr(evidence, item.name) for item in fields(evidence)}
        loaded = {name: self._load(path) for name, path in evidence_paths.items()}
        self._validate(loaded)
        payload: dict[str, Any] = {
            "schema_version": "mnemo.v2-wp17-certified-state/1",
            "status": "PRODUCTION_CERTIFICATION_PASS",
            "authority": "WP17CertificationAuthorityV1",
            "decision_reference": "ADR-0076",
            "operator_actor_id": str(principal.actor_id),
            "production_store_identity": STORE_IDENTITY,
            "production_store_sha256": STORE_SHA256,
            "bge_revision": BGE_REVISION,
            "pair_policy": PAIR_POLICY,
            "evidence_digests": {name: _digest_file(path) for name, path in evidence_paths.items()},
            "lifecycle": {
                "DECLARED": True,
                "IMPLEMENTED": True,
                "CONFIGURED": True,
                "BUILDABLE": True,
                "READY": True,
                "ACTIVE": True,
                "EXPOSED": True,
                "EVALUATED": True,
                "VERIFIED": True,
                "CERTIFIED": True,
            },
        }
        payload["signature"] = hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()
        self._atomic_write(payload)
        return payload

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError(f"WP17_EVIDENCE_INVALID:{path.name}")
        return value

    @staticmethod
    def _validate(values: dict[str, dict[str, Any]]) -> None:
        required_status = {
            "amendment": "ACCEPTED",
            "qrels": "PASS",
            "thresholds": "APPROVED_BEFORE_FRESH_CERTIFICATION_RUN",
            "evaluation": "PRODUCTION_PARITY_EVALUATION_PASS",
            "wp16": "PASS",
            "activation": "PASS",
            "transport_parity": "PASS",
            "security": "PASS",
            "rollback": "PASS",
            "final_active_state": "PASS",
        }
        for name, status in required_status.items():
            if values[name].get("status") != status:
                raise RuntimeError(f"WP17_EVIDENCE_GATE_FAILED:{name}")
        approval = values["approval"]
        if approval.get("approval_type") != "PROJECT_OWNER_GOVERNANCE_APPROVAL":
            raise RuntimeError("WP17_APPROVAL_INVALID")
        amendment = values["amendment"]
        bindings = amendment.get("bindings", {})
        if (
            bindings.get("production_store_identity") != STORE_IDENTITY
            or bindings.get("production_store_sha256") != STORE_SHA256
            or bindings.get("bge_revision") != BGE_REVISION
            or bindings.get("pair_policy") != PAIR_POLICY
            or bindings.get("device") != "cuda"
            or bindings.get("batch_size") != 2
            or bindings.get("cpu_fallback") is not False
            or bindings.get("internal_candidate_k") != 50
        ):
            raise RuntimeError("WP17_GOVERNANCE_BINDING_MISMATCH")
        evaluation = values["evaluation"]
        metrics = evaluation.get("metrics", {})
        floors = values["thresholds"].get("floors", {})
        metric_names = {
            "recall_at_1": "recall_at_1",
            "recall_at_5": "recall_at_5",
            "recall_at_10": "recall_at_10",
            "mrr": "mrr",
            "ndcg_at_10": "ndcg_at_10",
        }
        for result_name, floor_name in metric_names.items():
            if float(metrics.get(result_name, -1)) < float(floors.get(floor_name, 2)):
                raise RuntimeError(f"WP17_THRESHOLD_FAILED:{result_name}")
        active = values["final_active_state"]
        if (
            active.get("bge_active") is not True
            or active.get("reranker_mode") != "BGE_V2_M3"
            or active.get("production_store_sha256") != STORE_SHA256
        ):
            raise RuntimeError("WP17_FINAL_ACTIVE_STATE_INVALID")

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            temporary_path = Path(temporary)
            if temporary_path.exists():
                temporary_path.unlink()
