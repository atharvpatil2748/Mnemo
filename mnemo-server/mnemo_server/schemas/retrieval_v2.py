"""Strict transport contracts for additive Phase 8.5 evidence retrieval."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mnemo.models import (
    AdvancedRetrievalMode,
    DeduplicationPolicy,
    EvidenceRepresentation,
    ExpansionPolicy,
    PositionalScopeV2,
    RankingPolicyV2,
    RetrievalBudgetsV2,
    RetrievalPlanV2,
    RetrievalScopeV2,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EvidenceScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    notebook_id: UUID
    source_ids: tuple[UUID, ...] = Field(default=(), max_length=200)
    document_ids: tuple[UUID, ...] = Field(default=(), max_length=200)
    version_ids: tuple[UUID, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def bound_combined_scope(self) -> EvidenceScopeRequest:
        if len(self.source_ids) + len(self.document_ids) + len(self.version_ids) > 500:
            raise ValueError("combined retrieval scope exceeds 500 identities")
        return self


class PositionalScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_indexes: tuple[int, ...] = ()
    heading_prefix: tuple[str, ...] = ()


class EvidenceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(max_length=4096)
    mode: AdvancedRetrievalMode
    scope: EvidenceScopeRequest
    representations: tuple[EvidenceRepresentation, ...] = Field(min_length=1)
    cursor: str | None = None
    candidate_budget: int = Field(default=100, ge=1, le=1000)
    evidence_budget: int = Field(default=50, ge=1, le=200)
    max_serialized_bytes: int = Field(default=1_000_000, ge=256, le=10_000_000)
    max_content_characters: int = Field(default=200_000, ge=1, le=2_000_000)
    positional_scope: PositionalScopeRequest = PositionalScopeRequest()
    expansion_policy: ExpansionPolicy = ExpansionPolicy.NONE
    deduplication_policy: DeduplicationPolicy = DeduplicationPolicy.AUTHORITATIVE_IDENTITY
    partition_document_ids: tuple[UUID, ...] = Field(
        default=(),
        max_length=100,
        description=(
            "Explicit authorized document partitions for deterministic multi-document retrieval."
        ),
    )
    partition_cursors: dict[UUID, str] = Field(
        default_factory=dict,
        description=(
            "Opaque per-document continuation cursors returned by a prior partitioned request."
        ),
    )
    all_authorized_documents: bool = Field(
        default=False,
        description=(
            "Resolve every document authorized in the notebook scope as deterministic partitions."
        ),
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized

    def to_plan(
        self,
        *,
        max_candidate_budget: int,
        max_evidence_budget: int,
        max_response_bytes: int,
        max_content_characters: int,
        max_rerank_candidates: int = 200,
        production_candidate_pool_k: int | None = None,
        security_scope_identity: str | None = None,
    ) -> RetrievalPlanV2:
        requested_recall = min(self.candidate_budget, max_candidate_budget)
        recall = (
            requested_recall
            if production_candidate_pool_k is None
            else max(requested_recall, production_candidate_pool_k)
        )
        expansion = (
            min(100, recall)
            if self.mode is AdvancedRetrievalMode.RANKED
            and self.expansion_policy is not ExpansionPolicy.NONE
            else 0
        )
        fusion = min(500, recall + expansion)
        rerank = min(
            max_rerank_candidates,
            fusion,
            production_candidate_pool_k or max_rerank_candidates,
        )
        result = min(self.evidence_budget, max_evidence_budget, rerank)
        return RetrievalPlanV2(
            query=self.query,
            mode=self.mode,
            scope=RetrievalScopeV2(**self.scope.model_dump()),
            position=PositionalScopeV2(**self.positional_scope.model_dump()),
            representations=self.representations,
            budgets=RetrievalBudgetsV2(
                recall_limit=recall,
                expansion_limit=expansion,
                fusion_limit=fusion,
                rerank_limit=rerank,
                result_limit=result,
                max_serialized_bytes=min(self.max_serialized_bytes, max_response_bytes),
                max_content_characters=min(self.max_content_characters, max_content_characters),
            ),
            expansion_policy=self.expansion_policy,
            deduplication_policy=self.deduplication_policy,
            ranking_policy=(
                RankingPolicyV2.SOURCE_RANK_FUSION
                if self.mode is AdvancedRetrievalMode.RANKED
                else RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER
            ),
            security_scope_identity=security_scope_identity,
        )


class EvidenceSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    operation: str
    request_id: UUID
    mode: str
    scope: dict[str, Any]
    items: list[dict[str, Any]]
    completeness: str
    coverage: dict[str, Any]
    omissions: list[str]
    limits: dict[str, Any]
    next_cursor: str | None
    recommended_next_actions: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    partitions: list[dict[str, Any]] = Field(default_factory=list)
