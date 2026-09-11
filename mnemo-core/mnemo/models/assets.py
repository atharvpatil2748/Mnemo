"""Binary asset and Phase 8.5 occurrence-provenance domain models."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from ._shared import (
    BoundingBox,
    FrozenMetadata,
    identity_equal,
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
)

_OCCURRENCE_NAMESPACE = UUID("7f000001-0000-4d6d-b000-000000000085")
_DERIVATION_NAMESPACE = UUID("7f000001-0000-4d6d-b000-000000000086")


class DocumentBinaryRole(StrEnum):
    """Role played by retained bytes for one exact document version."""

    ORIGINAL = "original"


class DocumentBinaryAvailability(StrEnum):
    """Whether authoritative original bytes are retained."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class AssetContainerKind(StrEnum):
    """Source container that owns an asset occurrence."""

    PDF = "pdf"
    PPTX = "pptx"
    DOCX = "docx"
    XLSX = "xlsx"
    MARKDOWN = "markdown"
    HTML = "html"
    STANDALONE = "standalone"
    OTHER = "other"


class AssetLocatorKind(StrEnum):
    """Discriminator for typed asset location data."""

    PDF_PAGE = "pdf_page"
    PPTX_SLIDE = "pptx_slide"
    DOCX_POSITION = "docx_position"
    XLSX_CELL = "xlsx_cell"
    DOM_POSITION = "dom_position"
    STANDALONE = "standalone"
    DOCUMENT_POSITION = "document_position"


class AssetDerivationStatus(StrEnum):
    """Lifecycle of an optional derived representation."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IndexGenerationState(StrEnum):
    """Lifecycle of an additive derived index generation."""

    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Asset:
    """Storage-independent metadata for an immutable local binary asset."""

    asset_id: UUID
    mime_type: str
    content_hash: str
    storage_uri: str
    width: int | None = None
    height: int | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate the asset snapshot."""
        require_uuid(self.asset_id, "asset_id")
        require_non_empty(self.mime_type, "mime_type")
        require_sha256(self.content_hash, "content_hash")
        require_non_empty(self.storage_uri, "storage_uri")
        if self.width is not None:
            require_positive(self.width, "width")
        if self.height is not None:
            require_positive(self.height, "height")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")

    def __eq__(self, other: object) -> bool:
        """Compare assets by stable identity."""
        return identity_equal(self, other, Asset, self.asset_id, getattr(other, "asset_id", None))

    def __hash__(self) -> int:
        """Hash the stable asset identity."""
        return hash(self.asset_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetLocator:
    """Strongly typed source position for one asset occurrence.

    ``geometry=None`` explicitly means that geometry is unavailable. The
    mandatory ordinal preserves source ordering without fabricating location
    data that a parser did not provide.
    """

    kind: AssetLocatorKind
    ordinal: int
    page_number: int | None = None
    slide_number: int | None = None
    section_path: tuple[str, ...] = ()
    inline_position: int | None = None
    sheet_name: str | None = None
    cell_reference: str | None = None
    dom_path: str | None = None
    geometry: BoundingBox | None = None

    def __post_init__(self) -> None:
        require_enum(self.kind, AssetLocatorKind, "kind")
        require_non_negative(self.ordinal, "ordinal")
        if self.page_number is not None:
            require_positive(self.page_number, "page_number")
        if self.slide_number is not None:
            require_positive(self.slide_number, "slide_number")
        require_tuple(self.section_path, "section_path")
        for section in self.section_path:
            require_non_empty(section, "section_path item")
        if self.inline_position is not None:
            require_non_negative(self.inline_position, "inline_position")
        require_optional_non_empty(self.sheet_name, "sheet_name")
        require_optional_non_empty(self.cell_reference, "cell_reference")
        require_optional_non_empty(self.dom_path, "dom_path")
        if self.geometry is not None:
            require_tuple(self.geometry, "geometry")
            if len(self.geometry) != 4:
                raise ValueError("geometry must contain four coordinates")
            x0, y0, x1, y1 = self.geometry
            for coordinate in self.geometry:
                require_finite(coordinate, "geometry coordinate")
            if x0 > x1 or y0 > y1:
                raise ValueError("geometry coordinates must be ordered")

        match self.kind:
            case AssetLocatorKind.PDF_PAGE:
                if self.page_number is None:
                    raise ValueError("PDF_PAGE locator requires page_number")
            case AssetLocatorKind.PPTX_SLIDE:
                if self.slide_number is None:
                    raise ValueError("PPTX_SLIDE locator requires slide_number")
            case AssetLocatorKind.DOCX_POSITION:
                if self.inline_position is None:
                    raise ValueError("DOCX_POSITION locator requires inline_position")
            case AssetLocatorKind.XLSX_CELL:
                if self.sheet_name is None:
                    raise ValueError("XLSX_CELL locator requires sheet_name")
            case AssetLocatorKind.DOM_POSITION:
                if self.dom_path is None:
                    raise ValueError("DOM_POSITION locator requires dom_path")
            case AssetLocatorKind.STANDALONE:
                if (
                    any(
                        value is not None
                        for value in (
                            self.page_number,
                            self.slide_number,
                            self.inline_position,
                            self.sheet_name,
                            self.cell_reference,
                            self.dom_path,
                            self.geometry,
                        )
                    )
                    or self.section_path
                ):
                    raise ValueError("STANDALONE locator cannot carry container coordinates")

    def to_payload(self) -> dict[str, object]:
        """Return deterministic JSON-compatible locator data."""
        return {
            "cell_reference": self.cell_reference,
            "dom_path": self.dom_path,
            "geometry": None if self.geometry is None else list(self.geometry),
            "inline_position": self.inline_position,
            "kind": self.kind.value,
            "ordinal": self.ordinal,
            "page_number": self.page_number,
            "section_path": list(self.section_path),
            "sheet_name": self.sheet_name,
            "slide_number": self.slide_number,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AssetLocator":
        """Reconstruct and validate a serialized locator."""
        geometry_value = payload.get("geometry")
        if geometry_value is None:
            geometry = None
        elif isinstance(geometry_value, list) and len(geometry_value) == 4:
            if not all(isinstance(item, (int, float)) for item in geometry_value):
                raise TypeError("geometry must contain numeric coordinates")
            geometry = (
                float(geometry_value[0]),
                float(geometry_value[1]),
                float(geometry_value[2]),
                float(geometry_value[3]),
            )
        else:
            raise TypeError("geometry must be null or a four-item list")
        section_value = payload.get("section_path", [])
        if not isinstance(section_value, list):
            raise TypeError("section_path must be a list")
        return cls(
            kind=AssetLocatorKind(str(payload["kind"])),
            ordinal=_required_int(payload["ordinal"], "ordinal"),
            page_number=_optional_int(payload.get("page_number")),
            slide_number=_optional_int(payload.get("slide_number")),
            section_path=tuple(str(item) for item in section_value),
            inline_position=_optional_int(payload.get("inline_position")),
            sheet_name=_optional_str(payload.get("sheet_name")),
            cell_reference=_optional_str(payload.get("cell_reference")),
            dom_path=_optional_str(payload.get("dom_path")),
            geometry=geometry,
        )

    def canonical_json(self) -> str:
        """Serialize with stable cross-process ordering."""
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetExtractionProvenance:
    """Exact parser observation that produced an occurrence."""

    parser_id: str
    parser_version: str
    parser_local_id: str | None = None
    block_ordinal: int | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        require_non_empty(self.parser_id, "parser_id")
        require_non_empty(self.parser_version, "parser_version")
        require_optional_non_empty(self.parser_local_id, "parser_local_id")
        if self.block_ordinal is not None:
            require_non_negative(self.block_ordinal, "block_ordinal")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentBinaryReference:
    """Authoritative original bytes retained for one exact document version."""

    document_id: UUID
    version_id: UUID
    asset_id: UUID
    role: DocumentBinaryRole
    media_type: str
    byte_size: int
    created_at: datetime

    def __post_init__(self) -> None:
        require_uuid(self.document_id, "document_id")
        require_uuid(self.version_id, "version_id")
        require_uuid(self.asset_id, "asset_id")
        require_enum(self.role, DocumentBinaryRole, "role")
        require_non_empty(self.media_type, "media_type")
        require_positive(self.byte_size, "byte_size")
        require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class AssetOccurrence:
    """One logical appearance of immutable asset bytes in an exact version."""

    occurrence_id: UUID
    asset_id: UUID
    document_id: UUID
    version_id: UUID
    container_kind: AssetContainerKind
    locator: AssetLocator
    authored_alt_text: str | None
    extraction_provenance: AssetExtractionProvenance
    created_at: datetime

    def __post_init__(self) -> None:
        require_uuid(self.occurrence_id, "occurrence_id")
        require_uuid(self.asset_id, "asset_id")
        require_uuid(self.document_id, "document_id")
        require_uuid(self.version_id, "version_id")
        require_enum(self.container_kind, AssetContainerKind, "container_kind")
        if not isinstance(self.locator, AssetLocator):
            raise TypeError("locator must be an AssetLocator")
        require_optional_non_empty(self.authored_alt_text, "authored_alt_text")
        if not isinstance(self.extraction_provenance, AssetExtractionProvenance):
            raise TypeError("extraction_provenance must be AssetExtractionProvenance")
        require_utc(self.created_at, "created_at")

    def __eq__(self, other: object) -> bool:
        return identity_equal(
            self,
            other,
            AssetOccurrence,
            self.occurrence_id,
            getattr(other, "occurrence_id", None),
        )

    def __hash__(self) -> int:
        return hash(self.occurrence_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class AssetDerivation:
    """Versioned provenance for optional processing of one occurrence."""

    derivation_id: UUID
    occurrence_id: UUID
    operation: str
    provider_identity: str
    model_identity: str
    configuration_digest: str
    output_asset_id: UUID | None
    output_payload: FrozenMetadata
    status: AssetDerivationStatus
    confidence: float | None
    language: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        require_uuid(self.derivation_id, "derivation_id")
        require_uuid(self.occurrence_id, "occurrence_id")
        require_non_empty(self.operation, "operation")
        require_non_empty(self.provider_identity, "provider_identity")
        require_non_empty(self.model_identity, "model_identity")
        require_sha256(self.configuration_digest, "configuration_digest")
        if self.output_asset_id is not None:
            require_uuid(self.output_asset_id, "output_asset_id")
        if not isinstance(self.output_payload, FrozenMetadata):
            raise TypeError("output_payload must be FrozenMetadata")
        require_enum(self.status, AssetDerivationStatus, "status")
        if self.confidence is not None:
            require_unit_interval(self.confidence, "confidence")
        require_optional_non_empty(self.language, "language")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")

    def __eq__(self, other: object) -> bool:
        return identity_equal(
            self,
            other,
            AssetDerivation,
            self.derivation_id,
            getattr(other, "derivation_id", None),
        )

    def __hash__(self) -> int:
        return hash(self.derivation_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class IndexGeneration:
    """Immutable identity and mutable lifecycle snapshot for a derived index."""

    generation_id: UUID
    capability: str
    profile: str
    schema_version: int
    input_scope: str
    provider_identity: str | None
    model_identity: str | None
    configuration_digest: str
    dimensions: int | None
    state: IndexGenerationState
    item_count: int
    checksum: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        require_uuid(self.generation_id, "generation_id")
        require_non_empty(self.capability, "capability")
        require_non_empty(self.profile, "profile")
        require_positive(self.schema_version, "schema_version")
        require_non_empty(self.input_scope, "input_scope")
        require_optional_non_empty(self.provider_identity, "provider_identity")
        require_optional_non_empty(self.model_identity, "model_identity")
        require_sha256(self.configuration_digest, "configuration_digest")
        if self.dimensions is not None:
            require_positive(self.dimensions, "dimensions")
        require_enum(self.state, IndexGenerationState, "state")
        require_non_negative(self.item_count, "item_count")
        if self.checksum is not None:
            require_sha256(self.checksum, "checksum")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")

    def __eq__(self, other: object) -> bool:
        return identity_equal(
            self,
            other,
            IndexGeneration,
            self.generation_id,
            getattr(other, "generation_id", None),
        )

    def __hash__(self) -> int:
        return hash(self.generation_id)


def asset_occurrence_id(
    *,
    document_id: UUID,
    version_id: UUID,
    asset_id: UUID,
    locator: AssetLocator,
) -> UUID:
    """Derive a deterministic occurrence identity from exact provenance."""
    require_uuid(document_id, "document_id")
    require_uuid(version_id, "version_id")
    require_uuid(asset_id, "asset_id")
    if not isinstance(locator, AssetLocator):
        raise TypeError("locator must be an AssetLocator")
    logical = json.dumps(
        {
            "asset_id": str(asset_id),
            "document_id": str(document_id),
            "locator": locator.to_payload(),
            "version_id": str(version_id),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid5(_OCCURRENCE_NAMESPACE, logical)


def asset_derivation_id(
    *,
    occurrence_id: UUID,
    operation: str,
    provider_identity: str,
    model_identity: str,
    configuration_digest: str,
) -> UUID:
    """Derive the idempotency identity for one logical derived operation."""
    require_uuid(occurrence_id, "occurrence_id")
    require_non_empty(operation, "operation")
    require_non_empty(provider_identity, "provider_identity")
    require_non_empty(model_identity, "model_identity")
    require_sha256(configuration_digest, "configuration_digest")
    logical = json.dumps(
        {
            "configuration_digest": configuration_digest,
            "model_identity": model_identity,
            "occurrence_id": str(occurrence_id),
            "operation": operation,
            "provider_identity": provider_identity,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid5(_DERIVATION_NAMESPACE, logical)


def _optional_int(value: object) -> int | None:
    return None if value is None else _required_int(value, "integer field")


def _required_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
