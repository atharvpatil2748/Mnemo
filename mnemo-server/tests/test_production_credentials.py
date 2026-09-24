"""Isolated credential-generation tests; never use the OS credential store."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mnemo_server.services.production_credentials import (
    CertificationStage,
    CredentialGeneration,
    CredentialKind,
    CredentialRegistryDocument,
    CredentialState,
    ProductionCredentialRegistry,
    _write_new,
)
from mnemo_server.services.production_generation_evidence import (
    ProductionGenerationEvidenceAuthority,
)
from pydantic import ValidationError
from test_production_generation_evidence import _chain


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def put(self, reference: str, secret: str) -> None:
        self.values[reference] = secret

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


def _registry(tmp_path: Path) -> tuple[ProductionCredentialRegistry, FakeSecretStore]:
    store = FakeSecretStore()
    return (
        ProductionCredentialRegistry(path=tmp_path / "credentials.json", secret_store=store),
        store,
    )


def test_provisioning_is_secret_free_and_not_active(tmp_path: Path) -> None:
    registry, store = _registry(tmp_path)
    record = registry.provision(
        kinds=(
            CredentialKind.DELIVERY_CURSOR,
            CredentialKind.API_KEY,
            CredentialKind.CERTIFICATION_SIGNING,
        ),
        owner_subject="local-operator",
        service_subject="local-mcp-service",
        scope="certified-v2",
        reason="re-key after original credential loss",
    )
    assert record.state is CredentialState.PROVISIONED
    assert registry.load().active_generation_id is None
    assert len(store.values) == 3
    assert registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
    metadata = registry.path.read_text(encoding="utf-8")
    markdown = registry.render_markdown()
    assert str(record.generation_id) in metadata
    assert str(record.generation_id) in markdown
    for secret in store.values.values():
        assert secret not in metadata
        assert secret not in markdown
    assert all(len(secret) >= 32 for secret in store.values.values())


@pytest.mark.parametrize(
    "kinds",
    [
        (),
        (CredentialKind.API_KEY,),
        (CredentialKind.DELIVERY_CURSOR,),
        (CredentialKind.DELIVERY_CURSOR, CredentialKind.API_KEY),
        (CredentialKind.DELIVERY_CURSOR, CredentialKind.API_KEY, CredentialKind.JWT_SECRET),
        (CredentialKind.DELIVERY_CURSOR, CredentialKind.API_KEY, CredentialKind.API_KEY),
    ],
)
def test_invalid_credential_sets_do_not_write(
    tmp_path: Path, kinds: tuple[CredentialKind, ...]
) -> None:
    registry, store = _registry(tmp_path)
    with pytest.raises(ValueError):
        registry.provision(
            kinds=kinds,
            owner_subject="local-operator",
            service_subject="local-mcp-service",
            scope="certified-v2",
            reason="test",
        )
    assert not registry.path.exists()
    assert not store.values


def test_missing_and_mismatched_secret_fail_closed(tmp_path: Path) -> None:
    registry, store = _registry(tmp_path)
    record = registry.provision(
        kinds=(
            CredentialKind.DELIVERY_CURSOR,
            CredentialKind.API_KEY,
            CredentialKind.CERTIFICATION_SIGNING,
        ),
        owner_subject="local-operator",
        service_subject="local-mcp-service",
        scope="certified-v2",
        reason="test",
    )
    reference = record.secrets[0].store_reference
    store.values[reference] = "a different secret"
    with pytest.raises(RuntimeError, match="MNEMO_CREDENTIAL_FINGERPRINT_MISMATCH"):
        registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
    store.delete(reference)
    with pytest.raises(RuntimeError, match="MNEMO_CREDENTIAL_FINGERPRINT_MISMATCH"):
        registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)


def test_corrupt_registry_and_false_active_pointer_fail_closed(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    registry.path.write_text('{"schema_version":"wrong"}', encoding="utf-8")
    with pytest.raises(ValidationError):
        registry.load()
    registry.path.write_text(
        json.dumps(
            {
                "schema_version": "mnemo.production-credential-registry/1",
                "active_generation_id": "00000000-0000-0000-0000-000000000001",
                "generations": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        registry.load()


def test_domain_separation_rejects_tunnel_and_provider_records() -> None:
    for domain in ("TUNNEL_CLIENT", "OPENAI_PROVIDER"):
        with pytest.raises(ValidationError):
            CredentialGeneration(
                generation_id="00000000-0000-0000-0000-000000000001",
                domain=domain,
                owner_subject="operator",
                scope="production",
                state=CredentialState.PROVISIONED,
                created_at="2026-09-23T00:00:00+00:00",
            )


def test_duplicate_generation_and_relative_registry_path_rejected(tmp_path: Path) -> None:
    _, store = _registry(tmp_path)
    record = CredentialGeneration(
        generation_id="00000000-0000-0000-0000-000000000001",
        owner_subject="operator",
        scope="production",
        state=CredentialState.SUPERSEDED,
        created_at="2026-09-23T00:00:00+00:00",
    )
    with pytest.raises(ValidationError):
        CredentialRegistryDocument(generations=(record, record))
    with pytest.raises(ValueError, match="NOT_ABSOLUTE"):
        ProductionCredentialRegistry(path=Path("credentials.json"), secret_store=store)


def _provision(registry: ProductionCredentialRegistry) -> CredentialGeneration:
    return registry.provision(
        kinds=(
            CredentialKind.DELIVERY_CURSOR,
            CredentialKind.API_KEY,
            CredentialKind.CERTIFICATION_SIGNING,
        ),
        owner_subject="local-operator",
        service_subject="local-mcp-service",
        scope="certified-v2",
        reason="re-key after original credential loss",
    )


def _bound_chain(
    tmp_path: Path,
    registry: ProductionCredentialRegistry,
    generation_id: UUID,
    *,
    model_profile_fingerprint: str = "a" * 64,
    stage_activation: Callable[[Path, UUID], UUID] | None = None,
) -> ProductionGenerationEvidenceAuthority:
    cursor = registry.retrieve(generation_id, CredentialKind.DELIVERY_CURSOR)
    certificate = registry.retrieve(generation_id, CredentialKind.CERTIFICATION_SIGNING)
    return _chain(
        tmp_path,
        generation_id,
        cursor_signing_key=hmac.new(
            cursor.encode("utf-8"), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
        ).digest(),
        certification_signing_key=certificate.encode("utf-8"),
        model_profile_fingerprint=model_profile_fingerprint,
        stage_activation=stage_activation,
    )


def test_evidence_validation_promotion_and_revocation(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    record = _provision(registry)
    with pytest.raises(RuntimeError, match="ACTIVE_CREDENTIAL_UNAVAILABLE"):
        registry.retrieve_active(CredentialKind.API_KEY)
    authority = _bound_chain(tmp_path / "chain", registry, record.generation_id)
    authority.create()
    validated = registry.validate_with_evidence(
        generation_id=record.generation_id, authority=authority
    )
    assert validated.state is CredentialState.VALIDATED
    assert registry.load().active_generation_id is None
    promoted = registry.promote(generation_id=record.generation_id, authority=authority)
    assert promoted.state is CredentialState.ACTIVE
    active, secret = registry.retrieve_active(CredentialKind.API_KEY)
    assert active.generation_id == record.generation_id
    assert secret
    registry.revoke(record.generation_id)
    assert registry.load().active_generation_id is None
    with pytest.raises(RuntimeError, match="ACTIVE_CREDENTIAL_UNAVAILABLE"):
        registry.retrieve_active(CredentialKind.API_KEY)
    with pytest.raises(RuntimeError, match="GENERATION_UNAVAILABLE"):
        registry.retrieve(record.generation_id, CredentialKind.API_KEY)


def test_staged_observation_requires_signed_convergence_before_final_evidence(
    tmp_path: Path,
) -> None:
    registry, _ = _registry(tmp_path)
    record = _provision(registry)
    cursor = registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
    certification = registry.retrieve(record.generation_id, CredentialKind.CERTIFICATION_SIGNING)

    def stage(path: Path, activation_id: UUID) -> UUID:
        staged = registry.stage_observation(
            generation_id=record.generation_id,
            activation_path=path,
            activation_generation_id=activation_id,
        )
        assert staged.certification_stage is CertificationStage.PRE_CERTIFICATION_OBSERVATION
        assert staged.observation_campaign_id is not None
        return staged.observation_campaign_id

    authority = _chain(
        tmp_path / "chain",
        record.generation_id,
        cursor_signing_key=hmac.new(
            cursor.encode(), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
        ).digest(),
        certification_signing_key=certification.encode(),
        stage_activation=stage,
    )
    with pytest.raises(RuntimeError, match="FINAL_EVIDENCE_STAGE_INVALID"):
        registry.record_final_evidence(generation_id=record.generation_id, authority=authority)
    observed = registry.record_observation_convergence(
        generation_id=record.generation_id, convergence_path=authority.transport_parity_path
    )
    assert observed.certification_stage is CertificationStage.OBSERVATION_CONVERGED
    with pytest.raises(RuntimeError, match="OBSERVATION_STAGE_INVALID"):
        registry.record_observation_convergence(
            generation_id=record.generation_id, convergence_path=authority.transport_parity_path
        )
    authority.create()
    recorded = registry.record_final_evidence(
        generation_id=record.generation_id, authority=authority
    )
    assert recorded.certification_stage is CertificationStage.FINAL_EVIDENCE_GENERATED
    validated = registry.validate_with_evidence(
        generation_id=record.generation_id, authority=authority
    )
    assert validated.certification_stage is CertificationStage.CERTIFIED
    assert registry.load().active_generation_id is None
    promoted = registry.promote(generation_id=record.generation_id, authority=authority)
    assert promoted.certification_stage is CertificationStage.ACTIVE


def test_observation_stage_rejects_wrong_generation_and_paths(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    record = _provision(registry)
    with pytest.raises(RuntimeError, match="GENERATION_AMBIGUOUS"):
        registry.stage_observation(
            generation_id=uuid4(),
            activation_path=tmp_path / "absent.json",
            activation_generation_id=uuid4(),
        )
    with pytest.raises(RuntimeError, match="OBSERVATION_STAGE_INVALID"):
        registry.record_observation_convergence(
            generation_id=record.generation_id,
            convergence_path=tmp_path / "absent.json",
        )
    cursor = registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
    certification = registry.retrieve(record.generation_id, CredentialKind.CERTIFICATION_SIGNING)
    campaign: UUID | None = None

    def stage(path: Path, activation_id: UUID) -> UUID:
        nonlocal campaign
        with pytest.raises(RuntimeError, match="ACTIVATION_PATH_REJECTED"):
            registry.stage_observation(
                generation_id=record.generation_id,
                activation_path=registry.path,
                activation_generation_id=activation_id,
            )
        staged = registry.stage_observation(
            generation_id=record.generation_id,
            activation_path=path,
            activation_generation_id=activation_id,
        )
        campaign = staged.observation_campaign_id
        assert campaign is not None
        with pytest.raises(RuntimeError, match="ALREADY_STAGED"):
            registry.stage_observation(
                generation_id=record.generation_id,
                activation_path=path,
                activation_generation_id=activation_id,
            )
        return campaign

    authority = _chain(
        tmp_path / "chain",
        record.generation_id,
        cursor_signing_key=hmac.new(
            cursor.encode(), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
        ).digest(),
        certification_signing_key=certification.encode(),
        stage_activation=stage,
    )
    assert campaign is not None
    with pytest.raises(RuntimeError, match="OBSERVATION_PATH_REJECTED"):
        registry.record_observation_convergence(
            generation_id=record.generation_id,
            convergence_path=Path(__file__),
        )
    registry.record_observation_convergence(
        generation_id=record.generation_id,
        convergence_path=authority.transport_parity_path,
    )
    assert registry.load().active_generation_id is None


def test_failed_rekey_keeps_previous_active(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    first = _provision(registry)
    first_authority = _bound_chain(tmp_path / "first", registry, first.generation_id)
    first_authority.create()
    registry.validate_with_evidence(generation_id=first.generation_id, authority=first_authority)
    registry.promote(generation_id=first.generation_id, authority=first_authority)

    second = _provision(registry)
    second_authority = _bound_chain(tmp_path / "second", registry, second.generation_id)
    second_authority.create()
    registry.validate_with_evidence(generation_id=second.generation_id, authority=second_authority)
    final_path = tmp_path / "second" / "new-final-evidence.json"
    final_path.write_text('{"corrupt":true}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        registry.promote(generation_id=second.generation_id, authority=second_authority)
    assert registry.load().active_generation_id == first.generation_id
    assert registry.load().generations[0].state is CredentialState.ACTIVE
    assert registry.load().generations[1].state is CredentialState.VALIDATED


def test_evidence_signed_by_other_keys_cannot_validate_generation(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    record = _provision(registry)
    foreign_authority = _chain(tmp_path / "foreign", record.generation_id)
    foreign_authority.create()
    with pytest.raises(RuntimeError, match="EVIDENCE_KEY_MISMATCH"):
        registry.validate_with_evidence(
            generation_id=record.generation_id, authority=foreign_authority
        )
    assert registry.load().active_generation_id is None
    assert registry.load().generations[0].state is CredentialState.PROVISIONED


def test_successful_rekey_preserves_prior_evidence_and_supersedes(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    first = _provision(registry)
    first_authority = _bound_chain(tmp_path / "first", registry, first.generation_id)
    first_authority.create()
    registry.validate_with_evidence(generation_id=first.generation_id, authority=first_authority)
    registry.promote(generation_id=first.generation_id, authority=first_authority)
    first_paths = first_authority.artifact_paths
    original_bytes = tuple(path.read_bytes() for path in first_paths)

    second = _provision(registry)
    second_authority = _bound_chain(tmp_path / "second", registry, second.generation_id)
    second_authority.create()
    registry.validate_with_evidence(generation_id=second.generation_id, authority=second_authority)
    registry.promote(generation_id=second.generation_id, authority=second_authority)

    document = registry.load()
    assert document.active_generation_id == second.generation_id
    assert document.generations[0].state is CredentialState.SUPERSEDED
    assert document.generations[0].superseded_at is not None
    assert document.generations[1].state is CredentialState.ACTIVE
    assert tuple(path.read_bytes() for path in first_paths) == original_bytes
    assert registry.retrieve_active(CredentialKind.API_KEY)[0].generation_id == second.generation_id
    with pytest.raises(RuntimeError, match="NOT_VALIDATED"):
        registry.promote(generation_id=first.generation_id, authority=first_authority)


def test_missing_generation_and_missing_secret_fail_closed(tmp_path: Path) -> None:
    registry, store = _registry(tmp_path)
    missing = UUID("00000000-0000-0000-0000-000000000001")
    with pytest.raises(RuntimeError, match="GENERATION_UNAVAILABLE"):
        registry.retrieve(missing, CredentialKind.API_KEY)
    with pytest.raises(RuntimeError, match="NOT_PROVISIONED"):
        registry.validate_with_evidence(
            generation_id=missing,
            authority=_chain(tmp_path / "unused", missing),
        )
    record = _provision(registry)
    with pytest.raises(RuntimeError, match="NOT_VALIDATED"):
        registry.promote(
            generation_id=record.generation_id,
            authority=_bound_chain(tmp_path / "unused2", registry, record.generation_id),
        )
    reference = record.secrets[0].store_reference
    store.delete(reference)
    with pytest.raises(RuntimeError, match="FINGERPRINT_MISMATCH"):
        registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)


def test_generation_artifact_create_only_never_replaces_existing(tmp_path: Path) -> None:
    artifact = tmp_path / "activation-history.json"
    _write_new(artifact, "first\n")
    with pytest.raises(FileExistsError):
        _write_new(artifact, "replacement\n")
    assert artifact.read_text(encoding="utf-8") == "first\n"


def test_partial_secret_store_failure_does_not_publish_generation(tmp_path: Path) -> None:
    class FailingStore(FakeSecretStore):
        def put(self, reference: str, secret: str) -> None:
            if len(self.values) == 1:
                raise RuntimeError("synthetic store failure")
            super().put(reference, secret)

    store = FailingStore()
    registry = ProductionCredentialRegistry(path=tmp_path / "registry.json", secret_store=store)
    with pytest.raises(RuntimeError, match="synthetic store failure"):
        registry.provision(
            kinds=(
                CredentialKind.DELIVERY_CURSOR,
                CredentialKind.API_KEY,
                CredentialKind.CERTIFICATION_SIGNING,
            ),
            owner_subject="local-operator",
            service_subject="local-mcp-service",
            scope="certified-v2",
            reason="test",
        )
    assert registry.load().generations == ()
    assert not registry.path.exists()
    assert not store.values


def test_registry_write_failure_removes_new_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, store = _registry(tmp_path)

    def fail_save(_document: CredentialRegistryDocument) -> None:
        raise OSError("synthetic registry storage failure")

    monkeypatch.setattr(registry, "_save", fail_save)
    with pytest.raises(OSError, match="synthetic registry storage failure"):
        _provision(registry)
    assert not store.values
    assert not registry.path.exists()


def test_wrong_generation_evidence_cannot_be_validated(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    record = _provision(registry)
    cursor = registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
    certification = registry.retrieve(record.generation_id, CredentialKind.CERTIFICATION_SIGNING)
    wrong_generation = UUID("00000000-0000-0000-0000-000000000002")
    authority = _chain(
        tmp_path / "wrong-generation",
        wrong_generation,
        cursor_signing_key=hmac.new(
            cursor.encode(), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
        ).digest(),
        certification_signing_key=certification.encode(),
    )
    authority.create()
    with pytest.raises(RuntimeError, match="EVIDENCE_GENERATION_MISMATCH"):
        registry.validate_with_evidence(generation_id=record.generation_id, authority=authority)
    assert registry.load().generations[0].state is CredentialState.PROVISIONED


def test_promotion_rejects_another_signed_artifact_set(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    record = _provision(registry)
    authority = _bound_chain(tmp_path / "first", registry, record.generation_id)
    authority.create()
    registry.validate_with_evidence(generation_id=record.generation_id, authority=authority)
    second_authority = _bound_chain(tmp_path / "second", registry, record.generation_id)
    second_authority.create()
    with pytest.raises(RuntimeError, match="EVIDENCE_CHANGED"):
        registry.promote(generation_id=record.generation_id, authority=second_authority)
    assert registry.load().active_generation_id is None


def test_revocation_and_missing_kind_are_unavailable(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    record = _provision(registry)
    with pytest.raises(RuntimeError, match="GENERATION_UNAVAILABLE"):
        registry.retrieve(record.generation_id, CredentialKind.JWT_SECRET)
    registry.revoke(record.generation_id)
    with pytest.raises(RuntimeError, match="GENERATION_UNAVAILABLE"):
        registry.revoke(record.generation_id)
    with pytest.raises(RuntimeError, match="GENERATION_UNAVAILABLE"):
        registry.retrieve(record.generation_id, CredentialKind.API_KEY)
