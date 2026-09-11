"""Phase 8.5.1 asset models, validation, authorization, and retention tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mnemo.asset_foundation import (
    AssetAccessContext,
    AssetAuthorizationService,
    AssetFoundationService,
    sanitize_asset_filename,
    validate_asset_payload,
)
from mnemo.asset_foundation.service import _container_kind, _locator_for_block
from mnemo.asset_foundation.validation import _signature_media_type
from mnemo.interfaces import AssetCatalogStoreV1, AssetRecordStoreV1, StorageInterfaceV1
from mnemo.interfaces.errors import ContractValidationError, IntegrityError, NotFoundError
from mnemo.models import (
    Asset,
    AssetContainerKind,
    AssetLocator,
    AssetLocatorKind,
    AssetOccurrence,
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    ImageBlock,
    ParsedDocument,
    asset_derivation_id,
    asset_occurrence_id,
)


def _document(data: bytes) -> tuple[Document, ParsedDocument]:
    content_hash = hashlib.sha256(data).hexdigest()
    document_id = uuid4()
    version_id = uuid4()
    now = datetime(2026, 8, 24, tzinfo=UTC)
    metadata = DocumentMetadata(content_hash=content_hash, page_count=2)
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    return (
        Document(
            document_id=document_id,
            versions=(version,),
            current_version_id=version_id,
            current_hash=content_hash,
            status=DocumentStatus.INDEXING,
            created_at=now,
            updated_at=now,
        ),
        ParsedDocument(blocks=(), metadata=metadata, language="en", doc_type=DocType.GENERIC),
    )


def test_typed_locators_round_trip_and_deterministic_identities() -> None:
    locator = AssetLocator(
        kind=AssetLocatorKind.PDF_PAGE,
        ordinal=3,
        page_number=2,
        geometry=(1.0, 2.0, 3.0, 4.0),
    )
    assert AssetLocator.from_payload(locator.to_payload()) == locator
    assert (
        locator.canonical_json() == AssetLocator.from_payload(locator.to_payload()).canonical_json()
    )
    values = {
        "document_id": uuid4(),
        "version_id": uuid4(),
        "asset_id": uuid4(),
        "locator": locator,
    }
    assert asset_occurrence_id(**values) == asset_occurrence_id(**values)
    derivation = {
        "occurrence_id": uuid4(),
        "operation": "ocr",
        "provider_identity": "provider",
        "model_identity": "model",
        "configuration_digest": "a" * 64,
    }
    assert asset_derivation_id(**derivation) == asset_derivation_id(**derivation)


@pytest.mark.parametrize(
    ("kind", "kwargs"),
    [
        (AssetLocatorKind.PDF_PAGE, {}),
        (AssetLocatorKind.PPTX_SLIDE, {}),
        (AssetLocatorKind.DOCX_POSITION, {}),
        (AssetLocatorKind.XLSX_CELL, {}),
        (AssetLocatorKind.DOM_POSITION, {}),
        (AssetLocatorKind.STANDALONE, {"page_number": 1}),
    ],
)
def test_typed_locator_rejects_incomplete_or_fabricated_coordinates(
    kind: AssetLocatorKind, kwargs: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        AssetLocator(kind=kind, ordinal=0, **kwargs)  # type: ignore[arg-type]


def test_asset_payload_validation_enforces_security_boundaries() -> None:
    payload = b"%PDF-1.7\nexample"
    result = validate_asset_payload(payload, "application/pdf", max_bytes=100, filename="x.pdf")
    assert result.content_hash == hashlib.sha256(payload).hexdigest()
    assert result.byte_size == len(payload)
    assert sanitize_asset_filename("safe.pdf") == "safe.pdf"
    with pytest.raises(ContractValidationError):
        sanitize_asset_filename("../secret.pdf")
    with pytest.raises(ContractValidationError):
        validate_asset_payload(payload, "application/pdf", max_bytes=2)
    with pytest.raises(IntegrityError):
        validate_asset_payload(payload, "image/png", max_bytes=100)
    assert (
        validate_asset_payload(payload, "application/octet-stream", max_bytes=100).media_type
        == "application/pdf"
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xffx", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"II*\x00", "image/tiff"),
        (b"BMdata", "image/bmp"),
        (b"RIFFxxxxWEBP", "image/webp"),
        (b"PK\x03\x04invalid", "application/zip"),
        (b"unknown", None),
    ],
)
def test_signature_sniffing_is_deterministic(payload: bytes, expected: str | None) -> None:
    assert _signature_media_type(payload) == expected


def test_asset_validation_rejects_malformed_inputs() -> None:
    for filename in ("", ".", "bad\x00name", "folder/file"):
        with pytest.raises((ContractValidationError, TypeError)):
            sanitize_asset_filename(filename)
    with pytest.raises(TypeError):
        sanitize_asset_filename(3)  # type: ignore[arg-type]
    for data, media_type, limit in (
        (b"", "text/plain", 10),
        (b"x", "", 10),
        (b"x", "bad type", 10),
        (b"x", "text/plain", 0),
    ):
        with pytest.raises(ContractValidationError):
            validate_asset_payload(data, media_type, max_bytes=limit)
    generic = validate_asset_payload(b"arbitrary binary", "application/octet-stream", max_bytes=100)
    assert generic.byte_size == 16


def test_container_and_locator_mapping_preserves_only_observed_coordinates() -> None:
    assert _container_kind("application/pdf") is AssetContainerKind.PDF
    assert _container_kind("image/png") is AssetContainerKind.STANDALONE
    assert _container_kind("application/x-custom") is AssetContainerKind.OTHER
    cases = (
        (
            AssetContainerKind.PPTX,
            ImageBlock(ordinal=0, asset_id=uuid4(), page_number=4),
            AssetLocatorKind.PPTX_SLIDE,
        ),
        (
            AssetContainerKind.DOCX,
            ImageBlock(ordinal=0, asset_id=uuid4()),
            AssetLocatorKind.DOCX_POSITION,
        ),
        (
            AssetContainerKind.XLSX,
            ImageBlock(
                ordinal=0,
                asset_id=uuid4(),
                metadata=FrozenMetadata({"sheet_name": "Sheet1", "cell_reference": "B2"}),
            ),
            AssetLocatorKind.XLSX_CELL,
        ),
        (
            AssetContainerKind.STANDALONE,
            ImageBlock(ordinal=0, asset_id=uuid4()),
            AssetLocatorKind.STANDALONE,
        ),
        (
            AssetContainerKind.HTML,
            ImageBlock(ordinal=0, asset_id=uuid4()),
            AssetLocatorKind.DOCUMENT_POSITION,
        ),
    )
    for container, block, expected in cases:
        assert _locator_for_block(container, block).kind is expected


@pytest.mark.anyio
async def test_retention_is_idempotent_and_keeps_original_bytes_authoritative() -> None:
    data = b"plain source bytes"
    document, parsed = _document(data)
    original = Asset(
        asset_id=uuid4(),
        mime_type="text/plain",
        content_hash=hashlib.sha256(data).hexdigest(),
        storage_uri="blob://content",
    )
    storage = AsyncMock(spec=StorageInterfaceV1)
    storage.contains_hash.side_effect = [False, True]
    storage.put_asset.return_value = original
    catalog = AsyncMock(spec=AssetCatalogStoreV1)
    records = AsyncMock(spec=AssetRecordStoreV1)
    catalog.get_document_binary_reference.side_effect = lambda version_id: catalog.reference
    catalog.list_asset_occurrences.return_value = ()

    async def register(**kwargs: object) -> None:
        catalog.reference = kwargs["binary_reference"]

    catalog.register_asset_ingestion.side_effect = register
    service = AssetFoundationService(
        storage=storage,
        catalog=catalog,
        asset_records=records,
        max_asset_bytes=1024,
    )
    first = await service.retain_ingested_version(
        data=data,
        filename="source.txt",
        declared_media_type="text/plain",
        document=document,
        parsed_document=parsed,
    )
    second = await service.retain_ingested_version(
        data=data,
        filename="source.txt",
        declared_media_type="text/plain",
        document=document,
        parsed_document=parsed,
    )
    assert first.binary_reference.asset_id == original.asset_id
    assert first.deduplicated_blob is False
    assert second.deduplicated_blob is True
    assert storage.put_asset.await_count == 2


@pytest.mark.anyio
async def test_retention_creates_occurrence_from_available_parser_provenance() -> None:
    data = b"%PDF-1.7\nsource"
    document, empty = _document(data)
    embedded = Asset(
        asset_id=uuid4(),
        mime_type="image/png",
        content_hash="b" * 64,
        storage_uri="blob://embedded",
    )
    parsed = ParsedDocument(
        blocks=(
            ImageBlock(
                ordinal=0,
                asset_id=embedded.asset_id,
                page_number=2,
                alt_text="Authored description",
                bounding_box=(1.0, 2.0, 3.0, 4.0),
            ),
        ),
        metadata=empty.metadata,
        language="en",
        doc_type=DocType.PAPER,
    )
    original = Asset(
        asset_id=uuid4(),
        mime_type="application/pdf",
        content_hash=hashlib.sha256(data).hexdigest(),
        storage_uri="blob://original",
    )
    storage = AsyncMock(spec=StorageInterfaceV1)
    storage.contains_hash.return_value = False
    storage.put_asset.return_value = original
    catalog = AsyncMock(spec=AssetCatalogStoreV1)
    records = AsyncMock(spec=AssetRecordStoreV1)
    records.get_asset_record.return_value = embedded

    async def register(**kwargs: object) -> None:
        catalog.reference = kwargs["binary_reference"]
        catalog.occurrences = kwargs["occurrences"]

    catalog.register_asset_ingestion.side_effect = register
    catalog.get_document_binary_reference.side_effect = lambda version_id: catalog.reference
    catalog.list_asset_occurrences.side_effect = lambda version_id: catalog.occurrences
    result = await AssetFoundationService(
        storage=storage,
        catalog=catalog,
        asset_records=records,
        max_asset_bytes=1024,
    ).retain_ingested_version(
        data=data,
        filename="paper.pdf",
        declared_media_type="application/pdf",
        document=document,
        parsed_document=parsed,
    )
    occurrence = result.occurrences[0]
    assert occurrence.container_kind is AssetContainerKind.PDF
    assert occurrence.locator.page_number == 2
    assert occurrence.locator.geometry == (1.0, 2.0, 3.0, 4.0)
    assert occurrence.authored_alt_text == "Authored description"


@pytest.mark.anyio
async def test_retention_fails_closed_on_provenance_mismatch_or_missing_asset() -> None:
    data = b"%PDF-1.7\nsource"
    document, parsed = _document(data)
    storage = AsyncMock(spec=StorageInterfaceV1)
    catalog = AsyncMock(spec=AssetCatalogStoreV1)
    records = AsyncMock(spec=AssetRecordStoreV1)
    original = Asset(
        asset_id=uuid4(),
        mime_type="application/pdf",
        content_hash="f" * 64,
        storage_uri="blob://wrong",
    )
    storage.contains_hash.return_value = False
    storage.put_asset.return_value = original
    service = AssetFoundationService(
        storage=storage, catalog=catalog, asset_records=records, max_asset_bytes=1024
    )
    with pytest.raises(IntegrityError, match="stored original"):
        await service.retain_ingested_version(
            data=data,
            filename="paper.pdf",
            declared_media_type="application/pdf",
            document=document,
            parsed_document=parsed,
        )

    matching = Asset(
        asset_id=uuid4(),
        mime_type="application/pdf",
        content_hash=hashlib.sha256(data).hexdigest(),
        storage_uri="blob://right",
    )
    storage.put_asset.return_value = matching
    image_parsed = ParsedDocument(
        blocks=(ImageBlock(ordinal=0, asset_id=uuid4(), page_number=1),),
        metadata=parsed.metadata,
        language="en",
        doc_type=DocType.PAPER,
    )
    records.get_asset_record.return_value = None
    with pytest.raises(IntegrityError, match="missing asset metadata"):
        await service.retain_ingested_version(
            data=data,
            filename="paper.pdf",
            declared_media_type="application/pdf",
            document=document,
            parsed_document=image_parsed,
        )


@pytest.mark.anyio
async def test_retention_rejects_exact_version_and_catalog_mismatches() -> None:
    data = b"exact bytes"
    document, parsed = _document(data)
    storage = AsyncMock(spec=StorageInterfaceV1)
    catalog = AsyncMock(spec=AssetCatalogStoreV1)
    records = AsyncMock(spec=AssetRecordStoreV1)
    original = Asset(
        asset_id=uuid4(),
        mime_type="text/plain",
        content_hash=hashlib.sha256(data).hexdigest(),
        storage_uri="blob://exact",
    )
    storage.contains_hash.return_value = False
    storage.put_asset.return_value = original
    catalog.get_document_binary_reference.return_value = None
    catalog.list_asset_occurrences.return_value = ()
    service = AssetFoundationService(
        storage=storage, catalog=catalog, asset_records=records, max_asset_bytes=1024
    )
    with pytest.raises(IntegrityError, match="could not be reloaded"):
        await service.retain_ingested_version(
            data=data,
            filename="exact.txt",
            declared_media_type="text/plain",
            document=document,
            parsed_document=parsed,
        )

    other_document, _ = _document(b"different")
    with pytest.raises(IntegrityError, match="original byte hash"):
        await service.retain_ingested_version(
            data=data,
            filename="exact.txt",
            declared_media_type="text/plain",
            document=other_document,
            parsed_document=parsed,
        )


@pytest.mark.anyio
async def test_reference_aware_gc_requires_safe_storage_capability() -> None:
    storage = AsyncMock(spec=StorageInterfaceV1)
    catalog = AsyncMock(spec=AssetCatalogStoreV1)
    records = AsyncMock(spec=AssetRecordStoreV1)
    service = AssetFoundationService(
        storage=storage, catalog=catalog, asset_records=records, max_asset_bytes=1
    )
    with pytest.raises(ContractValidationError):
        await service.garbage_collect_unreferenced(uuid4())

    class SafeStorage:
        async def delete_unreferenced_asset(self, asset_id):  # type: ignore[no-untyped-def]
            return True

    safe_service = AssetFoundationService(
        storage=SafeStorage(),  # type: ignore[arg-type]
        catalog=catalog,
        asset_records=records,
        max_asset_bytes=1,
    )
    assert await safe_service.garbage_collect_unreferenced(uuid4()) is True


def test_foundation_constructor_rejects_missing_additive_capabilities() -> None:
    storage = AsyncMock(spec=StorageInterfaceV1)
    catalog = AsyncMock(spec=AssetCatalogStoreV1)
    records = AsyncMock(spec=AssetRecordStoreV1)
    with pytest.raises(TypeError):
        AssetFoundationService(
            storage=storage,
            catalog=object(),  # type: ignore[arg-type]
            asset_records=records,
            max_asset_bytes=1,
        )
    with pytest.raises(TypeError):
        AssetFoundationService(
            storage=storage,
            catalog=catalog,
            asset_records=object(),  # type: ignore[arg-type]
            max_asset_bytes=1,
        )
    with pytest.raises(ValueError):
        AssetFoundationService(
            storage=storage,
            catalog=catalog,
            asset_records=records,
            max_asset_bytes=0,
        )
    with pytest.raises(TypeError):
        AssetAuthorizationService(object())  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_authorization_is_occurrence_and_notebook_scoped() -> None:
    occurrence = AsyncMock(spec=AssetOccurrence)
    catalog = AsyncMock(spec=AssetCatalogStoreV1)
    catalog.get_authorized_asset_occurrence.side_effect = [occurrence, None]
    service = AssetAuthorizationService(catalog)
    context = AssetAccessContext(notebook_id=uuid4(), actor_id="actor")
    occurrence_id = uuid4()
    assert await service.authorize_occurrence(context, occurrence_id) is occurrence
    with pytest.raises(NotFoundError):
        await service.authorize_occurrence(context, occurrence_id)
    with pytest.raises(TypeError):
        await service.authorize_occurrence(object(), occurrence_id)  # type: ignore[arg-type]
