"""ADR-0076 typed, fail-closed WP-17 engineering certification authority."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo.interfaces import PrincipalContextV1

from .production_credentials import _write_new

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


@dataclass(frozen=True, slots=True, kw_only=True)
class WP17GenerationBindingV2:
    credential_generation_id: UUID
    activation_generation_id: UUID
    certificate_generation_id: UUID
    final_evidence_generation_id: UUID
    activation_state_sha256: str
    predecessor_certificate_sha256: str

    def __post_init__(self) -> None:
        for digest in (self.activation_state_sha256, self.predecessor_certificate_sha256):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("WP17_GENERATION_DIGEST_INVALID")


class WP17CertificationAuthorityV1:
    """Validate the complete evidence graph and atomically certify one snapshot."""

    def __init__(
        self,
        *,
        state_path: Path,
        signing_key: bytes,
        authorized_operator_actor_id: UUID,
        prohibited_paths: tuple[Path, ...],
        generation_binding: WP17GenerationBindingV2 | None = None,
    ) -> None:
        resolved = state_path.resolve()
        if any(resolved == item.resolve() for item in prohibited_paths):
            raise ValueError("certification state path is a protected database")
        if len(signing_key) < 32:
            raise ValueError("certification signing key must contain at least 32 bytes")
        self._path = resolved
        self._key = signing_key
        self._actor = authorized_operator_actor_id
        self._generation_binding = generation_binding

    def verify_generation_rehearsal(self, *, evidence: WP17EvidencePathsV1) -> dict[str, Any]:
        """Verify all pre-activation inputs without creating a certificate."""
        binding = self._generation_binding
        if binding is None:
            raise RuntimeError("WP17_GENERATION_BINDING_REQUIRED")
        evidence_paths = {item.name: getattr(evidence, item.name) for item in fields(evidence)}
        loaded = {name: self._load(path) for name, path in evidence_paths.items()}
        self._validate(loaded)
        self._validate_generation_evidence(
            loaded, binding, transport_path=evidence.transport_parity, signing_key=self._key
        )
        return {
            "status": "PRE_ACTIVATION_REHEARSAL_VERIFIED",
            "credential_generation_id": str(binding.credential_generation_id),
            "evidence_digests": {name: _digest_file(path) for name, path in evidence_paths.items()},
        }

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
        if self._generation_binding is not None:
            self._validate_generation_evidence(
                loaded,
                self._generation_binding,
                transport_path=evidence.transport_parity,
                signing_key=self._key,
            )
        payload: dict[str, Any] = {
            "schema_version": (
                "mnemo.v2-wp17-certified-state/3"
                if self._generation_binding is not None
                else "mnemo.v2-wp17-certified-state/1"
            ),
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
                "ACTIVE": self._generation_binding is None,
                "EXPOSED": self._generation_binding is None,
                "EVALUATED": True,
                "VERIFIED": True,
                "CERTIFIED": True,
            },
        }
        if self._generation_binding is not None:
            if self._path.exists():
                raise RuntimeError("WP17_GENERATION_CERTIFICATE_ALREADY_EXISTS")
            binding = self._generation_binding
            payload["authorization_state"] = "PRE_ACTIVATION_CERTIFIED"
            payload["generation_binding"] = {
                "credential_generation_id": str(binding.credential_generation_id),
                "activation_generation_id": str(binding.activation_generation_id),
                "certificate_generation_id": str(binding.certificate_generation_id),
                "final_evidence_generation_id": str(binding.final_evidence_generation_id),
                "activation_state_sha256": binding.activation_state_sha256,
                "predecessor_certificate_sha256": binding.predecessor_certificate_sha256,
            }
        payload["signature"] = hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()
        if self._generation_binding is None:
            self._atomic_write(payload)
        else:
            _write_new(
                self._path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
        return payload

    @staticmethod
    def verify_generation(
        *, path: Path, signing_key: bytes, binding: WP17GenerationBindingV2
    ) -> dict[str, Any]:
        """Independently verify one generation-bound WP-17 certificate."""
        raw = WP17CertificationAuthorityV1._load(path)
        signature = raw.pop("signature", None)
        if raw.get("schema_version") != "mnemo.v2-wp17-certified-state/3" or not isinstance(
            signature, str
        ):
            raise RuntimeError("WP17_GENERATION_CERTIFICATE_INVALID")
        expected_signature = hmac.new(signing_key, _canonical(raw), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise RuntimeError("WP17_GENERATION_CERTIFICATE_SIGNATURE_INVALID")
        expected = {
            "credential_generation_id": str(binding.credential_generation_id),
            "activation_generation_id": str(binding.activation_generation_id),
            "certificate_generation_id": str(binding.certificate_generation_id),
            "final_evidence_generation_id": str(binding.final_evidence_generation_id),
            "activation_state_sha256": binding.activation_state_sha256,
            "predecessor_certificate_sha256": binding.predecessor_certificate_sha256,
        }
        if (
            raw.get("generation_binding") != expected
            or raw.get("status") != "PRODUCTION_CERTIFICATION_PASS"
            or raw.get("production_store_identity") != STORE_IDENTITY
            or raw.get("production_store_sha256") != STORE_SHA256
            or raw.get("bge_revision") != BGE_REVISION
            or raw.get("pair_policy") != PAIR_POLICY
            or raw.get("authorization_state") != "PRE_ACTIVATION_CERTIFIED"
            or not isinstance(raw.get("lifecycle"), dict)
            or raw["lifecycle"].get("ACTIVE") is not False
            or raw["lifecycle"].get("EXPOSED") is not False
        ):
            raise RuntimeError("WP17_GENERATION_CERTIFICATE_BINDING_INVALID")
        return {**raw, "signature": signature}

    @staticmethod
    def _validate_generation_evidence(
        values: dict[str, dict[str, Any]],
        binding: WP17GenerationBindingV2,
        *,
        transport_path: Path,
        signing_key: bytes,
    ) -> None:
        for name in (
            "activation",
            "transport_parity",
            "security",
            "rollback",
            "final_active_state",
        ):
            if values[name].get("credential_generation_id") != str(
                binding.credential_generation_id
            ):
                raise RuntimeError(f"WP17_GENERATION_EVIDENCE_MISMATCH:{name}")
        if (
            values["activation"].get("activation_generation_id")
            != str(binding.activation_generation_id)
            or values["activation"].get("activation_state_sha256")
            != binding.activation_state_sha256
        ):
            raise RuntimeError("WP17_GENERATION_ACTIVATION_MISMATCH")
        rehearsal = values["final_active_state"]
        if (
            rehearsal.get("scope") != "ISOLATED_WP17_REHEARSAL"
            or rehearsal.get("global_generation_active") is not False
            or rehearsal.get("public_production_exposed") is not False
        ):
            raise RuntimeError("WP17_GENERATION_REHEARSAL_SCOPE_INVALID")
        from .pre_certification_observation import (
            PreCertificationObservationAuthority,
            observation_root_for_convergence,
        )

        try:
            campaign_id = UUID(str(values["transport_parity"]["campaign_id"]))
            verifier = PreCertificationObservationAuthority(
                generation_id=binding.credential_generation_id,
                signing_key=signing_key,
                observation_root=observation_root_for_convergence(
                    transport_path,
                    generation_id=binding.credential_generation_id,
                    campaign_id=campaign_id,
                ),
                campaign_id=campaign_id,
            )
            verified = verifier.verify_convergence(transport_path)
        except (KeyError, ValueError, RuntimeError) as exc:
            raise RuntimeError("WP17_GENERATION_TRANSPORT_OBSERVATIONS_INVALID") from exc
        identity = verified["identity"]
        if (
            identity.get("database_sha256") != STORE_SHA256
            or identity.get("database_identity") != STORE_IDENTITY
            or identity.get("reranker_revision") != BGE_REVISION
            or identity.get("activation_sha256") != binding.activation_state_sha256
        ):
            raise RuntimeError("WP17_GENERATION_TRANSPORT_IDENTITY_MISMATCH")
        try:
            convergence_time = datetime.fromisoformat(str(verified["converged_at"]))
            if convergence_time.tzinfo is None:
                raise ValueError("naive convergence time")
        except (KeyError, ValueError) as exc:
            raise RuntimeError("WP17_GENERATION_CONVERGENCE_TIME_INVALID") from exc
        required_checks = {
            "evaluation": ("frozen_inputs_verified", "candidate_protocol_verified"),
            "activation": ("signature_verified", "revision_verified"),
            "security": (
                "authentication_enforced",
                "unauthorized_access_rejected",
                "restricted_tool_surface_verified",
            ),
            "rollback": (
                "pass_through_after_restart",
                "reactivated_after_rollback",
                "bge_restored_after_second_restart",
            ),
            "final_active_state": ("rehearsal_bge_execution_verified",),
        }
        evidence_key = hmac.new(
            signing_key, b"mnemo.wp17-generation-rehearsal/1", hashlib.sha256
        ).digest()
        for name, checks in required_checks.items():
            artifact = values[name]
            signature = artifact.get("signature")
            unsigned = {key: value for key, value in artifact.items() if key != "signature"}
            try:
                execution_time = datetime.fromisoformat(str(artifact["executed_at"]))
                fresh = execution_time.tzinfo is not None and execution_time >= convergence_time
            except (KeyError, ValueError):
                fresh = False
            if (
                artifact.get("schema_version") != "mnemo.wp17-generation-rehearsal/1"
                or artifact.get("evidence_type") != name
                or artifact.get("credential_generation_id") != str(binding.credential_generation_id)
                or artifact.get("activation_state_sha256") != binding.activation_state_sha256
                or artifact.get("identity") != identity
                or artifact.get("scope") != "ISOLATED_WP17_REHEARSAL"
                or artifact.get("global_generation_active") is not False
                or artifact.get("public_production_exposed") is not False
                or not fresh
                or not isinstance(artifact.get("checks"), dict)
                or any(artifact["checks"].get(check) is not True for check in checks)
                or not isinstance(signature, str)
                or not hmac.compare_digest(
                    signature,
                    hmac.new(evidence_key, _canonical(unsigned), hashlib.sha256).hexdigest(),
                )
            ):
                raise RuntimeError(f"WP17_GENERATION_REHEARSAL_EVIDENCE_INVALID:{name}")

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
