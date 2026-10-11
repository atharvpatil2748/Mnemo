"""Server-planned, additive V2 automatic retrieval transport contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from mnemo.models import AdvancedRetrievalMode
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from mnemo_server.schemas.retrieval_v2 import EvidenceSearchResponse


class AutomaticQueryV2Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=4096)
    mode: AdvancedRetrievalMode = AdvancedRetrievalMode.RANKED
    cursor: str | None = None
    candidate_budget: StrictInt = Field(default=100, ge=1, le=1000)
    evidence_budget: StrictInt = Field(default=20, ge=1, le=200)
    max_serialized_bytes: StrictInt = Field(default=1_000_000, ge=256, le=10_000_000)
    max_content_characters: StrictInt = Field(default=200_000, ge=1, le=2_000_000)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized


class AutomaticRepresentationStatus(StrEnum):
    SEARCHED = "searched"
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    OMITTED_BY_BUDGET = "omitted_by_budget"


class RepresentationDecisionV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    representation: str
    status: AutomaticRepresentationStatus
    reason: str


class AutomaticQueryV2Response(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "mnemo.automatic-query/v2"
    request_id: UUID
    plan_version: str = "automatic-evidence-plan/v1"
    notebook_id: UUID
    representation_decisions: list[RepresentationDecisionV2]
    evidence: EvidenceSearchResponse
    answer_status: str = "not_generated"
    answer: None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
