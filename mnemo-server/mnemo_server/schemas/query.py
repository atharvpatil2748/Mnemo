"""Transport DTOs for the POST /v1/query endpoint."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QueryFilters(BaseModel):
    """Optional metadata filters for retrieval constraints."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_type: list[str] | None = None
    date_after: date | None = None
    date_before: date | None = None
    source_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def _validate_date_order(self) -> QueryFilters:
        if (
            self.date_after is not None
            and self.date_before is not None
            and self.date_after > self.date_before
        ):
            raise ValueError("date_after cannot be later than date_before")
        return self


class RetrievalConfig(BaseModel):
    """Retrieval parameters governing multi-mode search and reranking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    modes: list[str] = Field(default_factory=lambda: ["dense", "sparse"])
    top_k: int = Field(default=20, ge=1, le=100)
    filters: QueryFilters | None = None
    enable_reranking: bool = True
    enable_parent_retrieval: bool = True

    @field_validator("modes")
    @classmethod
    def _validate_modes(cls, value: list[str]) -> list[str]:
        allowed = {"dense", "sparse", "hybrid"}
        for mode in value:
            if mode.lower() not in allowed:
                raise ValueError(f"unsupported retrieval mode '{mode}'. Allowed: {sorted(allowed)}")
        return [m.lower() for m in value]


class SynthesisConfig(BaseModel):
    """Configuration for optional LLM grounded answer synthesis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    llm_role: str = "synthesizer"
    max_response_tokens: int = Field(default=1000, ge=1, le=4096)
    system_prompt: str | None = None


class QueryRequest(BaseModel):
    """Request payload for POST /v1/query per Architecture §5.1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(min_length=1, max_length=10000)
    notebook_id: UUID | None = None
    context_budget: int = Field(default=8000, ge=1, le=1_000_000)
    retrieval_config: RetrievalConfig = Field(default_factory=RetrievalConfig)
    synthesis: SynthesisConfig = Field(default_factory=SynthesisConfig)

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("question must not be empty or whitespace only")
        return normalized


class CitationResponse(BaseModel):
    """Attributed citation evidence item linked to retrieved context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID | str
    chunk_id: str
    document_title: str | None = None
    page: int | None = None
    heading_path: list[str] = Field(default_factory=list)
    quote: str | None = None
    confidence: float | None = None


class RetrievalMetadataResponse(BaseModel):
    """Telemetry and performance metrics for the retrieval execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunks_retrieved: int
    chunks_used: int
    retrieval_modes_used: list[str]
    latency_ms: int


class QueryResponse(BaseModel):
    """Response payload for POST /v1/query."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    retrieval_metadata: RetrievalMetadataResponse
