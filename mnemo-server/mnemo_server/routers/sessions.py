"""FastAPI router for conversation session and turn management endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, status
from mnemo.engine import KnowledgeEngine

from ..dependencies import get_engine
from ..schemas.common import PageResponse
from ..schemas.sessions import (
    CreateSessionRequest,
    CreateTurnRequest,
    SessionDetailResponse,
    SessionSummaryResponse,
    TurnResponse,
)
from ..services.sessions import SessionService

router = APIRouter(prefix="/notebooks", tags=["sessions"])

EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
NotebookIdPath = Annotated[UUID, Path(description="The unique notebook ID")]
SessionIdPath = Annotated[UUID, Path(description="The unique session ID")]


@router.get(
    "/{notebook_id}/sessions",
    response_model=PageResponse[SessionSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List sessions for a notebook",
)
async def list_sessions(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor UUID")] = None,
) -> PageResponse[SessionSummaryResponse]:
    """Return a keyset-paginated list of sessions attached to a notebook."""
    service = SessionService(engine)
    return await service.list_sessions(notebook_id, limit=limit, cursor=cursor)


@router.post(
    "/{notebook_id}/sessions",
    response_model=SessionSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation session",
)
async def create_session(
    notebook_id: NotebookIdPath,
    request: CreateSessionRequest,
    engine: EngineDep,
) -> SessionSummaryResponse:
    """Create a new conversational session attached to a notebook."""
    service = SessionService(engine)
    return await service.create_session(notebook_id, request)


@router.get(
    "/{notebook_id}/sessions/{session_id}",
    response_model=SessionDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get conversation session history",
)
async def get_session(
    notebook_id: NotebookIdPath,
    session_id: SessionIdPath,
    engine: EngineDep,
) -> SessionDetailResponse:
    """Get full session history with ordered turns and citations."""
    service = SessionService(engine)
    return await service.get_session(notebook_id, session_id)


@router.post(
    "/{notebook_id}/sessions/{session_id}/turns",
    response_model=TurnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a turn to a session",
)
async def append_turn(
    notebook_id: NotebookIdPath,
    session_id: SessionIdPath,
    request: CreateTurnRequest,
    engine: EngineDep,
) -> TurnResponse:
    """Append one user or assistant message turn to a session."""
    service = SessionService(engine)
    return await service.append_turn(notebook_id, session_id, request)


@router.delete(
    "/{notebook_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a conversation session",
)
async def delete_session(
    notebook_id: NotebookIdPath,
    session_id: SessionIdPath,
    engine: EngineDep,
) -> Response:
    """Delete a conversation session and all associated turns and citations."""
    service = SessionService(engine)
    await service.delete_session(notebook_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
