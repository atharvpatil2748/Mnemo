"""Immutable value records used directly by Module 1.2 contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from mnemo.models import DocType, FrozenMetadata, JSONValue
from mnemo.models._shared import (
    require_finite,
    require_non_empty,
    require_non_negative,
    require_optional_non_empty,
    require_positive,
    require_sha256,
    require_tuple,
    require_unique,
    require_utc,
)

type EmbeddingVector = tuple[float, ...]

_CAPABILITY_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")


class _Unset:
    __slots__ = ()


_UNSET = _Unset()
_EMPTY_METADATA = FrozenMetadata()


@dataclass(frozen=True, slots=True, kw_only=True)
class FileMetadata:
    """Caller-known immutable facts supplied to a parser."""

    content_hash: str
    size_bytes: int
    mime_type: str | None = None
    modified_at: datetime | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate file metadata invariants."""
        require_sha256(self.content_hash, "content_hash")
        require_non_negative(self.size_bytes, "size_bytes")
        require_optional_non_empty(self.mime_type, "mime_type")
        if self.modified_at is not None:
            require_utc(self.modified_at, "modified_at")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


@dataclass(frozen=True, slots=True, kw_only=True)
class ChunkingOptions:
    """Immutable limits controlling one chunking operation."""

    target_tokens: int
    max_tokens: int
    overlap_tokens: int = 0
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate chunking limits."""
        require_positive(self.target_tokens, "target_tokens")
        require_positive(self.max_tokens, "max_tokens")
        require_non_negative(self.overlap_tokens, "overlap_tokens")
        if self.target_tokens > self.max_tokens:
            raise ValueError("target_tokens must not exceed max_tokens")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingBatch:
    """Ordered embedding-provider output with model identity."""

    vectors: tuple[EmbeddingVector, ...]
    model_name: str
    dimensions: int

    def __post_init__(self) -> None:
        """Validate vector dimensions and numeric values."""
        require_tuple(self.vectors, "vectors")
        if not self.vectors:
            raise ValueError("vectors must not be empty")
        require_non_empty(self.model_name, "model_name")
        require_positive(self.dimensions, "dimensions")
        for vector in self.vectors:
            require_tuple(vector, "embedding vector")
            if len(vector) != self.dimensions:
                raise ValueError("embedding vector has unexpected dimensions")
            for component in vector:
                require_finite(component, "embedding component")


@dataclass(frozen=True, slots=True, kw_only=True)
class HealthStatus:
    """Transport-independent component health observation."""

    healthy: bool
    component: str
    checked_at: datetime
    detail: str | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate health observation fields."""
        if not isinstance(self.healthy, bool):
            raise TypeError("healthy must be a boolean")
        require_non_empty(self.component, "component")
        require_utc(self.checked_at, "checked_at")
        require_optional_non_empty(self.detail, "detail")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


class MessageRole(StrEnum):
    """Language-model message roles permitted by Mnemo."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True, kw_only=True)
class Message:
    """A transport-independent language-model input message."""

    role: MessageRole
    content: str
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate message fields."""
        if not isinstance(self.role, MessageRole):
            raise TypeError("role must be MessageRole")
        require_non_empty(self.content, "content")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class CompletionResult:
    """A completed text or structured language-model response."""

    model: str
    text: str | None = None
    structured: JSONValue = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __init__(
        self,
        *,
        model: str,
        text: str | None = None,
        structured: JSONValue | _Unset = _UNSET,
        metadata: FrozenMetadata = _EMPTY_METADATA,
    ) -> None:
        """Create exactly one text or explicitly supplied structured result."""
        require_non_empty(model, "model")
        structured_supplied = not isinstance(structured, _Unset)
        if (text is None) == (not structured_supplied):
            raise ValueError("exactly one of text or structured must be present")
        if text is not None:
            require_non_empty(text, "text")
        if not isinstance(metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "text", text)
        object.__setattr__(
            self,
            "structured",
            None if not structured_supplied else structured,
        )
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class ParserCapabilities:
    """Descriptive capabilities of a parser implementation."""

    supported_formats: tuple[str, ...]
    supports_tables: bool
    supports_images: bool
    supports_math: bool
    supports_ocr: bool
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate parser capability metadata."""
        _validate_string_capabilities(self.supported_formats, "supported_formats")
        _validate_booleans(
            self.supports_tables,
            self.supports_images,
            self.supports_math,
            self.supports_ocr,
        )
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChunkerCapabilities:
    """Descriptive capabilities of a chunker implementation."""

    supported_doc_types: tuple[DocType, ...]
    preserves_semantic_boundaries: bool
    supports_parent_child: bool
    supports_overlap: bool
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate chunker capability metadata."""
        require_tuple(self.supported_doc_types, "supported_doc_types")
        if not self.supported_doc_types:
            raise ValueError("supported_doc_types must not be empty")
        if not all(isinstance(item, DocType) for item in self.supported_doc_types):
            raise TypeError("supported_doc_types entries must be DocType")
        require_unique(self.supported_doc_types, "supported_doc_types")
        _validate_booleans(
            self.preserves_semantic_boundaries,
            self.supports_parent_child,
            self.supports_overlap,
        )
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingCapabilities:
    """Descriptive capabilities of an embedding provider."""

    dimensions: int
    supports_batch: bool
    max_batch: int
    multilingual: bool
    supports_normalization: bool
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate embedding capability metadata."""
        require_positive(self.dimensions, "dimensions")
        require_positive(self.max_batch, "max_batch")
        _validate_booleans(
            self.supports_batch,
            self.multilingual,
            self.supports_normalization,
        )
        if not self.supports_batch and self.max_batch != 1:
            raise ValueError("max_batch must be 1 when batching is unsupported")
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrieverCapabilities:
    """Descriptive capabilities of a retriever implementation."""

    supports_hybrid: bool
    supports_metadata_filters: bool
    supports_parent_child: bool
    supports_reranking: bool
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate retriever capability metadata."""
        _validate_booleans(
            self.supports_hybrid,
            self.supports_metadata_filters,
            self.supports_parent_child,
            self.supports_reranking,
        )
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankerCapabilities:
    """Descriptive capabilities of a reranker implementation."""

    supports_cross_encoder: bool
    supports_batch: bool
    preserves_raw_scores: bool
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate reranker capability metadata."""
        _validate_booleans(
            self.supports_cross_encoder,
            self.supports_batch,
            self.preserves_raw_scores,
        )
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCapabilities:
    """Descriptive capabilities of a language-model provider."""

    supports_streaming: bool
    supports_json: bool
    supports_vision: bool
    supports_reasoning: bool
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate language-model capability metadata."""
        _validate_booleans(
            self.supports_streaming,
            self.supports_json,
            self.supports_vision,
            self.supports_reasoning,
        )
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class StorageCapabilities:
    """Descriptive capabilities configured behind the atomic storage facade."""

    supports_blobs: bool
    supports_dense_search: bool
    supports_sparse_search: bool
    supports_metadata: bool
    supports_graph: bool
    supports_transactions: bool
    supports_health_checks: bool
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate storage capability metadata."""
        _validate_booleans(
            self.supports_blobs,
            self.supports_dense_search,
            self.supports_sparse_search,
            self.supports_metadata,
            self.supports_graph,
            self.supports_transactions,
            self.supports_health_checks,
        )
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class Page[T]:
    """An immutable, cursor-paginated repository result."""

    items: tuple[T, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        """Validate immutable page fields."""
        require_tuple(self.items, "items")
        require_optional_non_empty(self.next_cursor, "next_cursor")


def _validate_string_capabilities(values: tuple[str, ...], field_name: str) -> None:
    require_tuple(values, field_name)
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    for value in values:
        require_non_empty(value, f"{field_name} entry")
    require_unique(values, field_name)


def _validate_booleans(*values: bool) -> None:
    if not all(isinstance(value, bool) for value in values):
        raise TypeError("capability flags must be booleans")


def _validate_metadata(metadata: FrozenMetadata) -> None:
    if not isinstance(metadata, FrozenMetadata):
        raise TypeError("metadata must be FrozenMetadata")
    for key in metadata:
        if _CAPABILITY_KEY_PATTERN.fullmatch(key) is None:
            raise ValueError("capability extension metadata keys must be namespaced")
