"""Notebook request and response schemas for mnemo-server."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CreateNotebookRequest(BaseModel):
    """Request body for POST /v1/notebooks."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace only")
        return stripped

    @field_validator("description")
    @classmethod
    def _validate_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("description must not be empty whitespace if provided")
        return stripped


class UpdateNotebookRequest(BaseModel):
    """Request body for PATCH /v1/notebooks/{notebook_id}."""

    model_config = ConfigDict(frozen=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    metadata: dict[str, Any] | None = Field(default=None)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace only")
        return stripped

    @field_validator("description")
    @classmethod
    def _validate_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("description must not be empty whitespace if provided")
        return stripped

    @model_validator(mode="after")
    def _check_at_least_one_field(self) -> UpdateNotebookRequest:
        if self.title is None and self.description is None and self.metadata is None:
            raise ValueError("at least one field (title, description, metadata) must be provided")
        return self


class NotebookResponse(BaseModel):
    """Response model for a single notebook."""

    model_config = ConfigDict(frozen=True)

    notebook_id: UUID
    title: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
