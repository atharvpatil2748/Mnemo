"""Synthetic observation evidence tests; no governed database is opened."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mnemo.engine import EngineState
from mnemo_server.services.pre_certification_observation import (
    OBSERVATION_TYPE,
    TRANSPORTS,
    ObservationIdentity,
    PreCertificationObservationAuthority,
    Transport,
)
from mnemo_server.services.v2_reranker_lifecycle import V2RerankerMode


def _identity(generation: str) -> ObservationIdentity:
    return ObservationIdentity(
        credential_generation_id=generation,
        configuration_digest="a" * 64,
        database_identity="synthetic-db",
        database_sha256="b" * 64,
        model_profile_fingerprint="c" * 64,
        embedding_model="BAAI/bge-m3",
        embedding_revision="d" * 40,
        reranker_model="BAAI/bge-reranker-v2-m3",
        reranker_revision="e" * 40,
        reranker_mode="BGE_V2_M3",
        activation_sha256="f" * 64,
        operational_store_identity="1" * 64,
        runtime_binding_digest="2" * 64,
        composition_identity="3" * 64,
    )


def _authority(root: Path) -> PreCertificationObservationAuthority:
    return PreCertificationObservationAuthority(
        generation_id=uuid4(),
        signing_key=b"test-only-signing-key-32-bytes-long!!!",
        observation_root=root,
        campaign_id=uuid4(),
    )


def _runtime(identity: ObservationIdentity) -> tuple[SimpleNamespace, SimpleNamespace]:
    engine = SimpleNamespace(state=EngineState.READY, certified_read_only=True)
    runtime = SimpleNamespace(
        reranker=SimpleNamespace(
            mode=V2RerankerMode.BGE_V2_M3,
            activation_record=SimpleNamespace(revision=identity.reranker_revision),
        ),
        assembler=SimpleNamespace(
            identity=SimpleNamespace(
                database_identity=identity.database_identity,
                profile_fingerprint=identity.model_profile_fingerprint,
            )
        ),
        exposure_snapshot=SimpleNamespace(v2_exposed=True),
        embedding=SimpleNamespace(
            readiness=AsyncMock(return_value=SimpleNamespace(initialized=True, exact_identity=True))
        ),
    )
    return engine, runtime


def _four(
    authority: PreCertificationObservationAuthority,
    *,
    divergent: Transport | None = None,
) -> dict[Transport, Path]:
    identity = _identity(str(authority.generation_id))
    engine, runtime = _runtime(identity)
    return {
        transport: asyncio.run(
            authority.observe(
                transport=transport,
                identity=(
                    replace(identity, database_sha256="0" * 64)
                    if transport == divergent
                    else identity
                ),
                principal_subject="test-principal",
                correlation_id=uuid4(),
                engine=engine,
                runtime=runtime,
            )
        )
        for transport in TRANSPORTS
    }


def test_four_signed_observations_converge_without_certifying(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    observations = _four(authority)
    target = tmp_path / str(authority.generation_id) / str(authority.campaign_id) / "parity.json"
    authority.converge(observations=observations, output=target)
    result = authority.verify_convergence(target)
    assert result["status"] == "PASS"
    assert result["observation_state"] == "OBSERVATION_CONVERGED"
    assert result["evidence_type"] == "PRE_CERTIFICATION_TRANSPORT_CONVERGENCE"
    assert "CERTIFIED" not in json.dumps(result)
    for transport, path in observations.items():
        record = authority.verify_observation(path=path, transport=transport)
        assert record["evidence_type"] == OBSERVATION_TYPE
        assert record["correlation_id"]
        assert "test-principal" not in path.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="PATH_REJECTED"):
        authority.converge(observations=observations, output=tmp_path.parent / "outside.json")
    with pytest.raises(RuntimeError, match="PATH_REJECTED"):
        authority.verify_convergence(tmp_path.parent / "outside.json")


def test_observation_requires_ready_authenticated_generation(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    identity = _identity(str(authority.generation_id))
    arguments = {
        "transport": "http",
        "identity": identity,
        "principal_subject": "operator",
        "correlation_id": uuid4(),
        "engine": _runtime(identity)[0],
        "runtime": _runtime(identity)[1],
    }
    invalid_engine, _ = _runtime(identity)
    invalid_engine.state = EngineState.UNINITIALIZED
    for change in (
        {"engine": invalid_engine},
        {"principal_subject": ""},
        {"identity": replace(identity, credential_generation_id=str(uuid4()))},
        {"action": "mutate"},
    ):
        with pytest.raises(RuntimeError, match="OBSERVATION_REJECTED"):
            asyncio.run(authority.observe(**{**arguments, **change}))  # type: ignore[arg-type]
    assert not list(tmp_path.rglob("*.json"))


def test_tampering_wrong_key_and_fork_fail_closed(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    observations = _four(authority)
    wrong_key = PreCertificationObservationAuthority(
        generation_id=authority.generation_id,
        signing_key=b"another-test-only-signing-key-32-bytes!",
        observation_root=tmp_path,
        campaign_id=authority.campaign_id,
    )
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        wrong_key.verify_observation(path=observations["http"], transport="http")
    payload = json.loads(observations["http"].read_text(encoding="utf-8"))
    payload["identity"]["database_sha256"] = "0" * 64
    observations["http"].write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        authority.converge(
            observations=observations,
            output=tmp_path / str(authority.generation_id) / str(authority.campaign_id) / "p.json",
        )

    second = _authority(tmp_path / "second")
    divergent = _four(second, divergent="sse")
    with pytest.raises(RuntimeError, match="CONVERGENCE_FAILED"):
        second.converge(
            observations=divergent,
            output=(
                tmp_path
                / "second"
                / str(second.generation_id)
                / str(second.campaign_id)
                / "parity.json"
            ),
        )


def test_missing_transport_and_changed_record_rejected(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    observations = _four(authority)
    target = tmp_path / str(authority.generation_id) / str(authority.campaign_id) / "parity.json"
    with pytest.raises(RuntimeError, match="TRANSPORT_SET_INVALID"):
        authority.converge(
            observations={key: value for key, value in observations.items() if key != "sse"},
            output=target,
        )
    authority.converge(observations=observations, output=target)
    with pytest.raises(RuntimeError, match="PATH_REJECTED"):
        authority.converge(observations=observations, output=target)
    observations["sse"].write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        authority.verify_convergence(target)


def test_runtime_witness_rejects_each_unready_component(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    identity = _identity(str(authority.generation_id))
    for defect in (
        "writable",
        "reranker_mode",
        "activation_missing",
        "revision",
        "database_identity",
        "profile_fingerprint",
        "v2_hidden",
        "embedding_uninitialized",
        "embedding_inexact",
    ):
        engine, runtime = _runtime(identity)
        if defect == "writable":
            engine.certified_read_only = False
        elif defect == "reranker_mode":
            runtime.reranker.mode = V2RerankerMode.PASS_THROUGH
        elif defect == "activation_missing":
            runtime.reranker.activation_record = None
        elif defect == "revision":
            runtime.reranker.activation_record.revision = "wrong"
        elif defect == "database_identity":
            runtime.assembler.identity.database_identity = "wrong"
        elif defect == "profile_fingerprint":
            runtime.assembler.identity.profile_fingerprint = "wrong"
        elif defect == "v2_hidden":
            runtime.exposure_snapshot.v2_exposed = False
        elif defect == "embedding_uninitialized":
            runtime.embedding.readiness.return_value.initialized = False
        else:
            runtime.embedding.readiness.return_value.exact_identity = False
        with pytest.raises(RuntimeError, match="PRE_CERTIFICATION_"):
            asyncio.run(
                authority.observe(
                    transport="http",
                    identity=identity,
                    principal_subject="operator",
                    correlation_id=uuid4(),
                    engine=engine,
                    runtime=runtime,
                )
            )
    assert not list(tmp_path.rglob("*.json"))


def test_validly_signed_but_invalid_observation_fields_rejected(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    identity = _identity(str(authority.generation_id))
    engine, runtime = _runtime(identity)
    for field, replacement in (
        ("schema_version", "wrong"),
        ("evidence_type", "FINAL_CERTIFICATION_EVIDENCE"),
        ("observation_state", "CERTIFIED"),
        ("credential_generation_id", str(uuid4())),
        ("campaign_id", str(uuid4())),
        ("transport", "sse"),
        ("action", "mutate"),
        ("success", False),
        ("identity", {}),
        ("identity.credential_generation_id", str(uuid4())),
    ):
        path = asyncio.run(
            authority.observe(
                transport="http",
                identity=identity,
                principal_subject="operator",
                correlation_id=uuid4(),
                engine=engine,
                runtime=runtime,
            )
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if field == "identity.credential_generation_id":
            payload["identity"]["credential_generation_id"] = replacement
        else:
            payload[field] = replacement
        payload.pop("signature")
        payload["signature"] = authority._sign(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RuntimeError, match="OBSERVATION_INVALID"):
            authority.verify_observation(path=path, transport="http")


def test_validly_signed_but_invalid_convergence_fields_rejected(tmp_path: Path) -> None:
    for field, replacement in (
        ("schema_version", "wrong"),
        ("evidence_type", OBSERVATION_TYPE),
        ("observation_state", "CERTIFIED"),
        ("status", "FAIL"),
        ("credential_generation_id", str(uuid4())),
        ("campaign_id", str(uuid4())),
        ("observations", {}),
    ):
        root = tmp_path / str(uuid4())
        authority = _authority(root)
        observations = _four(authority)
        target = root / str(authority.generation_id) / str(authority.campaign_id) / "parity.json"
        authority.converge(observations=observations, output=target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload[field] = replacement
        payload.pop("signature")
        payload["signature"] = authority._sign(payload)
        target.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RuntimeError, match="CONVERGENCE_INVALID"):
            authority.verify_convergence(target)


def test_observation_evidence_rejects_missing_and_nondocument_payloads(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    generation = str(authority.generation_id)
    campaign = str(authority.campaign_id)
    missing = tmp_path / generation / campaign / "missing.json"
    with pytest.raises(RuntimeError, match="EVIDENCE_UNAVAILABLE"):
        authority.verify_observation(path=missing, transport="http")
    missing.parent.mkdir(parents=True)
    missing.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="EVIDENCE_INVALID"):
        authority.verify_observation(path=missing, transport="http")
    missing.write_text("{malformed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="EVIDENCE_UNAVAILABLE"):
        authority.verify_observation(path=missing, transport="http")
    missing.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        authority.verify_observation(path=missing, transport="http")
    with pytest.raises(ValueError, match="AUTHORITY_INVALID"):
        PreCertificationObservationAuthority(
            generation_id=authority.generation_id,
            signing_key=b"short",
            observation_root=tmp_path,
            campaign_id=authority.campaign_id,
        )
    with pytest.raises(ValueError, match="AUTHORITY_INVALID"):
        PreCertificationObservationAuthority(
            generation_id=authority.generation_id,
            signing_key=b"x" * 32,
            observation_root=Path("relative-observations"),
            campaign_id=authority.campaign_id,
        )


def test_signed_convergence_rechecks_record_hash_and_identity(tmp_path: Path) -> None:
    for defect, expected in (
        ("record_hash", "OBSERVATION_CHANGED"),
        ("record_correlation", "OBSERVATION_CHANGED"),
        ("identity", "CONVERGENCE_FAILED"),
        ("reference_type", "CONVERGENCE_INVALID"),
    ):
        root = tmp_path / str(uuid4())
        authority = _authority(root)
        observations = _four(authority)
        target = root / str(authority.generation_id) / str(authority.campaign_id) / "parity.json"
        authority.converge(observations=observations, output=target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        if defect == "record_hash":
            payload["observations"]["http"]["sha256"] = "0" * 64
        elif defect == "record_correlation":
            payload["observations"]["http"]["correlation_id"] = str(uuid4())
        elif defect == "identity":
            payload["identity"]["database_sha256"] = "0" * 64
        else:
            payload["observations"]["http"] = "wrong"
        payload.pop("signature")
        payload["signature"] = authority._sign(payload)
        target.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RuntimeError, match=expected):
            authority.verify_convergence(target)


def test_duplicate_correlation_is_not_convergence(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    observations = _four(authority)
    first = json.loads(observations["http"].read_text(encoding="utf-8"))
    second = json.loads(observations["sse"].read_text(encoding="utf-8"))
    second["correlation_id"] = first["correlation_id"]
    second.pop("signature")
    second["signature"] = authority._sign(second)
    observations["sse"].write_text(json.dumps(second), encoding="utf-8")
    target = tmp_path / str(authority.generation_id) / str(authority.campaign_id) / "parity.json"
    with pytest.raises(RuntimeError, match="CONVERGENCE_FAILED"):
        authority.converge(observations=observations, output=target)
    assert not target.exists()
