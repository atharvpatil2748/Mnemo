"""REST router for POST /v1/query."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError, TokenCounterInterfaceV1

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_token_counter
from mnemo_server.schemas.query import QueryRequest, QueryResponse
from mnemo_server.services.authorized_scope import AuthorizedNotebookScopeResolver
from mnemo_server.services.membership_http import membership_http_principal
from mnemo_server.services.query import QueryService
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority

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
    request: Request,
    payload: QueryRequest,
    engine: EngineDep,
    token_counter: TokenCounterDep,
) -> QueryResponse:
    """Execute evidence retrieval, ranking, context construction, and grounded synthesis."""
    authority = getattr(engine, "server_scope_authority", None)
    service = QueryService(engine=engine, token_counter=token_counter)
    if authority is None:
        config = getattr(request.app.state, "server_config", None)
        if (isinstance(config, ServerConfig) and config.auth_mode == "jwt") or getattr(
            engine, "server_actor_mapper", None
        ) is not None:
            raise DependencyUnavailableError(
                "trusted membership authority is unavailable", retryable=False
            )
        return await service.execute_query(payload)
    if not isinstance(authority, SQLiteNotebookScopeAuthority):
        raise DependencyUnavailableError(
            "trusted membership authority is unavailable", retryable=False
        )
    principal = membership_http_principal(request, engine)
    scope_resolver = AuthorizedNotebookScopeResolver(engine.storage, authority)
    scopes = await scope_resolver.resolve(
        principal, (payload.notebook_id,) if payload.notebook_id is not None else None
    )
    response = await service.execute_query(payload, principal)
    await scope_resolver.revalidate(principal, scopes)
    return response
