"""ADR-0055 persisted Final-QA endpoint."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError

from ..config import ServerConfig
from ..dependencies import get_engine
from ..schemas.final_qa import FinalQARequestBody, FinalQAResponse
from ..services.final_qa import FinalQAService
from ..services.membership_http import membership_http_principal

router = APIRouter(prefix="/notebooks", tags=["final-qa"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]


@router.post("/{notebook_id}/final-qa", response_model=FinalQAResponse)
async def final_qa_endpoint(
    notebook_id: Annotated[UUID, Path()],
    payload: FinalQARequestBody,
    engine: EngineDep,
    request: Request,
) -> FinalQAResponse:
    authority = getattr(engine, "server_scope_authority", None)
    if authority is None:
        config = getattr(request.app.state, "server_config", None)
        if (isinstance(config, ServerConfig) and config.auth_mode == "jwt") or getattr(
            engine, "server_actor_mapper", None
        ) is not None:
            raise DependencyUnavailableError(
                "trusted membership authority is unavailable", retryable=False
            )
    principal = membership_http_principal(request, engine) if authority is not None else None
    return await FinalQAService(engine).execute(notebook_id, payload, principal)
