"""Notebook summary response schemas for mnemo-server."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SummaryItemResponse(BaseModel):
    """A single summary insight record attached to a source within a notebook."""

    model_config = ConfigDict(frozen=True)

    insight_id: UUID
    source_id: UUID
    content: str
    confidence: float | None = None
    created_at: datetime


class NotebookSummaryResponse(BaseModel):
    """Response model for GET /v1/notebooks/{notebook_id}/summary."""

    model_config = ConfigDict(frozen=True)

    notebook_id: UUID
    summaries: list[SummaryItemResponse] = Field(default_factory=list)
    status: Literal["ready", "empty"]
