"""Issue and verify the generation-bound WP-17 chain from verified rehearsal evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

from mnemo_server.config import ServerConfig
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.production_credentials import (
    CertificationStage,
    CredentialKind,
    CredentialState,
    ProductionCredentialRegistry,
    WindowsCredentialStore,
    _write_new,
)
from mnemo_server.services.production_generation_evidence import (
    ProductionGenerationEvidenceAuthority,
)
from mnemo_server.services.production_runtime_binding import repository_root
from mnemo_server.services.v2_certification import (
    WP17CertificationAuthorityV1,
    WP17EvidencePathsV1,
    WP17GenerationBindingV2,
)
from run_wp17_generation_rehearsal import digest, document, verify


def _context(
    run_dir: Path,
    *,
    allow_active: bool = False,
) -> tuple[
    ProductionCredentialRegistry,
    UUID,
    WP17GenerationBindingV2,
    WP17EvidencePathsV1,
    ProductionGenerationEvidenceAuthority,
    WP17CertificationAuthorityV1,
]:
    root = repository_root()
    manifest = document(root / "config/production/full_multilingual_v2.production.json")
    registry_name = manifest["configuration_authority"].get("credential_registry")
    if not isinstance(registry_name, str):
        raise RuntimeError("WP17_REGISTRY_UNAVAILABLE")
    registry = ProductionCredentialRegistry(
        path=(root / registry_name).resolve(), secret_store=WindowsCredentialStore()
    )
    active_document = registry.load()
    if len(active_document.generations) != 1 or (
        active_document.active_generation_id is not None and not allow_active
    ):
        raise RuntimeError("WP17_GENERATION_SELECTION_INVALID")
    record = active_document.generations[0]
    generation_id = record.generation_id
    if (
        run_dir.parent.resolve()
        != (registry.path.parent / "wp17_rehearsal" / str(generation_id)).resolve()
    ):
        raise RuntimeError("WP17_RUN_DIRECTORY_INVALID")
    if record.activation_path is None or record.observation_convergence_path is None:
        raise RuntimeError("WP17_GENERATION_EVIDENCE_INCOMPLETE")
    activation_path = Path(record.activation_path)
    convergence_path = Path(record.observation_convergence_path)
    activation_generation_id = UUID(str(document(activation_path)["activation_generation_id"]))
    old_cert = root / "scratch/phase8_5_full_multilingual_v2/operational/certification.json"
    old_final = root / "scratch/mnemo-v2-final-certification.json"
    plan_path = run_dir / "certification-plan.json"
    if not plan_path.exists():
        _write_new(
            plan_path,
            json.dumps(
                {
                    "schema_version": "mnemo.wp17-generation-certification-plan/1",
                    "credential_generation_id": str(generation_id),
                    "activation_generation_id": str(activation_generation_id),
                    "certificate_generation_id": str(uuid4()),
                    "final_evidence_generation_id": str(uuid4()),
                    "activation_state_sha256": digest(activation_path),
                    "predecessor_certificate_sha256": digest(old_cert),
                    "predecessor_final_evidence_sha256": digest(old_final),
                    "convergence_sha256": digest(convergence_path),
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
        )
    plan = document(plan_path)
    if (
        plan.get("credential_generation_id") != str(generation_id)
        or plan.get("activation_generation_id") != str(activation_generation_id)
        or plan.get("activation_state_sha256") != digest(activation_path)
        or plan.get("predecessor_certificate_sha256") != digest(old_cert)
        or plan.get("predecessor_final_evidence_sha256") != digest(old_final)
        or plan.get("convergence_sha256") != digest(convergence_path)
    ):
        raise RuntimeError("WP17_CERTIFICATION_PLAN_STALE")
    binding = WP17GenerationBindingV2(
        credential_generation_id=generation_id,
        activation_generation_id=activation_generation_id,
        certificate_generation_id=UUID(str(plan["certificate_generation_id"])),
        final_evidence_generation_id=UUID(str(plan["final_evidence_generation_id"])),
        activation_state_sha256=digest(activation_path),
        predecessor_certificate_sha256=digest(old_cert),
    )
    evidence = WP17EvidencePathsV1(
        amendment=root / "scratch/mnemo-v2-governance-amendment.json",
        approval=root / "scratch/mnemo-v2-decision7-approval.json",
        qrels=root / "scratch/mnemo-v2-qrel-certification.json",
        thresholds=root / "scratch/mnemo-v2-threshold-certification.json",
        evaluation=run_dir / "wp17-evaluation.json",
        wp16=root / "scratch/mnemo-v2-wp16-certification.json",
        activation=run_dir / "wp17-activation.json",
        transport_parity=convergence_path,
        security=run_dir / "wp17-security.json",
        rollback=run_dir / "wp17-rollback.json",
        final_active_state=run_dir / "wp17-final-active-state.json",
    )
    certification_key = registry.retrieve(
        generation_id, CredentialKind.CERTIFICATION_SIGNING
    ).encode()
    cursor = registry.retrieve(generation_id, CredentialKind.DELIVERY_CURSOR)
    cursor_key = hmac.new(
        cursor.encode(), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
    ).digest()
    certificate_path = registry.path.parent / f"certificate-{generation_id}.json"
    final_path = registry.path.parent / f"final-evidence-{generation_id}.json"
    operator = principal_from_claims({"sub": record.owner_subject})
    if not operator.authenticated:
        raise RuntimeError("WP17_OPERATOR_UNAUTHENTICATED")
    wp17 = WP17CertificationAuthorityV1(
        state_path=certificate_path,
        signing_key=certification_key,
        authorized_operator_actor_id=operator.actor_id,
        prohibited_paths=(
            root / "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db",
        ),
        generation_binding=binding,
    )
    profile = document(convergence_path)["identity"]["model_profile_fingerprint"]
    final = ProductionGenerationEvidenceAuthority(
        activation_path=activation_path,
        certificate_path=certificate_path,
        transport_parity_path=convergence_path,
        final_evidence_path=final_path,
        cursor_signing_key=cursor_key,
        certification_signing_key=certification_key,
        generation_binding=binding,
        model_profile_fingerprint=profile,
        predecessor_final_evidence_sha256=digest(old_final),
    )
    return registry, generation_id, binding, evidence, final, wp17


def certify(run_dir: Path) -> dict[str, str]:
    preflight = verify(run_dir)
    if preflight["status"] != "PRE_ACTIVATION_REHEARSAL_VERIFIED":
        raise RuntimeError("WP17_REHEARSAL_NOT_VERIFIED")
    registry, generation_id, binding, evidence, final, wp17 = _context(run_dir)
    record = registry.load().generations[0]
    if record.state is not CredentialState.PROVISIONED or (
        record.certification_stage is not CertificationStage.OBSERVATION_CONVERGED
    ):
        raise RuntimeError("WP17_CERTIFICATION_STAGE_INVALID")
    operator_subject = ServerConfig.from_env(
        certified_production=True, pre_certification_observation=True
    ).reranker_activation_operator_subject
    operator = principal_from_claims({"sub": operator_subject})
    wp17.verify_generation_rehearsal(evidence=evidence)
    wp17.certify(principal=operator, evidence=evidence)
    cert_path = final.artifact_paths[1]
    WP17CertificationAuthorityV1.verify_generation(
        path=cert_path,
        signing_key=registry.retrieve(generation_id, CredentialKind.CERTIFICATION_SIGNING).encode(),
        binding=binding,
    )
    final.create()
    final.verify()
    registry.record_final_evidence(generation_id=generation_id, authority=final)
    validated = registry.validate_with_evidence(generation_id=generation_id, authority=final)
    if validated.state is not CredentialState.VALIDATED:
        raise RuntimeError("WP17_VALIDATION_NOT_RECORDED")
    return {
        "status": "PRE_ACTIVATION_CERTIFIED",
        "generation_id": str(generation_id),
        "certificate_sha256": digest(cert_path),
        "final_evidence_sha256": digest(final.artifact_paths[2]),
    }


def promote(run_dir: Path) -> dict[str, str]:
    verify_chain(run_dir)
    registry, generation_id, _, _, final, _ = _context(run_dir)
    record = registry.load().generations[0]
    if record.state is not CredentialState.VALIDATED:
        raise RuntimeError("WP17_NOT_VALIDATED_FOR_PROMOTION")
    final.verify()
    promoted = registry.promote(generation_id=generation_id, authority=final)
    document_ = registry.load()
    if (
        promoted.state is not CredentialState.ACTIVE
        or document_.active_generation_id != generation_id
        or len([x for x in document_.generations if x.state is CredentialState.ACTIVE]) != 1
    ):
        raise RuntimeError("WP17_PROMOTION_NOT_ATOMIC")
    return {"status": "ACTIVE", "generation_id": str(generation_id)}


def verify_chain(run_dir: Path) -> dict[str, str]:
    """Reopen and independently verify signed rehearsal, certificate and final state."""
    registry, generation_id, binding, evidence, final, wp17 = _context(run_dir, allow_active=True)
    rehearsal = wp17.verify_generation_rehearsal(evidence=evidence)
    certificate_path = final.artifact_paths[1]
    certificate = WP17CertificationAuthorityV1.verify_generation(
        path=certificate_path,
        signing_key=registry.retrieve(generation_id, CredentialKind.CERTIFICATION_SIGNING).encode(),
        binding=binding,
    )
    final_state = final.verify()
    record = registry.load().generations[0]
    if (
        rehearsal["status"] != "PRE_ACTIVATION_REHEARSAL_VERIFIED"
        or certificate["status"] != "PRODUCTION_CERTIFICATION_PASS"
        or final_state["status"] != "PRODUCTION_CERTIFICATION_PASS"
        or record.certificate_sha256 != digest(certificate_path)
        or record.final_evidence_sha256 != digest(final.artifact_paths[2])
    ):
        raise RuntimeError("WP17_SIGNED_CHAIN_INVALID")
    return {
        "status": "WP17_SIGNED_CHAIN_VERIFIED",
        "generation_id": str(generation_id),
        "certificate_sha256": digest(certificate_path),
        "final_evidence_sha256": digest(final.artifact_paths[2]),
    }


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"certify", "verify", "promote"}:
        raise SystemExit(
            "usage: complete_wp17_generation_certification.py certify|verify|promote RUN_DIR"
        )
    path = Path(sys.argv[2]).resolve(strict=True)
    result = (
        certify(path)
        if sys.argv[1] == "certify"
        else verify_chain(path)
        if sys.argv[1] == "verify"
        else promote(path)
    )
    print(json.dumps(result, sort_keys=True))
