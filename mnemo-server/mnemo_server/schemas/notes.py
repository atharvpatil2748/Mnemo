"""Pydantic V2 DTO schemas for note endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from mnemo.models.notebook import NoteOrigin
from pydantic import BaseModel, ConfigDict, Field


class CreateNoteRequest(BaseModel):
    """Request payload for creating a note."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(..., min_length=1)
    title: str | None = Field(default=None, max_length=255)
    origin: NoteOrigin = Field(default=NoteOrigin.USER)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateNoteRequest(BaseModel):
    """Request payload for updating a note via PATCH."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] | None = None


class NoteResponse(BaseModel):
    """Transport schema for note resources."""

    model_config = ConfigDict(frozen=True)

    note_id: UUID
    notebook_id: UUID
    title: str | None = None
    content: str
    origin: NoteOrigin
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
