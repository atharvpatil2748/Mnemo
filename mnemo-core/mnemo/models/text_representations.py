"""Full Multilingual V2 language-independent text representation contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from ._shared import require_non_empty, require_sha256, require_unit_interval, require_utc
from .multilingual import LanguageEvidenceReferenceV3

REPRESENTATION_CONTRACT_VERSION = "mnemo.representation-transformation/1"
_OBSERVATION_NAMESPACE = UUID("3c03c344-713e-5a28-b86e-abcb29d19387")
_TRANSFORMATION_NAMESPACE = UUID("2870887c-8d68-530d-a0b9-95bf2935bb54")
_REFERENCE_NAMESPACE = UUID("fbc3e199-15b1-5a3a-a676-cdb1a12bd78b")


class TextRepresentationType(StrEnum):
    UNICODE_SEMANTIC_TEXT = "unicode_semantic_text"
    LEGACY_FONT_ENCODED_TEXT = "legacy_font_encoded_text"
    PDF_ENCODING_ANOMALY = "pdf_encoding_anomaly"
    OCR_TEXT = "ocr_text"
    VISION_TEXT = "vision_text"
    TRANSLITERATED_TEXT = "transliterated_text"
    NORMALIZED_UNICODE_TEXT = "normalized_unicode_text"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class RepresentationAuthorityClass(StrEnum):
    AUTHORITATIVE_SOURCE_METADATA = "authoritative_source_metadata"
    ADJUDICATED = "adjudicated"
    PARSER_METADATA = "parser_metadata"
    PROVIDER_METADATA = "provider_metadata"
    GOVERNED_DETECTOR = "governed_detector"
    UNKNOWN = "unknown"


class RepresentationAuthority(StrEnum):
    ORIGINAL = "original"
    EXISTING_DERIVED = "existing_derived"
    REPRESENTATION_DERIVED = "representation_derived"


class ObservationKind(StrEnum):
    LANGUAGE = "language"
    SCRIPT = "script"


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationReferenceV1:
    observation_id: UUID
    observation_kind: ObservationKind
    observation_digest: str

    def __post_init__(self) -> None:
        require_sha256(self.observation_digest, "observation_digest")


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationScopeV1:
    """Sanitized server-computed scope binding; it never grants access."""

    actor_scope_digest: str
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID | None
    derivation_id: UUID | None
    authorization_policy_id: str
    authorization_policy_revision: str

    def __post_init__(self) -> None:
        require_sha256(self.actor_scope_digest, "actor_scope_digest")
        require_non_empty(self.authorization_policy_id, "authorization_policy_id")
        require_non_empty(self.authorization_policy_revision, "authorization_policy_revision")


@dataclass(frozen=True, slots=True, kw_only=True)
class RepresentationObservationV1:
    observation_id: UUID
    source_reference: LanguageEvidenceReferenceV3
    representation_type: TextRepresentationType
    detector_id: str
    detector_revision: str
    configuration_digest: str
    input_content_hash: str
    confidence: float
    calibrated: bool
    authority_class: RepresentationAuthorityClass
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty(self.detector_id, "detector_id")
        require_non_empty(self.detector_revision, "detector_revision")
        require_sha256(self.configuration_digest, "configuration_digest")
        require_sha256(self.input_content_hash, "input_content_hash")
        require_unit_interval(self.confidence, "confidence")
        require_utc(self.created_at, "created_at")
        if self.input_content_hash != self.source_reference.source_content_hash:
            raise ValueError("representation observation input hash conflicts with source")
        if self.observation_id != representation_observation_id(
            source_reference_digest=self.source_reference.identity_digest,
            detector_id=self.detector_id,
            detector_revision=self.detector_revision,
            configuration_digest=self.configuration_digest,
            input_content_hash=self.input_content_hash,
            representation_type=self.representation_type,
        ):
            raise ValueError("representation observation identity mismatch")
        _validate_observation_refs(self.language_observation_references, ObservationKind.LANGUAGE)
        _validate_observation_refs(self.script_observation_references, ObservationKind.SCRIPT)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationProfileV1:
    profile_id: str
    provider_id: str
    provider_revision: str
    configuration_digest: str
    allowed_source_representations: tuple[TextRepresentationType, ...]
    target_representation: TextRepresentationType
    deterministic: bool = True
    offline_only: bool = True
    authorization_required: bool = True
    failure_policy: str = "fail_closed_no_output"

    def __post_init__(self) -> None:
        require_non_empty(self.profile_id, "profile_id")
        require_non_empty(self.provider_id, "provider_id")
        require_non_empty(self.provider_revision, "provider_revision")
        require_sha256(self.configuration_digest, "configuration_digest")
        if not self.allowed_source_representations:
            raise ValueError("transformation profile requires source representations")
        if len(set(self.allowed_source_representations)) != len(
            self.allowed_source_representations
        ):
            raise ValueError("source representations must be unique")
        if not self.deterministic or not self.offline_only or not self.authorization_required:
            raise ValueError("V2 transformations must be deterministic, offline, and authorized")
        if self.failure_policy != "fail_closed_no_output":
            raise ValueError("unsupported transformation failure policy")


@dataclass(frozen=True, slots=True, kw_only=True)
class TextRepresentationReferenceV1:
    reference_id: UUID
    evidence_reference: LanguageEvidenceReferenceV3
    representation_type: TextRepresentationType
    representation_authority: RepresentationAuthority
    content_hash: str
    representation_observation_id: UUID
    representation_derivation_id: UUID | None
    source_generation_ids: tuple[UUID, ...]
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]

    def __post_init__(self) -> None:
        require_sha256(self.content_hash, "content_hash")
        if self.representation_authority is RepresentationAuthority.REPRESENTATION_DERIVED:
            if self.representation_derivation_id is None or not self.source_generation_ids:
                raise ValueError("derived representation requires derivation and generation")
        elif self.representation_derivation_id is not None:
            raise ValueError("non-derived representation cannot claim representation derivation")
        if self.reference_id != text_representation_reference_id(
            evidence_reference_digest=self.evidence_reference.identity_digest,
            representation_type=self.representation_type,
            authority=self.representation_authority,
            content_hash=self.content_hash,
            observation_id=self.representation_observation_id,
            derivation_id=self.representation_derivation_id,
            source_generation_ids=self.source_generation_ids,
        ):
            raise ValueError("text representation reference identity mismatch")
        _validate_observation_refs(self.language_observation_references, ObservationKind.LANGUAGE)
        _validate_observation_refs(self.script_observation_references, ObservationKind.SCRIPT)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationProvenanceV1:
    source_reference_digest: str
    source_representation_reference_id: UUID
    source_representation_observation_id: UUID
    profile_id: str
    profile_configuration_digest: str
    input_content_hash: str
    output_content_hash: str
    generation_id: UUID
    authorization_scope_digest: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.source_reference_digest, "source_reference_digest"),
            (self.profile_configuration_digest, "profile_configuration_digest"),
            (self.input_content_hash, "input_content_hash"),
            (self.output_content_hash, "output_content_hash"),
            (self.authorization_scope_digest, "authorization_scope_digest"),
        ):
            require_sha256(value, name)
        require_non_empty(self.profile_id, "profile_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class RepresentationTransformationV1:
    transformation_id: UUID
    source_representation: TextRepresentationReferenceV1
    source_observation: RepresentationObservationV1
    transformation_profile: TransformationProfileV1
    target_representation_type: TextRepresentationType
    input_content_hash: str
    output_content_hash: str
    output_reference: TextRepresentationReferenceV1
    generation_id: UUID
    source_generation_ids: tuple[UUID, ...]
    authorization_scope: AuthorizationScopeV1
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]
    provenance: TransformationProvenanceV1
    created_at: datetime

    def __post_init__(self) -> None:
        require_sha256(self.input_content_hash, "input_content_hash")
        require_sha256(self.output_content_hash, "output_content_hash")
        require_utc(self.created_at, "created_at")
        if self.source_representation.content_hash != self.input_content_hash:
            raise ValueError("transformation input hash conflicts with source representation")
        if self.source_observation.input_content_hash != self.input_content_hash:
            raise ValueError("transformation input hash conflicts with observation")
        if self.target_representation_type is not self.transformation_profile.target_representation:
            raise ValueError("transformation target conflicts with profile")
        if self.source_representation.representation_type not in (
            self.transformation_profile.allowed_source_representations
        ):
            raise ValueError("source representation is not admitted by profile")
        if self.output_reference.content_hash != self.output_content_hash:
            raise ValueError("output reference hash mismatch")
        if self.output_reference.representation_type is not self.target_representation_type:
            raise ValueError("output representation type mismatch")
        if self.output_reference.representation_authority is not (
            RepresentationAuthority.REPRESENTATION_DERIVED
        ):
            raise ValueError("transformation output must be representation-derived")
        if self.output_reference.representation_derivation_id != self.transformation_id:
            raise ValueError("output representation does not bind transformation identity")
        if self.authorization_scope.actor_scope_digest != (
            self.provenance.authorization_scope_digest
        ):
            raise ValueError("authorization scope digest mismatch")
        if self.transformation_id != representation_transformation_id(
            source_reference_digest=self.source_representation.evidence_reference.identity_digest,
            source_representation_reference_id=self.source_representation.reference_id,
            profile=self.transformation_profile,
            input_content_hash=self.input_content_hash,
            target_representation=self.target_representation_type,
            generation_id=self.generation_id,
        ):
            raise ValueError("representation transformation identity mismatch")
        _validate_scope(self.authorization_scope, self.source_representation.evidence_reference)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationRegistryEntryV1:
    profile: TransformationProfileV1
    implementation_id: str
    configured: bool
    provider_ready: bool
    enabled: bool
    reason_code: str | None

    def __post_init__(self) -> None:
        require_non_empty(self.implementation_id, "implementation_id")
        if self.enabled and (not self.configured or not self.provider_ready):
            raise ValueError("enabled transformation requires configured ready provider")


def representation_observation_id(
    *,
    source_reference_digest: str,
    detector_id: str,
    detector_revision: str,
    configuration_digest: str,
    input_content_hash: str,
    representation_type: TextRepresentationType,
) -> UUID:
    return uuid5(
        _OBSERVATION_NAMESPACE,
        _digest(
            {
                "source_reference_digest": source_reference_digest,
                "detector_id": detector_id,
                "detector_revision": detector_revision,
                "configuration_digest": configuration_digest,
                "input_content_hash": input_content_hash,
                "representation_type": representation_type.value,
            }
        ),
    )


def representation_transformation_id(
    *,
    source_reference_digest: str,
    source_representation_reference_id: UUID,
    profile: TransformationProfileV1,
    input_content_hash: str,
    target_representation: TextRepresentationType,
    generation_id: UUID,
) -> UUID:
    return uuid5(
        _TRANSFORMATION_NAMESPACE,
        _digest(
            {
                "source_reference_digest": source_reference_digest,
                "source_representation_reference_id": str(source_representation_reference_id),
                "profile_id": profile.profile_id,
                "provider_revision": profile.provider_revision,
                "configuration_digest": profile.configuration_digest,
                "input_content_hash": input_content_hash,
                "target_representation": target_representation.value,
                "generation_id": str(generation_id),
            }
        ),
    )


def text_representation_reference_id(
    *,
    evidence_reference_digest: str,
    representation_type: TextRepresentationType,
    authority: RepresentationAuthority,
    content_hash: str,
    observation_id: UUID,
    derivation_id: UUID | None,
    source_generation_ids: tuple[UUID, ...],
) -> UUID:
    return uuid5(
        _REFERENCE_NAMESPACE,
        _digest(
            {
                "evidence_reference_digest": evidence_reference_digest,
                "representation_type": representation_type.value,
                "authority": authority.value,
                "content_hash": content_hash,
                "observation_id": str(observation_id),
                "derivation_id": None if derivation_id is None else str(derivation_id),
                "source_generation_ids": [str(item) for item in source_generation_ids],
            }
        ),
    )


def content_hash(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_observation_refs(
    values: tuple[ObservationReferenceV1, ...], kind: ObservationKind
) -> None:
    if len({item.observation_id for item in values}) != len(values):
        raise ValueError("observation references must be unique")
    if any(item.observation_kind is not kind for item in values):
        raise ValueError(f"expected only {kind.value} observation references")


def _validate_scope(scope: AuthorizationScopeV1, source: LanguageEvidenceReferenceV3) -> None:
    if (
        scope.notebook_id != source.notebook_id
        or scope.source_id != source.source_id
        or scope.document_id != source.document_id
        or scope.version_id != source.version_id
        or scope.occurrence_id != source.occurrence_id
        or scope.derivation_id != source.derivation_id
    ):
        raise ValueError("authorization scope conflicts with source evidence")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
