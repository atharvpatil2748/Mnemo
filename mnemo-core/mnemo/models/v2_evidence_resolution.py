"""Governed Full Multilingual V2 semantic-evidence and runtime-security contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from ._shared import require_non_empty, require_sha256
from .multilingual import LanguageEvidenceReferenceV3
from .multilingual_index import MultilingualEvidencePositionV1
from .text_representations import (
    ObservationReferenceV1,
    RepresentationAuthority,
    TextRepresentationReferenceV1,
    TextRepresentationType,
)
from .v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1

AUTHORIZED_V2_EVIDENCE_RESOLUTION_SCHEMA = "mnemo.v2-authorized-evidence-resolution/1"
V2_CANDIDATE_RUNTIME_SECURITY_SCHEMA = "mnemo.v2-candidate-runtime-security/1"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class V2RepresentationResolutionState(StrEnum):
    CANONICAL = "canonical"
    DERIVED = "derived"


@dataclass(frozen=True, slots=True, kw_only=True)
class V2GenerationSetBindingV1:
    """The four capabilities remain explicit and cannot be interchanged."""

    representation_generation_id: UUID
    language_text_generation_id: UUID
    embedding_generation_id: UUID
    vector_generation_id: UUID

    def __post_init__(self) -> None:
        if len(set(self.ordered_ids)) != 4:
            raise ValueError("V2 generation binding requires four distinct identities")
        if self.vector_generation_id == self.embedding_generation_id:
            raise ValueError("vector and embedding generations must remain distinct")

    @property
    def ordered_ids(self) -> tuple[UUID, ...]:
        return (
            self.representation_generation_id,
            self.language_text_generation_id,
            self.embedding_generation_id,
            self.vector_generation_id,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class V2TransformationLineageV1:
    transformation_profile_identity: str
    transformation_version: str
    transformation_digest: str
    source_representation: TextRepresentationType
    target_representation: TextRepresentationType
    transformation_derivation_identity: UUID
    source_reference_digest: str
    source_generation_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        require_non_empty(self.transformation_profile_identity, "transformation_profile_identity")
        require_non_empty(self.transformation_version, "transformation_version")
        require_sha256(self.transformation_digest, "transformation_digest")
        require_sha256(self.source_reference_digest, "source_reference_digest")
        if not self.source_generation_ids:
            raise ValueError("transformation lineage requires source generations")
        if len(set(self.source_generation_ids)) != len(self.source_generation_ids):
            raise ValueError("transformation source generations must be unique")
        if self.source_representation is self.target_representation:
            raise ValueError("transformation source and target representations must differ")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2CandidateRuntimeSecurityBindingV1:
    """Non-expandable authorization and runtime identity attached to V2 evidence."""

    authorization_decision: V2RetrievalAuthorizationDecisionV1
    generations: V2GenerationSetBindingV1
    profile_id: str
    model_identity: str
    schema_version: str = V2_CANDIDATE_RUNTIME_SECURITY_SCHEMA

    def __post_init__(self) -> None:
        require_non_empty(self.profile_id, "profile_id")
        require_non_empty(self.model_identity, "model_identity")
        runtime = self.authorization_decision.runtime_binding
        if runtime.generation_ids != self.generations.ordered_ids:
            raise PermissionError("authorization generation set does not match candidate runtime")

    @property
    def authorization_decision_fingerprint(self) -> str:
        return self.authorization_decision.decision_fingerprint

    @property
    def active_alias_set_identity(self) -> str:
        return self.authorization_decision.runtime_binding.alias_set_digest

    @property
    def profile_fingerprint(self) -> str:
        return self.authorization_decision.runtime_binding.profile_fingerprint

    @property
    def vector_space_identity(self) -> str:
        return self.authorization_decision.runtime_binding.vector_space_identity

    @property
    def database_identity(self) -> str:
        return self.authorization_decision.runtime_binding.database_identity

    @property
    def build_run_identity(self) -> UUID:
        return self.authorization_decision.runtime_binding.build_run_id

    @property
    def identity_digest(self) -> str:
        return _digest(
            {
                "schema_version": self.schema_version,
                "authorization_decision_fingerprint": (self.authorization_decision_fingerprint),
                "active_alias_set_identity": self.active_alias_set_identity,
                "generation_ids": [str(value) for value in self.generations.ordered_ids],
                "profile_id": self.profile_id,
                "profile_fingerprint": self.profile_fingerprint,
                "model_identity": self.model_identity,
                "vector_space_identity": self.vector_space_identity,
                "database_identity": self.database_identity,
                "build_run_identity": str(self.build_run_identity),
            }
        )

    def to_contract_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authorization_decision_fingerprint": self.authorization_decision_fingerprint,
            "active_alias_set_identity": self.active_alias_set_identity,
            "generation_ids": [str(value) for value in self.generations.ordered_ids],
            "profile_identity": self.profile_id,
            "profile_fingerprint": self.profile_fingerprint,
            "model_identity": self.model_identity,
            "vector_space_identity": self.vector_space_identity,
            "database_identity": self.database_identity,
            "build_run_identity": str(self.build_run_identity),
            "identity_digest": self.identity_digest,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class V2AuthorizedEvidenceHandleV1:
    """An enumerated evidence identity already bounded to the active V2 runtime."""

    source_reference: LanguageEvidenceReferenceV3
    representation_reference: TextRepresentationReferenceV1
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]
    semantic_generation_id: UUID
    runtime_security: V2CandidateRuntimeSecurityBindingV1

    def __post_init__(self) -> None:
        if self.representation_reference.evidence_reference != self.source_reference:
            raise ValueError("authorized evidence handle representation/source mismatch")
        if self.semantic_generation_id not in self.runtime_security.generations.ordered_ids:
            raise ValueError("semantic evidence generation is outside the authorized runtime")
        if self.language_observation_references != (
            self.representation_reference.language_observation_references
        ):
            raise ValueError("language observation references do not match representation")
        if self.script_observation_references != (
            self.representation_reference.script_observation_references
        ):
            raise ValueError("script observation references do not match representation")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2SemanticEvidenceRecordV1:
    """Exact storage result; it contains semantic evidence, never display metadata alone."""

    handle: V2AuthorizedEvidenceHandleV1
    semantic_text: str
    semantic_text_content_hash: str
    representation_state: V2RepresentationResolutionState
    representation_observation_reference: UUID
    transformation_lineage: V2TransformationLineageV1 | None
    title_metadata: str | None = None
    position: MultilingualEvidencePositionV1 | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.semantic_text, "semantic_text")
        if not self.semantic_text.strip():
            raise ValueError("V2 semantic evidence cannot be blank")
        if re.fullmatch(r"\s*title:\s*[^\r\n]+\s*", self.semantic_text, re.IGNORECASE):
            raise ValueError("title-only V2 semantic evidence is forbidden")
        require_sha256(self.semantic_text_content_hash, "semantic_text_content_hash")
        if hashlib.sha256(self.semantic_text.encode("utf-8")).hexdigest() != (
            self.semantic_text_content_hash
        ):
            raise ValueError("V2 semantic evidence content hash mismatch")
        representation = self.handle.representation_reference
        if representation.content_hash != self.semantic_text_content_hash:
            raise ValueError("semantic text differs from governed representation")
        if representation.representation_observation_id != (
            self.representation_observation_reference
        ):
            raise ValueError("representation observation identity mismatch")
        if self.title_metadata is not None:
            require_non_empty(self.title_metadata, "title_metadata")
            if self.semantic_text.strip() == self.title_metadata.strip():
                raise ValueError("title-only V2 semantic evidence is forbidden")
        if self.representation_state is V2RepresentationResolutionState.DERIVED:
            if self.transformation_lineage is None:
                raise ValueError("derived semantic evidence requires transformation lineage")
            if representation.representation_authority is not (
                RepresentationAuthority.REPRESENTATION_DERIVED
            ):
                raise ValueError("derived semantic evidence requires derived authority")
            if representation.representation_derivation_id != (
                self.transformation_lineage.transformation_derivation_identity
            ):
                raise ValueError("transformation derivation identity mismatch")
        elif self.transformation_lineage is not None:
            raise ValueError("canonical semantic evidence cannot claim transformation lineage")


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizedV2EvidenceResolutionV1:
    """Production V2 evidence resolution bound to one authorization/runtime context."""

    resolution_identity: UUID
    request_fingerprint: str
    record: V2SemanticEvidenceRecordV1
    provenance_digest: str
    schema_version: str = AUTHORIZED_V2_EVIDENCE_RESOLUTION_SCHEMA

    def __post_init__(self) -> None:
        require_sha256(self.request_fingerprint, "request_fingerprint")
        require_sha256(self.provenance_digest, "provenance_digest")
        if self.provenance_digest != self.expected_provenance_digest:
            raise ValueError("V2 evidence resolution provenance digest mismatch")

    @classmethod
    def create(
        cls,
        *,
        resolution_identity: UUID,
        request_fingerprint: str,
        record: V2SemanticEvidenceRecordV1,
    ) -> AuthorizedV2EvidenceResolutionV1:
        """Construct a resolution without duplicating canonical digest logic."""
        lineage = record.transformation_lineage
        provenance_digest = _digest(
            {
                "source_reference_digest": record.handle.source_reference.identity_digest,
                "representation_reference_id": str(
                    record.handle.representation_reference.reference_id
                ),
                "semantic_text_content_hash": record.semantic_text_content_hash,
                "semantic_generation_id": str(record.handle.semantic_generation_id),
                "runtime_security_identity": record.handle.runtime_security.identity_digest,
                "transformation_digest": (
                    None if lineage is None else lineage.transformation_digest
                ),
            }
        )
        return cls(
            resolution_identity=resolution_identity,
            request_fingerprint=request_fingerprint,
            record=record,
            provenance_digest=provenance_digest,
        )

    @property
    def source_reference(self) -> LanguageEvidenceReferenceV3:
        return self.record.handle.source_reference

    @property
    def representation_reference(self) -> TextRepresentationReferenceV1:
        return self.record.handle.representation_reference

    @property
    def runtime_security(self) -> V2CandidateRuntimeSecurityBindingV1:
        return self.record.handle.runtime_security

    @property
    def semantic_text(self) -> str:
        return self.record.semantic_text

    @property
    def position(self) -> MultilingualEvidencePositionV1 | None:
        return self.record.position

    @property
    def title_metadata(self) -> str | None:
        return self.record.title_metadata

    @property
    def canonical_evidence_identity(self) -> str:
        return self.source_reference.identity_digest

    @property
    def expected_provenance_digest(self) -> str:
        lineage = self.record.transformation_lineage
        return _digest(
            {
                "source_reference_digest": self.source_reference.identity_digest,
                "representation_reference_id": str(self.representation_reference.reference_id),
                "semantic_text_content_hash": self.record.semantic_text_content_hash,
                "semantic_generation_id": str(self.record.handle.semantic_generation_id),
                "runtime_security_identity": self.runtime_security.identity_digest,
                "transformation_digest": (
                    None if lineage is None else lineage.transformation_digest
                ),
            }
        )

    @property
    def resolution_fingerprint(self) -> str:
        return _digest(
            {
                "schema_version": self.schema_version,
                "resolution_identity": str(self.resolution_identity),
                "request_fingerprint": self.request_fingerprint,
                "authorization_decision_fingerprint": (
                    self.runtime_security.authorization_decision_fingerprint
                ),
                "canonical_evidence_identity": self.canonical_evidence_identity,
                "provenance_digest": self.provenance_digest,
            }
        )

    def to_contract_payload(self) -> dict[str, object]:
        generations = self.runtime_security.generations
        lineage = self.record.transformation_lineage
        return {
            "record_type": "AuthorizedV2EvidenceResolutionV1",
            "contract_version": self.schema_version,
            "resolution_identity": str(self.resolution_identity),
            "request_fingerprint": self.request_fingerprint,
            "authorization_decision_fingerprint": (
                self.runtime_security.authorization_decision_fingerprint
            ),
            "source_reference": self.source_reference.identity_payload(),
            "canonical_evidence_identity": self.canonical_evidence_identity,
            "runtime_binding": {
                "active_alias_set_identity": self.runtime_security.active_alias_set_identity,
                "representation_generation_identity": str(generations.representation_generation_id),
                "language_text_generation_identity": str(generations.language_text_generation_id),
                "embedding_generation_identity": str(generations.embedding_generation_id),
                "vector_generation_identity": str(generations.vector_generation_id),
                "profile_identity": self.runtime_security.profile_id,
                "profile_fingerprint": self.runtime_security.profile_fingerprint,
                "model_identity": self.runtime_security.model_identity,
                "vector_space_identity": self.runtime_security.vector_space_identity,
                "database_identity": self.runtime_security.database_identity,
                "build_run_identity": str(self.runtime_security.build_run_identity),
            },
            "lineage": {
                "representation_state": self.record.representation_state.value,
                "language_observation_references": [
                    str(value.observation_id)
                    for value in self.record.handle.language_observation_references
                ],
                "script_observation_references": [
                    str(value.observation_id)
                    for value in self.record.handle.script_observation_references
                ],
                "representation_observation_reference": str(
                    self.record.representation_observation_reference
                ),
                "transformation": (
                    None
                    if lineage is None
                    else {
                        "profile_identity": lineage.transformation_profile_identity,
                        "version": lineage.transformation_version,
                        "digest": lineage.transformation_digest,
                        "source_representation": lineage.source_representation.value,
                        "target_representation": lineage.target_representation.value,
                        "derivation_identity": str(lineage.transformation_derivation_identity),
                        "source_reference_digest": lineage.source_reference_digest,
                        "source_generation_ids": [
                            str(value) for value in lineage.source_generation_ids
                        ],
                    }
                ),
            },
            "semantic_text": self.record.semantic_text,
            "semantic_text_content_hash": self.record.semantic_text_content_hash,
            "title_metadata": self.record.title_metadata,
            "provenance_digest": self.provenance_digest,
            "resolution_fingerprint": self.resolution_fingerprint,
        }
