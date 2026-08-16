"""Pydantic V2 schemas for WebSocket streaming query protocol."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mnemo_server.schemas.query import CitationResponse, RetrievalMetadataResponse


class _StrictSchema(BaseModel):
    """Base schema enforcing extra field prohibition and string stripping."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class StreamEventType(StrEnum):
    """Enumeration of standard Architecture §5.3 streaming events."""

    RETRIEVAL_START = "retrieval_start"
    CHUNK_RETRIEVED = "chunk_retrieved"
    SYNTHESIS_TOKEN = "synthesis_token"
    CITATIONS_READY = "citations_ready"
    DONE = "done"
    ERROR = "error"
    PONG = "pong"


class ChunkRetrievedData(_StrictSchema):
    """Data payload for chunk_retrieved event."""

    chunk_id: str
    score: float
    document_id: UUID | None = None


class SynthesisTokenData(_StrictSchema):
    """Data payload for synthesis_token event."""

    token: str


class CitationsReadyData(_StrictSchema):
    """Data payload for citations_ready event."""

    citations: list[CitationResponse] = Field(default_factory=list)


class DoneData(_StrictSchema):
    """Data payload for done completion event."""

    retrieval_metadata: RetrievalMetadataResponse
    answer: str | None = None


class StreamErrorData(_StrictSchema):
    """Data payload for streaming error notification."""

    code: str
    message: str
    detail: str | None = None


class StreamEvent(_StrictSchema):
    """Enveloping schema for typed WebSocket streaming messages."""

    event: StreamEventType
    data: Any | None = None
