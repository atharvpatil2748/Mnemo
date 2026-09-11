"""Additive Phase 8.5 bounded resource-delivery HTTP routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import StreamingResponse
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError
from mnemo.models import (
    AssetAnalysisModality,
    AssetAnalysisSelection,
    AssetAnalysisSelector,
    BinaryDelivery,
    DeliveryRequest,
    DeliveryView,
)

from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_server_config
from mnemo_server.schemas.delivery import (
    DeliveryResponseBody,
    DocumentExpansionRequestBody,
)
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
    principal_from_claims,
)
from mnemo_server.services.delivery import build_delivery_service, delivery_response_body

router = APIRouter(tags=["delivery-v2"])
EngineDep = Annotated[KnowledgeEngine, Depends(get_engine)]
ConfigDep = Annotated[ServerConfig, Depends(get_server_config)]


@router.get(
    "/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}",
    response_model=DeliveryResponseBody,
)
async def get_document_delivery(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    document_id: Annotated[UUID, Path()],
    version_id: Annotated[UUID, Path()],
    engine: EngineDep,
    config: ConfigDep,
    cursor: Annotated[str | None, Query()] = None,
    max_bytes: Annotated[int | None, Query(ge=1)] = None,
    max_items: Annotated[int | None, Query(ge=1)] = None,
) -> DeliveryResponseBody:
    await _authorize_document(request, engine, notebook_id, document_id, version_id)
    result = await build_delivery_service(engine, config).expand_document(
        DeliveryRequest(
            notebook_id=notebook_id,
            document_id=document_id,
            version_id=version_id,
            view=DeliveryView.BLOCKS,
            cursor=cursor,
            max_bytes=max_bytes,
            max_items=max_items,
        )
    )
    return delivery_response_body(result)


@router.post(
    "/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/expand",
    response_model=DeliveryResponseBody,
)
async def expand_document_delivery_v2(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    document_id: Annotated[UUID, Path()],
    version_id: Annotated[UUID, Path()],
    body: DocumentExpansionRequestBody,
    engine: EngineDep,
    config: ConfigDep,
) -> DeliveryResponseBody:
    """Resolve exactly one positional selector without semantic ranking."""
    await _authorize_document(request, engine, notebook_id, document_id, version_id)
    result = await build_delivery_service(engine, config).expand_document_v2(
        body.to_core(notebook_id=notebook_id, document_id=document_id, version_id=version_id)
    )
    return delivery_response_body(result)


@router.get("/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/original")
async def get_original_document_delivery(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    document_id: Annotated[UUID, Path()],
    version_id: Annotated[UUID, Path()],
    engine: EngineDep,
    config: ConfigDep,
    cursor: Annotated[str | None, Query()] = None,
    max_bytes: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    await _authorize_document(request, engine, notebook_id, document_id, version_id)
    result = await build_delivery_service(engine, config).get_original_document(
        DeliveryRequest(
            notebook_id=notebook_id,
            document_id=document_id,
            version_id=version_id,
            view=DeliveryView.ORIGINAL,
            cursor=cursor,
            max_bytes=max_bytes,
        )
    )
    headers = _binary_headers(result)
    headers["Content-Disposition"] = f'attachment; filename="document-{document_id}"'
    return StreamingResponse(
        iter((result.content,)),
        media_type=result.media_type,
        headers=headers,
        status_code=206 if result.completeness.value == "truncated" else 200,
    )


@router.get(
    "/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/chunks/{chunk_id}",
    response_model=DeliveryResponseBody,
)
async def get_document_chunk_delivery(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    document_id: Annotated[UUID, Path()],
    version_id: Annotated[UUID, Path()],
    chunk_id: Annotated[str, Path(min_length=64, max_length=64)],
    engine: EngineDep,
    config: ConfigDep,
) -> DeliveryResponseBody:
    await _authorize_document(request, engine, notebook_id, document_id, version_id)
    result = await build_delivery_service(engine, config).get_document_chunk(
        notebook_id=notebook_id,
        document_id=document_id,
        version_id=version_id,
        chunk_id=chunk_id,
    )
    return delivery_response_body(result)


@router.get(
    "/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/assets",
    response_model=DeliveryResponseBody,
)
async def list_document_assets_delivery(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    document_id: Annotated[UUID, Path()],
    version_id: Annotated[UUID, Path()],
    engine: EngineDep,
    config: ConfigDep,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> DeliveryResponseBody:
    await _authorize_document(request, engine, notebook_id, document_id, version_id)
    result = await build_delivery_service(engine, config).list_assets(
        notebook_id=notebook_id,
        document_id=document_id,
        version_id=version_id,
        cursor=cursor,
        limit=limit,
    )
    return delivery_response_body(result)


@router.get("/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content")
async def get_asset_delivery(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    occurrence_id: Annotated[UUID, Path()],
    engine: EngineDep,
    config: ConfigDep,
    cursor: Annotated[str | None, Query()] = None,
    max_bytes: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    await _authorize_notebook(request, engine, notebook_id)
    result = await build_delivery_service(engine, config).get_asset(
        notebook_id=notebook_id,
        occurrence_id=occurrence_id,
        cursor=cursor,
        max_bytes=max_bytes,
    )
    headers = _binary_headers(result)
    headers["Content-Disposition"] = "inline"
    return StreamingResponse(
        iter((result.content,)),
        media_type=result.media_type,
        headers=headers,
        status_code=206 if result.completeness.value == "truncated" else 200,
    )


@router.get(
    "/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis",
    response_model=DeliveryResponseBody,
)
async def get_asset_analysis_delivery(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    occurrence_id: Annotated[UUID, Path()],
    engine: EngineDep,
    config: ConfigDep,
    ocr_derivation_id: Annotated[UUID | None, Query()] = None,
    vision_derivation_id: Annotated[UUID | None, Query()] = None,
    selection: Annotated[AssetAnalysisSelection | None, Query()] = None,
    modalities: Annotated[list[AssetAnalysisModality] | None, Query()] = None,
    profile: Annotated[str | None, Query(min_length=1)] = None,
) -> DeliveryResponseBody:
    await _authorize_notebook(request, engine, notebook_id)
    service = build_delivery_service(engine, config)
    if selection is None and modalities is None and profile is None:
        result = await service.get_image_analysis(
            notebook_id=notebook_id,
            occurrence_id=occurrence_id,
            ocr_derivation_id=ocr_derivation_id,
            vision_derivation_id=vision_derivation_id,
        )
    else:
        try:
            selector = AssetAnalysisSelector(
                selection=selection or AssetAnalysisSelection.EXPLICIT,
                modalities=tuple(
                    modalities or (AssetAnalysisModality.OCR, AssetAnalysisModality.VISION)
                ),
                derivation_ids=tuple(
                    item for item in (ocr_derivation_id, vision_derivation_id) if item is not None
                ),
                profile=profile,
            )
        except (TypeError, ValueError) as error:
            raise ContractValidationError("analysis selection is invalid") from error
        result = await service.get_image_analysis_v2(
            notebook_id=notebook_id, occurrence_id=occurrence_id, selector=selector
        )
    return delivery_response_body(result)


@router.get(
    "/notebooks/{notebook_id}/final-qa/{assistant_turn_id}/evidence",
    response_model=DeliveryResponseBody,
)
async def get_final_qa_v2_evidence_delivery(
    request: Request,
    notebook_id: Annotated[UUID, Path()],
    assistant_turn_id: Annotated[UUID, Path()],
    engine: EngineDep,
    config: ConfigDep,
    cursor: Annotated[str | None, Query()] = None,
) -> DeliveryResponseBody:
    await _authorize_notebook(request, engine, notebook_id)
    result = await build_delivery_service(engine, config).get_final_qa_evidence(
        notebook_id=notebook_id,
        assistant_turn_id=assistant_turn_id,
        cursor=cursor,
    )
    return delivery_response_body(result)


async def _authorize_notebook(request: Request, engine: KnowledgeEngine, notebook_id: UUID) -> None:
    if type(engine) is not KnowledgeEngine:
        return
    principal = principal_from_claims(getattr(request.state, "auth", None))
    await CentralAuthorizationServiceV1(engine).authorize_notebook(
        principal, notebook_id, AuthorizationOperationV1.DELIVER
    )


async def _authorize_document(
    request: Request,
    engine: KnowledgeEngine,
    notebook_id: UUID,
    document_id: UUID,
    version_id: UUID,
) -> None:
    if type(engine) is not KnowledgeEngine:
        return
    principal = principal_from_claims(getattr(request.state, "auth", None))
    await CentralAuthorizationServiceV1(engine).authorize_document(
        principal,
        notebook_id,
        document_id,
        version_id,
        AuthorizationOperationV1.DELIVER,
    )


def _binary_headers(result: BinaryDelivery) -> dict[str, str]:
    start = result.range_start
    end = start + len(result.content) - 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{result.total_byte_size}",
        "X-Mnemo-Completeness": result.completeness.value,
        "X-Mnemo-Content-SHA256": result.content_hash,
        "X-Mnemo-Snapshot": result.snapshot_identity,
        "X-Mnemo-Next-Cursor": result.next_cursor or "",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Length": str(len(result.content)),
        "X-Mnemo-Notebook-Id": str(result.attribution.notebook_id),
        "X-Mnemo-Source-Id": str(result.attribution.source_id),
        "X-Mnemo-Document-Id": str(result.attribution.document_id),
        "X-Mnemo-Version-Id": str(result.attribution.version_id),
    }
    if result.attribution.asset_id is not None:
        headers["X-Mnemo-Asset-Id"] = str(result.attribution.asset_id)
    if result.attribution.occurrence_id is not None:
        headers["X-Mnemo-Occurrence-Id"] = str(result.attribution.occurrence_id)
    return headers
