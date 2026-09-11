"""Thin application composition for the shared bounded delivery service."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from mnemo.cursors import CursorCodecV2, CursorSigningKeyV2
from mnemo.delivery import BoundedDocumentExpansionService
from mnemo.engine import KnowledgeEngine
from mnemo.models import DeliveryLimits, DeliveryResponse

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.delivery import DeliveryResponseBody


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
