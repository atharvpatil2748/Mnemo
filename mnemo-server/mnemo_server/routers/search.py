"""REST router for POST /v1/search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from mnemo.engine import KnowledgeEngine

from mnemo_server.dependencies import get_engine
from mnemo_server.schemas.search import SearchRequest, SearchResponse
from mnemo_server.services.search import SearchService

router = APIRouter(tags=["search"])

EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]


@router.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute multi-mode search without synthesis",
    description="Performs dense/sparse/hybrid retrieval with RRF fusion and optional reranking.",
)
async def search_endpoint(
    payload: SearchRequest,
    engine: EngineDep,
) -> SearchResponse:
    """Execute global or notebook-scoped multi-mode search without LLM synthesis."""
    service = SearchService(engine=engine)
    return await service.execute_search(payload)
