"""FastAPI router for system-level health, configuration, and job tracking endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_job_service, get_server_config, get_system_service
from mnemo_server.schemas.common import PageResponse
from mnemo_server.schemas.system import (
    ConfigResponse,
    HealthResponse,
    JobResponse,
    JobStatus,
    ModelsConfigResponse,
    UpdateServerConfigRequest,
)
from mnemo_server.services.system import JobService, SystemService

system_router = APIRouter(tags=["system"])


@system_router.get(
    "/health",
    response_model=HealthResponse,
    summary="Probe system health and subsystem connectivity",
)
@system_router.get(
    "/v1/health",
    response_model=HealthResponse,
    summary="Probe system health and subsystem connectivity",
)
async def get_health(
    system_service: Annotated[SystemService, Depends(get_system_service)],
) -> HealthResponse:
    """Probe overall system health, storage connectivity, and provider readiness."""
    return await system_service.get_health()


@system_router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Get current runtime configuration",
)
@system_router.get(
    "/v1/config",
    response_model=ConfigResponse,
    summary="Get current runtime configuration",
)
async def get_config(
    system_service: Annotated[SystemService, Depends(get_system_service)],
    server_config: Annotated[ServerConfig, Depends(get_server_config)],
) -> ConfigResponse:
    """Return the active runtime and server configuration with sanitized credentials."""
    return system_service.get_config(server_config)


@system_router.get(
    "/config/models",
    response_model=ModelsConfigResponse,
    summary="List configured models across subsystems",
)
@system_router.get(
    "/v1/config/models",
    response_model=ModelsConfigResponse,
    summary="List configured models across subsystems",
)
async def get_models(
    system_service: Annotated[SystemService, Depends(get_system_service)],
) -> ModelsConfigResponse:
    """Return the inventory of active LLM, embedding, and reranking models."""
    return system_service.get_models()


@system_router.patch(
    "/config",
    response_model=ConfigResponse,
    summary="Update mutable server configuration",
)
@system_router.patch(
    "/v1/config",
    response_model=ConfigResponse,
    summary="Update mutable server configuration",
)
async def update_config(
    request: UpdateServerConfigRequest,
    raw_request: Request,
    system_service: Annotated[SystemService, Depends(get_system_service)],
    server_config: Annotated[ServerConfig, Depends(get_server_config)],
) -> ConfigResponse:
    """Update mutable server settings in-place (logging level, upload size, CORS origins)."""
    new_server_config, response = system_service.update_server_config(request, server_config)
    raw_request.app.state.server_config = new_server_config
    return response


@system_router.get(
    "/jobs",
    response_model=PageResponse[JobResponse],
    summary="List asynchronous background jobs",
)
@system_router.get(
    "/v1/jobs",
    response_model=PageResponse[JobResponse],
    summary="List asynchronous background jobs",
)
async def list_jobs(
    job_service: Annotated[JobService, Depends(get_job_service)],
    status: Annotated[JobStatus | None, Query(description="Filter by job status")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size limit")] = 20,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor")] = None,
) -> PageResponse[JobResponse]:
    """List background jobs with optional status filtering and keyset pagination."""
    return await job_service.list_jobs(status=status, limit=limit, cursor=cursor)


@system_router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get background job status",
)
@system_router.get(
    "/v1/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get background job status",
)
async def get_job(
    job_id: UUID,
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Get the current execution state and detail for one background job."""
    return await job_service.get_job(job_id)
