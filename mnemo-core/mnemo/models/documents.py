"""Document parsing, metadata, identity, and version domain models."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from ._shared import (
    FrozenMetadata,
    identity_equal,
    require_date,
    require_enum,
    require_non_empty,
    require_optional_non_empty,
    require_positive,
    require_sha256,
    require_tuple,
    require_unique,
    require_utc,
    require_uuid,
)
from .blocks import Block, CaptionBlock


class DocType(StrEnum):
    """Supported semantic document classifications."""

    BOOK = "book"
    PAPER = "paper"
    CODE = "code"
    EMAIL = "email"
    RESUME = "resume"
    SLIDES = "slides"
    MARKDOWN = "markdown"
    DOCUMENTATION = "documentation"
    GENERIC = "generic"


class DocumentStatus(StrEnum):
    """Ingestion state of a document's current version."""

    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ENRICHED = "enriched"
    FAILED = "failed"


class DocumentVersionStatus(StrEnum):
    """Selection state of a retained document version."""

    CURRENT = "current"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentMetadata:
    """Descriptive and provenance metadata for exact document bytes."""

    content_hash: str
    title: str | None = None
    authors: tuple[str, ...] = ()
    publication_date: date | None = None
    url: str | None = None
    doi: str | None = None
    isbn: str | None = None
    page_count: int | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate document metadata."""
        require_sha256(self.content_hash, "content_hash")
        require_optional_non_empty(self.title, "title")
        require_tuple(self.authors, "authors")
        for author in self.authors:
            require_non_empty(author, "author")
        if any(not isinstance(author, str) for author in self.authors):
            raise TypeError("authors must contain strings")
        if self.publication_date is not None:
            require_date(self.publication_date, "publication_date")
        require_optional_non_empty(self.url, "url")
        require_optional_non_empty(self.doi, "doi")
        require_optional_non_empty(self.isbn, "isbn")
        if self.page_count is not None:
            require_positive(self.page_count, "page_count")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


@dataclass(frozen=True, slots=True, kw_only=True)
class ParsedDocument:
    """Ordered, typed parser output independent of storage."""

    blocks: tuple[Block, ...]
    metadata: DocumentMetadata
    language: str
    doc_type: DocType

    def __post_init__(self) -> None:
        """Validate parsed-document structure."""
        require_tuple(self.blocks, "blocks")
        if any(not isinstance(block, Block) for block in self.blocks):
            raise TypeError("blocks must contain Block instances")
        expected_ordinals = tuple(range(len(self.blocks)))
        actual_ordinals = tuple(block.ordinal for block in self.blocks)
        if actual_ordinals != expected_ordinals:
            raise ValueError("block ordinals must be contiguous and match sequence order")
        if not isinstance(self.metadata, DocumentMetadata):
            raise TypeError("metadata must be DocumentMetadata")
        require_non_empty(self.language, "language")
        require_enum(self.doc_type, DocType, "doc_type")
        if self.metadata.page_count is not None and any(
            block.page_number is not None and block.page_number > self.metadata.page_count
            for block in self.blocks
        ):
            raise ValueError("block page_number cannot exceed document page_count")
        for block in self.blocks:
            if (
                isinstance(block, CaptionBlock)
                and block.target_ordinal is not None
                and block.target_ordinal >= len(self.blocks)
            ):
                raise ValueError("caption target_ordinal must resolve within blocks")


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class DocumentVersion:
    """One immutable version of a stable logical document."""

    version_id: UUID
    document_id: UUID
    content_hash: str
    metadata: DocumentMetadata
    status: DocumentVersionStatus
    created_at: datetime

    def __post_init__(self) -> None:
        """Validate the document-version snapshot."""
        require_uuid(self.version_id, "version_id")
        require_uuid(self.document_id, "document_id")
        require_sha256(self.content_hash, "content_hash")
        if not isinstance(self.metadata, DocumentMetadata):
            raise TypeError("metadata must be DocumentMetadata")
        if self.content_hash != self.metadata.content_hash:
            raise ValueError("content_hash must match metadata.content_hash")
        require_enum(self.status, DocumentVersionStatus, "status")
        require_utc(self.created_at, "created_at")

    def __eq__(self, other: object) -> bool:
        """Compare document versions by stable version identity."""
        return identity_equal(
            self,
            other,
            DocumentVersion,
            self.version_id,
            getattr(other, "version_id", None),
        )

    def __hash__(self) -> int:
        """Hash the stable version identity."""
        return hash(self.version_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Document:
    """Stable registry record for a logical document across versions."""

    document_id: UUID
    versions: tuple[DocumentVersion, ...]
    current_version_id: UUID
    current_hash: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Validate the document registry aggregate."""
        require_uuid(self.document_id, "document_id")
        require_tuple(self.versions, "versions")
        if not self.versions:
            raise ValueError("versions must not be empty")
        if any(not isinstance(version, DocumentVersion) for version in self.versions):
            raise TypeError("versions must contain DocumentVersion instances")
        if any(version.document_id != self.document_id for version in self.versions):
            raise ValueError("all versions must belong to document_id")
        require_unique(tuple(version.version_id for version in self.versions), "version IDs")
        require_unique(tuple(version.content_hash for version in self.versions), "version hashes")
        current_versions = tuple(
            version for version in self.versions if version.status is DocumentVersionStatus.CURRENT
        )
        if len(current_versions) != 1:
            raise ValueError("exactly one document version must be current")
        require_uuid(self.current_version_id, "current_version_id")
        current = current_versions[0]
        if current.version_id != self.current_version_id:
            raise ValueError("current_version_id must identify the current version")
        require_sha256(self.current_hash, "current_hash")
        if current.content_hash != self.current_hash:
            raise ValueError("current_hash must match the current version")
        require_enum(self.status, DocumentStatus, "status")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        if self.created_at > self.updated_at:
            raise ValueError("created_at cannot be later than updated_at")

    def __eq__(self, other: object) -> bool:
        """Compare documents by stable logical identity."""
        return identity_equal(
            self,
            other,
            Document,
            self.document_id,
            getattr(other, "document_id", None),
        )

    def __hash__(self) -> int:
        """Hash the stable logical document identity."""
        return hash(self.document_id)
