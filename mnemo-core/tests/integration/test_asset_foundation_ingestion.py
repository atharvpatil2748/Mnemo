"""Isolated production asset-retention integration for representative formats."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from mnemo.asset_foundation import AssetFoundationService
from mnemo.interfaces.types import FileMetadata
from mnemo.models import (
    DocType,
    Document,
    DocumentBinaryAvailability,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    ParsedDocument,
)
from mnemo.parsers.image import StandaloneImageParser
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.sqlite import SQLiteStore


def _ooxml(marker: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(marker, "<root/>")
    return output.getvalue()


def _document(data: bytes) -> tuple[Document, ParsedDocument]:
    import hashlib

    content_hash = hashlib.sha256(data).hexdigest()
    document_id, version_id = uuid4(), uuid4()
    now = datetime(2026, 8, 24, tzinfo=UTC)
    metadata = DocumentMetadata(content_hash=content_hash)
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
        ParsedDocument(blocks=(), metadata=metadata, language="und", doc_type=DocType.GENERIC),
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("filename", "media_type", "data"),
    [
        ("paper.pdf", "application/pdf", b"%PDF-1.7\nfoundation"),
        (
            "slides.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            _ooxml("ppt/presentation.xml"),
        ),
        (
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _ooxml("word/document.xml"),
        ),
        (
            "table.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _ooxml("xl/workbook.xml"),
        ),
        ("diagram.png", "image/png", b"\x89PNG\r\n\x1a\ncontent"),
    ],
)
async def test_exact_original_retention_for_representative_formats(
    tmp_path: Path, filename: str, media_type: str, data: bytes
) -> None:
    filesystem = FilesystemBlobStore(tmp_path / "blobs")
    sqlite = SQLiteStore(tmp_path / "metadata.db")
    await filesystem.open()
    await sqlite.open()
    document, parsed = _document(data)
    await sqlite.upsert_document(document)
    service = AssetFoundationService(
        storage=filesystem,
        catalog=sqlite,
        asset_records=filesystem,
        max_asset_bytes=1024 * 1024,
        clock=lambda: datetime(2026, 8, 24, tzinfo=UTC),
    )
    result = await service.retain_ingested_version(
        data=data,
        filename=filename,
        declared_media_type=media_type,
        document=document,
        parsed_document=parsed,
    )
    assert await filesystem.get_asset(result.original_asset.asset_id) == data
    assert result.binary_reference.version_id == document.current_version_id
    assert result.binary_reference.media_type == media_type
    assert result.binary_reference.byte_size == len(data)
    assert (
        await sqlite.get_document_binary_availability(document.current_version_id)
        is DocumentBinaryAvailability.AVAILABLE
    )
    await sqlite.close()
    await filesystem.close()


@pytest.mark.anyio
async def test_parser_v2_occurrence_publication_is_exact_and_idempotent(tmp_path: Path) -> None:
    data = b"\x89PNG\r\n\x1a\nasset-foundation"
    filesystem = FilesystemBlobStore(tmp_path / "blobs")
    sqlite = SQLiteStore(tmp_path / "metadata.db")
    await filesystem.open()
    await sqlite.open()
    document, parsed = _document(data)
    await sqlite.upsert_document(document)
    extraction = StandaloneImageParser().parse_with_assets(
        data,
        "diagram.png",
        FileMetadata(
            content_hash=document.current_hash,
            size_bytes=len(data),
            mime_type="image/png",
            modified_at=None,
            metadata=FrozenMetadata(),
        ),
    )
    transient = extraction.parse_result.extracted_assets[0]
    resolved = await filesystem.put_asset(
        transient.raw_bytes, transient.mime_type, FrozenMetadata()
    )
    service = AssetFoundationService(
        storage=filesystem,
        catalog=sqlite,
        asset_records=filesystem,
        max_asset_bytes=1024 * 1024,
        clock=lambda: datetime(2026, 8, 24, tzinfo=UTC),
    )
    first = await service.retain_ingested_version(
        data=data,
        filename="diagram.png",
        declared_media_type="image/png",
        document=document,
        parsed_document=parsed,
        extraction=extraction,
        resolved_assets={transient.parser_local_id: resolved},
    )
    second = await service.retain_ingested_version(
        data=data,
        filename="diagram.png",
        declared_media_type="image/png",
        document=document,
        parsed_document=parsed,
        extraction=extraction,
        resolved_assets={transient.parser_local_id: resolved},
    )
    assert first.occurrences == second.occurrences
    assert len(second.occurrences) == 1
    assert second.occurrences[0].asset_id == resolved.asset_id
    assert second.occurrences[0].version_id == document.current_version_id
    assert await filesystem.get_asset(resolved.asset_id) == data
    await sqlite.close()
    await filesystem.close()
