"""Transient transport models for parser outputs."""

from dataclasses import dataclass, field
from enum import StrEnum

from mnemo.models import (
    AssetExtractionProvenance,
    AssetLocator,
    DocType,
    DocumentMetadata,
)
from mnemo.models._shared import (
    BoundingBox,
    FrozenMetadata,
    require_finite,
    require_non_empty,
    require_non_negative,
    require_optional_non_empty,
    require_positive,
    require_tuple,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransientAsset:
    """Temporary in-memory asset extracted during parsing."""

    parser_local_id: str
    raw_bytes: bytes
    mime_type: str
    page_number: int | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.parser_local_id, "parser_local_id")
        if not isinstance(self.raw_bytes, bytes) or not self.raw_bytes:
            raise ValueError("raw_bytes must be non-empty bytes")
        require_non_empty(self.mime_type, "mime_type")
        if self.page_number is not None:
            require_positive(self.page_number, "page_number")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawBlock:
    """Abstract base for transient parser blocks."""

    ordinal: int
    page_number: int | None = None
    bounding_box: BoundingBox | None = None
    language: str | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        if type(self) is RawBlock:
            raise TypeError("RawBlock is abstract and cannot be instantiated directly")
        require_non_negative(self.ordinal, "ordinal")
        if self.page_number is not None:
            require_positive(self.page_number, "page_number")
        if self.bounding_box is not None:
            require_tuple(self.bounding_box, "bounding_box")
            if len(self.bounding_box) != 4:
                raise ValueError("bounding_box must contain four coordinates")
            x0, y0, x1, y1 = self.bounding_box
            for coordinate in self.bounding_box:
                require_finite(coordinate, "bounding_box coordinate")
            if x0 > x1 or y0 > y1:
                raise ValueError("bounding_box coordinates must be ordered")
            if self.page_number is None:
                raise ValueError("bounding_box requires page_number")
        require_optional_non_empty(self.language, "language")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawTextBlock(RawBlock):
    text: str

    def __post_init__(self) -> None:
        RawBlock.__post_init__(self)
        require_non_empty(self.text, "text")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawHeadingBlock(RawBlock):
    text: str
    level: int

    def __post_init__(self) -> None:
        RawBlock.__post_init__(self)
        require_non_empty(self.text, "text")
        require_positive(self.level, "level")
        if self.level > 6:
            raise ValueError("level must be between 1 and 6")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawListBlock(RawBlock):
    items: tuple[str, ...]

    def __post_init__(self) -> None:
        RawBlock.__post_init__(self)
        require_tuple(self.items, "items")
        if not self.items:
            raise ValueError("items must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawTableBlock(RawBlock):
    rows: tuple[tuple[str, ...], ...]
    header_row_count: int = 0

    def __post_init__(self) -> None:
        RawBlock.__post_init__(self)
        require_tuple(self.rows, "rows")
        if not self.rows or not self.rows[0]:
            raise ValueError("rows must contain at least one row and one column")
        width = len(self.rows[0])
        for row in self.rows:
            require_tuple(row, "row")
            if len(row) != width:
                raise ValueError("table rows must have equal width")
        require_non_negative(self.header_row_count, "header_row_count")
        if self.header_row_count > len(self.rows):
            raise ValueError("header_row_count cannot exceed row count")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawCodeBlock(RawBlock):
    code: str
    code_language: str | None = None

    def __post_init__(self) -> None:
        RawBlock.__post_init__(self)
        require_non_empty(self.code, "code")
        require_optional_non_empty(self.code_language, "code_language")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawMathBlock(RawBlock):
    latex: str
    display: bool = True

    def __post_init__(self) -> None:
        RawBlock.__post_init__(self)
        require_non_empty(self.latex, "latex")
        if not isinstance(self.display, bool):
            raise TypeError("display must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class RawImageBlock(RawBlock):
    parser_local_id: str
    alt_text: str | None = None

    def __post_init__(self) -> None:
        RawBlock.__post_init__(self)
        require_non_empty(self.parser_local_id, "parser_local_id")
        require_optional_non_empty(self.alt_text, "alt_text")


@dataclass(frozen=True, slots=True, kw_only=True)
class ParseResult:
    """Pure transformation output from a parser."""

    blocks: tuple[RawBlock, ...]
    extracted_assets: tuple[TransientAsset, ...]
    metadata: DocumentMetadata
    language: str
    doc_type: DocType

    def __post_init__(self) -> None:
        require_tuple(self.blocks, "blocks")
        for block in self.blocks:
            if not isinstance(block, RawBlock):
                raise TypeError("blocks must contain RawBlock instances")

        expected_ordinals = tuple(range(len(self.blocks)))
        actual_ordinals = tuple(b.ordinal for b in self.blocks)
        if actual_ordinals != expected_ordinals:
            raise ValueError("block ordinals must be contiguous and match sequence order")

        require_tuple(self.extracted_assets, "extracted_assets")
        for asset in self.extracted_assets:
            if not isinstance(asset, TransientAsset):
                raise TypeError("extracted_assets must contain TransientAsset instances")

        asset_ids = tuple(asset.parser_local_id for asset in self.extracted_assets)
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("extracted asset parser_local_id values must be unique")
        image_ids = {
            block.parser_local_id for block in self.blocks if isinstance(block, RawImageBlock)
        }
        if image_ids != set(asset_ids):
            raise ValueError(
                "RawImageBlock and TransientAsset parser_local_id values must correlate"
            )

        if not isinstance(self.metadata, DocumentMetadata):
            raise TypeError("metadata must be DocumentMetadata")
        require_non_empty(self.language, "language")
        if not isinstance(self.doc_type, DocType):
            raise TypeError("doc_type must be a DocType")


class AssetExtractionOutcome(StrEnum):
    """Auditable result of bounded parser-level asset discovery."""

    NO_ASSETS = "no_assets"
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    REJECTED = "rejected"


class AssetOmissionReason(StrEnum):
    """Stable reason codes for assets that could not be safely extracted."""

    CORRUPT_ASSET = "corrupt_asset"
    EXTERNAL_REFERENCE = "external_reference"
    LIMIT_EXCEEDED = "limit_exceeded"
    MALFORMED_RELATIONSHIP = "malformed_relationship"
    UNSUPPORTED_MEDIA = "unsupported_media"


@dataclass(frozen=True, slots=True, kw_only=True)
class TransientAssetOccurrence:
    """Pure parser observation correlated to one transient asset."""

    parser_local_id: str
    locator: AssetLocator
    authored_alt_text: str | None
    extraction_provenance: AssetExtractionProvenance

    def __post_init__(self) -> None:
        require_non_empty(self.parser_local_id, "parser_local_id")
        if not isinstance(self.locator, AssetLocator):
            raise TypeError("locator must be an AssetLocator")
        require_optional_non_empty(self.authored_alt_text, "authored_alt_text")
        if not isinstance(self.extraction_provenance, AssetExtractionProvenance):
            raise TypeError("extraction_provenance must be AssetExtractionProvenance")


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetExtractionOmission:
    """Typed, content-free evidence that one optional asset was omitted."""

    reason: AssetOmissionReason
    ordinal: int
    locator: AssetLocator | None = None
    relationship_id: str | None = None
    declared_media_type: str | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        if not isinstance(self.reason, AssetOmissionReason):
            raise TypeError("reason must be an AssetOmissionReason")
        require_non_negative(self.ordinal, "ordinal")
        if self.locator is not None and not isinstance(self.locator, AssetLocator):
            raise TypeError("locator must be an AssetLocator or None")
        require_optional_non_empty(self.relationship_id, "relationship_id")
        require_optional_non_empty(self.declared_media_type, "declared_media_type")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


@dataclass(frozen=True, slots=True, kw_only=True)
class ParseResultV2:
    """Additive parser transport retaining V1 text and typed asset provenance."""

    parse_result: ParseResult
    asset_occurrences: tuple[TransientAssetOccurrence, ...]
    omissions: tuple[AssetExtractionOmission, ...]
    outcome: AssetExtractionOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.parse_result, ParseResult):
            raise TypeError("parse_result must be a ParseResult")
        require_tuple(self.asset_occurrences, "asset_occurrences")
        require_tuple(self.omissions, "omissions")
        if any(not isinstance(item, TransientAssetOccurrence) for item in self.asset_occurrences):
            raise TypeError("asset_occurrences must contain TransientAssetOccurrence instances")
        if any(not isinstance(item, AssetExtractionOmission) for item in self.omissions):
            raise TypeError("omissions must contain AssetExtractionOmission instances")
        if not isinstance(self.outcome, AssetExtractionOutcome):
            raise TypeError("outcome must be an AssetExtractionOutcome")
        asset_ids = {asset.parser_local_id for asset in self.parse_result.extracted_assets}
        if any(item.parser_local_id not in asset_ids for item in self.asset_occurrences):
            raise ValueError("asset occurrence references an unknown transient asset")
        if self.outcome is AssetExtractionOutcome.COMPLETE and not self.asset_occurrences:
            raise ValueError("COMPLETE extraction requires at least one occurrence")
        if self.outcome is AssetExtractionOutcome.NO_ASSETS and (
            self.asset_occurrences or self.omissions
        ):
            raise ValueError("NO_ASSETS extraction cannot contain occurrences or omissions")
        if self.outcome is AssetExtractionOutcome.PARTIAL and (
            not self.asset_occurrences or not self.omissions
        ):
            raise ValueError("PARTIAL extraction requires occurrences and omissions")
        if self.outcome is AssetExtractionOutcome.REJECTED and not self.omissions:
            raise ValueError("REJECTED extraction requires at least one omission")
