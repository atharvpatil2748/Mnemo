"""Service orchestrating note creation, listing, retrieval, update, and deletion."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError, NotFoundError
from mnemo.models._shared import FrozenMetadata
from mnemo.models.notebook import Note

from ..schemas.common import PageResponse
from ..schemas.notes import CreateNoteRequest, NoteResponse, UpdateNoteRequest


class NoteService:
    """Service layer coordinating note operations with frozen storage."""

    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def list_notes(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> PageResponse[NoteResponse]:
        """List notes in a notebook with keyset pagination."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        if cursor is not None:
            try:
                UUID(cursor)
            except ValueError as err:
                raise ContractValidationError(f"Invalid cursor format: {cursor}") from err

        page = await self._engine.storage.list_notes(notebook_id, limit=limit, cursor=cursor)
        items = [
            NoteResponse(
                note_id=n.note_id,
                notebook_id=n.notebook_id,
                title=n.title,
                content=n.content,
                origin=n.origin,
                created_at=n.created_at,
                updated_at=n.updated_at,
                metadata=dict(n.metadata),
            )
            for n in page.items
        ]
        return PageResponse(items=items, next_cursor=page.next_cursor, limit=limit)

    async def create_note(
        self,
        notebook_id: UUID,
        request: CreateNoteRequest,
    ) -> NoteResponse:
        """Create a new note in a notebook."""
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
            metadata=dict(note.metadata),
        )

    async def get_note(
        self,
        notebook_id: UUID,
        note_id: UUID,
    ) -> NoteResponse:
        """Get a note by ID with notebook ownership verification."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        note = await self._engine.storage.get_note(note_id)
        if note is None or note.notebook_id != notebook_id:
            raise NotFoundError(f"Note {note_id} not found in notebook {notebook_id}")

        return NoteResponse(
            note_id=note.note_id,
            notebook_id=note.notebook_id,
            title=note.title,
            content=note.content,
            origin=note.origin,
            created_at=note.created_at,
            updated_at=note.updated_at,
            metadata=dict(note.metadata),
        )

    async def update_note(
        self,
        notebook_id: UUID,
        note_id: UUID,
        request: UpdateNoteRequest,
    ) -> NoteResponse:
        """Update a note via PATCH with Last-Write-Wins semantics."""
        if request.title is None and request.content is None and request.metadata is None:
            raise ContractValidationError("At least one field must be provided for update")

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
            metadata=dict(updated_note.metadata),
        )

    async def delete_note(
        self,
        notebook_id: UUID,
        note_id: UUID,
    ) -> None:
        """Delete a note."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        note = await self._engine.storage.get_note(note_id)
        if note is None or note.notebook_id != notebook_id:
            raise NotFoundError(f"Note {note_id} not found in notebook {notebook_id}")

        deleted = await self._engine.storage.delete_note(note_id)
        if not deleted:
            raise NotFoundError(f"Note {note_id} not found")
