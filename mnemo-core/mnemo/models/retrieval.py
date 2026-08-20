"""Retrieval result and metadata-filter domain models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._shared import require_finite, require_non_empty
from .chunks import Chunk
from .documents import DocType

MAX_SUBQUERIES = 16
MAX_SUBQUERY_RESULTS = 100


class RetrievalIntent(StrEnum):
    """Planner intents defined by the Phase 6 retrieval architecture."""

    FACTUAL = "factual"
    COMPARATIVE = "comparative"
    EXPLORATORY = "exploratory"
    SYNTHESIS = "synthesis"


class RetrievalMode(StrEnum):
    """Retrieval strategies that a planner may request without executing."""

    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"
    GRAPH = "graph"
    PARENT = "parent"


class RerankPolicy(StrEnum):
    """Applied Module 6.6 ranking policy."""

    CROSS_ENCODER = "cross_encoder"
    RRF_FALLBACK = "rrf_fallback"
    UNCHANGED_EMPTY = "unchanged_empty"


class RerankFallbackReason(StrEnum):
    """Allowed V1 reason for retaining the existing RRF order."""

    PROVIDER_UNAVAILABLE = "provider_unavailable"


class MetadataFilter(BaseModel):
    """Immutable validated hard constraints for retrieval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    notebook_id: UUID | None = None
    doc_types: tuple[DocType, ...] = ()
    date_after: date | None = None
    date_before: date | None = None
    source_ids: tuple[UUID, ...] = ()

    @field_validator("doc_types")
    @classmethod
    def _require_unique_doc_types(cls, value: tuple[DocType, ...]) -> tuple[DocType, ...]:
        if len(set(value)) != len(value):
            raise ValueError("doc_types must contain unique values")
        return value

    @field_validator("source_ids")
    @classmethod
    def _require_unique_source_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("source_ids must contain unique values")
        return value

    @model_validator(mode="after")
    def _require_ordered_dates(self) -> MetadataFilter:
        if (
            self.date_after is not None
            and self.date_before is not None
            and self.date_after > self.date_before
        ):
            raise ValueError("date_after cannot be later than date_before")
        return self


class SubQuery(BaseModel):
    """One bounded, validated retrieval operation in a retrieval plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_text: str
    retrieval_mode: RetrievalMode
    filters: MetadataFilter
    max_results: int = Field(strict=True, ge=1, le=MAX_SUBQUERY_RESULTS)

    @field_validator("query_text")
    @classmethod
    def _normalize_query_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("query_text must not be empty")
        return normalized


class RetrievalPlan(BaseModel):
    """A deterministic, serializable strategy produced by QueryPlanner."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: RetrievalIntent
    sub_queries: tuple[SubQuery, ...] = Field(
        min_length=1,
        max_length=MAX_SUBQUERIES,
    )
    requires_multi_hop: bool = Field(strict=True)
    requires_multi_doc: bool = Field(strict=True)

    @model_validator(mode="after")
    def _reject_duplicate_subqueries(self) -> RetrievalPlan:
        identities = tuple(
            (
                subquery.query_text.casefold(),
                subquery.retrieval_mode,
                subquery.filters,
            )
            for subquery in self.sub_queries
        )
        if len(set(identities)) != len(identities):
            raise ValueError("sub_queries must not contain semantic duplicates")
        return self


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoredChunk:
    """A chunk paired with one ranking source's raw score and rank."""

    chunk: Chunk
    score: float
    source: str
    rank: int

    def __post_init__(self) -> None:
        """Validate the raw retrieval result fields."""
        if not isinstance(self.chunk, Chunk):
            raise TypeError("chunk must be Chunk")
        require_finite(self.score, "score")
        require_non_empty(self.source, "source")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int):
            raise TypeError("rank must be an integer")
        if self.rank < 1:
            raise ValueError("rank must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalInvocationTrace:
    """Bounded raw and promoted evidence for one retriever invocation."""

    invocation_id: str
    subquery_index: int
    declared_mode: RetrievalMode
    effective_mode: RetrievalMode
    query_text: str
    filters: MetadataFilter
    requested_top_k: int
    raw_results: tuple[ScoredChunk, ...]
    promoted_results: tuple[ScoredChunk, ...]

    def __post_init__(self) -> None:
        """Validate deterministic invocation identity and bounded evidence."""
        require_non_empty(self.invocation_id, "invocation_id")
        if isinstance(self.subquery_index, bool) or not isinstance(self.subquery_index, int):
            raise TypeError("subquery_index must be an integer")
        if self.subquery_index < 1 or self.subquery_index > MAX_SUBQUERIES:
            raise ValueError("subquery_index must be from 1 through MAX_SUBQUERIES")
        if not isinstance(self.declared_mode, RetrievalMode):
            raise TypeError("declared_mode must be RetrievalMode")
        if self.effective_mode not in (RetrievalMode.DENSE, RetrievalMode.SPARSE):
            raise ValueError("effective_mode must be dense or sparse")
        expected_id = f"sq-{self.subquery_index}:{self.effective_mode.value}"
        if self.invocation_id != expected_id:
            raise ValueError("invocation_id does not match subquery identity")
        require_non_empty(self.query_text, "query_text")
        if not isinstance(self.filters, MetadataFilter):
            raise TypeError("filters must be MetadataFilter")
        if isinstance(self.requested_top_k, bool) or not isinstance(self.requested_top_k, int):
            raise TypeError("requested_top_k must be an integer")
        if self.requested_top_k < 1 or self.requested_top_k > MAX_SUBQUERY_RESULTS:
            raise ValueError("requested_top_k must be from 1 through MAX_SUBQUERY_RESULTS")
        for field_name, results in (
            ("raw_results", self.raw_results),
            ("promoted_results", self.promoted_results),
        ):
            if not isinstance(results, tuple):
                raise TypeError(f"{field_name} must be a tuple")
            if len(results) > self.requested_top_k:
                raise ValueError(f"{field_name} exceeds requested_top_k")
            if any(not isinstance(result, ScoredChunk) for result in results):
                raise TypeError(f"{field_name} must contain ScoredChunk values")


@dataclass(frozen=True, slots=True, kw_only=True)
class FusionEvidence:
    """One source-local rank contribution to a globally fused chunk."""

    invocation_id: str
    subquery_index: int
    declared_mode: RetrievalMode
    effective_mode: RetrievalMode
    result: ScoredChunk
    identity_introduced_by_parent_promotion: bool

    def __post_init__(self) -> None:
        """Validate traceable source-local evidence."""
        require_non_empty(self.invocation_id, "invocation_id")
        if isinstance(self.subquery_index, bool) or not isinstance(self.subquery_index, int):
            raise TypeError("subquery_index must be an integer")
        if self.subquery_index < 1 or self.subquery_index > MAX_SUBQUERIES:
            raise ValueError("subquery_index must be from 1 through MAX_SUBQUERIES")
        if not isinstance(self.declared_mode, RetrievalMode):
            raise TypeError("declared_mode must be RetrievalMode")
        if self.effective_mode not in (RetrievalMode.DENSE, RetrievalMode.SPARSE):
            raise ValueError("effective_mode must be dense or sparse")
        expected_id = f"sq-{self.subquery_index}:{self.effective_mode.value}"
        if self.invocation_id != expected_id:
            raise ValueError("invocation_id does not match evidence identity")
        if not isinstance(self.result, ScoredChunk):
            raise TypeError("result must be ScoredChunk")
        if not isinstance(self.identity_introduced_by_parent_promotion, bool):
            raise TypeError("identity_introduced_by_parent_promotion must be boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class FusedChunkResult:
    """One canonical chunk with RRF score, global rank, and raw evidence."""

    chunk: Chunk
    rrf_score: float
    global_rank: int
    evidence: tuple[FusionEvidence, ...]

    def __post_init__(self) -> None:
        """Validate a provenance-preserving fused candidate."""
        if not isinstance(self.chunk, Chunk):
            raise TypeError("chunk must be Chunk")
        require_finite(self.rrf_score, "rrf_score")
        if self.rrf_score <= 0:
            raise ValueError("rrf_score must be positive")
        if isinstance(self.global_rank, bool) or not isinstance(self.global_rank, int):
            raise TypeError("global_rank must be an integer")
        if self.global_rank < 1:
            raise ValueError("global_rank must be positive")
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be a tuple")
        if not self.evidence:
            raise ValueError("evidence must not be empty")
        if any(not isinstance(item, FusionEvidence) for item in self.evidence):
            raise TypeError("evidence must contain FusionEvidence values")
        if any(item.result.chunk.id != self.chunk.id for item in self.evidence):
            raise ValueError("evidence chunk identity must match fused chunk")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalFusionResult:
    """Deterministic bounded output of one Module 6.5 orchestration pass."""

    plan: RetrievalPlan
    invocations: tuple[RetrievalInvocationTrace, ...]
    results: tuple[FusedChunkResult, ...]

    def __post_init__(self) -> None:
        """Validate ordered invocation and global result records."""
        if not isinstance(self.plan, RetrievalPlan):
            raise TypeError("plan must be RetrievalPlan")
        if not isinstance(self.invocations, tuple):
            raise TypeError("invocations must be a tuple")
        if any(not isinstance(item, RetrievalInvocationTrace) for item in self.invocations):
            raise TypeError("invocations must contain RetrievalInvocationTrace values")
        invocation_ids = tuple(item.invocation_id for item in self.invocations)
        if len(set(invocation_ids)) != len(invocation_ids):
            raise ValueError("invocation identities must be unique")
        if not isinstance(self.results, tuple):
            raise TypeError("results must be a tuple")
        if len(self.results) > MAX_SUBQUERY_RESULTS:
            raise ValueError("results exceed the global result bound")
        if any(not isinstance(item, FusedChunkResult) for item in self.results):
            raise TypeError("results must contain FusedChunkResult values")
        expected_ranks = tuple(range(1, len(self.results) + 1))
        if tuple(item.global_rank for item in self.results) != expected_ranks:
            raise ValueError("global ranks must be contiguous and match tuple order")


def stable_sigmoid(value: float) -> float:
    """Return a numerically stable sigmoid for one finite raw logit."""
    require_finite(value, "raw_logit")
    if value >= 0:
        factor = math.exp(-value)
        return 1.0 / (1.0 + factor)
    factor = math.exp(value)
    return factor / (1.0 + factor)


@dataclass(frozen=True, slots=True, kw_only=True)
class CrossEncoderEvidence:
    """Query-transient cross-encoder evidence for one canonical chunk."""

    chunk_id: str
    raw_logit: float
    relevance_score: float
    below_relevance_threshold: bool
    model_id: str
    model_revision: str

    def __post_init__(self) -> None:
        """Validate the pinned score domain and threshold semantics."""
        from ._shared import require_sha256

        require_sha256(self.chunk_id, "chunk_id")
        require_finite(self.raw_logit, "raw_logit")
        require_finite(self.relevance_score, "relevance_score")
        if not 0.0 < self.relevance_score < 1.0:
            raise ValueError("relevance_score must be strictly between zero and one")
        expected = stable_sigmoid(self.raw_logit)
        if not math.isclose(
            self.relevance_score,
            expected,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise ValueError("relevance_score must equal sigmoid(raw_logit)")
        if not isinstance(self.below_relevance_threshold, bool):
            raise TypeError("below_relevance_threshold must be boolean")
        if self.below_relevance_threshold is not (self.relevance_score < 0.4):
            raise ValueError("below_relevance_threshold does not match the 0.4 threshold")
        require_non_empty(self.model_id, "model_id")
        require_non_empty(self.model_revision, "model_revision")


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankedChunkResult:
    """One fused candidate with separate cross-encoder evidence and rank."""

    fused_result: FusedChunkResult
    rerank_evidence: CrossEncoderEvidence | None
    reranked_rank: int

    def __post_init__(self) -> None:
        """Validate identity and the independent reranked rank."""
        if not isinstance(self.fused_result, FusedChunkResult):
            raise TypeError("fused_result must be FusedChunkResult")
        if self.rerank_evidence is not None:
            if not isinstance(self.rerank_evidence, CrossEncoderEvidence):
                raise TypeError("rerank_evidence must be CrossEncoderEvidence or None")
            if self.rerank_evidence.chunk_id != self.fused_result.chunk.id:
                raise ValueError("rerank evidence chunk identity must match fused result")
        if isinstance(self.reranked_rank, bool) or not isinstance(self.reranked_rank, int):
            raise TypeError("reranked_rank must be an integer")
        if self.reranked_rank < 1:
            raise ValueError("reranked_rank must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalRerankResult:
    """Canonical provenance-preserving Module 6.6 output."""

    query: str
    fusion_result: RetrievalFusionResult
    policy: RerankPolicy
    results: tuple[RerankedChunkResult, ...]
    fallback_reason: RerankFallbackReason | None = None

    def __post_init__(self) -> None:
        """Validate policy, cardinality, provenance, and deterministic order."""
        normalized = " ".join(self.query.split())
        if not normalized:
            raise ValueError("query must not be empty")
        if self.query != normalized:
            raise ValueError("query must be normalized")
        if not isinstance(self.fusion_result, RetrievalFusionResult):
            raise TypeError("fusion_result must be RetrievalFusionResult")
        if not isinstance(self.policy, RerankPolicy):
            raise TypeError("policy must be RerankPolicy")
        if not isinstance(self.results, tuple):
            raise TypeError("results must be a tuple")
        if any(not isinstance(item, RerankedChunkResult) for item in self.results):
            raise TypeError("results must contain RerankedChunkResult values")
        if len(self.results) != len(self.fusion_result.results):
            raise ValueError("reranking must preserve candidate cardinality")
        expected_ranks = tuple(range(1, len(self.results) + 1))
        if tuple(item.reranked_rank for item in self.results) != expected_ranks:
            raise ValueError("reranked ranks must be contiguous and match tuple order")
        original_by_id = {item.chunk.id: item for item in self.fusion_result.results}
        if {item.fused_result.chunk.id for item in self.results} != set(original_by_id):
            raise ValueError("reranking must preserve exact candidate identities")
        if any(
            item.fused_result is not original_by_id[item.fused_result.chunk.id]
            for item in self.results
        ):
            raise ValueError("reranking must retain original fused result objects")
        self._validate_policy()

    def _validate_policy(self) -> None:
        if self.policy is RerankPolicy.UNCHANGED_EMPTY:
            if self.results or self.fusion_result.results:
                raise ValueError("unchanged-empty policy requires empty candidates")
            if self.fallback_reason is not None:
                raise ValueError("unchanged-empty policy cannot have a fallback reason")
            return
        if not self.results:
            raise ValueError("non-empty rerank policy requires candidates")
        if self.policy is RerankPolicy.RRF_FALLBACK:
            if self.fallback_reason is not RerankFallbackReason.PROVIDER_UNAVAILABLE:
                raise ValueError("RRF fallback requires PROVIDER_UNAVAILABLE")
            if any(item.rerank_evidence is not None for item in self.results):
                raise ValueError("RRF fallback cannot contain cross-encoder evidence")
            if tuple(item.fused_result for item in self.results) != self.fusion_result.results:
                raise ValueError("RRF fallback must preserve the exact fusion order")
            if any(item.reranked_rank != item.fused_result.global_rank for item in self.results):
                raise ValueError("RRF fallback ranks must equal original global ranks")
            return
        if self.fallback_reason is not None:
            raise ValueError("cross-encoder policy cannot have a fallback reason")
        if any(item.rerank_evidence is None for item in self.results):
            raise ValueError("cross-encoder policy requires evidence for every candidate")
        expected = tuple(
            sorted(
                self.results,
                key=lambda item: (
                    -int(
                        bool(item.fused_result.chunk.metadata.get("retrieval_title_match", False))
                    ),
                    -_evidence(item).relevance_score,
                    item.fused_result.global_rank,
                    item.fused_result.chunk.id,
                ),
            )
        )
        if self.results != expected:
            raise ValueError("cross-encoder results are not deterministically ordered")
        identities = {
            (_evidence(item).model_id, _evidence(item).model_revision) for item in self.results
        }
        if len(identities) != 1:
            raise ValueError("cross-encoder evidence must use one model identity")


def _evidence(item: RerankedChunkResult) -> CrossEncoderEvidence:
    evidence = item.rerank_evidence
    if evidence is None:  # pragma: no cover - guarded by RetrievalRerankResult
        raise RuntimeError("cross-encoder evidence is unavailable")
    return evidence
