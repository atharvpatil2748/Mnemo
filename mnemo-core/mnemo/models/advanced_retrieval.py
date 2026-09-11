"""Additive Phase 8.5.6 advanced retrieval and completeness contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._shared import FrozenMetadata, require_finite, require_non_empty, require_sha256
from .chunks import Chunk

ADVANCED_RETRIEVAL_VERSION = "retrieval-plan-v2/1"
_CANDIDATE_NAMESPACE = UUID("42b5d918-dbcf-55d5-ac29-63a9d541f8c1")


class AdvancedRetrievalMode(StrEnum):
    RANKED = "ranked"
    EXHAUSTIVE = "exhaustive"


class EvidenceRepresentation(StrEnum):
    CANONICAL_TEXT = "canonical_text"
    TITLE_METADATA = "title_metadata"
    OCR_TEXT = "ocr_text"
    VISION_ANALYSIS = "vision_analysis"
    VISUAL_VECTOR = "visual_vector"
    ASSET_METADATA = "asset_metadata"
    MULTILINGUAL_TEXT = "multilingual_text"
    POSITIONAL_METADATA = "positional_metadata"


class RetrievalCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"
    EMPTY = "empty"


class RepresentationSearchStatus(StrEnum):
    SEARCHED = "searched"
    UNAVAILABLE = "unavailable"
    OMITTED = "omitted"
    FAILED = "failed"


class DeduplicationPolicy(StrEnum):
    AUTHORITATIVE_IDENTITY = "authoritative_identity"


class ExpansionPolicy(StrEnum):
    NONE = "none"
    ADJACENT = "adjacent"
    PARENT_AND_ADJACENT = "parent_and_adjacent"


class RankingPolicyV2(StrEnum):
    SOURCE_RANK_FUSION = "source_rank_fusion"
    DETERMINISTIC_STORAGE_ORDER = "deterministic_storage_order"


class RetrievalScopeV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    notebook_id: UUID
    source_ids: tuple[UUID, ...] = ()
    document_ids: tuple[UUID, ...] = ()
    version_ids: tuple[UUID, ...] = ()

    @field_validator("source_ids", "document_ids", "version_ids")
    @classmethod
    def _unique_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("scope identities must be unique")
        return value


class PositionalScopeV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page_start: int | None = Field(default=None, strict=True, ge=1)
    page_end: int | None = Field(default=None, strict=True, ge=1)
    section_indexes: tuple[int, ...] = ()
    heading_prefix: tuple[str, ...] = ()

    @field_validator("section_indexes")
    @classmethod
    def _unique_sections(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(isinstance(item, bool) or item < 0 for item in value):
            raise ValueError("section indexes must be non-negative integers")
        if len(value) != len(set(value)):
            raise ValueError("section indexes must be unique")
        return value

    @field_validator("heading_prefix")
    @classmethod
    def _headings_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("heading prefix entries must not be empty")
        return value

    @model_validator(mode="after")
    def _ordered_pages(self) -> PositionalScopeV2:
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_start > self.page_end
        ):
            raise ValueError("page_start cannot exceed page_end")
        return self


class RetrievalBudgetsV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recall_limit: int = Field(strict=True, ge=1, le=1000)
    expansion_limit: int = Field(strict=True, ge=0, le=500)
    fusion_limit: int = Field(strict=True, ge=1, le=500)
    rerank_limit: int = Field(strict=True, ge=1, le=200)
    result_limit: int = Field(strict=True, ge=1, le=200)
    max_serialized_bytes: int = Field(strict=True, ge=256, le=10_000_000)
    max_content_characters: int = Field(strict=True, ge=1, le=2_000_000)

    @model_validator(mode="after")
    def _ordered_pipeline(self) -> RetrievalBudgetsV2:
        if self.fusion_limit > self.recall_limit + self.expansion_limit:
            raise ValueError("fusion_limit exceeds possible recalled and expanded candidates")
        if self.rerank_limit > self.fusion_limit:
            raise ValueError("rerank_limit cannot exceed fusion_limit")
        if self.result_limit > self.rerank_limit:
            raise ValueError("result_limit cannot exceed rerank_limit")
        return self


class RetrievalPlanV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    mode: AdvancedRetrievalMode
    scope: RetrievalScopeV2
    position: PositionalScopeV2 = PositionalScopeV2()
    representations: tuple[EvidenceRepresentation, ...]
    budgets: RetrievalBudgetsV2
    expansion_policy: ExpansionPolicy = ExpansionPolicy.NONE
    deduplication_policy: DeduplicationPolicy = DeduplicationPolicy.AUTHORITATIVE_IDENTITY
    ranking_policy: RankingPolicyV2
    security_scope_identity: str | None = None

    @field_validator("security_scope_identity")
    @classmethod
    def _security_scope_is_bounded(cls, value: str | None) -> str | None:
        if value is not None and (not value or len(value) > 128):
            raise ValueError("security_scope_identity must be non-empty and bounded")
        return value

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) > 4096:
            raise ValueError("query exceeds 4096 characters")
        return normalized

    @field_validator("representations")
    @classmethod
    def _representations_unique(
        cls, value: tuple[EvidenceRepresentation, ...]
    ) -> tuple[EvidenceRepresentation, ...]:
        if not value:
            raise ValueError("representations must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("representations must be unique")
        return value

    @model_validator(mode="after")
    def _validate_mode(self) -> RetrievalPlanV2:
        if self.mode is AdvancedRetrievalMode.RANKED and not self.query:
            raise ValueError("ranked retrieval requires a query")
        expected = (
            RankingPolicyV2.SOURCE_RANK_FUSION
            if self.mode is AdvancedRetrievalMode.RANKED
            else RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER
        )
        if self.ranking_policy is not expected:
            raise ValueError("ranking policy does not match retrieval mode")
        return self

    @property
    def fingerprint(self) -> str:
        material = {
            "version": ADVANCED_RETRIEVAL_VERSION,
            "plan": self.model_dump(mode="json"),
        }
        return hashlib.sha256(_canonical_json(material)).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalPathEvidenceV2:
    path: str
    source_rank: int
    source_score: float | None
    title_match: bool = False
    parent_promoted: bool = False

    def __post_init__(self) -> None:
        require_non_empty(self.path, "path")
        if isinstance(self.source_rank, bool) or self.source_rank < 1:
            raise ValueError("source_rank must be a positive integer")
        if self.source_score is not None:
            require_finite(self.source_score, "source_score")


def advanced_candidate_id(
    *,
    representation: EvidenceRepresentation,
    document_id: UUID,
    version_id: UUID,
    chunk_id: str | None,
    occurrence_id: UUID | None,
    derivation_id: UUID | None,
) -> UUID:
    derived_identity = derivation_id or occurrence_id
    authoritative = chunk_id or (None if derived_identity is None else str(derived_identity))
    if not authoritative:
        raise ValueError("candidate requires an authoritative evidence identity")
    return uuid5(
        _CANDIDATE_NAMESPACE,
        f"{representation.value}:{document_id}:{version_id}:{authoritative}",
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvancedRetrievalCandidate:
    candidate_id: UUID
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    representation: EvidenceRepresentation
    chunk: Chunk | None
    occurrence_id: UUID | None
    derivation_id: UUID | None
    locator: FrozenMetadata
    document_title: str | None
    content: str | None
    paths: tuple[RetrievalPathEvidenceV2, ...]
    fused_score: float | None = None
    final_rank: int | None = None
    expansion_reason: str | None = None

    def __post_init__(self) -> None:
        if self.chunk is None and self.occurrence_id is None and self.derivation_id is None:
            raise ValueError("candidate requires chunk, occurrence, or derivation provenance")
        if self.chunk is not None and (
            self.chunk.document_id != self.document_id or self.chunk.version_id != self.version_id
        ):
            raise ValueError("chunk provenance does not match candidate")
        expected = advanced_candidate_id(
            representation=self.representation,
            document_id=self.document_id,
            version_id=self.version_id,
            chunk_id=None if self.chunk is None else self.chunk.id,
            occurrence_id=self.occurrence_id,
            derivation_id=self.derivation_id,
        )
        if self.candidate_id != expected:
            raise ValueError("candidate_id does not match authoritative provenance")
        if not isinstance(self.locator, FrozenMetadata):
            raise TypeError("locator must be FrozenMetadata")
        if self.document_title is not None:
            require_non_empty(self.document_title, "document_title")
        if self.content is not None and not self.content:
            raise ValueError("content must be non-empty when present")
        if not self.paths:
            raise ValueError("candidate paths must not be empty")
        if len({item.path for item in self.paths}) != len(self.paths):
            raise ValueError("candidate paths must be unique")
        if self.fused_score is not None:
            require_finite(self.fused_score, "fused_score")
        if self.final_rank is not None and (
            isinstance(self.final_rank, bool) or self.final_rank < 1
        ):
            raise ValueError("final_rank must be a positive integer")
        if self.expansion_reason is not None:
            require_non_empty(self.expansion_reason, "expansion_reason")

    @property
    def title_match(self) -> bool:
        return any(path.title_match for path in self.paths)

    @property
    def serialized_size(self) -> int:
        material = {
            "candidate_id": str(self.candidate_id),
            "representation": self.representation.value,
            "document": str(self.document_id),
            "version": str(self.version_id),
            "content": self.content,
            "locator": dict(self.locator),
            "paths": [item.path for item in self.paths],
        }
        return len(_canonical_json(material))


@dataclass(frozen=True, slots=True, kw_only=True)
class RepresentationReportV2:
    representation: EvidenceRepresentation
    status: RepresentationSearchStatus
    examined: int
    returned: int
    exhausted: bool
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.examined < 0 or self.returned < 0:
            raise ValueError("representation counts must be non-negative")
        if self.returned > self.examined:
            raise ValueError("returned count cannot exceed examined count")
        if self.reason_code is not None:
            require_non_empty(self.reason_code, "reason_code")
        if self.status is RepresentationSearchStatus.SEARCHED and self.reason_code is not None:
            raise ValueError("searched representation cannot have a failure reason")
        if self.status is not RepresentationSearchStatus.SEARCHED and self.reason_code is None:
            raise ValueError("non-searched representation requires a reason")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalDiagnosticsV2:
    mode: AdvancedRetrievalMode
    recalled: int
    expanded: int
    deduplicated: int
    fused: int
    reranked: int
    returned: int
    serialized_bytes: int
    content_characters: int
    truncated: bool
    truncation_reason: str | None
    elapsed_milliseconds: int
    representation_reports: tuple[RepresentationReportV2, ...]

    def __post_init__(self) -> None:
        for value in (
            self.recalled,
            self.expanded,
            self.deduplicated,
            self.fused,
            self.reranked,
            self.returned,
            self.serialized_bytes,
            self.content_characters,
            self.elapsed_milliseconds,
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError("diagnostic counts must be non-negative integers")
        if self.truncated != (self.truncation_reason is not None):
            raise ValueError("truncation reason must match truncated status")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalResultSetV1:
    query_fingerprint: str
    snapshot_identity: str
    ordering_policy: RankingPolicyV2
    completeness: RetrievalCompleteness
    results: tuple[AdvancedRetrievalCandidate, ...]
    examined_count: int
    returned_count: int
    next_cursor: str | None
    diagnostics: RetrievalDiagnosticsV2

    def __post_init__(self) -> None:
        require_sha256(self.query_fingerprint, "query_fingerprint")
        require_sha256(self.snapshot_identity, "snapshot_identity")
        if self.returned_count != len(self.results):
            raise ValueError("returned_count must match results")
        if self.examined_count < self.returned_count:
            raise ValueError("examined_count cannot be less than returned_count")
        if tuple(item.final_rank for item in self.results) != tuple(
            range(1, len(self.results) + 1)
        ):
            raise ValueError("final ranks must be contiguous")
        if self.completeness is RetrievalCompleteness.TRUNCATED and self.next_cursor is None:
            raise ValueError("truncated result requires a continuation cursor")
        if (
            self.next_cursor is not None
            and self.completeness is not RetrievalCompleteness.TRUNCATED
        ):
            raise ValueError("continuation cursor is only valid for truncated results")
        if self.completeness is RetrievalCompleteness.EMPTY and self.results:
            raise ValueError("empty completeness requires no results")
        if self.diagnostics.returned != self.returned_count:
            raise ValueError("diagnostic returned count must match result set")
        if self.diagnostics.mode is AdvancedRetrievalMode.RANKED and (
            self.ordering_policy is not RankingPolicyV2.SOURCE_RANK_FUSION
        ):
            raise ValueError("ranked diagnostics require source-rank-fusion ordering")
        if self.diagnostics.mode is AdvancedRetrievalMode.EXHAUSTIVE and (
            self.ordering_policy is not RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER
        ):
            raise ValueError("exhaustive diagnostics require deterministic ordering")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
