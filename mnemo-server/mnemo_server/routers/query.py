"""REST router for POST /v1/query."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import TokenCounterInterfaceV1

from mnemo_server.dependencies import get_engine, get_token_counter
from mnemo_server.schemas.query import QueryRequest, QueryResponse
from mnemo_server.services.query import QueryService

router = APIRouter(tags=["query"])

EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
TokenCounterDep = Annotated[TokenCounterInterfaceV1, Depends(get_token_counter)]


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute evidence retrieval and grounded synthesis query",
)
async def query_endpoint(
    payload: QueryRequest,
    engine: EngineDep,
    token_counter: TokenCounterDep,
) -> QueryResponse:
    """Execute evidence retrieval, ranking, context construction, and grounded synthesis."""
    service = QueryService(engine=engine, token_counter=token_counter)
    return await service.execute_query(payload)
