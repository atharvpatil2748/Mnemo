"""Provider-neutral vision and visual-vector derivations for Phase 8.5.5."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from ._shared import (
    BoundingBox,
    FrozenMetadata,
    require_enum,
    require_finite,
    require_non_empty,
    require_non_negative,
    require_optional_non_empty,
    require_positive,
    require_sha256,
    require_tuple,
    require_unit_interval,
    require_utc,
    require_uuid,
    thaw_metadata,
)
from .assets import asset_derivation_id

VISION_RESULT_SCHEMA_VERSION = 1
VISION_IDENTITY_DOMAIN = "mnemo.vision.derivation.v1"
VISUAL_EMBEDDING_IDENTITY_DOMAIN = "mnemo.visual-embedding.derivation.v1"
VISION_EVIDENCE_KIND = "derived_vision"
_ENTITY_NAMESPACE = UUID("a3af9315-dfbf-56a8-8ab5-f9fa15db30ee")
_REGION_NAMESPACE = UUID("c99f9b67-bec5-56a6-901d-f15cd75a0b5a")
_SAFE_CODE = re.compile(r"[a-z0-9_.:-]{1,128}")


class VisionCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class VisionFailureClass(StrEnum):
    TRANSIENT = "transient"
    UNSUPPORTED = "unsupported"
    INVALID_INPUT = "invalid_input"
    SECURITY_LIMIT = "security_limit"
    PROVIDER = "provider"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


class VisualDistanceMetric(StrEnum):
    COSINE = "cosine"
    DOT = "dot"
    EUCLIDEAN = "euclidean"


class VisualNormalization(StrEnum):
    UNIT = "unit"
    NONE = "none"


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionConfidence:
    value: float | None

    def __post_init__(self) -> None:
        if self.value is not None:
            require_unit_interval(self.value, "value")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionLanguageObservation:
    language_code: str | None
    script: str | None
    confidence: VisionConfidence
    mixed: bool = False

    def __post_init__(self) -> None:
        require_optional_non_empty(self.language_code, "language_code")
        require_optional_non_empty(self.script, "script")
        if not isinstance(self.confidence, VisionConfidence):
            raise TypeError("confidence must be VisionConfidence")
        if not isinstance(self.mixed, bool):
            raise TypeError("mixed must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionCapability:
    supported_media_types: tuple[str, ...]
    supported_languages: tuple[str, ...]
    max_width: int
    max_height: int
    max_pixels: int
    max_response_bytes: int
    max_captions: int
    max_entities: int
    max_regions: int
    max_relations: int
    geometry: bool
    confidence: bool
    cancellation: bool

    def __post_init__(self) -> None:
        require_tuple(self.supported_media_types, "supported_media_types")
        require_tuple(self.supported_languages, "supported_languages")
        for value in (*self.supported_media_types, *self.supported_languages):
            require_non_empty(value, "capability value")
        for name in (
            "max_width",
            "max_height",
            "max_pixels",
            "max_response_bytes",
            "max_captions",
            "max_entities",
            "max_regions",
            "max_relations",
        ):
            require_positive(getattr(self, name), name)
        for name in ("geometry", "confidence", "cancellation"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionProviderMetadata:
    provider_identity: str
    model_identity: str
    model_revision: str
    profile_id: str
    capability: VisionCapability

    def __post_init__(self) -> None:
        for name in ("provider_identity", "model_identity", "model_revision", "profile_id"):
            require_non_empty(getattr(self, name), name)
        if not isinstance(self.capability, VisionCapability):
            raise TypeError("capability must be VisionCapability")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionProfile:
    profile_id: str
    provider_identity: str
    model_identity: str
    model_revision: str
    preprocessing: FrozenMetadata
    analysis_schema_version: int
    prompt_template_id: str
    prompt_hash: str
    language_hints: tuple[str, ...]
    max_pixels: int
    max_output_characters: int
    max_observations: int
    generation_id: UUID

    def __post_init__(self) -> None:
        for name in (
            "profile_id",
            "provider_identity",
            "model_identity",
            "model_revision",
            "prompt_template_id",
        ):
            require_non_empty(getattr(self, name), name)
        if not isinstance(self.preprocessing, FrozenMetadata):
            raise TypeError("preprocessing must be FrozenMetadata")
        require_positive(self.analysis_schema_version, "analysis_schema_version")
        require_sha256(self.prompt_hash, "prompt_hash")
        require_tuple(self.language_hints, "language_hints")
        for language in self.language_hints:
            require_non_empty(language, "language hint")
        require_positive(self.max_pixels, "max_pixels")
        require_positive(self.max_output_characters, "max_output_characters")
        require_positive(self.max_observations, "max_observations")
        require_uuid(self.generation_id, "generation_id")

    @property
    def preprocessing_digest(self) -> str:
        return hashlib.sha256(_canonical_json(thaw_metadata(self.preprocessing))).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionRequest:
    actor_id: str
    notebook_id: UUID
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    asset_id: UUID
    asset_content_hash: str
    media_type: str
    profile: VisionProfile

    def __post_init__(self) -> None:
        require_non_empty(self.actor_id, "actor_id")
        for name in ("notebook_id", "document_id", "version_id", "occurrence_id", "asset_id"):
            require_uuid(getattr(self, name), name)
        require_sha256(self.asset_content_hash, "asset_content_hash")
        require_non_empty(self.media_type, "media_type")
        if not isinstance(self.profile, VisionProfile):
            raise TypeError("profile must be VisionProfile")

    def identity_payload(self) -> dict[str, object]:
        return {
            "domain": VISION_IDENTITY_DOMAIN,
            "asset_id": str(self.asset_id),
            "asset_content_hash": self.asset_content_hash,
            "occurrence_id": str(self.occurrence_id),
            "document_id": str(self.document_id),
            "version_id": str(self.version_id),
            "media_type": self.media_type,
            "profile_id": self.profile.profile_id,
            "provider_identity": self.profile.provider_identity,
            "model_identity": self.profile.model_identity,
            "model_revision": self.profile.model_revision,
            "preprocessing": thaw_metadata(self.profile.preprocessing),
            "analysis_schema_version": self.profile.analysis_schema_version,
            "prompt_template_id": self.profile.prompt_template_id,
            "prompt_hash": self.profile.prompt_hash,
            "language_hints": self.profile.language_hints,
            "max_pixels": self.profile.max_pixels,
            "max_output_characters": self.profile.max_output_characters,
            "max_observations": self.profile.max_observations,
            "generation_id": str(self.profile.generation_id),
        }

    @property
    def cache_key(self) -> str:
        return hashlib.sha256(_canonical_json(self.identity_payload())).hexdigest()

    @property
    def derivation_id(self) -> UUID:
        return asset_derivation_id(
            occurrence_id=self.occurrence_id,
            operation="vision_analysis",
            provider_identity=self.profile.provider_identity,
            model_identity=f"{self.profile.model_identity}@{self.profile.model_revision}",
            configuration_digest=self.cache_key,
        )


def vision_region_id(
    *, derivation_id: UUID, order_index: int, bounding_box: BoundingBox | None
) -> UUID:
    material = json.dumps(
        {
            "derivation_id": str(derivation_id),
            "order_index": order_index,
            "bounding_box": bounding_box,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid5(_REGION_NAMESPACE, material)


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionRegion:
    region_id: UUID
    order_index: int
    bounding_box: BoundingBox | None

    def __post_init__(self) -> None:
        require_uuid(self.region_id, "region_id")
        require_non_negative(self.order_index, "order_index")
        if self.bounding_box is not None:
            require_tuple(self.bounding_box, "bounding_box")
            if len(self.bounding_box) != 4:
                raise ValueError("bounding_box must contain four coordinates")
            x0, y0, x1, y1 = self.bounding_box
            for value in self.bounding_box:
                require_finite(value, "bounding_box coordinate")
            if x0 > x1 or y0 > y1:
                raise ValueError("bounding_box coordinates must be ordered")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionCaption:
    text: str
    confidence: VisionConfidence
    language: VisionLanguageObservation | None
    evidence_kind: str = VISION_EVIDENCE_KIND

    def __post_init__(self) -> None:
        require_non_empty(self.text, "text")
        if not isinstance(self.confidence, VisionConfidence):
            raise TypeError("confidence must be VisionConfidence")
        if self.language is not None and not isinstance(self.language, VisionLanguageObservation):
            raise TypeError("language must be VisionLanguageObservation")
        if self.evidence_kind != VISION_EVIDENCE_KIND:
            raise ValueError("vision captions must be labelled derived_vision")


def vision_entity_id(*, derivation_id: UUID, order_index: int, label: str) -> UUID:
    return uuid5(_ENTITY_NAMESPACE, f"{derivation_id}:{order_index}:{label}")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionEntity:
    entity_id: UUID
    order_index: int
    label: str
    attributes: FrozenMetadata
    region_id: UUID | None
    confidence: VisionConfidence

    def __post_init__(self) -> None:
        require_uuid(self.entity_id, "entity_id")
        require_non_negative(self.order_index, "order_index")
        require_non_empty(self.label, "label")
        if not isinstance(self.attributes, FrozenMetadata):
            raise TypeError("attributes must be FrozenMetadata")
        if self.region_id is not None:
            require_uuid(self.region_id, "region_id")
        if not isinstance(self.confidence, VisionConfidence):
            raise TypeError("confidence must be VisionConfidence")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionRelation:
    source_entity_id: UUID
    target_entity_id: UUID
    relation: str
    confidence: VisionConfidence

    def __post_init__(self) -> None:
        require_uuid(self.source_entity_id, "source_entity_id")
        require_uuid(self.target_entity_id, "target_entity_id")
        if self.source_entity_id == self.target_entity_id:
            raise ValueError("vision relation endpoints must differ")
        require_non_empty(self.relation, "relation")
        if not isinstance(self.confidence, VisionConfidence):
            raise TypeError("confidence must be VisionConfidence")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionObservation:
    order_index: int
    kind: str
    value: str
    region_id: UUID | None
    confidence: VisionConfidence
    evidence_kind: str = VISION_EVIDENCE_KIND

    def __post_init__(self) -> None:
        require_non_negative(self.order_index, "order_index")
        require_non_empty(self.kind, "kind")
        require_non_empty(self.value, "value")
        if self.region_id is not None:
            require_uuid(self.region_id, "region_id")
        if not isinstance(self.confidence, VisionConfidence):
            raise TypeError("confidence must be VisionConfidence")
        if self.evidence_kind != VISION_EVIDENCE_KIND:
            raise ValueError("vision observations must be labelled derived_vision")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionFailure:
    input_index: int | None
    classification: VisionFailureClass
    reason_code: str
    retryable: bool

    def __post_init__(self) -> None:
        if self.input_index is not None:
            require_non_negative(self.input_index, "input_index")
        require_enum(self.classification, VisionFailureClass, "classification")
        require_non_empty(self.reason_code, "reason_code")
        if _SAFE_CODE.fullmatch(self.reason_code) is None:
            raise ValueError("reason_code must be a bounded machine code")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionResult:
    derivation_id: UUID
    cache_key: str
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    asset_id: UUID
    generation_id: UUID
    provider: VisionProviderMetadata
    preprocessing_digest: str
    completeness: VisionCompleteness
    captions: tuple[VisionCaption, ...]
    observations: tuple[VisionObservation, ...]
    regions: tuple[VisionRegion, ...]
    entities: tuple[VisionEntity, ...]
    relations: tuple[VisionRelation, ...]
    languages: tuple[VisionLanguageObservation, ...]
    failures: tuple[VisionFailure, ...]
    inputs_submitted: int
    inputs_succeeded: int
    content_hash: str
    created_at: datetime
    warnings: tuple[str, ...] = ()
    schema_version: int = VISION_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "derivation_id",
            "document_id",
            "version_id",
            "occurrence_id",
            "asset_id",
            "generation_id",
        ):
            require_uuid(getattr(self, name), name)
        require_sha256(self.cache_key, "cache_key")
        if not isinstance(self.provider, VisionProviderMetadata):
            raise TypeError("provider must be VisionProviderMetadata")
        require_sha256(self.preprocessing_digest, "preprocessing_digest")
        require_enum(self.completeness, VisionCompleteness, "completeness")
        for name in (
            "captions",
            "observations",
            "regions",
            "entities",
            "relations",
            "languages",
            "failures",
            "warnings",
        ):
            require_tuple(getattr(self, name), name)
        require_non_negative(self.inputs_submitted, "inputs_submitted")
        require_non_negative(self.inputs_succeeded, "inputs_succeeded")
        if self.inputs_succeeded > self.inputs_submitted:
            raise ValueError("inputs_succeeded cannot exceed inputs_submitted")
        if self.completeness is VisionCompleteness.COMPLETE and (
            self.inputs_succeeded != self.inputs_submitted or self.failures
        ):
            raise ValueError("complete vision result cannot omit or fail inputs")
        if self.completeness is VisionCompleteness.PARTIAL and (
            not self.failures or self.inputs_succeeded == 0
        ):
            raise ValueError("partial vision result requires successes and failures")
        if self.completeness is VisionCompleteness.FAILED and (
            not self.failures or self.inputs_succeeded != 0
        ):
            raise ValueError("failed vision result requires failures and no successes")
        if self.completeness in {VisionCompleteness.FAILED, VisionCompleteness.UNAVAILABLE} and (
            self.captions or self.observations or self.entities or self.relations
        ):
            raise ValueError("non-publishable vision result cannot contain observations")
        if tuple(sorted(self.regions, key=lambda value: value.order_index)) != self.regions:
            raise ValueError("vision regions must be ordered")
        if (
            tuple(sorted(self.observations, key=lambda value: value.order_index))
            != self.observations
        ):
            raise ValueError("vision observations must be ordered")
        region_ids = {region.region_id for region in self.regions}
        if len(region_ids) != len(self.regions) or any(
            region.region_id
            != vision_region_id(
                derivation_id=self.derivation_id,
                order_index=region.order_index,
                bounding_box=region.bounding_box,
            )
            for region in self.regions
        ):
            raise ValueError("vision region identity is not deterministic")
        entity_ids = {entity.entity_id for entity in self.entities}
        if len(entity_ids) != len(self.entities) or any(
            entity.entity_id
            != vision_entity_id(
                derivation_id=self.derivation_id,
                order_index=entity.order_index,
                label=entity.label,
            )
            for entity in self.entities
        ):
            raise ValueError("vision entity identity is not deterministic")
        if any(
            entity.region_id is not None and entity.region_id not in region_ids
            for entity in self.entities
        ):
            raise ValueError("vision entity references an unknown region")
        if any(
            relation.source_entity_id not in entity_ids
            or relation.target_entity_id not in entity_ids
            for relation in self.relations
        ):
            raise ValueError("vision relation references an unknown entity")
        require_sha256(self.content_hash, "content_hash")
        if self.content_hash != vision_result_content_hash(
            completeness=self.completeness,
            captions=self.captions,
            observations=self.observations,
            regions=self.regions,
            entities=self.entities,
            relations=self.relations,
            languages=self.languages,
            failures=self.failures,
            warnings=self.warnings,
        ):
            raise ValueError("content_hash does not match the complete vision result")
        require_utc(self.created_at, "created_at")
        require_positive(self.schema_version, "schema_version")
        for warning in self.warnings:
            require_non_empty(warning, "warning")
            if _SAFE_CODE.fullmatch(warning) is None:
                raise ValueError("warnings must be bounded machine codes")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionDerivation:
    derivation_id: UUID
    cache_key: str
    occurrence_id: UUID
    generation_id: UUID
    result_content_hash: str | None

    def __post_init__(self) -> None:
        for name in ("derivation_id", "occurrence_id", "generation_id"):
            require_uuid(getattr(self, name), name)
        require_sha256(self.cache_key, "cache_key")
        if self.result_content_hash is not None:
            require_sha256(self.result_content_hash, "result_content_hash")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualEmbeddingCapability:
    supported_media_types: tuple[str, ...]
    dimensions: int
    metric: VisualDistanceMetric
    normalization: VisualNormalization
    shared_space_id: str | None
    max_width: int
    max_height: int
    max_pixels: int
    max_bytes: int
    cancellation: bool

    def __post_init__(self) -> None:
        require_tuple(self.supported_media_types, "supported_media_types")
        for media_type in self.supported_media_types:
            require_non_empty(media_type, "supported media type")
        require_positive(self.dimensions, "dimensions")
        require_enum(self.metric, VisualDistanceMetric, "metric")
        require_enum(self.normalization, VisualNormalization, "normalization")
        require_optional_non_empty(self.shared_space_id, "shared_space_id")
        for name in ("max_width", "max_height", "max_pixels", "max_bytes"):
            require_positive(getattr(self, name), name)
        if not isinstance(self.cancellation, bool):
            raise TypeError("cancellation must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualEmbeddingProfile:
    profile_id: str
    provider_identity: str
    model_identity: str
    model_revision: str
    preprocessing: FrozenMetadata
    dimensions: int
    metric: VisualDistanceMetric
    normalization: VisualNormalization
    shared_space_id: str | None
    generation_id: UUID

    def __post_init__(self) -> None:
        for name in ("profile_id", "provider_identity", "model_identity", "model_revision"):
            require_non_empty(getattr(self, name), name)
        if not isinstance(self.preprocessing, FrozenMetadata):
            raise TypeError("preprocessing must be FrozenMetadata")
        require_positive(self.dimensions, "dimensions")
        require_enum(self.metric, VisualDistanceMetric, "metric")
        require_enum(self.normalization, VisualNormalization, "normalization")
        require_optional_non_empty(self.shared_space_id, "shared_space_id")
        require_uuid(self.generation_id, "generation_id")

    @property
    def preprocessing_digest(self) -> str:
        return hashlib.sha256(_canonical_json(thaw_metadata(self.preprocessing))).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualEmbeddingRequest:
    actor_id: str
    notebook_id: UUID
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    asset_id: UUID
    asset_content_hash: str
    media_type: str
    profile: VisualEmbeddingProfile
    source_vision_derivation_id: UUID | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.actor_id, "actor_id")
        for name in ("notebook_id", "document_id", "version_id", "occurrence_id", "asset_id"):
            require_uuid(getattr(self, name), name)
        require_sha256(self.asset_content_hash, "asset_content_hash")
        require_non_empty(self.media_type, "media_type")
        if not isinstance(self.profile, VisualEmbeddingProfile):
            raise TypeError("profile must be VisualEmbeddingProfile")
        if self.source_vision_derivation_id is not None:
            require_uuid(self.source_vision_derivation_id, "source_vision_derivation_id")

    def identity_payload(self) -> dict[str, object]:
        return {
            "domain": VISUAL_EMBEDDING_IDENTITY_DOMAIN,
            "asset_id": str(self.asset_id),
            "asset_content_hash": self.asset_content_hash,
            "occurrence_id": str(self.occurrence_id),
            "document_id": str(self.document_id),
            "version_id": str(self.version_id),
            "media_type": self.media_type,
            "profile_id": self.profile.profile_id,
            "provider_identity": self.profile.provider_identity,
            "model_identity": self.profile.model_identity,
            "model_revision": self.profile.model_revision,
            "preprocessing": thaw_metadata(self.profile.preprocessing),
            "dimensions": self.profile.dimensions,
            "metric": self.profile.metric.value,
            "normalization": self.profile.normalization.value,
            "shared_space_id": self.profile.shared_space_id,
            "generation_id": str(self.profile.generation_id),
            "source_vision_derivation_id": (
                None
                if self.source_vision_derivation_id is None
                else str(self.source_vision_derivation_id)
            ),
        }

    @property
    def cache_key(self) -> str:
        return hashlib.sha256(_canonical_json(self.identity_payload())).hexdigest()

    @property
    def derivation_id(self) -> UUID:
        return asset_derivation_id(
            occurrence_id=self.occurrence_id,
            operation="visual_embedding",
            provider_identity=self.profile.provider_identity,
            model_identity=f"{self.profile.model_identity}@{self.profile.model_revision}",
            configuration_digest=self.cache_key,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualEmbeddingProviderMetadata:
    provider_identity: str
    model_identity: str
    model_revision: str
    profile_id: str
    capability: VisualEmbeddingCapability

    def __post_init__(self) -> None:
        for name in ("provider_identity", "model_identity", "model_revision", "profile_id"):
            require_non_empty(getattr(self, name), name)
        if not isinstance(self.capability, VisualEmbeddingCapability):
            raise TypeError("capability must be VisualEmbeddingCapability")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualEmbedding:
    derivation_id: UUID
    cache_key: str
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    asset_id: UUID
    generation_id: UUID
    source_vision_derivation_id: UUID | None
    provider: VisualEmbeddingProviderMetadata
    preprocessing_digest: str
    dimensions: int
    metric: VisualDistanceMetric
    normalization: VisualNormalization
    shared_space_id: str | None
    vector: tuple[float, ...]
    vector_hash: str
    created_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "derivation_id",
            "document_id",
            "version_id",
            "occurrence_id",
            "asset_id",
            "generation_id",
        ):
            require_uuid(getattr(self, name), name)
        if self.source_vision_derivation_id is not None:
            require_uuid(self.source_vision_derivation_id, "source_vision_derivation_id")
        require_sha256(self.cache_key, "cache_key")
        if not isinstance(self.provider, VisualEmbeddingProviderMetadata):
            raise TypeError("provider must be VisualEmbeddingProviderMetadata")
        require_sha256(self.preprocessing_digest, "preprocessing_digest")
        require_positive(self.dimensions, "dimensions")
        require_enum(self.metric, VisualDistanceMetric, "metric")
        require_enum(self.normalization, VisualNormalization, "normalization")
        require_optional_non_empty(self.shared_space_id, "shared_space_id")
        require_tuple(self.vector, "vector")
        if len(self.vector) != self.dimensions:
            raise ValueError("visual embedding dimension mismatch")
        for value in self.vector:
            require_finite(value, "vector value")
        if self.normalization is VisualNormalization.UNIT:
            magnitude = math.sqrt(sum(value * value for value in self.vector))
            if not math.isclose(magnitude, 1.0, rel_tol=1e-6, abs_tol=1e-6):
                raise ValueError("visual embedding does not satisfy unit normalization")
        require_sha256(self.vector_hash, "vector_hash")
        if self.vector_hash != visual_vector_hash(self.vector):
            raise ValueError("vector_hash does not match visual embedding")
        require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualEmbeddingDerivation:
    derivation_id: UUID
    cache_key: str
    occurrence_id: UUID
    generation_id: UUID
    vector_hash: str | None

    def __post_init__(self) -> None:
        for name in ("derivation_id", "occurrence_id", "generation_id"):
            require_uuid(getattr(self, name), name)
        require_sha256(self.cache_key, "cache_key")
        if self.vector_hash is not None:
            require_sha256(self.vector_hash, "vector_hash")


def visual_vector_hash(vector: tuple[float, ...]) -> str:
    return hashlib.sha256(_canonical_json(vector)).hexdigest()


def vision_result_content_hash(
    *,
    completeness: VisionCompleteness,
    captions: tuple[VisionCaption, ...],
    observations: tuple[VisionObservation, ...],
    regions: tuple[VisionRegion, ...],
    entities: tuple[VisionEntity, ...],
    relations: tuple[VisionRelation, ...],
    languages: tuple[VisionLanguageObservation, ...],
    failures: tuple[VisionFailure, ...],
    warnings: tuple[str, ...] = (),
) -> str:
    material = {
        "completeness": completeness.value,
        "captions": [
            {
                "text": value.text,
                "confidence": value.confidence.value,
                "language": (
                    None
                    if value.language is None
                    else {
                        "language": value.language.language_code,
                        "script": value.language.script,
                        "confidence": value.language.confidence.value,
                        "mixed": value.language.mixed,
                    }
                ),
            }
            for value in captions
        ],
        "observations": [
            {
                "order": value.order_index,
                "kind": value.kind,
                "value": value.value,
                "region": None if value.region_id is None else str(value.region_id),
                "confidence": value.confidence.value,
            }
            for value in observations
        ],
        "regions": [
            {
                "id": str(value.region_id),
                "order": value.order_index,
                "box": value.bounding_box,
            }
            for value in regions
        ],
        "entities": [
            {
                "id": str(value.entity_id),
                "order": value.order_index,
                "label": value.label,
                "attributes": thaw_metadata(value.attributes),
                "region": None if value.region_id is None else str(value.region_id),
                "confidence": value.confidence.value,
            }
            for value in entities
        ],
        "relations": [
            {
                "source": str(value.source_entity_id),
                "target": str(value.target_entity_id),
                "relation": value.relation,
                "confidence": value.confidence.value,
            }
            for value in relations
        ],
        "languages": [
            {
                "language": value.language_code,
                "script": value.script,
                "confidence": value.confidence.value,
                "mixed": value.mixed,
            }
            for value in languages
        ],
        "failures": [
            {
                "input": value.input_index,
                "classification": value.classification.value,
                "reason": value.reason_code,
                "retryable": value.retryable,
            }
            for value in failures
        ],
        "warnings": warnings,
    }
    return hashlib.sha256(_canonical_json(material)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
