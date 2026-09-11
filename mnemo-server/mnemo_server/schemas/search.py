"""Transport DTOs for the POST /v1/search endpoint."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .query import QueryFilters


class SearchRequest(BaseModel):
    """Request payload for POST /v1/search (global or scoped search)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1, max_length=10000)
    notebook_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)
    top_k: int | None = Field(default=None, ge=1, le=100)
    modes: list[str] = Field(default_factory=lambda: ["dense", "sparse"])
    filters: QueryFilters | None = None
    enable_reranking: bool = True

    @model_validator(mode="before")
    @classmethod
    def _harmonize_limit_top_k(cls, data: Any) -> Any:
        if isinstance(data, dict):
            top_k = data.get("top_k")
            limit = data.get("limit")
            if top_k is not None and limit is None:
                data = dict(data)
                data["limit"] = top_k
            elif limit is not None and top_k is None:
                data = dict(data)
                data["top_k"] = limit
            elif top_k is not None and limit is not None and top_k != limit:
                raise ValueError("Conflicting values provided for limit and top_k")
        return data

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("query must not be empty or whitespace only")
        return normalized

    @field_validator("modes")
    @classmethod
    def _validate_modes(cls, value: list[str]) -> list[str]:
        allowed = {"dense", "sparse", "hybrid"}
        for mode in value:
            if mode.lower() not in allowed:
                raise ValueError(f"unsupported retrieval mode '{mode}'. Allowed: {sorted(allowed)}")
        return [m.lower() for m in value]


class SearchResultItem(BaseModel):
    """Individual ranked chunk search result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    notebook_id: UUID | None = None
    document_id: UUID
    version_id: UUID
    text: str
    score: float
    rank: int
    retrieval_mode: str
    heading_path: list[str] = Field(default_factory=list)
    page_number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Response payload for POST /v1/search."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    results: list[SearchResultItem] = Field(default_factory=list)
    total: int
    latency_ms: int
