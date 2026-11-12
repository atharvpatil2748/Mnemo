"""Additive Phase 8.5 ranked/exhaustive evidence retrieval route."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from mnemo.engine import KnowledgeEngine

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import (
    get_engine,
    get_server_config,
)
from mnemo_server.schemas.automatic_query_v2 import (
    AutomaticQueryV2Request,
    AutomaticQueryV2Response,
)
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest, EvidenceSearchResponse
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


@router.post(
    "/retrieval/automatic",
    response_model=AutomaticQueryV2Response,
)
async def query_notebook_v2(
    request: Request, body: AutomaticQueryV2Request, engine: EngineDep, config: ConfigDep
) -> AutomaticQueryV2Response:
    principal = (
        membership_http_principal(request, engine)
        if getattr(engine, "server_scope_authority", None) is not None
        else principal_from_claims(getattr(request.state, "auth", None))
    )
    result = await SharedSearchApplicationService(engine, config).execute(
        SharedSearchRequest(SharedSearchKind.AUTOMATIC, body), principal
    )
    return cast(AutomaticQueryV2Response, result.response)


@router.post("/retrieval/evidence", response_model=EvidenceSearchResponse)
async def search_evidence(
    request: Request, body: EvidenceSearchRequest, engine: EngineDep, config: ConfigDep
) -> EvidenceSearchResponse:
    principal = (
        membership_http_principal(request, engine)
        if getattr(engine, "server_scope_authority", None) is not None
        else principal_from_claims(getattr(request.state, "auth", None))
    )
    result = await SharedSearchApplicationService(engine, config).execute(
        SharedSearchRequest(SharedSearchKind.EVIDENCE, body), principal
    )
    return cast(EvidenceSearchResponse, result.response)
