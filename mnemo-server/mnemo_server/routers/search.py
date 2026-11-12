"""REST router for POST /v1/search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine
from mnemo_server.schemas.search import SearchRequest, SearchResponse
from mnemo_server.services.authorized_scope import AuthorizedNotebookScopeResolver
from mnemo_server.services.membership_http import membership_http_principal
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
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
    request: Request,
    payload: SearchRequest,
    engine: EngineDep,
) -> SearchResponse:
    """Execute global or notebook-scoped multi-mode search without LLM synthesis."""
    authority = getattr(engine, "server_scope_authority", None)
    service = SearchService(engine=engine)
    if authority is None:
        config = getattr(request.app.state, "server_config", None)
        if (isinstance(config, ServerConfig) and config.auth_mode == "jwt") or getattr(
            engine, "server_actor_mapper", None
        ) is not None:
            raise DependencyUnavailableError(
                "trusted membership authority is unavailable", retryable=False
            )
        return await service.execute_search(payload)
    if not isinstance(authority, SQLiteNotebookScopeAuthority):
        raise DependencyUnavailableError(
            "trusted membership authority is unavailable", retryable=False
        )
    principal = membership_http_principal(request, engine)
    scope_resolver = AuthorizedNotebookScopeResolver(engine.storage, authority)
    scopes = await scope_resolver.resolve(
        principal, (payload.notebook_id,) if payload.notebook_id is not None else None
    )
    response = await service.execute_search(payload, principal)
    await scope_resolver.revalidate(principal, scopes)
    return response
