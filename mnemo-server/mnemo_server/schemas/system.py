"""Pydantic V2 schemas for system-level REST endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _StrictSchema(BaseModel):
    """Base schema enforcing extra field prohibition and string stripping."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ComponentHealthResponse(_StrictSchema):
    """Health status for a single subsystem component."""

    component: str = Field(description="Component identifier (e.g. storage.sqlite).")
    healthy: bool = Field(description="Whether the component is operating normally.")
    checked_at: datetime = Field(description="UTC timestamp of the health observation.")
    detail: str | None = Field(default=None, description="Optional diagnostic detail.")


class HealthResponse(_StrictSchema):
    """Comprehensive system health observation."""

    status: str = Field(description="Overall health status ('ok', 'degraded', 'unhealthy').")
    healthy: bool = Field(description="True if all critical components are healthy.")
    version: str = Field(description="Mnemo package version.")
    engine_state: str = Field(description="Lifecycle state of the KnowledgeEngine.")
    checked_at: datetime = Field(description="UTC timestamp of the overall check.")
    components: list[ComponentHealthResponse] = Field(
        default_factory=list, description="Health observations across individual subsystems."
    )


class ServerConfigResponse(_StrictSchema):
    """Transport and process-level server configuration."""

    host: str
    port: int
    cors_origins: list[str]
    log_level: str
    max_upload_bytes: int


class FilesystemStorageConfigResponse(_StrictSchema):
    """Filesystem blob storage configuration."""

    enabled: bool
    root: str


class SQLiteStorageConfigResponse(_StrictSchema):
    """SQLite metadata storage configuration."""

    enabled: bool
    path: str


class QdrantStorageConfigResponse(_StrictSchema):
    """Qdrant vector storage configuration with redacted credentials."""

    enabled: bool
    url: str
    collection_name: str
    on_disk: bool
    api_key_configured: bool


class SurrealDBStorageConfigResponse(_StrictSchema):
    """SurrealDB metadata and graph storage configuration with redacted credentials."""

    enabled: bool
    url: str
    username: str
    namespace: str
    database: str


class StorageConfigResponse(_StrictSchema):
    """Configuration across composite storage backends."""

    filesystem: FilesystemStorageConfigResponse
    sqlite: SQLiteStorageConfigResponse
    qdrant: QdrantStorageConfigResponse
    surrealdb: SurrealDBStorageConfigResponse


class LLMRoleConfigResponse(_StrictSchema):
    """Configuration for one LLM role."""

    provider: str
    model: str
    max_context_tokens: int


class LLMConfigResponse(_StrictSchema):
    """Configuration for mandatory LLM roles."""

    planner: LLMRoleConfigResponse
    synthesizer: LLMRoleConfigResponse
    extractor: LLMRoleConfigResponse
    classifier: LLMRoleConfigResponse


class EmbeddingConfigResponse(_StrictSchema):
    """Configuration for the embedding provider."""

    provider: str
    model: str
    dimensions: int
    api_base: str | None = None


class RerankerConfigResponse(_StrictSchema):
    """Configuration for the candidate reranker."""

    provider: str
    model: str


class PluginConfigResponse(_StrictSchema):
    """Configuration for plugin discovery."""

    directory: str


class ConfigResponse(_StrictSchema):
    """Full runtime configuration response with sanitized credentials."""

    server: ServerConfigResponse
    storage: StorageConfigResponse
    llm: LLMConfigResponse
    embedding: EmbeddingConfigResponse
    reranker: RerankerConfigResponse
    plugins: PluginConfigResponse


class ModelsConfigResponse(_StrictSchema):
    """Inventory of configured models across subsystems."""

    llm: dict[str, dict[str, Any]]
    embedding: dict[str, Any]
    reranker: dict[str, Any]


class UpdateServerConfigRequest(_StrictSchema):
    """Request payload for updating mutable server configuration."""

    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] | None = Field(
        default=None, description="New logging level."
    )
    max_upload_bytes: int | None = Field(
        default=None, ge=1, description="New maximum upload size in bytes."
    )
    cors_origins: list[str] | None = Field(
        default=None, description="New allowed CORS origin list."
    )


class JobStatus(StrEnum):
    """Execution status of an asynchronous background job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    """Categorization of background jobs."""

    INGESTION = "ingestion"
    REINDEX = "reindex"
    SYNTHESIS = "synthesis"
    CLEANUP = "cleanup"
    CUSTOM = "custom"


class JobResponse(_StrictSchema):
    """State observation of a background job."""

    job_id: UUID
    job_type: str
    status: JobStatus
    progress: float = Field(ge=0.0, le=1.0, description="Completion fraction from 0.0 to 1.0.")
    detail: str | None = Field(default=None, description="Status detail or progress message.")
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    error: str | None = Field(default=None, description="Failure description if failed.")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateJobRequest(_StrictSchema):
    """Payload to instantiate a tracked background job."""

    job_type: str = Field(min_length=1)
    detail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
