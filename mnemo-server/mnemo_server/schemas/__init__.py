"""Pydantic V2 request and response DTO schemas for mnemo-server."""

from __future__ import annotations

from .common import PageResponse
from .graph import EntityGraphResponse, GraphEdgeResponse, GraphNodeResponse
from .notebooks import CreateNotebookRequest, NotebookResponse, UpdateNotebookRequest
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
from .sources import SourceResponse, SourceStatusResponse
from .summary import NotebookSummaryResponse, SummaryItemResponse
from .timeline import TimelineEventResponse, TimelineResponse

__all__ = [
    "CitationResponse",
    "CreateNotebookRequest",
    "EntityGraphResponse",
    "GraphEdgeResponse",
    "GraphNodeResponse",
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
    "SourceResponse",
    "SourceStatusResponse",
    "SummaryItemResponse",
    "SynthesisConfig",
    "TimelineEventResponse",
    "TimelineResponse",
    "UpdateNotebookRequest",
]
