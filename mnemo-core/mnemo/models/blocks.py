"""Immutable parsed-document block hierarchy."""

from dataclasses import dataclass, field
from uuid import UUID

from ._shared import (
    BoundingBox,
    FrozenMetadata,
    require_finite,
    require_non_empty,
    require_non_negative,
    require_optional_non_empty,
    require_positive,
    require_tuple,
    require_uuid,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Block:
    """Abstract common schema for ordered parsed-document blocks."""

    ordinal: int
    page_number: int | None = None
    bounding_box: BoundingBox | None = None
    language: str | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate common block fields and prohibit direct construction."""
        if type(self) is Block:
            raise TypeError("Block is abstract and cannot be instantiated directly")
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
class TextBlock(Block):
    """A prose or plain-text block."""

    text: str

    def __post_init__(self) -> None:
        Block.__post_init__(self)
        require_non_empty(self.text, "text")


@dataclass(frozen=True, slots=True, kw_only=True)
class HeadingBlock(Block):
    """A hierarchy-bearing heading block."""

    text: str
    level: int

    def __post_init__(self) -> None:
        Block.__post_init__(self)
        require_non_empty(self.text, "text")
        require_positive(self.level, "level")
        if self.level > 6:
            raise ValueError("level must be between 1 and 6")


@dataclass(frozen=True, slots=True, kw_only=True)
class TableBlock(Block):
    """A rectangular table with explicit header-row count."""

    rows: tuple[tuple[str, ...], ...]
    header_row_count: int = 0

    def __post_init__(self) -> None:
        Block.__post_init__(self)
        require_tuple(self.rows, "rows")
        if not self.rows or not self.rows[0]:
            raise ValueError("rows must contain at least one row and one column")
        width = len(self.rows[0])
        if any(not isinstance(row, tuple) for row in self.rows):
            raise TypeError("each table row must be a tuple")
        if any(len(row) != width for row in self.rows):
            raise ValueError("table rows must have equal width")
        if any(not isinstance(cell, str) for row in self.rows for cell in row):
            raise TypeError("table cells must be strings")
        require_non_negative(self.header_row_count, "header_row_count")
        if self.header_row_count > len(self.rows):
            raise ValueError("header_row_count cannot exceed row count")


@dataclass(frozen=True, slots=True, kw_only=True)
class ImageBlock(Block):
    """An image occurrence referencing a storage-independent asset."""

    asset_id: UUID
    alt_text: str | None = None

    def __post_init__(self) -> None:
        Block.__post_init__(self)
        require_uuid(self.asset_id, "asset_id")
        require_optional_non_empty(self.alt_text, "alt_text")


@dataclass(frozen=True, slots=True, kw_only=True)
class CodeBlock(Block):
    """A verbatim source-code block."""

    code: str
    code_language: str | None = None

    def __post_init__(self) -> None:
        Block.__post_init__(self)
        require_non_empty(self.code, "code")
        require_optional_non_empty(self.code_language, "code_language")


@dataclass(frozen=True, slots=True, kw_only=True)
class EquationBlock(Block):
    """A verbatim LaTeX mathematical expression."""

    latex: str
    display: bool = True

    def __post_init__(self) -> None:
        Block.__post_init__(self)
        require_non_empty(self.latex, "latex")
        if not isinstance(self.display, bool):
            raise TypeError("display must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptionBlock(Block):
    """A caption optionally targeting another block by ordinal."""

    text: str
    target_ordinal: int | None = None

    def __post_init__(self) -> None:
        Block.__post_init__(self)
        require_non_empty(self.text, "text")
        if self.target_ordinal is not None:
            require_non_negative(self.target_ordinal, "target_ordinal")
            if self.target_ordinal == self.ordinal:
                raise ValueError("target_ordinal cannot reference the caption itself")
