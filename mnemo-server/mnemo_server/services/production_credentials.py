"""Non-secret production credential generations backed by an OS secret store.

This module does not activate a generation or certify evidence. Provisioning and
production promotion are deliberately separate operations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from mnemo_server.services.production_generation_evidence import (
        ProductionGenerationEvidenceAuthority,
    )


class CredentialKind(StrEnum):
    DELIVERY_CURSOR = "DELIVERY_CURSOR_SECRET"
    API_KEY = "API_KEY"
    JWT_SECRET = "JWT_SECRET"
    CERTIFICATION_SIGNING = "CERTIFICATION_SIGNING_SECRET"


class CredentialState(StrEnum):
    PROVISIONED = "PROVISIONED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"
    INVALID = "INVALID"


class CertificationStage(StrEnum):
    """Observation/evidence state; it never aliases active credential state."""

    CREDENTIAL_PROVISIONED = "CREDENTIAL_PROVISIONED"
    PRE_CERTIFICATION_OBSERVATION = "PRE_CERTIFICATION_OBSERVATION"
    OBSERVATION_CONVERGED = "OBSERVATION_CONVERGED"
    FINAL_EVIDENCE_GENERATED = "FINAL_EVIDENCE_GENERATED"
    CERTIFIED = "CERTIFIED"
    ACTIVE = "ACTIVE"


class SecretStore(Protocol):
    def put(self, reference: str, secret: str) -> None: ...

    def get(self, reference: str) -> str | None: ...

    def delete(self, reference: str) -> None: ...


class WindowsCredentialStore:
    """Fail-closed adapter to the current user's Windows Credential Manager."""

    _service = "mnemo-production"

    @staticmethod
    def _backend() -> object:
        if os.name != "nt":
            raise RuntimeError("MNEMO_OS_CREDENTIAL_STORE_UNAVAILABLE")
        import keyring

        backend = keyring.get_keyring()
        if type(backend).__module__ != "keyring.backends.Windows":
            raise RuntimeError("MNEMO_OS_CREDENTIAL_STORE_UNAVAILABLE")
        return keyring

    def put(self, reference: str, secret: str) -> None:
        self._backend().set_password(self._service, reference, secret)  # type: ignore[attr-defined]

    def get(self, reference: str) -> str | None:
        return cast(
            str | None,
            self._backend().get_password(self._service, reference),  # type: ignore[attr-defined]
        )

    def delete(self, reference: str) -> None:
        self._backend().delete_password(self._service, reference)  # type: ignore[attr-defined]


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


class CredentialSecretReference(BaseModel):
    """A fingerprint and an OS-store locator, never credential material."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CredentialKind
    store_reference: str = Field(min_length=1)
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CredentialGeneration(BaseModel):
    """Public generation metadata only; secrets are never part of this model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generation_id: UUID
    domain: str = "MNEMO_SERVER"
    owner_subject: str = Field(min_length=1)
    service_subject: str | None = None
    scope: str = Field(min_length=1)
    state: CredentialState
    created_at: str
    activated_at: str | None = None
    superseded_at: str | None = None
    rotation_reason: str | None = None
    secrets: tuple[CredentialSecretReference, ...] = ()
    activation_path: str | None = None
    activation_sha256: str | None = None
    certificate_path: str | None = None
    certificate_sha256: str | None = None
    final_evidence_path: str | None = None
    final_evidence_sha256: str | None = None
    observation_campaign_id: UUID | None = None
    observation_convergence_path: str | None = None
    observation_convergence_sha256: str | None = None

    @property
    def certification_stage(self) -> CertificationStage:
        if self.state is CredentialState.ACTIVE:
            return CertificationStage.ACTIVE
        if self.state is CredentialState.VALIDATED:
            return CertificationStage.CERTIFIED
        if self.final_evidence_path is not None:
            return CertificationStage.FINAL_EVIDENCE_GENERATED
        if self.observation_convergence_path is not None:
            return CertificationStage.OBSERVATION_CONVERGED
        if self.observation_campaign_id is not None:
            return CertificationStage.PRE_CERTIFICATION_OBSERVATION
        return CertificationStage.CREDENTIAL_PROVISIONED

    @model_validator(mode="after")
    def _valid(self) -> CredentialGeneration:
        if self.domain != "MNEMO_SERVER":
            raise ValueError("MNEMO_CREDENTIAL_DOMAIN_INVALID")
        kinds = [item.kind for item in self.secrets]
        if len(kinds) != len(set(kinds)):
            raise ValueError("MNEMO_CREDENTIAL_KIND_DUPLICATE")
        references = [item.store_reference for item in self.secrets]
        if len(references) != len(set(references)):
            raise ValueError("MNEMO_CREDENTIAL_REFERENCE_DUPLICATE")
        if self.state in {CredentialState.VALIDATED, CredentialState.ACTIVE} and (
            CredentialKind.DELIVERY_CURSOR not in kinds
            or CredentialKind.CERTIFICATION_SIGNING not in kinds
            or (CredentialKind.API_KEY in kinds) == (CredentialKind.JWT_SECRET in kinds)
        ):
            raise ValueError("MNEMO_CREDENTIAL_BUNDLE_INCOMPLETE")
        if self.state in {CredentialState.VALIDATED, CredentialState.ACTIVE} and (
            not self.secrets or not self.service_subject
        ):
            raise ValueError("MNEMO_CREDENTIAL_METADATA_INCOMPLETE")
        if self.state in {CredentialState.VALIDATED, CredentialState.ACTIVE} and not all(
            (
                self.activation_path,
                self.activation_sha256,
                self.certificate_path,
                self.certificate_sha256,
                self.final_evidence_path,
                self.final_evidence_sha256,
            )
        ):
            raise ValueError("MNEMO_CREDENTIAL_EVIDENCE_INCOMPLETE")
        if (self.observation_convergence_path is None) != (
            self.observation_convergence_sha256 is None
        ):
            raise ValueError("MNEMO_OBSERVATION_CONVERGENCE_METADATA_INVALID")
        return self


class CredentialRegistryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "mnemo.production-credential-registry/1"
    active_generation_id: UUID | None = None
    generations: tuple[CredentialGeneration, ...] = ()

    @model_validator(mode="after")
    def _valid(self) -> CredentialRegistryDocument:
        if self.schema_version != "mnemo.production-credential-registry/1":
            raise ValueError("MNEMO_CREDENTIAL_REGISTRY_SCHEMA_INVALID")
        ids = [record.generation_id for record in self.generations]
        if len(ids) != len(set(ids)):
            raise ValueError("MNEMO_CREDENTIAL_GENERATION_DUPLICATE")
        active = [record for record in self.generations if record.state is CredentialState.ACTIVE]
        if self.active_generation_id is None:
            if active:
                raise ValueError("MNEMO_CREDENTIAL_ACTIVE_POINTER_MISSING")
        elif len(active) != 1 or active[0].generation_id != self.active_generation_id:
            raise ValueError("MNEMO_CREDENTIAL_ACTIVE_POINTER_INVALID")
        return self


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_new(path: Path, content: str) -> None:
    """Create one immutable generation artifact without a replace race."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


class ProductionCredentialRegistry:
    """Operator-owned metadata registry, not a store for credential values."""

    def __init__(self, *, path: Path, secret_store: SecretStore) -> None:
        if not path.is_absolute():
            raise ValueError("MNEMO_CREDENTIAL_REGISTRY_PATH_NOT_ABSOLUTE")
        self.path = path.resolve()
        self.secret_store = secret_store

    def load(self) -> CredentialRegistryDocument:
        if not self.path.exists():
            return CredentialRegistryDocument()
        return CredentialRegistryDocument.model_validate_json(self.path.read_text(encoding="utf-8"))

    def provision(
        self,
        *,
        kinds: tuple[CredentialKind, ...],
        owner_subject: str,
        service_subject: str,
        scope: str,
        reason: str,
    ) -> CredentialGeneration:
        if not kinds or len(kinds) != len(set(kinds)):
            raise ValueError("MNEMO_CREDENTIAL_KIND_SET_INVALID")
        if CredentialKind.DELIVERY_CURSOR not in kinds:
            raise ValueError("MNEMO_DELIVERY_CREDENTIAL_REQUIRED")
        if CredentialKind.CERTIFICATION_SIGNING not in kinds:
            raise ValueError("MNEMO_CERTIFICATION_CREDENTIAL_REQUIRED")
        if (CredentialKind.API_KEY in kinds) == (CredentialKind.JWT_SECRET in kinds):
            raise ValueError("MNEMO_AUTH_CREDENTIAL_SELECTION_INVALID")
        document = self.load()
        generation_id = uuid4()
        references: list[CredentialSecretReference] = []
        created: list[str] = []
        try:
            for kind in kinds:
                reference = f"mnemo:{generation_id}:{kind.value}"
                secret = secrets.token_urlsafe(48)
                self.secret_store.put(reference, secret)
                created.append(reference)
                references.append(
                    CredentialSecretReference(
                        kind=kind,
                        store_reference=reference,
                        fingerprint_sha256=_fingerprint(secret),
                    )
                )
        except BaseException:
            for reference in created:
                self.secret_store.delete(reference)
            raise
        record = CredentialGeneration(
            generation_id=generation_id,
            owner_subject=owner_subject,
            service_subject=service_subject,
            scope=scope,
            state=CredentialState.PROVISIONED,
            created_at=_timestamp(),
            rotation_reason=reason,
            secrets=tuple(references),
        )
        try:
            self._save(document.model_copy(update={"generations": (*document.generations, record)}))
        except BaseException:
            for reference in created:
                self.secret_store.delete(reference)
            raise
        return record

    def validate_with_evidence(
        self,
        *,
        generation_id: UUID,
        authority: ProductionGenerationEvidenceAuthority,
    ) -> CredentialGeneration:
        """Bind a staged generation only to independently verified signed files."""
        document = self.load()
        record = next(
            (item for item in document.generations if item.generation_id == generation_id), None
        )
        if record is None or record.state is not CredentialState.PROVISIONED:
            raise RuntimeError("MNEMO_CREDENTIAL_NOT_PROVISIONED")
        if record.observation_campaign_id is not None and (
            record.final_evidence_path != str(authority.artifact_paths[2])
            or record.final_evidence_sha256 != _digest_file(authority.artifact_paths[2])
            or record.observation_convergence_path != str(authority.transport_parity_path)
            or record.observation_convergence_sha256
            != _digest_file(authority.transport_parity_path)
        ):
            raise RuntimeError("MNEMO_PRE_CERTIFICATION_CHAIN_INCOMPLETE")
        self._verify_authority_keys(record, authority)
        result = authority.verify()
        if result.get("credential_generation_id") != str(generation_id):
            raise RuntimeError("MNEMO_CREDENTIAL_EVIDENCE_GENERATION_MISMATCH")
        paths = authority.artifact_paths
        validated = record.model_copy(
            update={
                "state": CredentialState.VALIDATED,
                "activation_path": str(paths[0]),
                "activation_sha256": _digest_file(paths[0]),
                "certificate_path": str(paths[1]),
                "certificate_sha256": _digest_file(paths[1]),
                "final_evidence_path": str(paths[2]),
                "final_evidence_sha256": _digest_file(paths[2]),
            }
        )
        generations = tuple(
            validated if item.generation_id == generation_id else item
            for item in document.generations
        )
        self._save(document.model_copy(update={"generations": generations}))
        return validated

    def record_observation_convergence(
        self, *, generation_id: UUID, convergence_path: Path
    ) -> CredentialGeneration:
        """Bind signed four-way convergence to the one staged registry record."""
        from .pre_certification_observation import (
            PreCertificationObservationAuthority,
            observation_root_for_convergence,
        )

        document = self.load()
        record = next(
            (item for item in document.generations if item.generation_id == generation_id), None
        )
        if (
            record is None
            or record.state is not CredentialState.PROVISIONED
            or record.observation_campaign_id is None
            or record.certification_stage is not CertificationStage.PRE_CERTIFICATION_OBSERVATION
        ):
            raise RuntimeError("MNEMO_OBSERVATION_STAGE_INVALID")
        resolved = convergence_path.resolve(strict=True)
        if not resolved.is_relative_to(self.path.parent):
            raise RuntimeError("MNEMO_OBSERVATION_PATH_REJECTED")
        signing_secret = self.retrieve(generation_id, CredentialKind.CERTIFICATION_SIGNING)
        evidence = PreCertificationObservationAuthority(
            generation_id=generation_id,
            signing_key=signing_secret.encode("utf-8"),
            observation_root=observation_root_for_convergence(
                resolved,
                generation_id=generation_id,
                campaign_id=record.observation_campaign_id,
            ),
            campaign_id=record.observation_campaign_id,
        ).verify_convergence(resolved)
        if evidence["identity"].get("activation_sha256") != record.activation_sha256:
            raise RuntimeError("MNEMO_OBSERVATION_ACTIVATION_MISMATCH")
        updated = record.model_copy(
            update={
                "observation_convergence_path": str(resolved),
                "observation_convergence_sha256": _digest_file(resolved),
            }
        )
        self._save(
            document.model_copy(
                update={
                    "generations": tuple(
                        updated if item.generation_id == generation_id else item
                        for item in document.generations
                    )
                }
            )
        )
        return updated

    def record_final_evidence(
        self,
        *,
        generation_id: UUID,
        authority: ProductionGenerationEvidenceAuthority,
    ) -> CredentialGeneration:
        """Verify the full chain before recording FINAL_EVIDENCE_GENERATED."""
        document = self.load()
        record = next(
            (item for item in document.generations if item.generation_id == generation_id), None
        )
        if (
            record is None
            or record.state is not CredentialState.PROVISIONED
            or record.certification_stage is not CertificationStage.OBSERVATION_CONVERGED
            or record.observation_convergence_path != str(authority.transport_parity_path)
            or record.observation_convergence_sha256
            != _digest_file(authority.transport_parity_path)
        ):
            raise RuntimeError("MNEMO_FINAL_EVIDENCE_STAGE_INVALID")
        self._verify_authority_keys(record, authority)
        result = authority.verify()
        if result.get("credential_generation_id") != str(generation_id):
            raise RuntimeError("MNEMO_FINAL_EVIDENCE_GENERATION_MISMATCH")
        path = authority.artifact_paths[2]
        updated = record.model_copy(
            update={"final_evidence_path": str(path), "final_evidence_sha256": _digest_file(path)}
        )
        self._save(
            document.model_copy(
                update={
                    "generations": tuple(
                        updated if item.generation_id == generation_id else item
                        for item in document.generations
                    )
                }
            )
        )
        return updated

    def stage_observation(
        self,
        *,
        generation_id: UUID,
        activation_path: Path,
        activation_generation_id: UUID,
    ) -> CredentialGeneration:
        """Select one staged generation after verifying its new signed activation."""
        from .v2_reranker_lifecycle import DurableRerankerActivationStoreV1, V2RerankerMode

        document = self.load()
        staged = [
            item for item in document.generations if item.state is CredentialState.PROVISIONED
        ]
        if len(staged) != 1 or staged[0].generation_id != generation_id:
            raise RuntimeError("MNEMO_OBSERVATION_GENERATION_AMBIGUOUS")
        record = staged[0]
        if record.observation_campaign_id is not None:
            raise RuntimeError("MNEMO_OBSERVATION_ALREADY_STAGED")
        resolved = activation_path.resolve(strict=True)
        if not resolved.is_relative_to(self.path.parent) or resolved == self.path:
            raise RuntimeError("MNEMO_OBSERVATION_ACTIVATION_PATH_REJECTED")
        cursor = self.retrieve(generation_id, CredentialKind.DELIVERY_CURSOR)
        signing_key = hmac.new(
            cursor.encode("utf-8"), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
        ).digest()
        activation = DurableRerankerActivationStoreV1(
            path=resolved,
            signing_key=signing_key,
            prohibited_paths=(self.path,),
            credential_generation_id=generation_id,
            activation_generation_id=activation_generation_id,
        ).load()
        if activation.desired_mode is not V2RerankerMode.BGE_V2_M3:
            raise RuntimeError("MNEMO_OBSERVATION_ACTIVATION_INVALID")
        updated = record.model_copy(
            update={
                "activation_path": str(resolved),
                "activation_sha256": _digest_file(resolved),
                "observation_campaign_id": uuid4(),
            }
        )
        generations = tuple(
            updated if item.generation_id == generation_id else item
            for item in document.generations
        )
        self._save(document.model_copy(update={"generations": generations}))
        return updated

    def promote(
        self, *, generation_id: UUID, authority: ProductionGenerationEvidenceAuthority
    ) -> CredentialGeneration:
        """Atomically switch the registry pointer after re-verifying the chain."""
        document = self.load()
        record = next(
            (item for item in document.generations if item.generation_id == generation_id), None
        )
        if record is None or record.state is not CredentialState.VALIDATED:
            raise RuntimeError("MNEMO_CREDENTIAL_NOT_VALIDATED")
        self._verify_authority_keys(record, authority)
        result = authority.verify()
        paths = authority.artifact_paths
        if (
            result.get("credential_generation_id") != str(generation_id)
            or tuple(map(str, paths))
            != (record.activation_path, record.certificate_path, record.final_evidence_path)
            or (
                _digest_file(paths[0]),
                _digest_file(paths[1]),
                _digest_file(paths[2]),
            )
            != (
                record.activation_sha256,
                record.certificate_sha256,
                record.final_evidence_sha256,
            )
        ):
            raise RuntimeError("MNEMO_CREDENTIAL_EVIDENCE_CHANGED")
        for credential in record.secrets:
            self.retrieve(generation_id, credential.kind)
        now = _timestamp()
        promoted = record.model_copy(update={"state": CredentialState.ACTIVE, "activated_at": now})
        generations = tuple(
            promoted
            if item.generation_id == generation_id
            else item.model_copy(update={"state": CredentialState.SUPERSEDED, "superseded_at": now})
            if item.state is CredentialState.ACTIVE
            else item
            for item in document.generations
        )
        self._save(
            document.model_copy(
                update={"active_generation_id": generation_id, "generations": generations}
            )
        )
        return promoted

    def revoke(self, generation_id: UUID) -> CredentialGeneration:
        document = self.load()
        record = next(
            (item for item in document.generations if item.generation_id == generation_id), None
        )
        if record is None or record.state in {CredentialState.REVOKED, CredentialState.INVALID}:
            raise RuntimeError("MNEMO_CREDENTIAL_GENERATION_UNAVAILABLE")
        revoked = record.model_copy(update={"state": CredentialState.REVOKED})
        generations = tuple(
            revoked if item.generation_id == generation_id else item
            for item in document.generations
        )
        self._save(
            document.model_copy(
                update={
                    "active_generation_id": (
                        None
                        if document.active_generation_id == generation_id
                        else document.active_generation_id
                    ),
                    "generations": generations,
                }
            )
        )
        return revoked

    def _verify_authority_keys(
        self, record: CredentialGeneration, authority: ProductionGenerationEvidenceAuthority
    ) -> None:
        cursor = self.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
        certification = self.retrieve(record.generation_id, CredentialKind.CERTIFICATION_SIGNING)
        derived_cursor = hmac.new(
            cursor.encode("utf-8"), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
        ).digest()
        expected = (
            hashlib.sha256(derived_cursor).hexdigest(),
            hashlib.sha256(certification.encode("utf-8")).hexdigest(),
        )
        if not secrets.compare_digest(expected[0], authority.key_fingerprints[0]) or not (
            secrets.compare_digest(expected[1], authority.key_fingerprints[1])
        ):
            raise RuntimeError("MNEMO_CREDENTIAL_EVIDENCE_KEY_MISMATCH")

    def retrieve(self, generation_id: UUID, kind: CredentialKind) -> str:
        document = self.load()
        record = next(
            (item for item in document.generations if item.generation_id == generation_id), None
        )
        if record is None or record.state in {CredentialState.REVOKED, CredentialState.INVALID}:
            raise RuntimeError("MNEMO_CREDENTIAL_GENERATION_UNAVAILABLE")
        credential = next((item for item in record.secrets if item.kind is kind), None)
        if credential is None:
            raise RuntimeError("MNEMO_CREDENTIAL_GENERATION_UNAVAILABLE")
        secret = self.secret_store.get(credential.store_reference)
        if secret is None or not secrets.compare_digest(
            _fingerprint(secret), credential.fingerprint_sha256
        ):
            raise RuntimeError("MNEMO_CREDENTIAL_FINGERPRINT_MISMATCH")
        return secret

    def retrieve_active(self, kind: CredentialKind) -> tuple[CredentialGeneration, str]:
        """Production-only selection; callers cannot choose a generation ID."""
        document = self.load()
        if document.active_generation_id is None:
            raise RuntimeError("MNEMO_ACTIVE_CREDENTIAL_UNAVAILABLE")
        record = next(
            item
            for item in document.generations
            if item.generation_id == document.active_generation_id
        )
        if record.state is not CredentialState.ACTIVE:
            raise RuntimeError("MNEMO_ACTIVE_CREDENTIAL_UNAVAILABLE")
        return record, self.retrieve(record.generation_id, kind)

    def render_markdown(self) -> str:
        """Human-readable view containing only public registry fields."""
        document = self.load()
        lines = [
            "# Mnemo production credential generations",
            "",
            "Secret values are OS-stored and never shown here.",
            "",
        ]
        for item in document.generations:
            lines.extend(
                [
                    f"## {item.generation_id}",
                    "",
                    f"- State: `{item.state.value}`",
                    f"- Certification stage: `{item.certification_stage.value}`",
                    f"- Domain: `{item.domain}`",
                    f"- Owner: `{item.owner_subject}`",
                    f"- Service principal: `{item.service_subject or 'not assigned'}`",
                    f"- Scope: `{item.scope}`",
                    f"- Created: `{item.created_at}`",
                    f"- Activated: `{item.activated_at or 'not activated'}`",
                    f"- Superseded: `{item.superseded_at or 'not superseded'}`",
                    *(
                        f"- {credential.kind.value}: fingerprint "
                        f"`{credential.fingerprint_sha256}`, secure-store reference "
                        f"`{credential.store_reference}`"
                        for credential in item.secrets
                    ),
                    f"- Activation: `{item.activation_path or 'not linked'}`",
                    f"- Certificate: `{item.certificate_path or 'not linked'}`",
                    f"- Final evidence: `{item.final_evidence_path or 'not linked'}`",
                    f"- Observation campaign: `{item.observation_campaign_id or 'not staged'}`",
                    "- Signed convergence: "
                    f"`{item.observation_convergence_path or 'not recorded'}`",
                    f"- Rotation reason: `{item.rotation_reason or 'initial provisioning'}`",
                    "",
                ]
            )
        return "\n".join(lines)

    def _save(self, document: CredentialRegistryDocument) -> None:
        validated = CredentialRegistryDocument.model_validate(document.model_dump(mode="json"))
        content = json.dumps(
            validated.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        _atomic_write(self.path, content + "\n")
