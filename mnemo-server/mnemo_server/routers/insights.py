"""FastAPI router for insight listing and generation endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, status
from mnemo.engine import KnowledgeEngine
from mnemo.models.notebook import InsightType

from ..dependencies import get_engine, require_integrated_membership_route
from ..schemas.common import PageResponse
from ..schemas.insights import InsightResponse
from ..services.authorized_scope import AuthorizedNotebookPageCursor
from ..services.insights import InsightService
from ..services.membership_http import membership_http_principal

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
    request: Request,
    notebook_id: NotebookIdPath,
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor UUID")] = None,
    type: Annotated[
        InsightType | None, Query(description="Optional filter by insight type")
    ] = None,
) -> PageResponse[InsightResponse]:
    """Return a keyset-paginated list of insights extracted for a notebook."""
    principal = (
        membership_http_principal(request, engine)
        if getattr(engine, "server_scope_authority", None) is not None
        else None
    )
    page_cursor = (
        AuthorizedNotebookPageCursor(
            request.app.state.server_config.delivery_cursor_secret.encode()
        )
        if principal is not None
        else None
    )
    service = InsightService(engine, principal=principal, page_cursor=page_cursor)
    return await service.list_insights(notebook_id, limit=limit, cursor=cursor, insight_type=type)


@router.post(
    "/{notebook_id}/insights/generate",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Trigger automated insight generation",
    dependencies=[Depends(require_integrated_membership_route)],
)
async def generate_insights(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
) -> None:
    """Trigger automated insight generation. Formally deferred to Phase 10."""
    service = InsightService(engine)
    await service.generate_insights(notebook_id)
