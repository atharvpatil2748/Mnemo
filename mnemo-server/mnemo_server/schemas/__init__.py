"""Pydantic V2 request and response DTO schemas for mnemo-server."""

from __future__ import annotations

from .common import PageResponse
from .graph import EntityGraphResponse, GraphEdgeResponse, GraphNodeResponse
from .insights import InsightResponse
from .notebooks import CreateNotebookRequest, NotebookResponse, UpdateNotebookRequest
from .notes import CreateNoteRequest, NoteResponse, UpdateNoteRequest
from .query import (
    CitationResponse,
    QueryFilters,
    QueryRequest,
    QueryResponse,
    RetrievalConfig,
    RetrievalMetadataResponse,
    SynthesisConfig,
)
from .search import SearchRequest, SearchResponse, SearchResultItem
from .sessions import (
    CitationItemResponse,
    CreateSessionRequest,
    CreateTurnRequest,
    SessionDetailResponse,
    SessionSummaryResponse,
    TurnResponse,
)
from .sources import SourceResponse, SourceStatusResponse
from .summary import NotebookSummaryResponse, SummaryItemResponse
from .timeline import TimelineEventResponse, TimelineResponse

__all__ = [
    "CitationItemResponse",
    "CitationResponse",
    "CreateNoteRequest",
    "CreateNotebookRequest",
    "CreateSessionRequest",
    "CreateTurnRequest",
    "EntityGraphResponse",
    "GraphEdgeResponse",
    "GraphNodeResponse",
    "InsightResponse",
    "NoteResponse",
    "NotebookResponse",
    "NotebookSummaryResponse",
    "PageResponse",
    "QueryFilters",
    "QueryRequest",
    "QueryResponse",
    "RetrievalConfig",
    "RetrievalMetadataResponse",
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
    "SessionDetailResponse",
    "SessionSummaryResponse",
    "SourceResponse",
    "SourceStatusResponse",
    "SummaryItemResponse",
    "SynthesisConfig",
    "TimelineEventResponse",
    "TimelineResponse",
    "TurnResponse",
    "UpdateNoteRequest",
    "UpdateNotebookRequest",
]
