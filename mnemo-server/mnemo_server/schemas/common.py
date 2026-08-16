"""Shared pagination and common schemas for mnemo-server."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PageResponse[T](BaseModel):
    """Generic cursor-paginated response envelope."""

    model_config = ConfigDict(frozen=True)

    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None)
    limit: int = Field(..., ge=1, le=100)
