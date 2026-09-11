"""Provider-neutral OCR derivation records for Phase 8.5.4."""

from __future__ import annotations

import hashlib
import json
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

OCR_IDENTITY_DOMAIN = "mnemo.ocr.derivation.v1"
OCR_RESULT_SCHEMA_VERSION = 1
OCR_PROJECTION_SCHEMA_VERSION = 1
OCR_EVIDENCE_KIND = "derived_ocr"
_REGION_NAMESPACE = UUID("89e23702-f95b-568b-94ed-63306d26a645")
_SAFE_CODE = re.compile(r"[a-z0-9_.:-]{1,128}")


class OCRCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class OCRPageKind(StrEnum):
    TEXT_NATIVE = "text_native"
    IMAGE_ONLY = "image_only"
    MIXED = "mixed"
    BLANK = "blank"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class OCRDocumentScanStatus(StrEnum):
    DIGITAL = "digital"
    MIXED = "mixed"
    SCAN_LIKELY = "scan_likely"
    DETECTION_FAILED = "detection_failed"
    UNKNOWN = "unknown"


class OCRConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class OCRFailureClass(StrEnum):
    TRANSIENT = "transient"
    UNSUPPORTED = "unsupported"
    INVALID_INPUT = "invalid_input"
    SECURITY_LIMIT = "security_limit"
    PROVIDER = "provider"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRConfidence:
    value: float | None
    band: OCRConfidenceBand

    def __post_init__(self) -> None:
        if self.value is not None:
            require_unit_interval(self.value, "value")
        require_enum(self.band, OCRConfidenceBand, "band")
        if (self.value is None) != (self.band is OCRConfidenceBand.UNAVAILABLE):
            raise ValueError("unavailable confidence must have no numeric value")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRLanguageObservation:
    language_code: str | None
    script: str | None
    confidence: OCRConfidence
    mixed: bool = False

    def __post_init__(self) -> None:
        require_optional_non_empty(self.language_code, "language_code")
        require_optional_non_empty(self.script, "script")
        if not isinstance(self.confidence, OCRConfidence):
            raise TypeError("confidence must be OCRConfidence")
        if not isinstance(self.mixed, bool):
            raise TypeError("mixed must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRCapability:
    supported_media_types: tuple[str, ...]
    supported_languages: tuple[str, ...]
    supported_scripts: tuple[str, ...]
    max_pages: int
    max_pixels: int
    geometry: bool
    confidence: bool
    cancellation: bool

    def __post_init__(self) -> None:
        require_tuple(self.supported_media_types, "supported_media_types")
        require_tuple(self.supported_languages, "supported_languages")
        require_tuple(self.supported_scripts, "supported_scripts")
        for value in (
            *self.supported_media_types,
            *self.supported_languages,
            *self.supported_scripts,
        ):
            require_non_empty(value, "capability value")
        require_positive(self.max_pages, "max_pages")
        require_positive(self.max_pixels, "max_pixels")
        for name in ("geometry", "confidence", "cancellation"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRProviderMetadata:
    provider_identity: str
    model_identity: str
    model_revision: str
    profile_id: str
    capability: OCRCapability

    def __post_init__(self) -> None:
        require_non_empty(self.provider_identity, "provider_identity")
        require_non_empty(self.model_identity, "model_identity")
        require_non_empty(self.model_revision, "model_revision")
        require_non_empty(self.profile_id, "profile_id")
        if not isinstance(self.capability, OCRCapability):
            raise TypeError("capability must be OCRCapability")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRProfile:
    profile_id: str
    provider_identity: str
    model_identity: str
    model_revision: str
    preprocessing: FrozenMetadata
    language_hints: tuple[str, ...]
    max_pages: int
    max_pixels: int
    max_output_characters: int
    generation_id: UUID

    def __post_init__(self) -> None:
        require_non_empty(self.profile_id, "profile_id")
        require_non_empty(self.provider_identity, "provider_identity")
        require_non_empty(self.model_identity, "model_identity")
        require_non_empty(self.model_revision, "model_revision")
        if not isinstance(self.preprocessing, FrozenMetadata):
            raise TypeError("preprocessing must be FrozenMetadata")
        require_tuple(self.language_hints, "language_hints")
        for language in self.language_hints:
            require_non_empty(language, "language hint")
        require_positive(self.max_pages, "max_pages")
        require_positive(self.max_pixels, "max_pixels")
        require_positive(self.max_output_characters, "max_output_characters")
        require_uuid(self.generation_id, "generation_id")

    @property
    def preprocessing_digest(self) -> str:
        return hashlib.sha256(_canonical_json(thaw_metadata(self.preprocessing))).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRRequest:
    actor_id: str
    notebook_id: UUID
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    asset_id: UUID
    asset_content_hash: str
    media_type: str
    profile: OCRProfile
    page_numbers: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty(self.actor_id, "actor_id")
        for name in ("notebook_id", "document_id", "version_id", "occurrence_id", "asset_id"):
            require_uuid(getattr(self, name), name)
        require_sha256(self.asset_content_hash, "asset_content_hash")
        require_non_empty(self.media_type, "media_type")
        if not isinstance(self.profile, OCRProfile):
            raise TypeError("profile must be OCRProfile")
        require_tuple(self.page_numbers, "page_numbers")
        if len(self.page_numbers) > self.profile.max_pages:
            raise ValueError("page selection exceeds profile max_pages")
        if tuple(sorted(set(self.page_numbers))) != self.page_numbers:
            raise ValueError("page_numbers must be unique and ordered")
        for page in self.page_numbers:
            require_positive(page, "page_number")

    def identity_payload(self) -> dict[str, object]:
        return {
            "domain": OCR_IDENTITY_DOMAIN,
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
            "language_hints": self.profile.language_hints,
            "max_pages": self.profile.max_pages,
            "max_pixels": self.profile.max_pixels,
            "max_output_characters": self.profile.max_output_characters,
            "generation_id": str(self.profile.generation_id),
            "page_numbers": self.page_numbers,
        }

    @property
    def cache_key(self) -> str:
        return hashlib.sha256(_canonical_json(self.identity_payload())).hexdigest()

    @property
    def derivation_id(self) -> UUID:
        return asset_derivation_id(
            occurrence_id=self.occurrence_id,
            operation="ocr",
            provider_identity=self.profile.provider_identity,
            model_identity=f"{self.profile.model_identity}@{self.profile.model_revision}",
            configuration_digest=self.cache_key,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRRegion:
    region_id: UUID
    page_number: int
    order_index: int
    text: str
    bounding_box: BoundingBox | None
    confidence: OCRConfidence
    language: OCRLanguageObservation | None
    evidence_kind: str = OCR_EVIDENCE_KIND

    def __post_init__(self) -> None:
        require_uuid(self.region_id, "region_id")
        require_positive(self.page_number, "page_number")
        require_non_negative(self.order_index, "order_index")
        require_non_empty(self.text, "text")
        if self.bounding_box is not None:
            require_tuple(self.bounding_box, "bounding_box")
            if len(self.bounding_box) != 4:
                raise ValueError("bounding_box must contain four coordinates")
            x0, y0, x1, y1 = self.bounding_box
            for coordinate in self.bounding_box:
                require_finite(coordinate, "bounding_box coordinate")
            if x0 > x1 or y0 > y1:
                raise ValueError("bounding_box coordinates must be ordered")
        if not isinstance(self.confidence, OCRConfidence):
            raise TypeError("confidence must be OCRConfidence")
        if self.language is not None and not isinstance(self.language, OCRLanguageObservation):
            raise TypeError("language must be OCRLanguageObservation")
        if self.evidence_kind != OCR_EVIDENCE_KIND:
            raise ValueError("OCR regions must be labelled derived_ocr")


def ocr_region_id(
    *,
    derivation_id: UUID,
    page_number: int,
    order_index: int,
    text: str,
    bounding_box: BoundingBox | None,
) -> UUID:
    material = {
        "derivation_id": str(derivation_id),
        "page_number": page_number,
        "order_index": order_index,
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "bounding_box": bounding_box,
    }
    return uuid5(_REGION_NAMESPACE, hashlib.sha256(_canonical_json(material)).hexdigest())


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRFailure:
    page_number: int | None
    classification: OCRFailureClass
    reason_code: str
    retryable: bool

    def __post_init__(self) -> None:
        if self.page_number is not None:
            require_positive(self.page_number, "page_number")
        require_enum(self.classification, OCRFailureClass, "classification")
        require_non_empty(self.reason_code, "reason_code")
        if _SAFE_CODE.fullmatch(self.reason_code) is None:
            raise ValueError("reason_code must be a bounded machine code")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRResult:
    derivation_id: UUID
    cache_key: str
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    asset_id: UUID
    generation_id: UUID
    provider: OCRProviderMetadata
    preprocessing_digest: str
    completeness: OCRCompleteness
    regions: tuple[OCRRegion, ...]
    languages: tuple[OCRLanguageObservation, ...]
    failures: tuple[OCRFailure, ...]
    pages_submitted: int
    pages_succeeded: int
    content_hash: str
    created_at: datetime
    warnings: tuple[str, ...] = ()
    schema_version: int = OCR_RESULT_SCHEMA_VERSION

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
        if not isinstance(self.provider, OCRProviderMetadata):
            raise TypeError("provider must be OCRProviderMetadata")
        require_sha256(self.preprocessing_digest, "preprocessing_digest")
        require_enum(self.completeness, OCRCompleteness, "completeness")
        for name in ("regions", "languages", "failures", "warnings"):
            require_tuple(getattr(self, name), name)
        require_non_negative(self.pages_submitted, "pages_submitted")
        require_non_negative(self.pages_succeeded, "pages_succeeded")
        if self.pages_succeeded > self.pages_submitted:
            raise ValueError("pages_succeeded cannot exceed pages_submitted")
        if self.completeness is OCRCompleteness.COMPLETE and (
            self.pages_succeeded != self.pages_submitted or self.failures
        ):
            raise ValueError("complete OCR result cannot omit or fail pages")
        if self.completeness is OCRCompleteness.PARTIAL and (
            not self.failures or self.pages_succeeded == 0
        ):
            raise ValueError("partial OCR result requires successes and failures")
        if self.completeness is OCRCompleteness.FAILED and (
            not self.failures or self.pages_succeeded != 0
        ):
            raise ValueError("failed OCR result requires failures and no successful pages")
        if (
            self.completeness in {OCRCompleteness.FAILED, OCRCompleteness.UNAVAILABLE}
            and self.regions
        ):
            raise ValueError("failed or unavailable OCR result cannot publish regions")
        ordered = tuple(sorted(self.regions, key=lambda r: (r.page_number, r.order_index)))
        if (
            ordered != self.regions
            or len({(r.page_number, r.order_index) for r in self.regions}) != len(self.regions)
            or any(
                region.region_id
                != ocr_region_id(
                    derivation_id=self.derivation_id,
                    page_number=region.page_number,
                    order_index=region.order_index,
                    text=region.text,
                    bounding_box=region.bounding_box,
                )
                for region in self.regions
            )
        ):
            raise ValueError("OCR regions must be uniquely and deterministically ordered")
        require_sha256(self.content_hash, "content_hash")
        if self.content_hash != ocr_result_content_hash(
            self.regions,
            self.failures,
            self.completeness,
            self.languages,
            self.warnings,
        ):
            raise ValueError("content_hash does not match the complete OCR result")
        require_utc(self.created_at, "created_at")
        require_positive(self.schema_version, "schema_version")
        for warning in self.warnings:
            require_non_empty(warning, "warning")
            if _SAFE_CODE.fullmatch(warning) is None:
                raise ValueError("warnings must be bounded machine codes")

    @property
    def evidence_references(self) -> tuple[OCREvidenceReference, ...]:
        return tuple(
            OCREvidenceReference(
                document_id=self.document_id,
                version_id=self.version_id,
                occurrence_id=self.occurrence_id,
                asset_id=self.asset_id,
                derivation_id=self.derivation_id,
                region_id=region.region_id,
                page_number=region.page_number,
                bounding_box=region.bounding_box,
            )
            for region in self.regions
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRDerivation:
    derivation_id: UUID
    cache_key: str
    occurrence_id: UUID
    generation_id: UUID
    preprocessing_digest: str
    result_content_hash: str | None

    def __post_init__(self) -> None:
        for name in ("derivation_id", "occurrence_id", "generation_id"):
            require_uuid(getattr(self, name), name)
        require_sha256(self.cache_key, "cache_key")
        require_sha256(self.preprocessing_digest, "preprocessing_digest")
        if self.result_content_hash is not None:
            require_sha256(self.result_content_hash, "result_content_hash")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCREvidenceReference:
    """Citation-ready derived evidence that cannot masquerade as original text."""

    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    asset_id: UUID
    derivation_id: UUID
    region_id: UUID
    page_number: int
    bounding_box: BoundingBox | None
    evidence_kind: str = OCR_EVIDENCE_KIND

    def __post_init__(self) -> None:
        for name in (
            "document_id",
            "version_id",
            "occurrence_id",
            "asset_id",
            "derivation_id",
            "region_id",
        ):
            require_uuid(getattr(self, name), name)
        require_positive(self.page_number, "page_number")
        if self.bounding_box is not None:
            require_tuple(self.bounding_box, "bounding_box")
            if len(self.bounding_box) != 4:
                raise ValueError("bounding_box must contain four coordinates")
        if self.evidence_kind != OCR_EVIDENCE_KIND:
            raise ValueError("OCR evidence references must be labelled derived_ocr")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRPageSignal:
    page_number: int
    normalized_text_characters: int
    raster_coverage: float | None
    dominant_page_image: bool
    reliable_vector_text: bool
    supported: bool = True
    malformed: bool = False

    def __post_init__(self) -> None:
        require_positive(self.page_number, "page_number")
        require_non_negative(self.normalized_text_characters, "normalized_text_characters")
        if self.raster_coverage is not None:
            require_unit_interval(self.raster_coverage, "raster_coverage")
        for name in ("dominant_page_image", "reliable_vector_text", "supported", "malformed"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRPageDetection:
    page_number: int
    kind: OCRPageKind
    reason_code: str
    detector_version: str

    def __post_init__(self) -> None:
        require_positive(self.page_number, "page_number")
        require_enum(self.kind, OCRPageKind, "kind")
        require_non_empty(self.reason_code, "reason_code")
        require_non_empty(self.detector_version, "detector_version")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRDocumentDetection:
    status: OCRDocumentScanStatus
    pages: tuple[OCRPageDetection, ...]
    detector_version: str

    def __post_init__(self) -> None:
        require_enum(self.status, OCRDocumentScanStatus, "status")
        require_tuple(self.pages, "pages")
        require_non_empty(self.detector_version, "detector_version")


def ocr_result_content_hash(
    regions: tuple[OCRRegion, ...],
    failures: tuple[OCRFailure, ...] = (),
    completeness: OCRCompleteness = OCRCompleteness.COMPLETE,
    languages: tuple[OCRLanguageObservation, ...] = (),
    warnings: tuple[str, ...] = (),
) -> str:
    material = {
        "completeness": completeness.value,
        "regions": [
            {
                "region_id": str(region.region_id),
                "page_number": region.page_number,
                "order_index": region.order_index,
                "text": region.text,
                "bounding_box": region.bounding_box,
                "confidence": region.confidence.value,
                "language": None if region.language is None else region.language.language_code,
                "script": None if region.language is None else region.language.script,
            }
            for region in regions
        ],
        "failures": [
            {
                "page_number": failure.page_number,
                "classification": failure.classification.value,
                "reason_code": failure.reason_code,
                "retryable": failure.retryable,
            }
            for failure in failures
        ],
        "languages": [
            {
                "language_code": language.language_code,
                "script": language.script,
                "confidence": language.confidence.value,
                "mixed": language.mixed,
            }
            for language in languages
        ],
        "warnings": warnings,
    }
    return hashlib.sha256(_canonical_json(material)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
