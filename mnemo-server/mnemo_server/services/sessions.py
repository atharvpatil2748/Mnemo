"""Service orchestrating conversation session management, turn appending, and citation retrieval."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError, NotFoundError
from mnemo.models._shared import FrozenMetadata
from mnemo.models.notebook import Session, Turn

from ..schemas.common import PageResponse
from ..schemas.sessions import (
    CitationItemResponse,
    CreateSessionRequest,
    CreateTurnRequest,
    SessionDetailResponse,
    SessionSummaryResponse,
    TurnResponse,
)


class SessionService:
    """Service layer coordinating session operations with frozen storage."""

    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def list_sessions(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> PageResponse[SessionSummaryResponse]:
        """List sessions in a notebook with keyset pagination."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        if cursor is not None:
            try:
                UUID(cursor)
            except ValueError as err:
                raise ContractValidationError(f"Invalid cursor format: {cursor}") from err

        page = await self._engine.storage.list_sessions(notebook_id, limit=limit, cursor=cursor)
        items = [
            SessionSummaryResponse(
                session_id=s.session_id,
                notebook_id=s.notebook_id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                metadata=dict(s.metadata),
            )
            for s in page.items
        ]
        return PageResponse(items=items, next_cursor=page.next_cursor, limit=limit)

    async def create_session(
        self,
        notebook_id: UUID,
        request: CreateSessionRequest,
    ) -> SessionSummaryResponse:
        """Create a new conversational session in a notebook."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        now = datetime.now(UTC)
        session_id = uuid4()
        session = Session(
            session_id=session_id,
            notebook_id=notebook_id,
            title=request.title.strip() if request.title else None,
            created_at=now,
            updated_at=now,
            turns=(),
            metadata=FrozenMetadata(request.metadata),
        )
        await self._engine.storage.upsert_session(session)
        return SessionSummaryResponse(
            session_id=session.session_id,
            notebook_id=session.notebook_id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            metadata=dict(session.metadata),
        )

    async def get_session(
        self,
        notebook_id: UUID,
        session_id: UUID,
    ) -> SessionDetailResponse:
        """Get a session with all its turns and citations."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        session = await self._engine.storage.get_session(session_id)
        if session is None or session.notebook_id != notebook_id:
            raise NotFoundError(f"Session {session_id} not found in notebook {notebook_id}")

        turns_response: list[TurnResponse] = []
        for turn in session.turns:
            citations = await self._engine.storage.get_citations_for_turn(turn.turn_id)
            citations_dto = [
                CitationItemResponse(
                    citation_id=c.citation_id,
                    turn_id=c.turn_id,
                    source_number=c.source_number,
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    version_id=c.version_id,
                    document_title=c.document_title,
                    verbatim_quote=c.verbatim_quote,
                    page_number=c.page_number,
                    heading_path=list(c.heading_path),
                    created_at=c.created_at,
                )
                for c in citations
            ]
            turns_response.append(
                TurnResponse(
                    turn_id=turn.turn_id,
                    session_id=turn.session_id,
                    sequence=turn.sequence,
                    role=turn.role,
                    content=turn.content,
                    created_at=turn.created_at,
                    metadata=dict(turn.metadata),
                    citations=citations_dto,
                )
            )

        return SessionDetailResponse(
            session_id=session.session_id,
            notebook_id=session.notebook_id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            metadata=dict(session.metadata),
            turns=turns_response,
        )

    async def append_turn(
        self,
        notebook_id: UUID,
        session_id: UUID,
        request: CreateTurnRequest,
    ) -> TurnResponse:
        """Append one conversational turn to a session."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        session = await self._engine.storage.get_session(session_id)
        if session is None or session.notebook_id != notebook_id:
            raise NotFoundError(f"Session {session_id} not found in notebook {notebook_id}")

        now = datetime.now(UTC)
        turn_id = uuid4()
        next_sequence = len(session.turns)
        turn = Turn(
            turn_id=turn_id,
            session_id=session_id,
            sequence=next_sequence,
            role=request.role,
            content=request.content.strip(),
            created_at=now,
            metadata=FrozenMetadata(request.metadata),
        )
        await self._engine.storage.append_turn(session_id, turn)

        updated_session = replace(
            session,
            updated_at=now,
            turns=(*session.turns, turn),
        )
        await self._engine.storage.upsert_session(updated_session)

        return TurnResponse(
            turn_id=turn.turn_id,
            session_id=turn.session_id,
            sequence=turn.sequence,
            role=turn.role,
            content=turn.content,
            created_at=turn.created_at,
            metadata=dict(turn.metadata),
            citations=[],
        )

    async def delete_session(
        self,
        notebook_id: UUID,
        session_id: UUID,
    ) -> None:
        """Delete a session."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        session = await self._engine.storage.get_session(session_id)
        if session is None or session.notebook_id != notebook_id:
            raise NotFoundError(f"Session {session_id} not found in notebook {notebook_id}")

        deleted = await self._engine.storage.delete_session(session_id)
        if not deleted:
            raise NotFoundError(f"Session {session_id} not found")
