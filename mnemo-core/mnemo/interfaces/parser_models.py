"""Transient transport models for parser outputs."""

from dataclasses import dataclass, field

from mnemo.models import DocType, DocumentMetadata
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
