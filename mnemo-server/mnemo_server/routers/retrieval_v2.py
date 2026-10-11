"""Additive Phase 8.5 ranked/exhaustive evidence retrieval route."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from mnemo.engine import KnowledgeEngine

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_server_config
from mnemo_server.schemas.automatic_query_v2 import (
    AutomaticQueryV2Request,
    AutomaticQueryV2Response,
)
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest, EvidenceSearchResponse
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.automatic_query_v2 import AutomaticQueryV2ApplicationService
from mnemo_server.services.retrieval_v2 import EvidenceRetrievalApplicationService

router = APIRouter(tags=["retrieval-v2"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
ConfigDep = Annotated[ServerConfig, Depends(get_server_config)]


@router.post("/retrieval/automatic", response_model=AutomaticQueryV2Response)
async def query_notebook_v2(
    request: Request, body: AutomaticQueryV2Request, engine: EngineDep, config: ConfigDep
) -> AutomaticQueryV2Response:
    principal = principal_from_claims(getattr(request.state, "auth", None))
    return await AutomaticQueryV2ApplicationService(engine, config).execute(body, principal)


@router.post("/retrieval/evidence", response_model=EvidenceSearchResponse)
async def search_evidence(
    request: Request, body: EvidenceSearchRequest, engine: EngineDep, config: ConfigDep
) -> EvidenceSearchResponse:
    principal = principal_from_claims(getattr(request.state, "auth", None))
    return await EvidenceRetrievalApplicationService(engine, config).execute(body, principal)
