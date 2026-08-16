"""FastAPI router for insight listing and generation endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from mnemo.engine import KnowledgeEngine
from mnemo.models.notebook import InsightType

from ..dependencies import get_engine
from ..schemas.common import PageResponse
from ..schemas.insights import InsightResponse
from ..services.insights import InsightService

router = APIRouter(prefix="/notebooks", tags=["insights"])

EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
NotebookIdPath = Annotated[UUID, Path(description="The unique notebook ID")]


@router.get(
    "/{notebook_id}/insights",
    response_model=PageResponse[InsightResponse],
    status_code=status.HTTP_200_OK,
    summary="List extracted insights for a notebook",
)
async def list_insights(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor UUID")] = None,
    type: Annotated[
        InsightType | None, Query(description="Optional filter by insight type")
    ] = None,
) -> PageResponse[InsightResponse]:
    """Return a keyset-paginated list of insights extracted for a notebook."""
    service = InsightService(engine)
    return await service.list_insights(notebook_id, limit=limit, cursor=cursor, insight_type=type)


@router.post(
    "/{notebook_id}/insights/generate",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Trigger automated insight generation",
)
async def generate_insights(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
) -> None:
    """Trigger automated insight generation. Formally deferred to Phase 10."""
    service = InsightService(engine)
    await service.generate_insights(notebook_id)
