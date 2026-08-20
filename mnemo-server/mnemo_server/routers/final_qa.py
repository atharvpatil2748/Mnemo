"""ADR-0055 persisted Final-QA endpoint."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from mnemo.engine import KnowledgeEngine

from ..dependencies import get_engine
from ..schemas.final_qa import FinalQARequestBody, FinalQAResponse
from ..services.final_qa import FinalQAService

router = APIRouter(prefix="/notebooks", tags=["final-qa"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]


@router.post("/{notebook_id}/final-qa", response_model=FinalQAResponse)
async def final_qa_endpoint(
    notebook_id: Annotated[UUID, Path()], payload: FinalQARequestBody, engine: EngineDep
) -> FinalQAResponse:
    return await FinalQAService(engine).execute(notebook_id, payload)
