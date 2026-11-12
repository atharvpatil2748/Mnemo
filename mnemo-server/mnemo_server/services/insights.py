"""Service orchestrating insight listing and generation deferral."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    DependencyUnavailableError,
    NotFoundError,
    PrincipalContextV1,
)
from mnemo.models import thaw_metadata
from mnemo.models.notebook import InsightType

from ..schemas.common import PageResponse
from ..schemas.insights import InsightResponse
from .authorized_scope import (
    AuthorizedNotebookPageCursor,
    AuthorizedNotebookScope,
    AuthorizedNotebookScopeResolver,
)
from .scope_authority import SQLiteNotebookScopeAuthority


class InsightService:
    """Service layer coordinating insight operations with frozen storage."""

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

    async def list_insights(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
        insight_type: InsightType | None = None,
    ) -> PageResponse[InsightResponse]:
        """List insights in a notebook with keyset pagination and optional type filtering."""
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
                    domain="mnemo-insight-list/v1",
                    principal=self._principal,
                    scope=scope,
                    limit=limit,
                    selector=None if insight_type is None else insight_type.value,
                )

        if cursor is not None:
            try:
                UUID(cursor)
            except ValueError as err:
                raise ContractValidationError(f"Invalid cursor format: {cursor}") from err

        page = await self._engine.storage.list_insights(notebook_id, limit=limit, cursor=cursor)
        if scope is not None:
            for item in page.items:
                source = await self._engine.storage.get_source(item.source_id)
                if (
                    item.notebook_id != notebook_id
                    or source is None
                    or source.notebook_id != notebook_id
                ):
                    raise NotFoundError("authorized resource was not found")
        items = [
            InsightResponse(
                insight_id=ins.insight_id,
                notebook_id=ins.notebook_id,
                source_id=ins.source_id,
                type=ins.type,
                content=ins.content,
                created_at=ins.created_at,
                confidence=ins.confidence,
                metadata=thaw_metadata(ins.metadata),
            )
            for ins in page.items
            if insight_type is None or ins.type is insight_type
        ]
        await self._revalidate(scope)
        next_cursor = page.next_cursor
        if scope is not None and next_cursor is not None:
            if self._principal is None or self._page_cursor is None:
                raise PermissionError("trusted continuation authority is unavailable")
            next_cursor = self._page_cursor.encode(
                next_cursor,
                domain="mnemo-insight-list/v1",
                principal=self._principal,
                scope=scope,
                limit=limit,
                selector=None if insight_type is None else insight_type.value,
            )
        response = PageResponse(items=items, next_cursor=next_cursor, limit=limit)
        return response

    async def generate_insights(
        self,
        notebook_id: UUID,
    ) -> None:
        """Trigger insight generation. Formally deferred to Phase 10."""
        if getattr(self._engine, "server_scope_authority", None) is not None:
            raise DependencyUnavailableError("insight generation lacks governed ACL workflow")
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Automated insight extraction pipeline is scheduled "
                "for Phase 10 (background worker infrastructure)"
            ),
        )
