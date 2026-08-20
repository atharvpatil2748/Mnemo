"""Service orchestrating insight listing and generation deferral."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError, NotFoundError
from mnemo.models import thaw_metadata
from mnemo.models.notebook import InsightType

from ..schemas.common import PageResponse
from ..schemas.insights import InsightResponse


class InsightService:
    """Service layer coordinating insight operations with frozen storage."""

    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def list_insights(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
        insight_type: InsightType | None = None,
    ) -> PageResponse[InsightResponse]:
        """List insights in a notebook with keyset pagination and optional type filtering."""
        nb = await self._engine.storage.get_notebook(notebook_id)
        if nb is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")

        if cursor is not None:
            try:
                UUID(cursor)
            except ValueError as err:
                raise ContractValidationError(f"Invalid cursor format: {cursor}") from err

        page = await self._engine.storage.list_insights(notebook_id, limit=limit, cursor=cursor)
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
        return PageResponse(items=items, next_cursor=page.next_cursor, limit=limit)

    async def generate_insights(
        self,
        notebook_id: UUID,
    ) -> None:
        """Trigger insight generation. Formally deferred to Phase 10."""
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
