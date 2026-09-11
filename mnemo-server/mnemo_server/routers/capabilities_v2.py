"""Thin HTTP adapter for runtime-derived Phase 8.5 capabilities."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError
from pydantic import ValidationError

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_server_config
from mnemo_server.schemas.capabilities_v2 import CapabilityDiscoveryRequest, CapabilityDocument
from mnemo_server.services.capabilities_v2 import CapabilityDiscoveryService

router = APIRouter(tags=["capabilities-v2"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
ConfigDep = Annotated[ServerConfig, Depends(get_server_config)]


@router.get("/capabilities", response_model=CapabilityDocument)
async def get_capabilities(
    engine: EngineDep,
    config: ConfigDep,
    capability_ids: Annotated[list[str] | None, Query()] = None,
) -> CapabilityDocument:
    try:
        request = CapabilityDiscoveryRequest(capability_ids=tuple(capability_ids or ()))
    except ValidationError as error:
        raise ContractValidationError("capability filter is invalid") from error
    return CapabilityDiscoveryService(engine, config).document(request)
