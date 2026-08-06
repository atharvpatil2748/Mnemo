"""Immutable chunk domain models."""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from ._shared import (
    FrozenMetadata,
    identity_equal,
    require_enum,
    require_finite,
    require_non_empty,
    require_non_negative,
    require_positive,
    require_sha256,
    require_tuple,
    require_unique,
    require_uuid,
)


class ChunkType(StrEnum):
    """Supported semantic chunk roles."""

    PASSAGE = "passage"
    SUMMARY = "summary"
    VERBATIM = "verbatim"
    QUESTION = "question"
    CODE = "code"
    CAPTION = "caption"
    EQUATION = "equation"


@dataclass(frozen=True, slots=True, kw_only=True)
class ChunkPosition:
    """Navigation coordinates for a chunk within canonical extracted text."""

    section_index: int
    chunk_index_in_section: int
    page_number: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None

    def __post_init__(self) -> None:
        """Validate chunk navigation coordinates."""
        require_non_negative(self.section_index, "section_index")
        require_non_negative(self.chunk_index_in_section, "chunk_index_in_section")
        if self.page_number is not None:
            require_positive(self.page_number, "page_number")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must both be null or present")
        if self.start_offset is not None and self.end_offset is not None:
            require_non_negative(self.start_offset, "start_offset")
            require_non_negative(self.end_offset, "end_offset")
            if self.start_offset >= self.end_offset:
                raise ValueError("start_offset must be less than end_offset")


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Chunk:
    """A self-contained semantic retrieval unit from one document version."""

    id: str
    text: str
    document_id: UUID
    version_id: UUID
    chunk_type: ChunkType
    position: ChunkPosition
    heading_path: tuple[str, ...]
    parent_chunk_id: str | None = None
    sibling_ids: tuple[str, ...] = ()
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)
    embedding: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        """Validate the immutable chunk snapshot."""
        require_sha256(self.id, "id")
        require_non_empty(self.text, "text")
        require_uuid(self.document_id, "document_id")
        require_uuid(self.version_id, "version_id")
        require_enum(self.chunk_type, ChunkType, "chunk_type")
        if not isinstance(self.position, ChunkPosition):
            raise TypeError("position must be ChunkPosition")
        require_tuple(self.heading_path, "heading_path")
        for heading in self.heading_path:
            require_non_empty(heading, "heading_path entry")
        if self.parent_chunk_id is not None:
            require_sha256(self.parent_chunk_id, "parent_chunk_id")
            if self.parent_chunk_id == self.id:
                raise ValueError("parent_chunk_id cannot reference the chunk itself")
        require_tuple(self.sibling_ids, "sibling_ids")
        for sibling_id in self.sibling_ids:
            require_sha256(sibling_id, "sibling_id")
            if sibling_id == self.id:
                raise ValueError("sibling_ids cannot contain the chunk itself")
        require_unique(self.sibling_ids, "sibling_ids")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")
        if self.embedding is not None:
            require_tuple(self.embedding, "embedding")
            if not self.embedding:
                raise ValueError("embedding must not be empty when present")
            for component in self.embedding:
                require_finite(component, "embedding component")

    def __eq__(self, other: object) -> bool:
        """Compare chunks by their stable content-derived identity."""
        return identity_equal(self, other, Chunk, self.id, getattr(other, "id", None))

    def __hash__(self) -> int:
        """Hash the stable chunk identity."""
        return hash(self.id)
