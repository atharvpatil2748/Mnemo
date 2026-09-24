"""Synthetic signed-chain checks for a new final-evidence generation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.services.production_generation_evidence import (
    ProductionGenerationEvidenceAuthority,
)
from mnemo_server.services.v2_certification import (
    STORE_IDENTITY,
    WP17CertificationAuthorityV1,
    WP17GenerationBindingV2,
)
from mnemo_server.services.v2_reranker_lifecycle import (
    DurableRerankerActivationStoreV1,
    RerankerActivationEvidenceV1,
    V2RerankerMode,
)
from test_generation_bound_certification import _bind_evidence, _evidence


def _chain(
    tmp_path: Path,
    credential_id: UUID | None = None,
    *,
    cursor_signing_key: bytes = b"d" * 32,
    certification_signing_key: bytes = b"c" * 32,
    model_profile_fingerprint: str = "a" * 64,
    stage_activation: Callable[[Path, UUID], UUID] | None = None,
) -> ProductionGenerationEvidenceAuthority:
    tmp_path.mkdir(parents=True, exist_ok=True)
    actor = uuid4()
    principal = PrincipalContextV1(actor_id=actor, authenticated=True)
    credential_id = credential_id or uuid4()
    activation_id = uuid4()
    activation_path = tmp_path / "new-activation.json"
    activation_store = DurableRerankerActivationStoreV1(
        path=activation_path,
        signing_key=cursor_signing_key,
        prohibited_paths=(),
        credential_generation_id=credential_id,
        activation_generation_id=activation_id,
    )
    activation_store.commit(
        desired_mode=V2RerankerMode.BGE_V2_M3,
        principal=principal,
        evidence=RerankerActivationEvidenceV1(
            v2_exposed=True,
            production_evaluation_passed=True,
            production_store_identity=STORE_IDENTITY,
            expected_production_store_identity=STORE_IDENTITY,
        ),
    )
    activation_sha = hashlib.sha256(activation_path.read_bytes()).hexdigest()
    campaign_id = (
        stage_activation(activation_path, activation_id) if stage_activation is not None else None
    )
    binding = WP17GenerationBindingV2(
        credential_generation_id=credential_id,
        activation_generation_id=activation_id,
        certificate_generation_id=uuid4(),
        final_evidence_generation_id=uuid4(),
        activation_state_sha256=activation_sha,
        predecessor_certificate_sha256="1" * 64,
    )
    evidence = _evidence(tmp_path)
    _bind_evidence(
        evidence,
        binding,
        certification_signing_key,
        model_profile_fingerprint=model_profile_fingerprint,
        campaign_id=campaign_id,
    )
    certificate_path = tmp_path / "new-certificate.json"
    authority = WP17CertificationAuthorityV1(
        state_path=certificate_path,
        signing_key=certification_signing_key,
        authorized_operator_actor_id=actor,
        prohibited_paths=(),
        generation_binding=binding,
    )
    authority.certify(principal=principal, evidence=evidence)
    return ProductionGenerationEvidenceAuthority(
        activation_path=activation_path,
        certificate_path=certificate_path,
        transport_parity_path=evidence.transport_parity,
        final_evidence_path=tmp_path / "new-final-evidence.json",
        cursor_signing_key=cursor_signing_key,
        certification_signing_key=certification_signing_key,
        generation_binding=binding,
        model_profile_fingerprint=model_profile_fingerprint,
        predecessor_final_evidence_sha256="2" * 64,
    )


def test_final_evidence_verifies_complete_signed_chain(tmp_path: Path) -> None:
    authority = _chain(tmp_path)
    result = authority.create()
    assert result["status"] == "PRODUCTION_CERTIFICATION_PASS"
    assert authority.verify() == result
    with pytest.raises(RuntimeError, match="ALREADY_EXISTS"):
        authority.create()


def test_final_evidence_rejects_tampering_and_wrong_signer(tmp_path: Path) -> None:
    authority = _chain(tmp_path)
    authority.create()
    final_path = tmp_path / "new-final-evidence.json"
    value = json.loads(final_path.read_text(encoding="utf-8"))
    value["model_profile_fingerprint"] = "f" * 64
    final_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        authority.verify()


def test_final_evidence_rejects_changed_transport_evidence(tmp_path: Path) -> None:
    authority = _chain(tmp_path)
    authority.create()
    transport_path = tmp_path / "transport_parity.json"
    transport_path.write_text('{"status":"PASS","observations":{}}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSPORT_EVIDENCE_MISMATCH"):
        authority.verify()
