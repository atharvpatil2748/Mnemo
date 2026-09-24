"""New WP-17 generations must independently verify without rewriting history."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.services import v2_certification as certification_module
from mnemo_server.services.pre_certification_observation import (
    TRANSPORTS,
    ObservationIdentity,
    PreCertificationObservationAuthority,
)
from mnemo_server.services.v2_certification import (
    WP17CertificationAuthorityV1,
    WP17EvidencePathsV1,
    WP17GenerationBindingV2,
)
from test_pre_certification_observation import _runtime


def _evidence(tmp_path: Path) -> WP17EvidencePathsV1:
    from test_v2_certification_authority import _evidence as existing_fixture

    return existing_fixture(tmp_path)


def _bind_evidence(
    evidence: WP17EvidencePathsV1,
    binding: WP17GenerationBindingV2,
    signing_key: bytes = b"n" * 32,
    model_profile_fingerprint: str = "a" * 64,
    campaign_id: UUID | None = None,
) -> None:
    for path in (
        evidence.activation,
        evidence.security,
        evidence.rollback,
        evidence.final_active_state,
    ):
        value = json.loads(path.read_text(encoding="utf-8"))
        value["credential_generation_id"] = str(binding.credential_generation_id)
        if path == evidence.activation:
            value["activation_generation_id"] = str(binding.activation_generation_id)
            value["activation_state_sha256"] = binding.activation_state_sha256
        if path == evidence.final_active_state:
            value["scope"] = "ISOLATED_WP17_REHEARSAL"
            value["global_generation_active"] = False
            value["public_production_exposed"] = False
        path.write_text(json.dumps(value), encoding="utf-8")
    identity = ObservationIdentity(
        credential_generation_id=str(binding.credential_generation_id),
        configuration_digest="a" * 64,
        database_identity=certification_module.STORE_IDENTITY,
        database_sha256=certification_module.STORE_SHA256,
        model_profile_fingerprint=model_profile_fingerprint,
        embedding_model="BAAI/bge-m3",
        embedding_revision="c" * 40,
        reranker_model="BAAI/bge-reranker-v2-m3",
        reranker_revision=certification_module.BGE_REVISION,
        reranker_mode="BGE_V2_M3",
        activation_sha256=binding.activation_state_sha256,
        operational_store_identity="d" * 64,
        runtime_binding_digest="e" * 64,
        composition_identity="f" * 64,
    )
    observer = PreCertificationObservationAuthority(
        generation_id=binding.credential_generation_id,
        signing_key=signing_key,
        observation_root=evidence.transport_parity.parent,
        campaign_id=campaign_id or uuid4(),
    )
    engine, runtime = _runtime(identity)
    observations: dict[Any, Path] = {
        transport: asyncio.run(
            observer.observe(
                transport=transport,
                identity=identity,
                principal_subject="synthetic-test-principal",
                correlation_id=uuid4(),
                engine=engine,
                runtime=runtime,
            )
        )
        for transport in TRANSPORTS
    }
    evidence.transport_parity.unlink()
    observer.converge(observations=observations, output=evidence.transport_parity)
    convergence = observer.verify_convergence(evidence.transport_parity)
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
        path = getattr(evidence, name)
        value = json.loads(path.read_text(encoding="utf-8"))
        value.update(
            {
                "schema_version": "mnemo.wp17-generation-rehearsal/1",
                "evidence_type": name,
                "credential_generation_id": str(binding.credential_generation_id),
                "activation_state_sha256": binding.activation_state_sha256,
                "identity": convergence["identity"],
                "scope": "ISOLATED_WP17_REHEARSAL",
                "global_generation_active": False,
                "public_production_exposed": False,
                "executed_at": convergence["converged_at"],
                "checks": {check: True for check in checks},
            }
        )
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        value["signature"] = hmac.new(evidence_key, encoded, hashlib.sha256).hexdigest()
        path.write_text(json.dumps(value), encoding="utf-8")


def test_new_certificate_binds_generation_and_preserves_old(tmp_path: Path) -> None:
    actor = uuid4()
    principal = PrincipalContextV1(actor_id=actor, authenticated=True)
    evidence = _evidence(tmp_path)
    old_path = tmp_path / "old-certification.json"
    old = WP17CertificationAuthorityV1(
        state_path=old_path,
        signing_key=b"o" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
    )
    old.certify(principal=principal, evidence=evidence)
    old_sha = hashlib.sha256(old_path.read_bytes()).hexdigest()

    binding = WP17GenerationBindingV2(
        credential_generation_id=uuid4(),
        activation_generation_id=uuid4(),
        certificate_generation_id=uuid4(),
        final_evidence_generation_id=uuid4(),
        activation_state_sha256="a" * 64,
        predecessor_certificate_sha256=old_sha,
    )
    _bind_evidence(evidence, binding)
    new_path = tmp_path / "new-certification.json"
    authority = WP17CertificationAuthorityV1(
        state_path=new_path,
        signing_key=b"n" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(old_path,),
        generation_binding=binding,
    )
    preflight = authority.verify_generation_rehearsal(evidence=evidence)
    assert preflight["status"] == "PRE_ACTIVATION_REHEARSAL_VERIFIED"
    assert preflight["credential_generation_id"] == str(binding.credential_generation_id)
    assert not new_path.exists()
    authority.certify(principal=principal, evidence=evidence)
    new_sha = hashlib.sha256(new_path.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="ALREADY_EXISTS"):
        authority.certify(principal=principal, evidence=evidence)
    assert hashlib.sha256(new_path.read_bytes()).hexdigest() == new_sha
    verified = WP17CertificationAuthorityV1.verify_generation(
        path=new_path, signing_key=b"n" * 32, binding=binding
    )
    assert verified["schema_version"] == "mnemo.v2-wp17-certified-state/3"
    assert verified["authorization_state"] == "PRE_ACTIVATION_CERTIFIED"
    assert verified["lifecycle"]["ACTIVE"] is False
    assert verified["lifecycle"]["EXPOSED"] is False
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == old_sha
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        WP17CertificationAuthorityV1.verify_generation(
            path=new_path, signing_key=b"x" * 32, binding=binding
        )
    wrong_binding = WP17GenerationBindingV2(
        credential_generation_id=uuid4(),
        activation_generation_id=binding.activation_generation_id,
        certificate_generation_id=binding.certificate_generation_id,
        final_evidence_generation_id=binding.final_evidence_generation_id,
        activation_state_sha256=binding.activation_state_sha256,
        predecessor_certificate_sha256=binding.predecessor_certificate_sha256,
    )
    with pytest.raises(RuntimeError, match="BINDING_INVALID"):
        WP17CertificationAuthorityV1.verify_generation(
            path=new_path, signing_key=b"n" * 32, binding=wrong_binding
        )
    tampered = json.loads(new_path.read_text(encoding="utf-8"))
    tampered["pair_policy"] = "other"
    new_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        WP17CertificationAuthorityV1.verify_generation(
            path=new_path, signing_key=b"n" * 32, binding=binding
        )


@pytest.mark.parametrize(
    ("tampered_name", "field", "replacement", "error"),
    [
        ("security", "credential_generation_id", "wrong", "EVIDENCE_MISMATCH:security"),
        ("activation", "activation_generation_id", "wrong", "ACTIVATION_MISMATCH"),
        ("activation", "activation_state_sha256", "0" * 64, "ACTIVATION_MISMATCH"),
        ("transport_parity", "observations", {}, "OBSERVATIONS_INVALID"),
        (
            "transport_parity",
            "observations",
            {
                "http": {"composition_id": "a"},
                "stdio": {"composition_id": "b"},
                "sse": {"composition_id": "a"},
            },
            "OBSERVATIONS_INVALID",
        ),
    ],
)
def test_new_certificate_rejects_unbound_evidence(
    tmp_path: Path, tampered_name: str, field: str, replacement: object, error: str
) -> None:
    actor = uuid4()
    evidence = _evidence(tmp_path)
    binding = WP17GenerationBindingV2(
        credential_generation_id=uuid4(),
        activation_generation_id=uuid4(),
        certificate_generation_id=uuid4(),
        final_evidence_generation_id=uuid4(),
        activation_state_sha256="a" * 64,
        predecessor_certificate_sha256="b" * 64,
    )
    _bind_evidence(evidence, binding)
    path = getattr(evidence, tampered_name)
    value = json.loads(path.read_text(encoding="utf-8"))
    value[field] = replacement
    path.write_text(json.dumps(value), encoding="utf-8")
    authority = WP17CertificationAuthorityV1(
        state_path=tmp_path / "new-certificate.json",
        signing_key=b"n" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
        generation_binding=binding,
    )
    with pytest.raises(RuntimeError, match=error):
        authority.certify(
            principal=PrincipalContextV1(actor_id=actor, authenticated=True),
            evidence=evidence,
        )
    assert not (tmp_path / "new-certificate.json").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope", "GLOBAL_PRODUCTION"),
        ("global_generation_active", True),
        ("public_production_exposed", True),
    ],
)
def test_generation_certificate_rejects_false_global_activation(
    tmp_path: Path, field: str, value: object
) -> None:
    actor = uuid4()
    evidence = _evidence(tmp_path)
    binding = WP17GenerationBindingV2(
        credential_generation_id=uuid4(),
        activation_generation_id=uuid4(),
        certificate_generation_id=uuid4(),
        final_evidence_generation_id=uuid4(),
        activation_state_sha256="a" * 64,
        predecessor_certificate_sha256="b" * 64,
    )
    _bind_evidence(evidence, binding)
    rehearsal = json.loads(evidence.final_active_state.read_text(encoding="utf-8"))
    rehearsal[field] = value
    evidence.final_active_state.write_text(json.dumps(rehearsal), encoding="utf-8")
    authority = WP17CertificationAuthorityV1(
        state_path=tmp_path / "new-certificate.json",
        signing_key=b"n" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
        generation_binding=binding,
    )
    with pytest.raises(RuntimeError, match="WP17_GENERATION_REHEARSAL_SCOPE_INVALID"):
        authority.certify(
            principal=PrincipalContextV1(actor_id=actor, authenticated=True),
            evidence=evidence,
        )


@pytest.mark.parametrize(
    "name", ["evaluation", "activation", "security", "rollback", "final_active_state"]
)
def test_generation_certificate_rejects_historical_relabel_and_tampering(
    tmp_path: Path, name: str
) -> None:
    actor = uuid4()
    evidence = _evidence(tmp_path)
    binding = WP17GenerationBindingV2(
        credential_generation_id=uuid4(),
        activation_generation_id=uuid4(),
        certificate_generation_id=uuid4(),
        final_evidence_generation_id=uuid4(),
        activation_state_sha256="a" * 64,
        predecessor_certificate_sha256="b" * 64,
    )
    _bind_evidence(evidence, binding)
    path = getattr(evidence, name)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["checks"][next(iter(value["checks"]))] = False
    path.write_text(json.dumps(value), encoding="utf-8")
    authority = WP17CertificationAuthorityV1(
        state_path=tmp_path / "new-certificate.json",
        signing_key=b"n" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
        generation_binding=binding,
    )
    with pytest.raises(RuntimeError, match=f"WP17_GENERATION_REHEARSAL_EVIDENCE_INVALID:{name}"):
        authority.certify(
            principal=PrincipalContextV1(actor_id=actor, authenticated=True),
            evidence=evidence,
        )
    assert not (tmp_path / "new-certificate.json").exists()


def test_generation_certificate_rejects_unsigned_historical_evaluation(tmp_path: Path) -> None:
    actor = uuid4()
    evidence = _evidence(tmp_path)
    binding = WP17GenerationBindingV2(
        credential_generation_id=uuid4(),
        activation_generation_id=uuid4(),
        certificate_generation_id=uuid4(),
        final_evidence_generation_id=uuid4(),
        activation_state_sha256="a" * 64,
        predecessor_certificate_sha256="b" * 64,
    )
    _bind_evidence(evidence, binding)
    value = json.loads(evidence.evaluation.read_text(encoding="utf-8"))
    value.pop("signature")
    evidence.evaluation.write_text(json.dumps(value), encoding="utf-8")
    authority = WP17CertificationAuthorityV1(
        state_path=tmp_path / "new-certificate.json",
        signing_key=b"n" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
        generation_binding=binding,
    )
    with pytest.raises(RuntimeError, match="WP17_GENERATION_REHEARSAL_EVIDENCE_INVALID:evaluation"):
        authority.certify(
            principal=PrincipalContextV1(actor_id=actor, authenticated=True),
            evidence=evidence,
        )


def test_generation_certificate_rejects_stale_signed_rehearsal(tmp_path: Path) -> None:
    actor = uuid4()
    evidence = _evidence(tmp_path)
    binding = WP17GenerationBindingV2(
        credential_generation_id=uuid4(),
        activation_generation_id=uuid4(),
        certificate_generation_id=uuid4(),
        final_evidence_generation_id=uuid4(),
        activation_state_sha256="a" * 64,
        predecessor_certificate_sha256="b" * 64,
    )
    _bind_evidence(evidence, binding)
    value = json.loads(evidence.evaluation.read_text(encoding="utf-8"))
    value["executed_at"] = "2020-01-01T00:00:00+00:00"
    value.pop("signature")
    evidence_key = hmac.new(
        b"n" * 32, b"mnemo.wp17-generation-rehearsal/1", hashlib.sha256
    ).digest()
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    value["signature"] = hmac.new(evidence_key, encoded, hashlib.sha256).hexdigest()
    evidence.evaluation.write_text(json.dumps(value), encoding="utf-8")
    authority = WP17CertificationAuthorityV1(
        state_path=tmp_path / "new-certificate.json",
        signing_key=b"n" * 32,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
        generation_binding=binding,
    )
    with pytest.raises(RuntimeError, match="WP17_GENERATION_REHEARSAL_EVIDENCE_INVALID:evaluation"):
        authority.certify(
            principal=PrincipalContextV1(actor_id=actor, authenticated=True),
            evidence=evidence,
        )
