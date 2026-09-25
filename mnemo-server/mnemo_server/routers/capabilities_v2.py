"""Thin HTTP adapter for runtime-derived Phase 8.5 capabilities."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError
from pydantic import ValidationError

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_server_config
from mnemo_server.schemas.capabilities_v2 import CapabilityDiscoveryRequest, CapabilityDocument
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.capabilities_v2 import CapabilityDiscoveryService

router = APIRouter(tags=["capabilities-v2"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
ConfigDep = Annotated[ServerConfig, Depends(get_server_config)]


@router.get("/capabilities", response_model=CapabilityDocument)
async def get_capabilities(
    http_request: Request,
    engine: EngineDep,
    config: ConfigDep,
    capability_ids: Annotated[list[str] | None, Query()] = None,
    notebook_id: UUID | None = None,
) -> CapabilityDocument:
    try:
        capability_request = CapabilityDiscoveryRequest(
            capability_ids=tuple(capability_ids or ()), notebook_id=notebook_id
        )
    except ValidationError as error:
        raise ContractValidationError("capability filter is invalid") from error
    workspace_decision = getattr(http_request.app.state, "mutable_workspace_decision", None)
    service = CapabilityDiscoveryService(
        engine,
        config,
        workspace_decision,
        getattr(http_request.app.state, "certified_production_binding", None),
        "http",
    )
    if notebook_id is not None:
        return await service.document_for_principal(
            capability_request, principal_from_claims(getattr(http_request.state, "auth", None))
        )
    return service.document(capability_request)
