"""Phase 8.5 bounded resource-delivery contracts and typed failures."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces.errors import MnemoInterfaceError
from mnemo.models.chunks import Chunk
from mnemo.models.delivery import (
    AssetAnalysisSelector,
    BinaryDelivery,
    DeliveryCapability,
    DeliveryRequest,
    DeliveryResponse,
    DocumentExpansionRequestV2,
)


class DeliveryLimitExceededError(MnemoInterfaceError):
    code = "delivery.size_exceeded"


class DeliveryCursorError(MnemoInterfaceError):
    code = "delivery.cursor_invalid"


class DeliveryCursorExpiredError(DeliveryCursorError):
    code = "delivery.cursor_expired"


class DeliveryCursorConflictError(DeliveryCursorError):
    code = "delivery.cursor_conflict"


class DeliveryAuthorizationError(MnemoInterfaceError):
    code = "delivery.forbidden"


@runtime_checkable
class DocumentExpansionServiceV1(Protocol):  # pragma: no cover
    def capabilities(self) -> tuple[DeliveryCapability, ...]: ...

    async def expand_document(self, request: DeliveryRequest) -> DeliveryResponse: ...

    async def get_original_document(self, request: DeliveryRequest) -> BinaryDelivery: ...

    async def get_document_chunk(
        self, *, notebook_id: UUID, document_id: UUID, version_id: UUID, chunk_id: str
    ) -> DeliveryResponse: ...

    async def list_assets(
        self,
        *,
        notebook_id: UUID,
        document_id: UUID,
        version_id: UUID,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> DeliveryResponse: ...

    async def get_asset(
        self,
        *,
        notebook_id: UUID,
        occurrence_id: UUID,
        cursor: str | None = None,
        max_bytes: int | None = None,
    ) -> BinaryDelivery: ...

    async def get_image_analysis(
        self,
        *,
        notebook_id: UUID,
        occurrence_id: UUID,
        ocr_derivation_id: UUID | None = None,
        vision_derivation_id: UUID | None = None,
    ) -> DeliveryResponse: ...

    async def get_final_qa_evidence(
        self,
        *,
        notebook_id: UUID,
        assistant_turn_id: UUID,
        cursor: str | None = None,
    ) -> DeliveryResponse: ...


@runtime_checkable
class ExactDocumentReaderV1(Protocol):  # pragma: no cover
    """Additive exact-version canonical chunk reader; StorageInterfaceV1 stays frozen."""

    async def list_exact_document_chunks(
        self, *, document_id: UUID, version_id: UUID
    ) -> tuple[Chunk, ...]: ...


@runtime_checkable
class DocumentExpansionServiceV2(DocumentExpansionServiceV1, Protocol):  # pragma: no cover
    async def expand_document_v2(self, request: DocumentExpansionRequestV2) -> DeliveryResponse: ...


@runtime_checkable
class AssetDeliveryV2(Protocol):  # pragma: no cover
    async def get_asset(
        self,
        *,
        notebook_id: UUID,
        occurrence_id: UUID,
        cursor: str | None = None,
        max_bytes: int | None = None,
    ) -> BinaryDelivery: ...

    async def get_image_analysis_v2(
        self, *, notebook_id: UUID, occurrence_id: UUID, selector: AssetAnalysisSelector
    ) -> DeliveryResponse: ...
