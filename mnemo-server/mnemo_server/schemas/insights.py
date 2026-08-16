"""Pydantic V2 DTO schemas for insight endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from mnemo.models.notebook import InsightType
from pydantic import BaseModel, ConfigDict, Field


class InsightResponse(BaseModel):
    """Transport schema for insight resources."""

    model_config = ConfigDict(frozen=True)

    insight_id: UUID
    notebook_id: UUID
    source_id: UUID
    type: InsightType
    content: str
    created_at: datetime
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
