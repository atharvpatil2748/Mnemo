"""Additive Phase 8.5 exact structured retrieval route."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_server_config
from mnemo_server.schemas.structured_v2 import (
    StructuredRetrievalRequest,
    StructuredRetrievalResponse,
)
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.membership_http import membership_http_principal
from mnemo_server.services.shared_search import (
    SharedSearchApplicationService,
    SharedSearchKind,
    SharedSearchRequest,
)

router = APIRouter(tags=["retrieval-v2"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
ConfigDep = Annotated[ServerConfig, Depends(get_server_config)]


@router.post("/retrieval/structured", response_model=StructuredRetrievalResponse)
async def query_structured(
    request: Request, body: StructuredRetrievalRequest, engine: EngineDep, config: ConfigDep
) -> StructuredRetrievalResponse:
    authority = getattr(engine, "server_scope_authority", None)
    if authority is None and (
        config.auth_mode == "jwt" or getattr(engine, "server_actor_mapper", None) is not None
    ):
        raise DependencyUnavailableError(
            "trusted membership authority is unavailable", retryable=False
        )
    principal = (
        membership_http_principal(request, engine)
        if authority is not None
        else principal_from_claims(getattr(request.state, "auth", None))
    )
    result = await SharedSearchApplicationService(engine, config).execute(
        SharedSearchRequest(SharedSearchKind.STRUCTURED, body), principal
    )
    return cast(StructuredRetrievalResponse, result.response)
