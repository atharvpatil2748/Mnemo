"""Service orchestrating note creation, listing, retrieval, update, and deletion."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    DependencyUnavailableError,
    NotFoundError,
    PrincipalContextV1,
)
from mnemo.models import FrozenMetadata, thaw_metadata
from mnemo.models.notebook import Note
from mnemo.storage.sqlite import SQLiteStore

from ..schemas.common import PageResponse
from ..schemas.notes import CreateNoteRequest, NoteResponse, UpdateNoteRequest
from .authorized_scope import (
    AuthorizedNotebookPageCursor,
    AuthorizedNotebookScope,
    AuthorizedNotebookScopeResolver,
)
from .scope_authority import SQLiteNotebookScopeAuthority


class NoteService:
    """Service layer coordinating note operations with frozen storage."""

    def __init__(
        self,
        engine: KnowledgeEngine,
        *,
        principal: PrincipalContextV1 | None = None,
        page_cursor: AuthorizedNotebookPageCursor | None = None,
    ) -> None:
        self._engine = engine
        self._principal = principal
        self._page_cursor = page_cursor

    async def _read_scope(self, notebook_id: UUID) -> AuthorizedNotebookScope | None:
        authority = getattr(self._engine, "server_scope_authority", None)
        if authority is None:
            return None
        if not isinstance(authority, SQLiteNotebookScopeAuthority) or self._principal is None:
            raise PermissionError("trusted membership authority is unavailable")
        if not isinstance(self._engine.storage, SQLiteStore):
            raise DependencyUnavailableError("governed notebook write store is unavailable")
        return (
            await AuthorizedNotebookScopeResolver(self._engine.storage, authority).resolve(
                self._principal, (notebook_id,)
            )
        )[0]

    async def _revalidate(self, scope: AuthorizedNotebookScope | None) -> None:
        if scope is None:
            return
        authority = getattr(self._engine, "server_scope_authority", None)
        if not isinstance(authority, SQLiteNotebookScopeAuthority) or self._principal is None:
            raise PermissionError("trusted membership authority is unavailable")
        await AuthorizedNotebookScopeResolver(self._engine.storage, authority).revalidate(
            self._principal, (scope,)
        )

    def _mutation_lease(self, notebook_id: UUID) -> AbstractContextManager[int | None]:
        authority = getattr(self._engine, "server_scope_authority", None)
        if authority is None:
            return nullcontext(None)
        if not isinstance(authority, SQLiteNotebookScopeAuthority) or self._principal is None:
            raise PermissionError("trusted membership authority is unavailable")
        if not self._principal.authenticated:
            raise PermissionError("authenticated principal is required")
        return authority.owner_write_lease(
            actor_id=self._principal.actor_id, notebook_id=notebook_id
        )

    async def list_notes(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> PageResponse[NoteResponse]:
        """List notes in a notebook with keyset pagination."""
        scope = await self._read_scope(notebook_id)
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        if scope is not None:
            if self._principal is None or self._page_cursor is None:
                raise PermissionError("trusted continuation authority is unavailable")
            if cursor is not None:
                cursor = self._page_cursor.decode(
                    cursor,
                    domain="mnemo-note-list/v1",
                    principal=self._principal,
                    scope=scope,
                    limit=limit,
                )

        if cursor is not None:
            try:
                UUID(cursor)
            except ValueError as err:
                raise ContractValidationError(f"Invalid cursor format: {cursor}") from err

        page = await self._engine.storage.list_notes(notebook_id, limit=limit, cursor=cursor)
        if scope is not None and any(item.notebook_id != notebook_id for item in page.items):
            raise NotFoundError("authorized resource was not found")
        items = [
            NoteResponse(
                note_id=n.note_id,
                notebook_id=n.notebook_id,
                title=n.title,
                content=n.content,
                origin=n.origin,
                created_at=n.created_at,
                updated_at=n.updated_at,
                metadata=thaw_metadata(n.metadata),
            )
            for n in page.items
        ]
        await self._revalidate(scope)
        next_cursor = page.next_cursor
        if scope is not None and next_cursor is not None:
            if self._principal is None or self._page_cursor is None:
                raise PermissionError("trusted continuation authority is unavailable")
            next_cursor = self._page_cursor.encode(
                next_cursor,
                domain="mnemo-note-list/v1",
                principal=self._principal,
                scope=scope,
                limit=limit,
            )
        response = PageResponse(items=items, next_cursor=next_cursor, limit=limit)
        return response

    async def create_note(
        self,
        notebook_id: UUID,
        request: CreateNoteRequest,
    ) -> NoteResponse:
        """Create a new note in a notebook."""
        with self._mutation_lease(notebook_id):
            nb = await self._engine.storage.get_notebook(notebook_id)
            if nb is None:
                raise NotFoundError(f"Notebook {notebook_id} not found")

            now = datetime.now(UTC)
            note_id = uuid4()
            note = Note(
                note_id=note_id,
                notebook_id=notebook_id,
                title=request.title.strip() if request.title else None,
                content=request.content.strip(),
                origin=request.origin,
                created_at=now,
                updated_at=now,
                metadata=FrozenMetadata(request.metadata),
            )
            await self._engine.storage.upsert_note(note)
            return NoteResponse(
                note_id=note.note_id,
                notebook_id=note.notebook_id,
                title=note.title,
                content=note.content,
                origin=note.origin,
                created_at=note.created_at,
                updated_at=note.updated_at,
                metadata=thaw_metadata(note.metadata),
            )

    async def get_note(
        self,
        notebook_id: UUID,
        note_id: UUID,
    ) -> NoteResponse:
        """Get a note by ID with notebook ownership verification."""
        scope = await self._read_scope(notebook_id)
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        note = await self._engine.storage.get_note(note_id)
        if note is None or note.notebook_id != notebook_id:
            raise NotFoundError(f"Note {note_id} not found in notebook {notebook_id}")

        response = NoteResponse(
            note_id=note.note_id,
            notebook_id=note.notebook_id,
            title=note.title,
            content=note.content,
            origin=note.origin,
            created_at=note.created_at,
            updated_at=note.updated_at,
            metadata=thaw_metadata(note.metadata),
        )
        await self._revalidate(scope)
        return response

    async def update_note(
        self,
        notebook_id: UUID,
        note_id: UUID,
        request: UpdateNoteRequest,
    ) -> NoteResponse:
        """Update a note via PATCH with Last-Write-Wins semantics."""
        if request.title is None and request.content is None and request.metadata is None:
            raise ContractValidationError("At least one field must be provided for update")
        with self._mutation_lease(notebook_id):
            nb = await self._engine.storage.get_notebook(notebook_id)
            if nb is None:
                raise NotFoundError(f"Notebook {notebook_id} not found")

            note = await self._engine.storage.get_note(note_id)
            if note is None or note.notebook_id != notebook_id:
                raise NotFoundError(f"Note {note_id} not found in notebook {notebook_id}")

            now = datetime.now(UTC)
            new_title = request.title.strip() if request.title is not None else note.title
            new_content = request.content.strip() if request.content is not None else note.content
            new_metadata = (
                FrozenMetadata(request.metadata) if request.metadata is not None else note.metadata
            )

            updated_note = replace(
                note,
                title=new_title,
                content=new_content,
                metadata=new_metadata,
                updated_at=now,
            )
            await self._engine.storage.upsert_note(updated_note)
            return NoteResponse(
                note_id=updated_note.note_id,
                notebook_id=updated_note.notebook_id,
                title=updated_note.title,
                content=updated_note.content,
                origin=updated_note.origin,
                created_at=updated_note.created_at,
                updated_at=updated_note.updated_at,
                metadata=thaw_metadata(updated_note.metadata),
            )

    async def delete_note(
        self,
        notebook_id: UUID,
        note_id: UUID,
    ) -> None:
        """Delete a note."""
        with self._mutation_lease(notebook_id):
            nb = await self._engine.storage.get_notebook(notebook_id)
            if nb is None:
                raise NotFoundError(f"Notebook {notebook_id} not found")

            note = await self._engine.storage.get_note(note_id)
            if note is None or note.notebook_id != notebook_id:
                raise NotFoundError(f"Note {note_id} not found in notebook {notebook_id}")

            deleted = await self._engine.storage.delete_note(note_id)
            if not deleted:
                raise NotFoundError(f"Note {note_id} not found")
