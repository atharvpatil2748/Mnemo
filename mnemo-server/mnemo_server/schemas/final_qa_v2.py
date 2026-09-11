"""Strict public DTOs for the additive Final-QA V2 contract."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from mnemo.models.multimodal import MultimodalContextBudgetsV1
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .retrieval_v2 import EvidenceSearchRequest


class FinalQAPublicationPolicyV2(StrEnum):
    """Publication policy selected from the frozen V2 contract."""

    REQUIRE_COMPLETE = "require_complete"
    ALLOW_PARTIAL = "allow_partial"


class FinalQAV2RequestBody(BaseModel):
    """Transport-neutral, strict input accepted by HTTP and MCP."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    notebook_id: UUID
    session_id: UUID
    user_turn_id: UUID
    assistant_turn_id: UUID
    question: str = Field(min_length=1, max_length=4096)
    evidence_request_or_snapshot: EvidenceSearchRequest
    provider_profile: str = Field(min_length=1, max_length=512)
    context_budgets: MultimodalContextBudgetsV1 = Field(default_factory=MultimodalContextBudgetsV1)
    max_output_tokens: int = Field(default=1024, ge=1, le=4096)
    publication_policy: FinalQAPublicationPolicyV2 = FinalQAPublicationPolicyV2.REQUIRE_COMPLETE

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("question must not be empty")
        return normalized

    @model_validator(mode="after")
    def bind_evidence_query(self) -> FinalQAV2RequestBody:
        if self.evidence_request_or_snapshot.query != self.question:
            raise ValueError("evidence request query must exactly match question")
        return self


class FinalQAV2CitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: UUID
    source_number: int
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_id: str | None
    occurrence_id: UUID | None
    derivation_id: UUID | None
    generation_id: UUID | None
    kind: str
    authority: str
    document_title: str | None


class FinalQAV2Response(BaseModel):
    """Safe V2 response envelope shared by HTTP and MCP adapters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str
    execution_id: UUID
    replayed: bool
    status: str
    answer: str | None
    citations: tuple[FinalQAV2CitationResponse, ...]
    completeness: str
    coverage: dict[str, object]
    publication_status: str
    snapshot_identity: str | None
    omissions: tuple[str, ...]
    recommended_next_actions: tuple[dict[str, object], ...]
