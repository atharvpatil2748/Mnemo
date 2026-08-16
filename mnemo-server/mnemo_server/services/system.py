"""Services orchestrating system health checks, configuration, and background jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    NotFoundError,
    TokenCounterInterfaceV1,
)

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.common import PageResponse
from mnemo_server.schemas.system import (
    ComponentHealthResponse,
    ConfigResponse,
    EmbeddingConfigResponse,
    FilesystemStorageConfigResponse,
    HealthResponse,
    JobResponse,
    JobStatus,
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

_LOGGER = logging.getLogger(__name__)


class SystemService:
    """Coordinates system-level health probing, configuration serialization, and hot reload."""

    def __init__(
        self,
        engine: KnowledgeEngine,
        token_counter: TokenCounterInterfaceV1 | None = None,
    ) -> None:
        self._engine = engine
        self._token_counter = token_counter

    async def get_health(self) -> HealthResponse:
        """Probe the health of all subsystems and return an aggregated observation."""
        checked_at = datetime.now(UTC)
        engine_state = self._engine.state.value
        components: list[ComponentHealthResponse] = []

        # 1. Storage backend health
        try:
            storage_statuses = await self._engine.storage.health_check()
            for status in storage_statuses:
                components.append(
                    ComponentHealthResponse(
                        component=f"storage.{status.component}",
                        healthy=status.healthy,
                        checked_at=status.checked_at,
                        detail=status.detail,
                    )
                )
        except Exception as err:
            _LOGGER.warning("Storage health check failed: %s", err)
            components.append(
                ComponentHealthResponse(
                    component="storage",
                    healthy=False,
                    checked_at=checked_at,
                    detail=str(err),
                )
            )

        # 2. Embedding provider health
        try:
            emb_status = await self._engine.embedding_provider.health_check()
            components.append(
                ComponentHealthResponse(
                    component=f"embedding.{emb_status.component}",
                    healthy=emb_status.healthy,
                    checked_at=emb_status.checked_at,
                    detail=emb_status.detail,
                )
            )
        except Exception as err:
            _LOGGER.warning("Embedding health check failed: %s", err)
            components.append(
                ComponentHealthResponse(
                    component="embedding",
                    healthy=False,
                    checked_at=checked_at,
                    detail=str(err),
                )
            )

        # 3. LLM provider health for primary roles
        for role in ("planner", "synthesizer"):
            try:
                llm_prov = self._engine.llm(role)
                llm_status = await llm_prov.health_check()
                components.append(
                    ComponentHealthResponse(
                        component=f"llm.{role}",
                        healthy=llm_status.healthy,
                        checked_at=llm_status.checked_at,
                        detail=llm_status.detail,
                    )
                )
            except Exception as err:
                _LOGGER.warning("LLM health check for role '%s' failed: %s", role, err)
                components.append(
                    ComponentHealthResponse(
                        component=f"llm.{role}",
                        healthy=False,
                        checked_at=checked_at,
                        detail=str(err),
                    )
                )

        # 4. Tokenizer readiness
        if self._token_counter is not None:
            try:
                healthy_tc = self._token_counter.count("") == 0
                components.append(
                    ComponentHealthResponse(
                        component="token_counter",
                        healthy=healthy_tc,
                        checked_at=checked_at,
                        detail=self._token_counter.tokenizer_id,
                    )
                )
            except Exception as err:
                components.append(
                    ComponentHealthResponse(
                        component="token_counter",
                        healthy=False,
                        checked_at=checked_at,
                        detail=str(err),
                    )
                )

        all_healthy = self._engine.state is EngineState.READY and all(c.healthy for c in components)
        status_label = (
            "ok"
            if all_healthy
            else ("degraded" if any(c.healthy for c in components) else "unhealthy")
        )

        return HealthResponse(
            status=status_label,
            healthy=all_healthy,
            version=self._engine.version,
            engine_state=engine_state,
            checked_at=checked_at,
            components=components,
        )

    def get_config(self, server_config: ServerConfig) -> ConfigResponse:
        """Return the current runtime configuration with redacted credentials."""
        core_cfg = self._engine.config

        return ConfigResponse(
            server=ServerConfigResponse(
                host=server_config.host,
                port=server_config.port,
                cors_origins=list(server_config.cors_origins),
                log_level=server_config.log_level,
                max_upload_bytes=server_config.max_upload_bytes,
            ),
            storage=StorageConfigResponse(
                filesystem=FilesystemStorageConfigResponse(
                    enabled=core_cfg.storage.filesystem.enabled,
                    root=str(core_cfg.storage.filesystem.root),
                ),
                sqlite=SQLiteStorageConfigResponse(
                    enabled=core_cfg.storage.sqlite.enabled,
                    path=str(core_cfg.storage.sqlite.path),
                ),
                qdrant=QdrantStorageConfigResponse(
                    enabled=core_cfg.storage.qdrant.enabled,
                    url=str(core_cfg.storage.qdrant.url),
                    collection_name=core_cfg.storage.qdrant.collection_name,
                    on_disk=core_cfg.storage.qdrant.on_disk,
                    api_key_configured=core_cfg.storage.qdrant.api_key is not None,
                ),
                surrealdb=SurrealDBStorageConfigResponse(
                    enabled=core_cfg.storage.surrealdb.enabled,
                    url=str(core_cfg.storage.surrealdb.url),
                    username=core_cfg.storage.surrealdb.username,
                    namespace=core_cfg.storage.surrealdb.namespace,
                    database=core_cfg.storage.surrealdb.database,
                ),
            ),
            llm=LLMConfigResponse(
                planner=LLMRoleConfigResponse(
                    provider=core_cfg.llm.planner.provider,
                    model=core_cfg.llm.planner.model,
                    max_context_tokens=core_cfg.llm.planner.max_context_tokens,
                ),
                synthesizer=LLMRoleConfigResponse(
                    provider=core_cfg.llm.synthesizer.provider,
                    model=core_cfg.llm.synthesizer.model,
                    max_context_tokens=core_cfg.llm.synthesizer.max_context_tokens,
                ),
                extractor=LLMRoleConfigResponse(
                    provider=core_cfg.llm.extractor.provider,
                    model=core_cfg.llm.extractor.model,
                    max_context_tokens=core_cfg.llm.extractor.max_context_tokens,
                ),
                classifier=LLMRoleConfigResponse(
                    provider=core_cfg.llm.classifier.provider,
                    model=core_cfg.llm.classifier.model,
                    max_context_tokens=core_cfg.llm.classifier.max_context_tokens,
                ),
            ),
            embedding=EmbeddingConfigResponse(
                provider=core_cfg.embedding.provider,
                model=core_cfg.embedding.model,
                dimensions=core_cfg.embedding.dimensions,
                api_base=core_cfg.embedding.api_base,
            ),
            reranker=RerankerConfigResponse(
                provider=core_cfg.reranker.provider,
                model=core_cfg.reranker.model,
            ),
            plugins=PluginConfigResponse(
                directory=str(core_cfg.plugins.directory),
            ),
        )

    def get_models(self) -> ModelsConfigResponse:
        """Return the active model inventory across LLM, embedding, and reranking."""
        core_cfg = self._engine.config
        return ModelsConfigResponse(
            llm={
                "planner": {
                    "provider": core_cfg.llm.planner.provider,
                    "model": core_cfg.llm.planner.model,
                    "max_context_tokens": core_cfg.llm.planner.max_context_tokens,
                },
                "synthesizer": {
                    "provider": core_cfg.llm.synthesizer.provider,
                    "model": core_cfg.llm.synthesizer.model,
                    "max_context_tokens": core_cfg.llm.synthesizer.max_context_tokens,
                },
                "extractor": {
                    "provider": core_cfg.llm.extractor.provider,
                    "model": core_cfg.llm.extractor.model,
                    "max_context_tokens": core_cfg.llm.extractor.max_context_tokens,
                },
                "classifier": {
                    "provider": core_cfg.llm.classifier.provider,
                    "model": core_cfg.llm.classifier.model,
                    "max_context_tokens": core_cfg.llm.classifier.max_context_tokens,
                },
            },
            embedding={
                "provider": core_cfg.embedding.provider,
                "model": core_cfg.embedding.model,
                "dimensions": core_cfg.embedding.dimensions,
                "api_base": core_cfg.embedding.api_base,
            },
            reranker={
                "provider": core_cfg.reranker.provider,
                "model": core_cfg.reranker.model,
            },
        )

    def update_server_config(
        self,
        request: UpdateServerConfigRequest,
        current_server_config: ServerConfig,
    ) -> tuple[ServerConfig, ConfigResponse]:
        """Update mutable server configuration settings in-place and return the updated config."""
        if (
            request.log_level is None
            and request.max_upload_bytes is None
            and request.cors_origins is None
        ):
            raise ContractValidationError(
                "At least one configuration field must be provided for update"
            )

        new_log_level = request.log_level or current_server_config.log_level
        new_max_upload = request.max_upload_bytes or current_server_config.max_upload_bytes
        new_cors = (
            tuple(request.cors_origins)
            if request.cors_origins is not None
            else current_server_config.cors_origins
        )

        new_server_config = ServerConfig(
            host=current_server_config.host,
            port=current_server_config.port,
            cors_origins=new_cors,
            log_level=new_log_level,
            max_upload_bytes=new_max_upload,
        )

        if request.log_level is not None:
            numeric_level = getattr(logging, request.log_level.upper(), logging.INFO)
            logging.getLogger().setLevel(numeric_level)
            _LOGGER.info("Server log level updated to %s", request.log_level)

        return new_server_config, self.get_config(new_server_config)


class JobService:
    """In-memory asynchronous background job manager for single-process runtime."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, JobResponse] = {}
        self._lock = asyncio.Lock()

    async def create_job(
        self,
        job_type: str,
        *,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobResponse:
        """Create and track a new asynchronous background job."""
        job_id = uuid4()
        now = datetime.now(UTC)
        job = JobResponse(
            job_id=job_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            progress=0.0,
            detail=detail,
            created_at=now,
            updated_at=now,
            completed_at=None,
            error=None,
            metadata=metadata or {},
        )
        async with self._lock:
            self._jobs[job_id] = job
        return job

    async def get_job(self, job_id: UUID) -> JobResponse:
        """Get the current status of a background job."""
        async with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return job

    async def list_jobs(
        self,
        *,
        status: JobStatus | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> PageResponse[JobResponse]:
        """List background jobs with optional status filter and keyset pagination."""
        if cursor is not None:
            try:
                UUID(cursor)
            except ValueError as err:
                raise ContractValidationError(f"Invalid cursor format: {cursor}") from err

        async with self._lock:
            all_jobs = list(self._jobs.values())

        # Sort descending by created_at, then job_id
        all_jobs.sort(key=lambda j: (j.created_at, str(j.job_id)), reverse=True)

        if status is not None:
            all_jobs = [j for j in all_jobs if j.status == status]

        start_idx = 0
        if cursor is not None:
            cursor_uuid = UUID(cursor)
            for idx, j in enumerate(all_jobs):
                if j.job_id == cursor_uuid:
                    start_idx = idx + 1
                    break

        page_items = all_jobs[start_idx : start_idx + limit]
        next_cursor = (
            str(page_items[-1].job_id)
            if len(page_items) == limit and start_idx + limit < len(all_jobs)
            else None
        )

        return PageResponse(
            items=page_items,
            next_cursor=next_cursor,
            limit=limit,
        )

    async def update_job(
        self,
        job_id: UUID,
        *,
        status: JobStatus | None = None,
        progress: float | None = None,
        detail: str | None = None,
        error: str | None = None,
    ) -> JobResponse:
        """Update job execution status, progress, or failure message."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotFoundError(f"Job {job_id} not found")

            now = datetime.now(UTC)
            new_status = status or job.status
            new_progress = progress if progress is not None else job.progress
            new_detail = detail if detail is not None else job.detail
            new_error = error if error is not None else job.error
            completed_at = (
                now
                if new_status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
                else job.completed_at
            )

            updated_job = JobResponse(
                job_id=job.job_id,
                job_type=job.job_type,
                status=new_status,
                progress=new_progress,
                detail=new_detail,
                created_at=job.created_at,
                updated_at=now,
                completed_at=completed_at,
                error=new_error,
                metadata=job.metadata,
            )
            self._jobs[job_id] = updated_job
            return updated_job
