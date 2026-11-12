"""Service orchestrating conversation session management, turn appending, and citation retrieval."""

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
from mnemo.models.notebook import Session, Turn
from mnemo.storage.sqlite import SQLiteStore

from ..schemas.common import PageResponse
from ..schemas.sessions import (
    CitationItemResponse,
    CreateSessionRequest,
    CreateTurnRequest,
    SessionDetailResponse,
    SessionSummaryResponse,
    TurnResponse,
)
from .authorized_scope import (
    AuthorizedNotebookPageCursor,
    AuthorizedNotebookScope,
    AuthorizedNotebookScopeResolver,
)
from .scope_authority import SQLiteNotebookScopeAuthority


class SessionService:
    """Service layer coordinating session operations with frozen storage."""

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
        if not isinstance(self._engine.storage, SQLiteStore):
            raise DependencyUnavailableError("governed notebook write store is unavailable")
        if not self._principal.authenticated:
            raise PermissionError("authenticated principal is required")
        return authority.owner_write_lease(
            actor_id=self._principal.actor_id, notebook_id=notebook_id
        )

    async def list_sessions(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> PageResponse[SessionSummaryResponse]:
        """List sessions in a notebook with keyset pagination."""
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
                    domain="mnemo-session-list/v1",
                    principal=self._principal,
                    scope=scope,
                    limit=limit,
                )

        if cursor is not None:
            try:
                UUID(cursor)
            except ValueError as err:
                raise ContractValidationError(f"Invalid cursor format: {cursor}") from err

        page = await self._engine.storage.list_sessions(notebook_id, limit=limit, cursor=cursor)
        if scope is not None and any(item.notebook_id != notebook_id for item in page.items):
            raise NotFoundError("authorized resource was not found")
        items = [
            SessionSummaryResponse(
                session_id=s.session_id,
                notebook_id=s.notebook_id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                metadata=thaw_metadata(s.metadata),
            )
            for s in page.items
        ]
        await self._revalidate(scope)
        next_cursor = page.next_cursor
        if scope is not None and next_cursor is not None:
            if self._principal is None or self._page_cursor is None:
                raise PermissionError("trusted continuation authority is unavailable")
            next_cursor = self._page_cursor.encode(
                next_cursor,
                domain="mnemo-session-list/v1",
                principal=self._principal,
                scope=scope,
                limit=limit,
            )
        response = PageResponse(items=items, next_cursor=next_cursor, limit=limit)
        return response

    async def create_session(
        self,
        notebook_id: UUID,
        request: CreateSessionRequest,
    ) -> SessionSummaryResponse:
        """Create a new conversational session in a notebook."""
        with self._mutation_lease(notebook_id):
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
                metadata=thaw_metadata(session.metadata),
            )

    async def get_session(
        self,
        notebook_id: UUID,
        session_id: UUID,
    ) -> SessionDetailResponse:
        """Get a session with all its turns and citations."""
        scope = await self._read_scope(notebook_id)
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        session = await self._engine.storage.get_session(session_id)
        if session is None or session.notebook_id != notebook_id:
            raise NotFoundError(f"Session {session_id} not found in notebook {notebook_id}")

        turns_response: list[TurnResponse] = []
        for turn in session.turns:
            citations = await self._engine.storage.get_citations_for_turn(turn.turn_id)
            if scope is not None:
                if self._principal is None:
                    raise PermissionError("trusted membership identity is unavailable")
                for citation in citations:
                    try:
                        await self._engine.document_scope_resolver.resolve_document_scope(
                            self._principal,
                            citation.document_id,
                            citation.version_id,
                            notebook_id,
                        )
                    except (NotFoundError, ContractValidationError) as error:
                        raise NotFoundError("authorized resource was not found") from error
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
                    metadata=thaw_metadata(turn.metadata),
                    citations=citations_dto,
                )
            )

        response = SessionDetailResponse(
            session_id=session.session_id,
            notebook_id=session.notebook_id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            metadata=thaw_metadata(session.metadata),
            turns=turns_response,
        )
        await self._revalidate(scope)
        return response

    async def append_turn(
        self,
        notebook_id: UUID,
        session_id: UUID,
        request: CreateTurnRequest,
    ) -> TurnResponse:
        """Append one conversational turn to a session."""
        with self._mutation_lease(notebook_id):
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
            updated_session = replace(
                session,
                updated_at=now,
                turns=(*session.turns, turn),
            )
            if getattr(self._engine, "server_scope_authority", None) is None:
                # Preserve non-ACL storage implementations' historical call sequence.
                await self._engine.storage.append_turn(session_id, turn)
            # SQLiteStore.upsert_session inserts the session and all turns in
            # one notebook-store transaction under the ACL write lease.
            await self._engine.storage.upsert_session(updated_session)

            return TurnResponse(
                turn_id=turn.turn_id,
                session_id=turn.session_id,
                sequence=turn.sequence,
                role=turn.role,
                content=turn.content,
                created_at=turn.created_at,
                metadata=thaw_metadata(turn.metadata),
                citations=[],
            )

    async def delete_session(
        self,
        notebook_id: UUID,
        session_id: UUID,
    ) -> None:
        """Delete a session."""
        with self._mutation_lease(notebook_id):
            nb = await self._engine.storage.get_notebook(notebook_id)
            if nb is None:
                raise NotFoundError(f"Notebook {notebook_id} not found")

            session = await self._engine.storage.get_session(session_id)
            if session is None or session.notebook_id != notebook_id:
                raise NotFoundError(f"Session {session_id} not found in notebook {notebook_id}")

            deleted = await self._engine.storage.delete_session(session_id)
            if not deleted:
                raise NotFoundError(f"Session {session_id} not found")
