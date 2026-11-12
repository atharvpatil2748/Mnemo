"""FastAPI router for note CRUD endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from mnemo.engine import KnowledgeEngine

from ..dependencies import (
    get_engine,
    require_mutable_workspace,
)
from ..schemas.common import PageResponse
from ..schemas.notes import CreateNoteRequest, NoteResponse, UpdateNoteRequest
from ..services.authorized_scope import AuthorizedNotebookPageCursor
from ..services.membership_http import membership_http_principal
from ..services.notes import NoteService

router = APIRouter(prefix="/notebooks", tags=["notes"])

EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
NotebookIdPath = Annotated[UUID, Path(description="The unique notebook ID")]
NoteIdPath = Annotated[UUID, Path(description="The unique note ID")]


@router.get(
    "/{notebook_id}/notes",
    response_model=PageResponse[NoteResponse],
    status_code=status.HTTP_200_OK,
    summary="List notes for a notebook",
)
async def list_notes(
    request: Request,
    notebook_id: NotebookIdPath,
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor UUID")] = None,
) -> PageResponse[NoteResponse]:
    """Return a keyset-paginated list of notes in a notebook."""
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
    service = NoteService(engine, principal=principal, page_cursor=page_cursor)
    return await service.list_notes(notebook_id, limit=limit, cursor=cursor)


@router.post(
    "/{notebook_id}/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a note in a notebook",
    dependencies=[Depends(require_mutable_workspace)],
)
async def create_note(
    notebook_id: NotebookIdPath,
    request: CreateNoteRequest,
    engine: EngineDep,
    connection: Request,
) -> NoteResponse:
    """Create a new note in a notebook."""
    principal = (
        membership_http_principal(connection, engine)
        if getattr(engine, "server_scope_authority", None) is not None
        else None
    )
    service = NoteService(engine, principal=principal)
    return await service.create_note(notebook_id, request)


@router.get(
    "/{notebook_id}/notes/{note_id}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a note",
)
async def get_note(
    request: Request,
    notebook_id: NotebookIdPath,
    note_id: NoteIdPath,
    engine: EngineDep,
) -> NoteResponse:
    """Get a specific note by ID."""
    principal = (
        membership_http_principal(request, engine)
        if getattr(engine, "server_scope_authority", None) is not None
        else None
    )
    service = NoteService(engine, principal=principal)
    return await service.get_note(notebook_id, note_id)


@router.patch(
    "/{notebook_id}/notes/{note_id}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a note",
    dependencies=[Depends(require_mutable_workspace)],
)
async def update_note(
    notebook_id: NotebookIdPath,
    note_id: NoteIdPath,
    request: UpdateNoteRequest,
    engine: EngineDep,
    connection: Request,
) -> NoteResponse:
    """Update note fields via PATCH with Last-Write-Wins semantics."""
    principal = (
        membership_http_principal(connection, engine)
        if getattr(engine, "server_scope_authority", None) is not None
        else None
    )
    service = NoteService(engine, principal=principal)
    return await service.update_note(notebook_id, note_id, request)


@router.delete(
    "/{notebook_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a note",
    dependencies=[Depends(require_mutable_workspace)],
)
async def delete_note(
    notebook_id: NotebookIdPath,
    note_id: NoteIdPath,
    engine: EngineDep,
    request: Request,
) -> Response:
    """Delete a note."""
    principal = (
        membership_http_principal(request, engine)
        if getattr(engine, "server_scope_authority", None) is not None
        else None
    )
    service = NoteService(engine, principal=principal)
    await service.delete_note(notebook_id, note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
