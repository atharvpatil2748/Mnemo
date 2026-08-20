"""ADR-0055 transport DTOs for persisted Final QA."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .query import QueryFilters
from .sessions import CitationItemResponse


class FinalQARequestBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: UUID
    user_turn_id: UUID
    assistant_turn_id: UUID
    global_limit: int = Field(default=20, ge=1, le=100)
    context_budget: int = Field(default=8000, ge=1, le=1_000_000)
    max_output_tokens: int = Field(default=1000, ge=1, le=4096)
    filters: QueryFilters | None = None
    table_of_contents: tuple[str, ...] = ()


class FinalQAResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    execution: str
    answer: str | None
    citations: list[CitationItemResponse] = Field(default_factory=list)
