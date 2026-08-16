"""Notebook activity timeline response schemas for mnemo-server."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TimelineEventResponse(BaseModel):
    """A single synthesized chronological event in a notebook's activity history."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    event_id: UUID
    timestamp: datetime
    title: str
    details: dict[str, Any] = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    """Response model for GET /v1/notebooks/{notebook_id}/timeline."""

    model_config = ConfigDict(frozen=True)

    notebook_id: UUID
    events: list[TimelineEventResponse] = Field(default_factory=list)
    total: int
