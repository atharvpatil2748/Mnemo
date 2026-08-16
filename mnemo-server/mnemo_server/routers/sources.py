"""FastAPI router for source ingestion, listing, retrieval, deletion, and status polling."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi import (
    Path as FastPath,
)
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import TokenCounterInterfaceV1

from ..config import ServerConfig
from ..dependencies import get_engine, get_server_config, get_token_counter
from ..schemas.common import PageResponse
from ..schemas.sources import SourceResponse, SourceStatusResponse
from ..services.ingestion import IngestionService

router = APIRouter(prefix="/notebooks", tags=["sources"])

EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
TokenCounterDep = Annotated[TokenCounterInterfaceV1, Depends(get_token_counter)]
ServerConfigDep = Annotated[ServerConfig, Depends(get_server_config)]
NotebookIdPath = Annotated[UUID, FastPath(description="The unique notebook ID")]
SourceIdPath = Annotated[UUID, FastPath(description="The unique source ID")]


@router.post(
    "/{notebook_id}/sources",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a source file into a notebook",
)
async def ingest_source(
    notebook_id: NotebookIdPath,
    file: Annotated[UploadFile, File(description="Source file to upload and ingest")],
    engine: EngineDep,
    token_counter: TokenCounterDep,
    server_config: ServerConfigDep,
) -> SourceResponse:
    """Upload and ingest a source file into a notebook.

    Performs bounded streaming to enforce maximum upload limits, parsing,
    canonicalization, semantic chunking, dense embedding, and indexing.
    """
    # 1. Bounded chunk streaming reader (1MB slices)
    chunk_size = 1024 * 1024
    chunks: list[bytes] = []
    total_bytes = 0

    while chunk := await file.read(chunk_size):
        total_bytes += len(chunk)
        if total_bytes > server_config.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File upload exceeds maximum permitted size of "
                    f"{server_config.max_upload_bytes} bytes"
                ),
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty (0 bytes)",
        )

    # 2. Sanitize filename
    filename = Path(file.filename or "uploaded_file").name

    # 3. Coordinate ingestion
    service = IngestionService(engine=engine, token_counter=token_counter)
    return await service.ingest_source(
        notebook_id=notebook_id,
        filename=filename,
        data=data,
    )


@router.get(
    "/{notebook_id}/sources",
    response_model=PageResponse[SourceResponse],
    status_code=status.HTTP_200_OK,
    summary="List sources in a notebook",
)
async def list_sources(
    notebook_id: NotebookIdPath,
    engine: EngineDep,
    token_counter: TokenCounterDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Number of items to return")] = 50,
    cursor: Annotated[UUID | None, Query(description="Keyset cursor from previous page")] = None,
) -> PageResponse[SourceResponse]:
    """List sources in a notebook using keyset cursor pagination."""
    cursor_str = str(cursor) if cursor is not None else None
    service = IngestionService(engine=engine, token_counter=token_counter)
    return await service.list_sources(
        notebook_id=notebook_id,
        limit=limit,
        cursor=cursor_str,
    )


@router.get(
    "/{notebook_id}/sources/{source_id}",
    response_model=SourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get source details by ID",
)
async def get_source(
    notebook_id: NotebookIdPath,
    source_id: SourceIdPath,
    engine: EngineDep,
    token_counter: TokenCounterDep,
) -> SourceResponse:
    """Retrieve details and linked document metadata for a single source."""
    service = IngestionService(engine=engine, token_counter=token_counter)
    return await service.get_source(
        notebook_id=notebook_id,
        source_id=source_id,
    )


@router.delete(
    "/{notebook_id}/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a source from a notebook",
)
async def delete_source(
    notebook_id: NotebookIdPath,
    source_id: SourceIdPath,
    engine: EngineDep,
    token_counter: TokenCounterDep,
) -> Response:
    """Delete a source association and refresh vector memberships."""
    service = IngestionService(engine=engine, token_counter=token_counter)
    await service.delete_source(
        notebook_id=notebook_id,
        source_id=source_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{notebook_id}/sources/{source_id}/status",
    response_model=SourceStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ingestion lifecycle status for a source",
)
async def get_source_status(
    notebook_id: NotebookIdPath,
    source_id: SourceIdPath,
    engine: EngineDep,
    token_counter: TokenCounterDep,
) -> SourceStatusResponse:
    """Retrieve persisted document ingestion status for a source."""
    service = IngestionService(engine=engine, token_counter=token_counter)
    return await service.get_source_status(
        notebook_id=notebook_id,
        source_id=source_id,
    )
