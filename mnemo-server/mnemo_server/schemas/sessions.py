"""Pydantic V2 DTO schemas for session and turn endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from mnemo.models.notebook import TurnRole
from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    """Request payload for creating a new session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionSummaryResponse(BaseModel):
    """Transport schema for session summary in listings and creation."""

    model_config = ConfigDict(frozen=True)

    session_id: UUID
    notebook_id: UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateTurnRequest(BaseModel):
    """Request payload for appending a turn to a session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: TurnRole
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CitationItemResponse(BaseModel):
    """Transport schema for citations attached to a conversational turn."""

    model_config = ConfigDict(frozen=True)

    citation_id: UUID
    turn_id: UUID
    source_number: int
    chunk_id: str
    document_id: UUID
    version_id: UUID
    document_title: str
    verbatim_quote: str
    page_number: int | None = None
    heading_path: list[str] = Field(default_factory=list)
    created_at: datetime


class TurnResponse(BaseModel):
    """Transport schema for a conversational turn."""

    model_config = ConfigDict(frozen=True)

    turn_id: UUID
    session_id: UUID
    sequence: int
    role: TurnRole
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    citations: list[CitationItemResponse] = Field(default_factory=list)


class SessionDetailResponse(BaseModel):
    """Transport schema for full session history with ordered turns and citations."""

    model_config = ConfigDict(frozen=True)

    session_id: UUID
    notebook_id: UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    turns: list[TurnResponse] = Field(default_factory=list)
