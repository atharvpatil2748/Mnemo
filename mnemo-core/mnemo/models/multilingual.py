"""Phase 8.5.9 multilingual provenance and retrieval contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from ._shared import (
    FrozenMetadata,
    require_finite,
    require_non_empty,
    require_positive,
    require_sha256,
    require_unit_interval,
    require_utc,
    thaw_metadata,
)
from .advanced_retrieval import RetrievalCompleteness, RetrievalPlanV2
from .multimodal import EvidenceCandidateV2, FinalQARequestV2, FinalQAResultV2
from .processing import (
    ProcessingBudget,
    ProcessingConsent,
    ProcessingEstimate,
    ProcessingManifest,
    ProcessingTrustClass,
)

MULTILINGUAL_CONTRACT_VERSION = "multilingual-v1/1"
MULTILINGUAL_CONTRACT_V2 = "multilingual-v2/1"
MULTILINGUAL_CONTRACT_V3 = "mnemo.language-evidence-reference/3"
LANGUAGE_DERIVATION_SCHEMA_VERSION = 1
_OBSERVATION_NAMESPACE = UUID("c4f4ea9e-3040-5b8e-aedf-ff65d6a5deec")
_OBSERVATION_V2_NAMESPACE = UUID("2bf4fac7-6e8d-5838-b4b1-f0a0ed6baa09")
_SCRIPT_OBSERVATION_NAMESPACE = UUID("9709740c-79d8-568e-9d9b-6d2e144ddf56")
_DERIVATION_NAMESPACE = UUID("37d10a60-b077-509b-aa64-5aa696a38f04")
_EMBEDDING_NAMESPACE = UUID("b79808fe-b486-57b7-a57e-8e3959fac79b")
_BCP47 = re.compile(r"^(?:[a-z]{2,3}|und|zxx)(?:-[A-Za-z0-9]{2,8})*$")
_SCRIPT = re.compile(r"^[A-Z][a-z]{3}$")


@dataclass(frozen=True, slots=True, order=True)
class LanguageCode:
    """Normalized extensible BCP-47 language tag."""

    value: str

    def __post_init__(self) -> None:
        normalized = _normalize_language_tag(self.value)
        if _BCP47.fullmatch(normalized) is None:
            raise ValueError("language code must be a valid normalized BCP-47 tag")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class ScriptCode:
    """ISO 15924 script code; Zyyy/Zzzz represent common/unknown."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.title()
        if _SCRIPT.fullmatch(normalized) is None:
            raise ValueError("script code must be a four-letter ISO 15924 code")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


class LanguageDetectionSource(StrEnum):
    EXPLICIT_METADATA = "explicit_metadata"
    PARSER = "parser"
    OCR = "ocr"
    LIGHTWEIGHT_DETECTOR = "lightweight_detector"
    PROVIDER = "provider"
    USER_HINT = "user_hint"


class ObservationAuthorityClass(StrEnum):
    AUTHORITATIVE_SOURCE_METADATA = "authoritative_source_metadata"
    ADJUDICATED = "adjudicated"
    PARSER_METADATA = "parser_metadata"
    OCR_VISION_METADATA = "ocr_vision_metadata"
    GOVERNED_DETECTOR = "governed_detector"
    UNKNOWN = "unknown"


class LanguageObservationScope(StrEnum):
    DOCUMENT = "document"
    PAGE = "page"
    SECTION = "section"
    CHUNK = "chunk"
    OCR_REGION = "ocr_region"
    ASSET = "asset"
    QUERY = "query"


class LanguageCapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    POLICY_DENIED = "policy_denied"
    BUDGET_DENIED = "budget_denied"
    UNVALIDATED = "unvalidated"


class LanguageDerivationKind(StrEnum):
    TRANSLATION = "translation"
    TRANSLITERATION = "transliteration"


class LanguageEvidenceKindV2(StrEnum):
    """Additive source kinds for canonical and derived language evidence."""

    CANONICAL_CHUNK = "canonical_chunk"
    OCR_REGION = "ocr_region"
    VISION_DERIVATION = "vision_derivation"
    LANGUAGE_DERIVATION = "language_derivation"


class LanguageEvidenceKindV3(StrEnum):
    """Language-generic immutable evidence kinds for Full Multilingual V2."""

    CANONICAL_CHUNK = "canonical_chunk"
    OCR_OCCURRENCE = "ocr_occurrence"
    OCR_REGION = "ocr_region"
    VISION_DERIVATION = "vision_derivation"
    LANGUAGE_DERIVATION = "language_derivation"
    REPRESENTATION_DERIVATION = "representation_derivation"


class EvidenceLineageOriginV3(StrEnum):
    NATIVE_V3 = "native_v3"
    LEGACY_V2_UPGRADE = "legacy_v2_upgrade"


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageEvidenceReferenceV2:
    """Authorization-safe, path-free reference to immutable source evidence.

    The reference deliberately carries the complete notebook/document/version
    boundary.  Canonical chunks never use synthetic occurrence identities;
    asset-backed evidence must retain its real occurrence and derivation.
    """

    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    kind: LanguageEvidenceKindV2
    evidence_id: str
    source_content_hash: str
    chunk_id: str | None = None
    occurrence_id: UUID | None = None
    derivation_id: UUID | None = None
    source_generation_id: UUID | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.evidence_id, "evidence_id")
        require_sha256(self.source_content_hash, "source_content_hash")
        if self.kind is LanguageEvidenceKindV2.CANONICAL_CHUNK:
            if self.chunk_id is None:
                raise ValueError("canonical language evidence requires chunk_id")
            if any(
                value is not None
                for value in (self.occurrence_id, self.derivation_id, self.source_generation_id)
            ):
                raise ValueError("canonical language evidence cannot claim derived provenance")
        elif self.kind in {
            LanguageEvidenceKindV2.OCR_REGION,
            LanguageEvidenceKindV2.VISION_DERIVATION,
        }:
            if self.occurrence_id is None or self.derivation_id is None:
                raise ValueError(
                    "asset-derived language evidence requires occurrence and derivation"
                )
            if self.source_generation_id is None:
                raise ValueError("asset-derived language evidence requires source generation")
            if self.chunk_id is not None:
                raise ValueError("asset-derived language evidence cannot claim a canonical chunk")
        elif self.kind is LanguageEvidenceKindV2.LANGUAGE_DERIVATION:
            if self.derivation_id is None or self.source_generation_id is None:
                raise ValueError("language derivation evidence requires derivation and generation")
            if self.chunk_id is not None:
                raise ValueError("language derivation evidence cannot claim a canonical chunk")

    def identity_payload(self) -> dict[str, object]:
        return {
            "contract": MULTILINGUAL_CONTRACT_V2,
            "notebook_id": str(self.notebook_id),
            "source_id": str(self.source_id),
            "document_id": str(self.document_id),
            "version_id": str(self.version_id),
            "kind": self.kind.value,
            "evidence_id": self.evidence_id,
            "source_content_hash": self.source_content_hash,
            "chunk_id": self.chunk_id,
            "occurrence_id": None if self.occurrence_id is None else str(self.occurrence_id),
            "derivation_id": None if self.derivation_id is None else str(self.derivation_id),
            "source_generation_id": (
                None if self.source_generation_id is None else str(self.source_generation_id)
            ),
        }

    @property
    def identity_digest(self) -> str:
        return _digest(self.identity_payload())


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageEvidenceReferenceV3:
    """Additive V3 evidence identity; V2 remains unchanged and serially stable."""

    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    kind: LanguageEvidenceKindV3
    evidence_id: str
    source_content_hash: str
    lineage_origin: EvidenceLineageOriginV3 = EvidenceLineageOriginV3.NATIVE_V3
    chunk_id: str | None = None
    occurrence_id: UUID | None = None
    derivation_id: UUID | None = None
    source_generation_id: UUID | None = None
    parent_evidence_reference_digest: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.evidence_id, "evidence_id")
        require_sha256(self.source_content_hash, "source_content_hash")
        if self.parent_evidence_reference_digest is not None:
            require_sha256(
                self.parent_evidence_reference_digest,
                "parent_evidence_reference_digest",
            )
        if self.kind is LanguageEvidenceKindV3.CANONICAL_CHUNK:
            if not self.chunk_id:
                raise ValueError("canonical V3 evidence requires chunk_id")
            if any(
                value is not None
                for value in (
                    self.occurrence_id,
                    self.derivation_id,
                    self.source_generation_id,
                    self.parent_evidence_reference_digest,
                )
            ):
                raise ValueError("canonical V3 evidence cannot claim derived lineage")
        elif self.kind in {
            LanguageEvidenceKindV3.OCR_OCCURRENCE,
            LanguageEvidenceKindV3.OCR_REGION,
            LanguageEvidenceKindV3.VISION_DERIVATION,
        }:
            if self.chunk_id is not None:
                raise ValueError("asset-derived V3 evidence cannot claim a canonical chunk")
            if (
                self.occurrence_id is None
                or self.derivation_id is None
                or self.source_generation_id is None
            ):
                raise ValueError(
                    "asset-derived V3 evidence requires occurrence, derivation, and generation"
                )
            if self.parent_evidence_reference_digest is not None:
                raise ValueError("asset-derived V3 evidence cannot claim a parent reference")
        elif self.kind in {
            LanguageEvidenceKindV3.LANGUAGE_DERIVATION,
            LanguageEvidenceKindV3.REPRESENTATION_DERIVATION,
        }:
            if self.chunk_id is not None:
                raise ValueError("derived V3 evidence cannot claim a canonical chunk")
            if self.derivation_id is None or self.source_generation_id is None:
                raise ValueError("derived V3 evidence requires derivation and generation")
            legacy_language = (
                self.kind is LanguageEvidenceKindV3.LANGUAGE_DERIVATION
                and self.lineage_origin is EvidenceLineageOriginV3.LEGACY_V2_UPGRADE
            )
            if self.parent_evidence_reference_digest is None and not legacy_language:
                raise ValueError("native derived V3 evidence requires its parent reference digest")
        if (
            self.lineage_origin is EvidenceLineageOriginV3.LEGACY_V2_UPGRADE
            and self.kind is LanguageEvidenceKindV3.REPRESENTATION_DERIVATION
        ):
            raise ValueError("representation derivations have no V2 upgrade form")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": MULTILINGUAL_CONTRACT_V3,
            "lineage_origin": self.lineage_origin.value,
            "notebook_id": str(self.notebook_id),
            "source_id": str(self.source_id),
            "document_id": str(self.document_id),
            "version_id": str(self.version_id),
            "evidence_kind": self.kind.value,
            "evidence_id": self.evidence_id,
            "source_content_hash": self.source_content_hash,
            "chunk_id": self.chunk_id,
            "occurrence_id": None if self.occurrence_id is None else str(self.occurrence_id),
            "derivation_id": None if self.derivation_id is None else str(self.derivation_id),
            "source_generation_id": (
                None if self.source_generation_id is None else str(self.source_generation_id)
            ),
            "parent_evidence_reference_digest": self.parent_evidence_reference_digest,
        }

    @property
    def identity_digest(self) -> str:
        return _digest(self.identity_payload())

    @classmethod
    def from_v2(cls, source: LanguageEvidenceReferenceV2) -> LanguageEvidenceReferenceV3:
        """Losslessly upgrade one canonical V2 identity without reinterpretation."""
        return cls(
            notebook_id=source.notebook_id,
            source_id=source.source_id,
            document_id=source.document_id,
            version_id=source.version_id,
            kind=LanguageEvidenceKindV3(source.kind.value),
            evidence_id=source.evidence_id,
            source_content_hash=source.source_content_hash,
            lineage_origin=EvidenceLineageOriginV3.LEGACY_V2_UPGRADE,
            chunk_id=source.chunk_id,
            occurrence_id=source.occurrence_id,
            derivation_id=source.derivation_id,
            source_generation_id=source.source_generation_id,
            parent_evidence_reference_digest=None,
        )


class MultilingualRetrievalPath(StrEnum):
    NATIVE_SPARSE = "native_sparse"
    MULTILINGUAL_DENSE = "multilingual_dense"
    TRANSLATION = "translation"
    TRANSLITERATION = "transliteration"


class AnswerLanguageMode(StrEnum):
    QUERY = "query"
    EXPLICIT = "explicit"
    ORIGINAL_EVIDENCE = "original_evidence"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageConfidence:
    value: float
    calibrated: bool

    def __post_init__(self) -> None:
        require_unit_interval(self.value, "value")


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageRegion:
    order: int
    locator: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        require_positive(self.order, "order")


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageObservation:
    observation_id: UUID
    actor_id: UUID
    notebook_id: UUID
    document_id: UUID | None
    version_id: UUID | None
    target_scope: LanguageObservationScope
    target_id: str
    language: LanguageCode
    script: ScriptCode
    confidence: LanguageConfidence
    detection_source: LanguageDetectionSource
    detector: str
    detector_revision: str
    configuration_digest: str
    input_hash: str
    mixed_language: bool
    mixed_script: bool
    region: LanguageRegion | None
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty(self.target_id, "target_id")
        require_non_empty(self.detector, "detector")
        require_non_empty(self.detector_revision, "detector_revision")
        require_sha256(self.configuration_digest, "configuration_digest")
        require_sha256(self.input_hash, "input_hash")
        require_utc(self.created_at, "created_at")
        expected = language_observation_id(
            notebook_id=self.notebook_id,
            target_scope=self.target_scope,
            target_id=self.target_id,
            detector=self.detector,
            detector_revision=self.detector_revision,
            configuration_digest=self.configuration_digest,
            input_hash=self.input_hash,
        )
        if self.observation_id != expected:
            raise ValueError("observation_id does not match detection provenance")
        if (self.document_id is None) != (self.version_id is None):
            raise ValueError("document_id and version_id must be provided together")


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageHypothesisV2:
    language: LanguageCode
    confidence: LanguageConfidence
    authority_class: ObservationAuthorityClass
    evidence_digest: str

    def __post_init__(self) -> None:
        require_sha256(self.evidence_digest, "evidence_digest")


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageObservationV2:
    """Language-generic, multi-hypothesis observation independent of script."""

    observation_id: UUID
    actor_id: UUID
    notebook_id: UUID
    target_scope: LanguageObservationScope
    target_id: str
    hypotheses: tuple[LanguageHypothesisV2, ...]
    detector: str
    detector_revision: str
    configuration_digest: str
    input_hash: str
    mixed_language: bool
    source_reference: LanguageEvidenceReferenceV3 | None
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty(self.target_id, "target_id")
        require_non_empty(self.detector, "detector")
        require_non_empty(self.detector_revision, "detector_revision")
        require_sha256(self.configuration_digest, "configuration_digest")
        require_sha256(self.input_hash, "input_hash")
        require_utc(self.created_at, "created_at")
        if not self.hypotheses:
            raise ValueError("language observation requires at least one hypothesis")
        if len({item.language for item in self.hypotheses}) != len(self.hypotheses):
            raise ValueError("language hypotheses must have unique language codes")
        if self.mixed_language and len(self.hypotheses) < 2:
            raise ValueError("mixed language requires multiple hypotheses")
        expected = language_observation_v2_id(
            notebook_id=self.notebook_id,
            target_scope=self.target_scope,
            target_id=self.target_id,
            detector=self.detector,
            detector_revision=self.detector_revision,
            configuration_digest=self.configuration_digest,
            input_hash=self.input_hash,
            source_reference_digest=(
                None if self.source_reference is None else self.source_reference.identity_digest
            ),
        )
        if self.observation_id != expected:
            raise ValueError("V2 language observation identity mismatch")
        if self.source_reference is not None and (
            self.source_reference.notebook_id != self.notebook_id
            or self.source_reference.source_content_hash != self.input_hash
        ):
            raise ValueError("V2 language observation conflicts with source evidence")


@dataclass(frozen=True, slots=True, kw_only=True)
class ScriptHypothesisV1:
    script: ScriptCode
    confidence: LanguageConfidence
    authority_class: ObservationAuthorityClass
    evidence_digest: str

    def __post_init__(self) -> None:
        require_sha256(self.evidence_digest, "evidence_digest")


@dataclass(frozen=True, slots=True, kw_only=True)
class ScriptObservationV1:
    """Script-only observation; it never establishes a language."""

    observation_id: UUID
    actor_id: UUID
    notebook_id: UUID
    target_scope: LanguageObservationScope
    target_id: str
    hypotheses: tuple[ScriptHypothesisV1, ...]
    detector: str
    detector_revision: str
    configuration_digest: str
    input_hash: str
    mixed_script: bool
    source_reference: LanguageEvidenceReferenceV3 | None
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty(self.target_id, "target_id")
        require_non_empty(self.detector, "detector")
        require_non_empty(self.detector_revision, "detector_revision")
        require_sha256(self.configuration_digest, "configuration_digest")
        require_sha256(self.input_hash, "input_hash")
        require_utc(self.created_at, "created_at")
        if not self.hypotheses:
            raise ValueError("script observation requires at least one hypothesis")
        if len({item.script for item in self.hypotheses}) != len(self.hypotheses):
            raise ValueError("script hypotheses must have unique script codes")
        if self.mixed_script and len(self.hypotheses) < 2:
            raise ValueError("mixed script requires multiple hypotheses")
        expected = script_observation_v1_id(
            notebook_id=self.notebook_id,
            target_scope=self.target_scope,
            target_id=self.target_id,
            detector=self.detector,
            detector_revision=self.detector_revision,
            configuration_digest=self.configuration_digest,
            input_hash=self.input_hash,
            source_reference_digest=(
                None if self.source_reference is None else self.source_reference.identity_digest
            ),
        )
        if self.observation_id != expected:
            raise ValueError("script observation identity mismatch")
        if self.source_reference is not None and (
            self.source_reference.notebook_id != self.notebook_id
            or self.source_reference.source_content_hash != self.input_hash
        ):
            raise ValueError("script observation conflicts with source evidence")


def language_observation_id(
    *,
    notebook_id: UUID,
    target_scope: LanguageObservationScope,
    target_id: str,
    detector: str,
    detector_revision: str,
    configuration_digest: str,
    input_hash: str,
) -> UUID:
    return uuid5(
        _OBSERVATION_NAMESPACE,
        ":".join(
            (
                MULTILINGUAL_CONTRACT_VERSION,
                str(notebook_id),
                target_scope.value,
                target_id,
                detector,
                detector_revision,
                configuration_digest,
                input_hash,
            )
        ),
    )


def language_observation_v2_id(
    *,
    notebook_id: UUID,
    target_scope: LanguageObservationScope,
    target_id: str,
    detector: str,
    detector_revision: str,
    configuration_digest: str,
    input_hash: str,
    source_reference_digest: str | None,
) -> UUID:
    return uuid5(
        _OBSERVATION_V2_NAMESPACE,
        _digest(
            {
                "notebook_id": str(notebook_id),
                "target_scope": target_scope.value,
                "target_id": target_id,
                "detector": detector,
                "detector_revision": detector_revision,
                "configuration_digest": configuration_digest,
                "input_hash": input_hash,
                "source_reference_digest": source_reference_digest,
            }
        ),
    )


def script_observation_v1_id(
    *,
    notebook_id: UUID,
    target_scope: LanguageObservationScope,
    target_id: str,
    detector: str,
    detector_revision: str,
    configuration_digest: str,
    input_hash: str,
    source_reference_digest: str | None,
) -> UUID:
    return uuid5(
        _SCRIPT_OBSERVATION_NAMESPACE,
        _digest(
            {
                "notebook_id": str(notebook_id),
                "target_scope": target_scope.value,
                "target_id": target_id,
                "detector": detector,
                "detector_revision": detector_revision,
                "configuration_digest": configuration_digest,
                "input_hash": input_hash,
                "source_reference_digest": source_reference_digest,
            }
        ),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageProviderProfile:
    provider: str
    model: str
    revision: str
    profile: str
    configuration_digest: str
    trust_class: ProcessingTrustClass
    supported_languages: tuple[LanguageCode, ...]
    supported_scripts: tuple[ScriptCode, ...]
    supported_directions: tuple[str, ...]
    state: LanguageCapabilityState

    def __post_init__(self) -> None:
        for value, name in (
            (self.provider, "provider"),
            (self.model, "model"),
            (self.revision, "revision"),
            (self.profile, "profile"),
        ):
            require_non_empty(value, name)
        require_sha256(self.configuration_digest, "configuration_digest")
        if len(set(self.supported_languages)) != len(self.supported_languages):
            raise ValueError("supported_languages must be unique")
        if len(set(self.supported_scripts)) != len(self.supported_scripts):
            raise ValueError("supported_scripts must be unique")
        for direction in self.supported_directions:
            _parse_direction(direction)

    def supports_direction(self, source: LanguageCode, target: LanguageCode) -> bool:
        return f"{source.value}->{target.value}" in self.supported_directions


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageTransformationRequest:
    actor_id: UUID
    notebook_id: UUID
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    source_evidence_id: str
    source_text: str
    source_language: LanguageCode
    target_language: LanguageCode
    kind: LanguageDerivationKind
    provider_profile: LanguageProviderProfile
    preprocessing_digest: str
    generation_id: UUID
    consent: ProcessingConsent

    def __post_init__(self) -> None:
        require_non_empty(self.source_evidence_id, "source_evidence_id")
        require_non_empty(self.source_text, "source_text")
        require_sha256(self.preprocessing_digest, "preprocessing_digest")
        if (
            self.source_language == self.target_language
            and self.kind is LanguageDerivationKind.TRANSLATION
        ):
            raise ValueError("translation requires distinct source and target languages")

    @property
    def source_hash(self) -> str:
        return hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()

    def identity_payload(self) -> dict[str, object]:
        return {
            "contract": MULTILINGUAL_CONTRACT_VERSION,
            "kind": self.kind.value,
            "notebook_id": str(self.notebook_id),
            "document_id": str(self.document_id),
            "version_id": str(self.version_id),
            "occurrence_id": str(self.occurrence_id),
            "source_evidence_id": self.source_evidence_id,
            "source_hash": self.source_hash,
            "source_language": self.source_language.value,
            "target_language": self.target_language.value,
            "provider": self.provider_profile.provider,
            "model": self.provider_profile.model,
            "revision": self.provider_profile.revision,
            "profile": self.provider_profile.profile,
            "configuration_digest": self.provider_profile.configuration_digest,
            "preprocessing_digest": self.preprocessing_digest,
            "generation_id": str(self.generation_id),
        }

    def cache_key(self) -> str:
        return _digest(self.identity_payload())

    def derivation_id(self) -> UUID:
        return uuid5(_DERIVATION_NAMESPACE, self.cache_key())


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageTransformationRequestV2:
    """V2 transformation request using a generic, typed source reference."""

    actor_id: UUID
    source: LanguageEvidenceReferenceV2
    source_text: str
    source_language: LanguageCode
    target_language: LanguageCode
    kind: LanguageDerivationKind
    provider_profile: LanguageProviderProfile
    preprocessing_digest: str
    generation_id: UUID
    consent: ProcessingConsent

    def __post_init__(self) -> None:
        require_non_empty(self.source_text, "source_text")
        require_sha256(self.preprocessing_digest, "preprocessing_digest")
        if hashlib.sha256(self.source_text.encode("utf-8")).hexdigest() != (
            self.source.source_content_hash
        ):
            raise ValueError("source text does not match source reference hash")
        if (
            self.source_language == self.target_language
            and self.kind is LanguageDerivationKind.TRANSLATION
        ):
            raise ValueError("translation requires distinct source and target languages")

    @property
    def source_hash(self) -> str:
        return self.source.source_content_hash

    def identity_payload(self) -> dict[str, object]:
        return {
            "contract": MULTILINGUAL_CONTRACT_V2,
            "kind": self.kind.value,
            "actor_id": str(self.actor_id),
            "source": self.source.identity_payload(),
            "source_language": self.source_language.value,
            "target_language": self.target_language.value,
            "provider": self.provider_profile.provider,
            "model": self.provider_profile.model,
            "revision": self.provider_profile.revision,
            "profile": self.provider_profile.profile,
            "configuration_digest": self.provider_profile.configuration_digest,
            "preprocessing_digest": self.preprocessing_digest,
            "generation_id": str(self.generation_id),
        }

    def cache_key(self) -> str:
        return _digest(self.identity_payload())

    def derivation_id(self) -> UUID:
        return uuid5(_DERIVATION_NAMESPACE, self.cache_key())


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageDerivation:
    derivation_id: UUID
    cache_key: str
    actor_id: UUID
    notebook_id: UUID
    document_id: UUID
    version_id: UUID
    source_evidence_id: str
    source_hash: str
    source_language: LanguageCode
    target_language: LanguageCode
    kind: LanguageDerivationKind
    output_text: str
    output_hash: str
    provider_profile: LanguageProviderProfile
    preprocessing_digest: str
    generation_id: UUID
    created_at: datetime
    schema_version: int = LANGUAGE_DERIVATION_SCHEMA_VERSION
    source_reference: LanguageEvidenceReferenceV2 | None = None

    def __post_init__(self) -> None:
        require_sha256(self.cache_key, "cache_key")
        require_sha256(self.source_hash, "source_hash")
        require_non_empty(self.source_evidence_id, "source_evidence_id")
        require_non_empty(self.output_text, "output_text")
        require_sha256(self.output_hash, "output_hash")
        require_sha256(self.preprocessing_digest, "preprocessing_digest")
        require_utc(self.created_at, "created_at")
        require_positive(self.schema_version, "schema_version")
        if hashlib.sha256(self.output_text.encode("utf-8")).hexdigest() != self.output_hash:
            raise ValueError("output_hash does not match derived text")
        if self.derivation_id != uuid5(_DERIVATION_NAMESPACE, self.cache_key):
            raise ValueError("derivation_id does not match cache identity")
        if self.source_reference is not None and (
            self.source_reference.notebook_id != self.notebook_id
            or self.source_reference.document_id != self.document_id
            or self.source_reference.version_id != self.version_id
            or self.source_reference.evidence_id != self.source_evidence_id
            or self.source_reference.source_content_hash != self.source_hash
        ):
            raise ValueError("language derivation source reference conflicts with provenance")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualEmbeddingProfile:
    provider: str
    model: str
    revision: str
    profile: str
    generation_id: UUID
    dimension: int
    normalized: bool
    distance_metric: str
    preprocessing_digest: str
    languages: tuple[LanguageCode, ...]
    scripts: tuple[ScriptCode, ...]
    capability_state: LanguageCapabilityState

    def __post_init__(self) -> None:
        for value, name in (
            (self.provider, "provider"),
            (self.model, "model"),
            (self.revision, "revision"),
            (self.profile, "profile"),
            (self.distance_metric, "distance_metric"),
        ):
            require_non_empty(value, name)
        require_positive(self.dimension, "dimension")
        require_sha256(self.preprocessing_digest, "preprocessing_digest")

    @property
    def vector_space(self) -> str:
        return multilingual_vector_space_identity(
            provider=self.provider,
            model=self.model,
            revision=self.revision,
            dimension=self.dimension,
            normalized=self.normalized,
            distance_metric=self.distance_metric,
            preprocessing_digest=self.preprocessing_digest,
        )


def multilingual_vector_space_identity(
    *,
    provider: str,
    model: str,
    revision: str,
    dimension: int,
    normalized: bool,
    distance_metric: str,
    preprocessing_digest: str,
) -> str:
    """Return the canonical machine-independent semantic vector-space identity.

    Generation, deployment profile labels, and language capability claims do not
    alter vector compatibility. They remain independently governed provenance.
    """
    for value, name in (
        (provider, "provider"),
        (model, "model"),
        (revision, "revision"),
        (distance_metric, "distance_metric"),
    ):
        require_non_empty(value, name)
    require_positive(dimension, "dimension")
    require_sha256(preprocessing_digest, "preprocessing_digest")
    if not isinstance(normalized, bool):
        raise TypeError("normalized must be a boolean")
    return _digest(
        {
            "schema_version": "mnemo.multilingual-vector-space/1",
            "provider": provider,
            "model": model,
            "revision": revision,
            "dimension": dimension,
            "normalized": normalized,
            "distance_metric": distance_metric,
            "preprocessing_digest": preprocessing_digest,
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualEmbeddingInputV2:
    """One ordered document-side embedding input with immutable provenance."""

    source: LanguageEvidenceReferenceV2
    text: str
    language: LanguageCode

    def __post_init__(self) -> None:
        require_non_empty(self.text, "text")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != (
            self.source.source_content_hash
        ):
            raise ValueError("embedding input text does not match source content hash")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualQueryEmbeddingV2:
    query_hash: str
    language: LanguageCode
    profile: MultilingualEmbeddingProfile
    vector: tuple[float, ...]
    vector_hash: str

    def __post_init__(self) -> None:
        require_sha256(self.query_hash, "query_hash")
        require_sha256(self.vector_hash, "vector_hash")
        if len(self.vector) != self.profile.dimension:
            raise ValueError("multilingual query embedding dimension mismatch")
        if _vector_hash(self.vector) != self.vector_hash:
            raise ValueError("query vector hash does not match vector")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualProviderReadinessV2:
    available_locally: bool
    loadable: bool
    initialized: bool
    exact_identity: bool
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.loadable and not self.available_locally:
            raise ValueError("loadable provider requires local availability")
        if self.initialized and not self.loadable:
            raise ValueError("initialized provider requires loadability")
        if self.initialized and not self.exact_identity:
            raise ValueError("initialized provider requires exact frozen identity")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualRerankScoreV2:
    candidate_id: UUID
    score: float
    model: str
    revision: str
    preprocessing: str

    def __post_init__(self) -> None:
        require_finite(self.score, "score")
        require_non_empty(self.model, "model")
        require_non_empty(self.revision, "revision")
        require_non_empty(self.preprocessing, "preprocessing")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualEmbedding:
    embedding_id: UUID
    notebook_id: UUID
    source_evidence_id: str
    source_hash: str
    language: LanguageCode
    profile: MultilingualEmbeddingProfile
    vector: tuple[float, ...]
    vector_hash: str
    created_at: datetime
    source_reference: LanguageEvidenceReferenceV2 | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.source_evidence_id, "source_evidence_id")
        require_sha256(self.source_hash, "source_hash")
        require_sha256(self.vector_hash, "vector_hash")
        require_utc(self.created_at, "created_at")
        if len(self.vector) != self.profile.dimension:
            raise ValueError("multilingual embedding dimension mismatch")
        for component in self.vector:
            require_finite(component, "vector component")
        if _vector_hash(self.vector) != self.vector_hash:
            raise ValueError("vector_hash does not match vector")
        expected = uuid5(
            _EMBEDDING_NAMESPACE,
            f"{self.notebook_id}:{self.source_evidence_id}:{self.source_hash}:{self.language}:{self.profile.vector_space}",
        )
        if self.embedding_id != expected:
            raise ValueError("embedding_id does not match vector provenance")
        if self.source_reference is not None and (
            self.source_reference.notebook_id != self.notebook_id
            or self.source_reference.evidence_id != self.source_evidence_id
            or self.source_reference.source_content_hash != self.source_hash
        ):
            raise ValueError("embedding source reference conflicts with vector provenance")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualPathSelection:
    path: MultilingualRetrievalPath
    target_language: LanguageCode
    state: LanguageCapabilityState
    profile: str
    reason: str

    def __post_init__(self) -> None:
        require_non_empty(self.profile, "profile")
        require_non_empty(self.reason, "reason")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualRetrievalPlan:
    query: str
    query_observation: LanguageObservation
    base_plan: RetrievalPlanV2
    target_languages: tuple[LanguageCode, ...]
    paths: tuple[MultilingualPathSelection, ...]

    def __post_init__(self) -> None:
        require_non_empty(self.query, "query")
        if self.base_plan.query != self.query:
            raise ValueError("base retrieval query must match multilingual query")
        if not self.target_languages:
            raise ValueError("target_languages must not be empty")
        if len(set(self.target_languages)) != len(self.target_languages):
            raise ValueError("target_languages must be unique")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualCandidate:
    candidate: EvidenceCandidateV2
    evidence_language: LanguageCode
    evidence_script: ScriptCode
    paths: tuple[MultilingualPathSelection, ...]
    source_ranks: FrozenMetadata
    fused_score: float
    final_rank: int
    match_derivation_id: UUID | None = None
    match_embedding_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.paths:
            raise ValueError("multilingual candidate requires retrieval provenance")
        require_finite(self.fused_score, "fused_score")
        require_positive(self.final_rank, "final_rank")
        for value in self.source_ranks.values():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("source ranks must be positive integers")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualRetrievalResult:
    plan: MultilingualRetrievalPlan
    candidates: tuple[MultilingualCandidate, ...]
    completeness: RetrievalCompleteness
    unavailable_paths: tuple[MultilingualPathSelection, ...]
    diagnostics: FrozenMetadata

    def __post_init__(self) -> None:
        if tuple(item.final_rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("multilingual candidate ranks must be contiguous")


@dataclass(frozen=True, slots=True, kw_only=True)
class AnswerLanguagePolicy:
    mode: AnswerLanguageMode
    explicit_language: LanguageCode | None
    fallback_language: LanguageCode | None
    allow_fallback: bool

    def __post_init__(self) -> None:
        if self.mode is AnswerLanguageMode.EXPLICIT and self.explicit_language is None:
            raise ValueError("explicit answer language mode requires a language")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualFinalQARequest:
    request: FinalQARequestV2
    query_observation: LanguageObservation
    evidence_languages: tuple[LanguageCode, ...]
    answer_policy: AnswerLanguagePolicy

    def __post_init__(self) -> None:
        if not self.evidence_languages:
            raise ValueError("evidence_languages must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualFinalQAResult:
    result: FinalQAResultV2
    query_language: LanguageCode
    evidence_languages: tuple[LanguageCode, ...]
    answer_language: LanguageCode
    capability_state: LanguageCapabilityState
    original_evidence_citations: bool


def multilingual_embedding_id(
    *,
    notebook_id: UUID,
    source_evidence_id: str,
    source_hash: str,
    language: LanguageCode,
    profile: MultilingualEmbeddingProfile,
) -> UUID:
    return uuid5(
        _EMBEDDING_NAMESPACE,
        f"{notebook_id}:{source_evidence_id}:{source_hash}:{language}:{profile.vector_space}",
    )


def multilingual_vector_hash(vector: tuple[float, ...]) -> str:
    return _vector_hash(vector)


def language_processing_manifest(
    request: LanguageTransformationRequest,
    *,
    estimate: ProcessingEstimate,
    budget: ProcessingBudget,
    max_retries: int,
) -> ProcessingManifest:
    """Adapt an expensive language derivation to the existing durable job contract."""
    return ProcessingManifest(
        actor_id=str(request.actor_id),
        notebook_id=request.notebook_id,
        operation=f"language.{request.kind.value}",
        occurrence_id=request.occurrence_id,
        document_id=request.document_id,
        version_id=request.version_id,
        provider_profile=request.provider_profile.profile,
        provider_identity=request.provider_profile.provider,
        provider_trust=request.provider_profile.trust_class,
        model_identity=f"{request.provider_profile.model}@{request.provider_profile.revision}",
        configuration=FrozenMetadata(
            {
                "source_hash": request.source_hash,
                "source_language": request.source_language.value,
                "target_language": request.target_language.value,
                "preprocessing_digest": request.preprocessing_digest,
                "derivation_cache_key": request.cache_key(),
            }
        ),
        generation_id=request.generation_id,
        language=request.target_language.value,
        output_schema=f"language-derivation/v{LANGUAGE_DERIVATION_SCHEMA_VERSION}",
        policy_version=request.consent.policy_version,
        consent=request.consent,
        estimate=estimate,
        budget=budget,
        max_retries=max_retries,
    )


def _normalize_language_tag(value: str) -> str:
    require_non_empty(value, "language code")
    parts = value.replace("_", "-").split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        normalized.append(
            part.title()
            if len(part) == 4 and part.isalpha()
            else part.upper()
            if len(part) == 2 and part.isalpha()
            else part.lower()
        )
    return "-".join(normalized)


def _parse_direction(value: str) -> tuple[LanguageCode, LanguageCode]:
    parts = value.split("->")
    if len(parts) != 2:
        raise ValueError("language direction must use source->target")
    return LanguageCode(parts[0]), LanguageCode(parts[1])


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _vector_hash(vector: tuple[float, ...]) -> str:
    return _digest(list(vector))


def language_provider_profile_payload(profile: LanguageProviderProfile) -> dict[str, object]:
    return {
        "provider": profile.provider,
        "model": profile.model,
        "revision": profile.revision,
        "profile": profile.profile,
        "configuration_digest": profile.configuration_digest,
        "trust_class": profile.trust_class.value,
        "supported_languages": [item.value for item in profile.supported_languages],
        "supported_scripts": [item.value for item in profile.supported_scripts],
        "supported_directions": list(profile.supported_directions),
        "state": profile.state.value,
    }


def language_observation_payload(observation: LanguageObservation) -> dict[str, object]:
    return {
        "observation_id": str(observation.observation_id),
        "actor_id": str(observation.actor_id),
        "notebook_id": str(observation.notebook_id),
        "document_id": None if observation.document_id is None else str(observation.document_id),
        "version_id": None if observation.version_id is None else str(observation.version_id),
        "target_scope": observation.target_scope.value,
        "target_id": observation.target_id,
        "language": observation.language.value,
        "script": observation.script.value,
        "confidence": observation.confidence.value,
        "calibrated": observation.confidence.calibrated,
        "detection_source": observation.detection_source.value,
        "detector": observation.detector,
        "detector_revision": observation.detector_revision,
        "configuration_digest": observation.configuration_digest,
        "input_hash": observation.input_hash,
        "mixed_language": observation.mixed_language,
        "mixed_script": observation.mixed_script,
        "region": None
        if observation.region is None
        else {
            "order": observation.region.order,
            "locator": thaw_metadata(observation.region.locator),
        },
        "created_at": observation.created_at.isoformat(),
    }
