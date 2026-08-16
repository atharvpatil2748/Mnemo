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
from .streaming import (
    ChunkRetrievedData,
    CitationsReadyData,
    DoneData,
    StreamErrorData,
    StreamEvent,
    StreamEventType,
    SynthesisTokenData,
)
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
    "ChunkRetrievedData",
    "CitationItemResponse",
    "CitationResponse",
    "CitationsReadyData",
    "ComponentHealthResponse",
    "ConfigResponse",
    "CreateJobRequest",
    "CreateNoteRequest",
    "CreateNotebookRequest",
    "CreateSessionRequest",
    "CreateTurnRequest",
    "DoneData",
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
    "StreamErrorData",
    "StreamEvent",
    "StreamEventType",
    "SummaryItemResponse",
    "SurrealDBStorageConfigResponse",
    "SynthesisConfig",
    "SynthesisTokenData",
    "TimelineEventResponse",
    "TimelineResponse",
    "TurnResponse",
    "UpdateNoteRequest",
    "UpdateNotebookRequest",
    "UpdateServerConfigRequest",
]
