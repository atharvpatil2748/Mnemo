"""Additive Phase 8.5 exact structured retrieval route."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from mnemo.engine import KnowledgeEngine

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_server_config
from mnemo_server.schemas.structured_v2 import (
    StructuredRetrievalRequest,
    StructuredRetrievalResponse,
)
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.structured_v2 import StructuredRetrievalApplicationService

router = APIRouter(tags=["retrieval-v2"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
ConfigDep = Annotated[ServerConfig, Depends(get_server_config)]


@router.post("/retrieval/structured", response_model=StructuredRetrievalResponse)
async def query_structured(
    request: Request, body: StructuredRetrievalRequest, engine: EngineDep, config: ConfigDep
) -> StructuredRetrievalResponse:
    principal = principal_from_claims(getattr(request.state, "auth", None))
    return await StructuredRetrievalApplicationService(engine, config).execute(body, principal)
