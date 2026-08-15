"""Immutable Module 6.7 context-construction records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from ._shared import require_non_empty, require_positive, require_uuid
from .retrieval import RerankedChunkResult, RetrievalRerankResult


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentContextLabel:
    """Caller-supplied display title for one exact document version."""

    document_id: UUID
    version_id: UUID
    title: str

    def __post_init__(self) -> None:
        require_uuid(self.document_id, "document_id")
        require_uuid(self.version_id, "version_id")
        require_non_empty(self.title, "title")


class ContextItemKind(StrEnum):
    """Permitted representations of one selected context candidate."""

    VERBATIM = "verbatim"
    COMPRESSED = "compressed"


@dataclass(frozen=True, slots=True, kw_only=True)
class CompressionEvidence:
    """Query-transient Extractor evidence for compressed context."""

    extractor_provider: str
    extractor_model: str
    target_tokens: int = 100
    hard_max_tokens: int = 120
    compressed_token_count: int

    def __post_init__(self) -> None:
        require_non_empty(self.extractor_provider, "extractor_provider")
        require_non_empty(self.extractor_model, "extractor_model")
        if self.target_tokens != 100:
            raise ValueError("target_tokens must be 100")
        if self.hard_max_tokens != 120:
            raise ValueError("hard_max_tokens must be 120")
        require_positive(self.compressed_token_count, "compressed_token_count")
        if self.compressed_token_count > self.hard_max_tokens:
            raise ValueError("compressed_token_count exceeds hard_max_tokens")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextItem:
    """One rendered context item retaining its exact reranking record."""

    source_number: int
    reranked_result: RerankedChunkResult
    kind: ContextItemKind
    content: str
    content_token_count: int
    rendered_text: str
    rendered_token_count: int
    compression_evidence: CompressionEvidence | None = None

    def __post_init__(self) -> None:
        require_positive(self.source_number, "source_number")
        if not isinstance(self.reranked_result, RerankedChunkResult):
            raise TypeError("reranked_result must be RerankedChunkResult")
        if not isinstance(self.kind, ContextItemKind):
            raise TypeError("kind must be ContextItemKind")
        require_non_empty(self.content, "content")
        require_positive(self.content_token_count, "content_token_count")
        require_non_empty(self.rendered_text, "rendered_text")
        require_positive(self.rendered_token_count, "rendered_token_count")
        if self.kind is ContextItemKind.VERBATIM:
            if self.content != self.reranked_result.fused_result.chunk.text:
                raise ValueError("verbatim content must equal canonical chunk text")
            if self.compression_evidence is not None:
                raise ValueError("verbatim context cannot contain compression evidence")
        elif not isinstance(self.compression_evidence, CompressionEvidence):
            raise ValueError("compressed context requires compression evidence")


class ContextEmptyReason(StrEnum):
    """Typed valid reasons for an empty context result."""

    NO_CANDIDATES = "no_candidates"
    FIXED_OVERHEAD_EXHAUSTED = "fixed_overhead_exhausted"
    VERBATIM_PREFIX_DOES_NOT_FIT = "verbatim_prefix_does_not_fit"
    NO_ITEM_FITS = "no_item_fits"


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextBuildResult:
    """Canonical provenance-preserving Module 6.7 output."""

    rerank_result: RetrievalRerankResult
    tokenizer_id: str
    context_budget: int
    fixed_overhead_tokens: int
    available_context_tokens: int
    context_tokens: int
    rendered_context: str
    items: tuple[ContextItem, ...]
    omitted_results: tuple[RerankedChunkResult, ...]
    compression_available: bool
    empty_reason: ContextEmptyReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rerank_result, RetrievalRerankResult):
            raise TypeError("rerank_result must be RetrievalRerankResult")
        require_non_empty(self.tokenizer_id, "tokenizer_id")
        if isinstance(self.context_budget, bool) or not isinstance(self.context_budget, int):
            raise TypeError("context_budget must be an integer")
        if not 1 <= self.context_budget <= 1_000_000:
            raise ValueError("context_budget must be from 1 through 1000000")
        for name, value in (
            ("fixed_overhead_tokens", self.fixed_overhead_tokens),
            ("available_context_tokens", self.available_context_tokens),
            ("context_tokens", self.context_tokens),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.available_context_tokens != max(
            0, self.context_budget - self.fixed_overhead_tokens
        ):
            raise ValueError("available_context_tokens does not match the fixed overhead")
        if self.context_tokens > self.available_context_tokens:
            raise ValueError("context_tokens exceeds available_context_tokens")
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, ContextItem) for item in self.items
        ):
            raise TypeError("items must be a tuple of ContextItem values")
        if not isinstance(self.omitted_results, tuple) or any(
            not isinstance(item, RerankedChunkResult) for item in self.omitted_results
        ):
            raise TypeError("omitted_results must contain RerankedChunkResult values")
        if not isinstance(self.compression_available, bool):
            raise TypeError("compression_available must be boolean")
        if tuple(item.source_number for item in self.items) != tuple(range(1, len(self.items) + 1)):
            raise ValueError("source numbers must be contiguous and match item order")
        if self.rendered_context != "\n\n".join(item.rendered_text for item in self.items):
            raise ValueError("rendered_context does not match context items")
        selected = tuple(item.reranked_result for item in self.items)
        input_by_identity = {id(item): item for item in self.rerank_result.results}
        partition = selected + self.omitted_results
        if len(partition) != len(self.rerank_result.results) or {
            id(item) for item in partition
        } != set(input_by_identity):
            raise ValueError("selected and omitted results must partition input identities")
        if any(item is not input_by_identity.get(id(item)) for item in partition):
            raise ValueError("context result must retain original reranked result objects")
        if self.items:
            if self.empty_reason is not None:
                raise ValueError("non-empty context cannot have an empty reason")
        else:
            if not isinstance(self.empty_reason, ContextEmptyReason):
                raise ValueError("empty context requires an empty reason")
            if self.rendered_context or self.context_tokens:
                raise ValueError("empty context cannot contain rendered tokens")
