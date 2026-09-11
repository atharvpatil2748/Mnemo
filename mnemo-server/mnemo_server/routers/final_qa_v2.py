"""Thin HTTP adapter for Final-QA V2."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from mnemo.engine import KnowledgeEngine

from ..dependencies import get_engine, get_server_config
from ..schemas.final_qa_v2 import FinalQAV2RequestBody, FinalQAV2Response
from ..services.authorization import principal_from_claims
from ..services.final_qa_v2 import FinalQAV2ApplicationService

router = APIRouter(prefix="/notebooks", tags=["final-qa-v2"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]


@router.post("/{notebook_id}/final-qa", response_model=FinalQAV2Response)
async def final_qa_v2_endpoint(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    payload: FinalQAV2RequestBody,
    engine: EngineDep,
) -> FinalQAV2Response:
    config = get_server_config(request)
    principal = principal_from_claims(getattr(request.state, "auth", None))
    return await FinalQAV2ApplicationService(engine, config).execute(
        notebook_id, payload, principal
    )
