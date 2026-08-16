"""FastAPI router for notebook CRUD, activity timeline, summaries, and graph."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Path, Query, Response, status
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces.errors import NotFoundError
from mnemo.models import FrozenMetadata, InsightType, Notebook

from ..dependencies import get_engine
from ..schemas.common import PageResponse
from ..schemas.graph import EntityGraphResponse, GraphNodeResponse
from ..schemas.notebooks import (
    CreateNotebookRequest,
    NotebookResponse,
    UpdateNotebookRequest,
)
from ..schemas.summary import NotebookSummaryResponse, SummaryItemResponse
from ..schemas.timeline import TimelineEventResponse, TimelineResponse

router = APIRouter(prefix="/notebooks", tags=["notebooks"])

EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
NotebookIdPath = Annotated[UUID, Path(description="The unique notebook ID")]


def _unpack_metadata(meta: Any) -> dict[str, Any]:
    """Recursively unpack FrozenMetadata into a standard JSON dictionary."""
    if isinstance(meta, Mapping):
        return {k: _unpack_value(v) for k, v in meta.items()}
    return {}


def _unpack_value(v: Any) -> Any:
    """Recursively unpack FrozenMetadata and tuples into python primitives."""
    if isinstance(v, Mapping):
        return _unpack_metadata(v)
    if isinstance(v, (tuple, list)):
        return [_unpack_value(item) for item in v]
    return v


def _notebook_to_dto(notebook: Notebook) -> NotebookResponse:
    """Convert a frozen core Notebook dataclass to a transport NotebookResponse DTO."""
    return NotebookResponse(
        notebook_id=notebook.notebook_id,
        title=notebook.title,
        description=notebook.description,
        created_at=notebook.created_at,
        updated_at=notebook.updated_at,
        metadata=_unpack_metadata(notebook.metadata),
    )


@router.post(
    "",
    response_model=NotebookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new notebook",
)
async def create_notebook(
    body: CreateNotebookRequest,
    engine: EngineDep,
) -> NotebookResponse:
    """Create a new notebook collection with generated identity and UTC timestamps."""
    notebook_id = uuid4()
    now = datetime.now(UTC)
    notebook = Notebook(
        notebook_id=notebook_id,
        title=body.title,
        description=body.description,
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata(body.metadata),
    )
    await engine.storage.upsert_notebook(notebook)
    return _notebook_to_dto(notebook)


@router.get(
    "",
    response_model=PageResponse[NotebookResponse],
    status_code=status.HTTP_200_OK,
    summary="List notebooks",
)
async def list_notebooks(
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Number of items to return")] = 50,
    cursor: Annotated[UUID | None, Query(description="Keyset cursor from previous page")] = None,
) -> PageResponse[NotebookResponse]:
    """List notebooks using keyset cursor pagination."""
    cursor_str = str(cursor) if cursor is not None else None
    page = await engine.storage.list_notebooks(limit=limit, cursor=cursor_str)
    items = [_notebook_to_dto(item) for item in page.items]
    return PageResponse[NotebookResponse](
        items=items,
        next_cursor=page.next_cursor,
        limit=limit,
    )


@router.get(
    "/{notebook_id}",
    response_model=NotebookResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a notebook by ID",
)
async def get_notebook(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
) -> NotebookResponse:
    """Retrieve details for a single notebook."""
    notebook = await engine.storage.get_notebook(notebook_id)
    if notebook is None:
        raise NotFoundError(f"Notebook {notebook_id} was not found")
    return _notebook_to_dto(notebook)


@router.patch(
    "/{notebook_id}",
    response_model=NotebookResponse,
    status_code=status.HTTP_200_OK,
    summary="Update notebook metadata",
)
async def update_notebook(
    body: UpdateNotebookRequest,
    notebook_id: NotebookIdPath,
    engine: EngineDep,
) -> NotebookResponse:
    """Partially update notebook title, description, or metadata (Last-Write-Wins)."""
    existing = await engine.storage.get_notebook(notebook_id)
    if existing is None:
        raise NotFoundError(f"Notebook {notebook_id} was not found")

    title = body.title if body.title is not None else existing.title
    description = body.description if body.description is not None else existing.description

    metadata_dict = _unpack_metadata(existing.metadata)
    if body.metadata is not None:
        metadata_dict.update(body.metadata)

    updated = Notebook(
        notebook_id=existing.notebook_id,
        title=title,
        description=description,
        created_at=existing.created_at,
        updated_at=datetime.now(UTC),
        metadata=FrozenMetadata(metadata_dict),
    )
    await engine.storage.upsert_notebook(updated)
    return _notebook_to_dto(updated)


@router.delete(
    "/{notebook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a notebook",
)
async def delete_notebook(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
) -> Response:
    """Delete a notebook and cascade-clean all associated notes, sources, and sessions."""
    deleted = await engine.storage.delete_notebook(notebook_id)
    if not deleted:
        raise NotFoundError(f"Notebook {notebook_id} was not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{notebook_id}/summary",
    response_model=NotebookSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get notebook summaries",
)
async def get_notebook_summary(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
) -> NotebookSummaryResponse:
    """Retrieve already-persisted summary insights for a notebook (read-only)."""
    existing = await engine.storage.get_notebook(notebook_id)
    if existing is None:
        raise NotFoundError(f"Notebook {notebook_id} was not found")

    page = await engine.storage.list_insights(notebook_id=notebook_id, limit=50, cursor=None)
    summaries = [
        SummaryItemResponse(
            insight_id=item.insight_id,
            source_id=item.source_id,
            content=item.content,
            confidence=item.confidence,
            created_at=item.created_at,
        )
        for item in page.items
        if item.type == InsightType.SUMMARY
    ]
    status_val: Literal["ready", "empty"] = "ready" if summaries else "empty"
    return NotebookSummaryResponse(
        notebook_id=notebook_id,
        summaries=summaries,
        status=status_val,
    )


@router.get(
    "/{notebook_id}/timeline",
    response_model=TimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Get notebook activity timeline",
)
async def get_notebook_timeline(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Max timeline events to return")] = 50,
) -> TimelineResponse:
    """Retrieve chronological activity events for a notebook."""
    existing = await engine.storage.get_notebook(notebook_id)
    if existing is None:
        raise NotFoundError(f"Notebook {notebook_id} was not found")

    sources_page = await engine.storage.list_sources(
        notebook_id=notebook_id, limit=1000, cursor=None
    )
    notes_page = await engine.storage.list_notes(notebook_id=notebook_id, limit=1000, cursor=None)
    sessions_page = await engine.storage.list_sessions(
        notebook_id=notebook_id, limit=1000, cursor=None
    )

    events: list[TimelineEventResponse] = []
    for s in sources_page.items:
        events.append(
            TimelineEventResponse(
                event_type="source_added",
                event_id=s.source_id,
                timestamp=s.created_at,
                title="Source Added",
                details={"document_id": str(s.document_id)},
            )
        )
    for n in notes_page.items:
        events.append(
            TimelineEventResponse(
                event_type="note_created",
                event_id=n.note_id,
                timestamp=n.created_at,
                title=n.title or "Untitled Note",
                details={"origin": str(n.origin)},
            )
        )
    for sess in sessions_page.items:
        events.append(
            TimelineEventResponse(
                event_type="session_started",
                event_id=sess.session_id,
                timestamp=sess.created_at,
                title=sess.title or "New Conversation",
                details={},
            )
        )

    # Sort descending by timestamp (most recent first) and slice to requested limit
    events.sort(key=lambda e: e.timestamp, reverse=True)
    sliced_events = events[:limit]

    return TimelineResponse(
        notebook_id=notebook_id,
        events=sliced_events,
        total=len(sliced_events),
    )


@router.get(
    "/{notebook_id}/graph",
    response_model=EntityGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Get entity knowledge graph",
)
async def get_notebook_graph(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=500, description="Max entity nodes to return")] = 100,
) -> EntityGraphResponse:
    """Retrieve entity knowledge graph nodes for a notebook (nodes only)."""
    existing = await engine.storage.get_notebook(notebook_id)
    if existing is None:
        raise NotFoundError(f"Notebook {notebook_id} was not found")

    if not engine.storage.capabilities().supports_graph:
        return EntityGraphResponse(
            notebook_id=notebook_id,
            nodes=[],
            edges=[],
            status="disabled",
        )

    sources_page = await engine.storage.list_sources(
        notebook_id=notebook_id, limit=1000, cursor=None
    )
    doc_ids = tuple(s.document_id for s in sources_page.items)

    if not doc_ids:
        return EntityGraphResponse(
            notebook_id=notebook_id,
            nodes=[],
            edges=[],
            status="empty",
        )

    entities = await engine.storage.find_entities(
        canonical_name="",
        entity_type=None,
        document_ids=doc_ids,
        limit=limit,
    )

    nodes = [
        GraphNodeResponse(
            entity_id=e.entity_id,
            canonical_name=e.canonical_name,
            type=e.type,
            confidence=e.confidence,
            document_id=e.document_id,
            aliases=list(e.aliases),
        )
        for e in entities
    ]

    status_val: Literal["active", "disabled", "empty"] = "active" if nodes else "empty"
    return EntityGraphResponse(
        notebook_id=notebook_id,
        nodes=nodes,
        edges=[],
        status=status_val,
    )
