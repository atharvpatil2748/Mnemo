"""Thin application composition for the shared bounded delivery service."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from mnemo.cursors import CursorCodecV2, CursorSigningKeyV2
from mnemo.delivery import BoundedDocumentExpansionService
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError, PrincipalContextV1
from mnemo.models import DeliveryLimits, DeliveryResponse

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.delivery import DeliveryResponseBody
from mnemo_server.services.source_metadata import (
    AuthorizedSourceMetadataResolverV1,
    SourceMetadataReferenceV1,
)


def build_delivery_service(
    engine: KnowledgeEngine, config: ServerConfig
) -> BoundedDocumentExpansionService:
    codec = CursorCodecV2(
        CursorSigningKeyV2(
            key_id=config.delivery_cursor_key_id,
            secret=config.delivery_cursor_secret.encode("utf-8")
            if len(config.delivery_cursor_secret.encode("utf-8")) >= 32
            else hashlib.sha256(config.delivery_cursor_secret.encode("utf-8")).digest(),
        ),
        verification_keys=tuple(
            CursorSigningKeyV2(key_id=key_id, secret=secret.encode("utf-8"))
            for key_id, secret in config.delivery_cursor_rotation_keys
        ),
        ttl=timedelta(seconds=config.delivery_cursor_ttl_seconds),
    )
    return BoundedDocumentExpansionService(
        storage=engine.storage,
        catalog=engine.asset_catalog,
        limits=DeliveryLimits(
            max_document_bytes=config.max_delivery_document_bytes,
            max_asset_bytes=config.max_delivery_asset_bytes,
            max_assets=config.max_delivery_assets,
            max_response_bytes=config.max_delivery_response_bytes,
        ),
        cursor_secret=config.delivery_cursor_secret.encode("utf-8"),
        cursor_codec=codec,
        legacy_cursor_overlap=timedelta(seconds=config.delivery_cursor_legacy_v1_overlap_seconds),
        legacy_cursor_accept_until=config.delivery_cursor_legacy_v1_accept_until,
    )


def delivery_response_body(value: DeliveryResponse) -> DeliveryResponseBody:
    return DeliveryResponseBody.model_validate(value, from_attributes=True)


async def authorized_delivery_response_body(
    value: DeliveryResponse,
    engine: KnowledgeEngine,
    principal: PrincipalContextV1,
    *,
    max_response_bytes: int,
) -> DeliveryResponseBody:
    """Add source presentation metadata only after successful bounded delivery."""
    body = delivery_response_body(value)
    references = tuple(
        SourceMetadataReferenceV1(
            notebook_id=item.attribution.notebook_id,
            source_id=item.attribution.source_id,
            document_id=item.attribution.document_id,
            version_id=item.attribution.version_id,
        )
        for item in body.items
    )
    if not references:
        return body
    metadata = await AuthorizedSourceMetadataResolverV1(engine).resolve_many(principal, references)
    items = [
        item.model_copy(update={"source_metadata": metadata[reference].model_dump(mode="json")})
        for item, reference in zip(body.items, references, strict=True)
    ]
    unique = set(references)
    top = metadata[references[0]].model_dump(mode="json") if len(unique) == 1 else None
    enriched = body.model_copy(update={"items": items, "source_metadata": top})
    if len(enriched.model_dump_json().encode("utf-8")) > max_response_bytes:
        raise ContractValidationError("delivery response exceeds the server byte ceiling")
    return enriched
