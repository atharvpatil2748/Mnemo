"""Tests for Module 3.9 ingestion sequencing and publication boundaries."""

from datetime import UTC, datetime
from types import MappingProxyType
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion import DocumentCanonicalizer, IngestionPipeline
from mnemo.interfaces.errors import IntegrityError, StorageError
from mnemo.interfaces.parser_models import ParseResult, RawImageBlock, TransientAsset
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.models import (
    Asset,
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    ParsedDocument,
    TextBlock,
)
from mnemo.parsers import ParserRouter


def _result(*, two_assets: bool = False) -> ParseResult:
    blocks = [RawImageBlock(ordinal=0, parser_local_id="image-1")]
    assets = [TransientAsset(parser_local_id="image-1", raw_bytes=b"one", mime_type="image/png")]
    if two_assets:
        blocks.append(RawImageBlock(ordinal=1, parser_local_id="image-2"))
        assets.append(
            TransientAsset(parser_local_id="image-2", raw_bytes=b"two", mime_type="image/png")
        )
    return ParseResult(
        blocks=tuple(blocks),
        extracted_assets=tuple(assets),
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="und",
        doc_type=DocType.GENERIC,
    )


def _asset(identity: UUID | None = None) -> Asset:
    return Asset(
        asset_id=identity or uuid4(),
        mime_type="image/png",
        content_hash="b" * 64,
        storage_uri="blob://asset",
    )


def _pipeline(
    routed: Document | ParseResult,
) -> tuple[IngestionPipeline, AsyncMock, Mock, Mock, Mock]:
    router = Mock(spec=ParserRouter)
    router.route = AsyncMock(return_value=routed)
    storage = AsyncMock(spec=StorageInterfaceV1)
    cleaner = Mock(spec=DocumentCleaner)
    cleaner.clean.return_value = routed
    classifier = Mock(spec=DocumentClassifier)
    classifier.classify.return_value = routed
    canonicalizer = Mock(spec=DocumentCanonicalizer)
    pipeline = IngestionPipeline(
        router=router,
        storage=storage,
        cleaner=cleaner,
        classifier=classifier,
        canonicalizer=canonicalizer,
    )
    return pipeline, storage, cleaner, classifier, canonicalizer


@pytest.mark.anyio
async def test_pipeline_persists_assets_before_canonical_document_publication() -> None:
    result = _result()
    pipeline, storage, cleaner, classifier, canonicalizer = _pipeline(result)
    version_id = uuid4()
    asset = _asset()
    canonical = DocumentCanonicalizer().canonicalize(result, {"image-1": asset})
    events: list[str] = []

    async def put_asset(data: bytes, mime_type: str, metadata: FrozenMetadata) -> Asset:
        events.append("asset")
        assert (data, mime_type, metadata) == (b"one", "image/png", FrozenMetadata())
        return asset

    async def put_document(identity: UUID, document: ParsedDocument) -> None:
        events.append("document")
        assert identity == version_id
        assert document is canonical

    def canonicalize(parse_result: ParseResult, resolution: object) -> ParsedDocument:
        events.append("canonicalize")
        assert parse_result is result
        assert type(resolution) is type(MappingProxyType({}))
        return canonical

    storage.put_asset.side_effect = put_asset
    storage.put_parsed_document.side_effect = put_document
    canonicalizer.canonicalize.side_effect = canonicalize

    returned = await pipeline.ingest(b"raw", "document.pdf", version_id)

    assert returned is canonical
    assert events == ["asset", "canonicalize", "document"]
    cleaner.clean.assert_called_once_with(result)
    classifier.classify.assert_called_once_with(result, "document.pdf")


@pytest.mark.anyio
async def test_canonicalization_failure_prevents_document_publication() -> None:
    result = _result()
    pipeline, storage, _, _, canonicalizer = _pipeline(result)
    storage.put_asset.return_value = _asset()
    canonicalizer.canonicalize.side_effect = IntegrityError("invalid resolution")

    with pytest.raises(IntegrityError):
        await pipeline.ingest(b"raw", "document.pdf", uuid4())

    storage.put_parsed_document.assert_not_awaited()
    storage.delete_asset.assert_not_awaited()


@pytest.mark.anyio
async def test_asset_failure_leaves_content_addressed_assets_and_prevents_publication() -> None:
    result = _result(two_assets=True)
    pipeline, storage, _, _, canonicalizer = _pipeline(result)
    storage.put_asset.side_effect = (_asset(), StorageError("blob write failed"))

    with pytest.raises(StorageError, match="blob write failed"):
        await pipeline.ingest(b"raw", "document.pdf", uuid4())

    assert storage.put_asset.await_count == 2
    storage.delete_asset.assert_not_awaited()
    canonicalizer.canonicalize.assert_not_called()
    storage.put_parsed_document.assert_not_awaited()


def _document(parsed: ParsedDocument) -> Document:
    now = datetime.now(UTC)
    document_id = uuid4()
    version = DocumentVersion(
        version_id=uuid4(),
        document_id=document_id,
        content_hash=parsed.metadata.content_hash,
        metadata=parsed.metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    return Document(
        document_id=document_id,
        versions=(version,),
        current_version_id=version.version_id,
        current_hash=version.content_hash,
        status=DocumentStatus.INDEXED,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.anyio
async def test_deduplication_returns_existing_canonical_document_without_reparsing() -> None:
    parsed = ParsedDocument(
        blocks=(TextBlock(ordinal=0, text="canonical"),),
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="en",
        doc_type=DocType.GENERIC,
    )
    existing = _document(parsed)
    pipeline, storage, cleaner, classifier, canonicalizer = _pipeline(existing)
    storage.get_parsed_document.return_value = parsed

    returned = await pipeline.ingest(b"duplicate", "document.pdf", uuid4())

    assert returned is parsed
    storage.get_parsed_document.assert_awaited_once_with(existing.current_version_id)
    storage.put_asset.assert_not_awaited()
    storage.put_parsed_document.assert_not_awaited()
    cleaner.clean.assert_not_called()
    classifier.classify.assert_not_called()
    canonicalizer.canonicalize.assert_not_called()


@pytest.mark.anyio
async def test_deduplication_missing_canonical_document_is_integrity_failure() -> None:
    parsed = ParsedDocument(
        blocks=(),
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="und",
        doc_type=DocType.GENERIC,
    )
    pipeline, storage, _, _, _ = _pipeline(_document(parsed))
    storage.get_parsed_document.return_value = None

    with pytest.raises(IntegrityError, match="no canonical ParsedDocument"):
        await pipeline.ingest(b"duplicate", "document.pdf", uuid4())
