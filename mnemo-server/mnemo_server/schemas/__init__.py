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
from .system import (
    ComponentHealthResponse,
    ConfigResponse,
    CreateJobRequest,
    EmbeddingConfigResponse,
    FilesystemStorageConfigResponse,
    HealthResponse,
    JobResponse,
    JobStatus,
    JobType,
    LLMConfigResponse,
    LLMRoleConfigResponse,
    ModelsConfigResponse,
    PluginConfigResponse,
    QdrantStorageConfigResponse,
    RerankerConfigResponse,
    ServerConfigResponse,
    SQLiteStorageConfigResponse,
    StorageConfigResponse,
    SurrealDBStorageConfigResponse,
    UpdateServerConfigRequest,
)
from .timeline import TimelineEventResponse, TimelineResponse

__all__ = [
    "CitationItemResponse",
    "CitationResponse",
    "ComponentHealthResponse",
    "ConfigResponse",
    "CreateJobRequest",
    "CreateNoteRequest",
    "CreateNotebookRequest",
    "CreateSessionRequest",
    "CreateTurnRequest",
    "EmbeddingConfigResponse",
    "EntityGraphResponse",
    "FilesystemStorageConfigResponse",
    "GraphEdgeResponse",
    "GraphNodeResponse",
    "HealthResponse",
    "InsightResponse",
    "JobResponse",
    "JobStatus",
    "JobType",
    "LLMConfigResponse",
    "LLMRoleConfigResponse",
    "ModelsConfigResponse",
    "NoteResponse",
    "NotebookResponse",
    "NotebookSummaryResponse",
    "PageResponse",
    "PluginConfigResponse",
    "QdrantStorageConfigResponse",
    "QueryFilters",
    "QueryRequest",
    "QueryResponse",
    "RerankerConfigResponse",
    "RetrievalConfig",
    "RetrievalMetadataResponse",
    "SQLiteStorageConfigResponse",
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
    "ServerConfigResponse",
    "SessionDetailResponse",
    "SessionSummaryResponse",
    "SourceResponse",
    "SourceStatusResponse",
    "StorageConfigResponse",
    "SummaryItemResponse",
    "SurrealDBStorageConfigResponse",
    "SynthesisConfig",
    "TimelineEventResponse",
    "TimelineResponse",
    "TurnResponse",
    "UpdateNoteRequest",
    "UpdateNotebookRequest",
    "UpdateServerConfigRequest",
]
