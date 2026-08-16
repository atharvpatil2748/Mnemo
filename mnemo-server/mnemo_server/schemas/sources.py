"""Pydantic V2 DTO schemas for sources and ingestion REST endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceResponse(BaseModel):
    """Transport DTO for a source association and its linked document metadata."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID = Field(description="Unique identifier of the source association.")
    notebook_id: UUID = Field(description="Unique identifier of the owning notebook.")
    document_id: UUID = Field(description="Unique identifier of the underlying document.")
    filename: str = Field(description="Original filename of the ingested source.")
    content_hash: str = Field(description="SHA-256 digest of the raw document content.")
    mime_type: str = Field(description="MIME type of the source file.")
    size_bytes: int = Field(ge=0, description="Size of the raw document in bytes.")
    doc_type: str = Field(description="Semantic classification of the document.")
    status: str = Field(description="Current ingestion lifecycle status.")
    deduplicated: bool = Field(
        default=False,
        description="Whether this source reused an existing document via content deduplication.",
    )
    created_at: datetime = Field(description="Timestamp when the source association was created.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary document and provenance metadata.",
    )


class SourceStatusResponse(BaseModel):
    """Transport DTO for source ingestion lifecycle status polling."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID = Field(description="Unique identifier of the source association.")
    notebook_id: UUID = Field(description="Unique identifier of the owning notebook.")
    document_id: UUID = Field(description="Unique identifier of the underlying document.")
    status: str = Field(description="Current persisted DocumentStatus.")
    created_at: datetime = Field(description="Timestamp when the source was created.")
    updated_at: datetime = Field(description="Timestamp when the document was last updated.")
    error_message: str | None = Field(
        default=None,
        description="Error details if ingestion failed, or null if healthy.",
    )
