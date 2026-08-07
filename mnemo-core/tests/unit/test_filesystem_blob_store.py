"""Tests for Phase 2, Module 2.1: FilesystemBlobStore.

Coverage targets
----------------
- Round-trip blob storage (put_asset → get_asset)
- Round-trip parsed IR (put_parsed_document → get_parsed_document)
- Content-addressed SHA-256 path layout
- Atomic write discipline (no partial files)
- Idempotency of put_asset with identical content
- ConflictError on put_parsed_document with different content for same version
- IntegrityError on asset UUID collision for different content hash
- IntegrityError on corrupt blob read
- Missing identity returns None
- delete_asset removes index and blob; returns True/False correctly
- contains_hash positive and negative cases
- All Block subtypes survive serialization round-trip
- Large blob (1 MB)
- health_check healthy and unhealthy states
- capabilities() returns correct flags
- Lifecycle (open / close idempotency, calls before open raise LifecycleError)
- root must be absolute
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Coroutine
from datetime import date
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces.errors import (
    ConflictError,
    IntegrityError,
    LifecycleError,
)
from mnemo.models import (
    Asset,
    CaptionBlock,
    CodeBlock,
    DocType,
    DocumentMetadata,
    EquationBlock,
    FrozenMetadata,
    HeadingBlock,
    ImageBlock,
    ParsedDocument,
    TableBlock,
    TextBlock,
)
from mnemo.models.blocks import Block
from mnemo.storage.filesystem import (
    FilesystemBlobStore,
    _asset_id_for_hash,
    _compute_sha256,
    _deserialize_parsed_document,
    _serialize_parsed_document,
)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> FilesystemBlobStore:
    """Return an unopened FilesystemBlobStore backed by a temp directory."""
    return FilesystemBlobStore(root=tmp_path / "blobs")


@pytest.fixture
def open_store(store: FilesystemBlobStore) -> FilesystemBlobStore:
    """Return an already-opened FilesystemBlobStore."""
    import asyncio

    asyncio.run(store.open())
    return store


@pytest.fixture
def content_hash() -> str:
    """Return a valid deterministic SHA-256 digest."""
    return "a" * 64


@pytest.fixture
def version_id() -> UUID:
    """Return a deterministic version UUID."""
    return UUID("00000000-0000-4000-8000-000000000002")


@pytest.fixture
def minimal_metadata(content_hash: str) -> DocumentMetadata:
    """Return a minimal valid DocumentMetadata."""
    return DocumentMetadata(content_hash=content_hash)


@pytest.fixture
def text_block() -> TextBlock:
    """Return a minimal text block."""
    return TextBlock(ordinal=0, text="Hello, Mnemo!")


@pytest.fixture
def minimal_parsed_document(
    minimal_metadata: DocumentMetadata, text_block: TextBlock
) -> ParsedDocument:
    """Return a minimal valid ParsedDocument."""
    return ParsedDocument(
        blocks=(text_block,),
        metadata=minimal_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine synchronously in the current event loop."""
    import asyncio

    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_requires_absolute_path(tmp_path: Path) -> None:
    """FilesystemBlobStore rejects a relative root path."""
    with pytest.raises(ValueError, match="absolute"):
        FilesystemBlobStore(root=Path("relative/path"))


def test_construction_requires_path_type() -> None:
    """FilesystemBlobStore rejects a non-Path root."""
    with pytest.raises(TypeError):
        FilesystemBlobStore(root="/tmp/blobs")  # type: ignore[arg-type]


def test_construction_stores_root(tmp_path: Path) -> None:
    """The root attribute matches the supplied absolute path."""
    root = tmp_path / "store"
    s = FilesystemBlobStore(root=root)
    assert s._root == root


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_open_creates_required_subdirectories(store: FilesystemBlobStore) -> None:
    """open() creates the _index/assets and parsed subdirectories."""
    _run(store.open())
    assert (store._root / "_index" / "assets").is_dir()
    assert (store._root / "parsed").is_dir()


def test_open_is_idempotent(store: FilesystemBlobStore) -> None:
    """Calling open() twice does not raise."""
    _run(store.open())
    _run(store.open())


def test_close_is_idempotent(store: FilesystemBlobStore) -> None:
    """Calling close() multiple times does not raise."""
    _run(store.open())
    _run(store.close())
    _run(store.close())


def test_operations_require_open(store: FilesystemBlobStore, version_id: UUID) -> None:
    """All data operations raise LifecycleError before open() is called."""
    with pytest.raises(LifecycleError):
        _run(store.put_asset(b"data", "text/plain", FrozenMetadata()))
    with pytest.raises(LifecycleError):
        _run(store.get_asset(uuid4()))
    with pytest.raises(LifecycleError):
        _run(store.delete_asset(uuid4()))
    with pytest.raises(LifecycleError):
        _run(store.contains_hash("a" * 64))
    # A minimal ParsedDocument is not needed here — it should fail before
    # touching the document argument.
    with pytest.raises(LifecycleError):
        _run(
            store.put_parsed_document(
                version_id,
                ParsedDocument(
                    blocks=(TextBlock(ordinal=0, text="x"),),
                    metadata=DocumentMetadata(content_hash="a" * 64),
                    language="en",
                    doc_type=DocType.GENERIC,
                ),
            )
        )
    with pytest.raises(LifecycleError):
        _run(store.get_parsed_document(version_id))


def test_operations_fail_after_close(open_store: FilesystemBlobStore, version_id: UUID) -> None:
    """Data operations raise LifecycleError after close()."""
    _run(open_store.close())
    with pytest.raises(LifecycleError):
        _run(open_store.get_asset(uuid4()))


# ---------------------------------------------------------------------------
# capabilities() and health_check()
# ---------------------------------------------------------------------------


def test_capabilities(open_store: FilesystemBlobStore) -> None:
    """capabilities() returns blob-only flags with no search/graph support."""
    caps = open_store.capabilities()
    assert caps.supports_blobs is True
    assert caps.supports_dense_search is False
    assert caps.supports_sparse_search is False
    assert caps.supports_metadata is False
    assert caps.supports_graph is False
    assert caps.supports_transactions is False
    assert caps.supports_health_checks is True


def test_health_check_healthy(open_store: FilesystemBlobStore) -> None:
    """health_check() reports healthy when the store is open and root exists."""
    statuses = _run(open_store.health_check())
    assert len(statuses) == 1
    status = statuses[0]
    assert status.healthy is True
    assert status.component == "storage.filesystem"
    assert status.detail is None


def test_health_check_unhealthy_when_closed(store: FilesystemBlobStore, tmp_path: Path) -> None:
    """health_check() reports unhealthy before open()."""
    statuses = _run(store.health_check())
    assert statuses[0].healthy is False


# ---------------------------------------------------------------------------
# put_asset / get_asset round-trip
# ---------------------------------------------------------------------------


def test_put_get_asset_round_trip(open_store: FilesystemBlobStore) -> None:
    """Stored bytes are retrieved unchanged and pass hash verification."""
    data = b"Hello, content-addressed world!"
    asset = _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))

    assert isinstance(asset, Asset)
    assert asset.mime_type == "text/plain"
    assert asset.content_hash == _compute_sha256(data)
    assert asset.storage_uri.startswith("blob://")

    retrieved = _run(open_store.get_asset(asset.asset_id))
    assert retrieved == data


def test_put_asset_is_idempotent(open_store: FilesystemBlobStore) -> None:
    """put_asset with identical bytes returns the same Asset and does not error."""
    data = b"idempotent bytes"
    asset1 = _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))
    asset2 = _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))
    assert asset1 == asset2
    assert asset1.asset_id == asset2.asset_id


def test_asset_id_is_deterministic(open_store: FilesystemBlobStore) -> None:
    """The same bytes always produce the same asset_id."""
    data = b"deterministic"
    a1 = _run(open_store.put_asset(data, "image/png", FrozenMetadata()))
    a2 = _run(open_store.put_asset(data, "image/png", FrozenMetadata()))
    assert a1.asset_id == a2.asset_id


def test_get_asset_returns_none_for_unknown_id(open_store: FilesystemBlobStore) -> None:
    """get_asset returns None for an asset_id that was never stored."""
    result = _run(open_store.get_asset(uuid4()))
    assert result is None


def test_put_asset_content_addressed_path(open_store: FilesystemBlobStore, tmp_path: Path) -> None:
    """Blob bytes are stored at <root>/<hash[:2]>/<hash[2:]>/raw.<ext>."""
    data = b"path check"
    content_hash = _compute_sha256(data)
    asset = _run(open_store.put_asset(data, "application/pdf", FrozenMetadata()))
    assert asset.content_hash == content_hash

    expected_dir = open_store._root / content_hash[:2] / content_hash[2:]
    assert expected_dir.is_dir()
    matches = list(expected_dir.glob("raw.*"))
    assert len(matches) == 1
    assert matches[0].read_bytes() == data


def test_put_asset_with_metadata(open_store: FilesystemBlobStore) -> None:
    """Metadata attached at put_asset is available on the returned Asset."""
    meta = FrozenMetadata({"vision.model": "local"})
    asset = _run(open_store.put_asset(b"img bytes", "image/png", meta))
    assert asset.metadata == meta


def test_put_asset_rejects_empty_mime_type(open_store: FilesystemBlobStore) -> None:
    """put_asset raises ValueError for an empty mime_type."""
    with pytest.raises(ValueError):
        _run(open_store.put_asset(b"data", "  ", FrozenMetadata()))


def test_put_asset_rejects_non_bytes(open_store: FilesystemBlobStore) -> None:
    """put_asset raises TypeError for non-bytes data."""
    with pytest.raises(TypeError):
        _run(open_store.put_asset("not bytes", "text/plain", FrozenMetadata()))  # type: ignore[arg-type]


def test_put_asset_rejects_non_frozen_metadata(open_store: FilesystemBlobStore) -> None:
    """put_asset raises TypeError for non-FrozenMetadata metadata."""
    with pytest.raises(TypeError):
        _run(open_store.put_asset(b"data", "text/plain", {}))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# delete_asset
# ---------------------------------------------------------------------------


def test_delete_asset_returns_true_when_found(open_store: FilesystemBlobStore) -> None:
    """delete_asset returns True and removes the asset when it existed."""
    data = b"to delete"
    asset = _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))
    assert _run(open_store.delete_asset(asset.asset_id)) is True
    assert _run(open_store.get_asset(asset.asset_id)) is None


def test_delete_asset_returns_false_when_not_found(open_store: FilesystemBlobStore) -> None:
    """delete_asset returns False for an unknown asset_id."""
    assert _run(open_store.delete_asset(uuid4())) is False


def test_delete_asset_removes_index_file(open_store: FilesystemBlobStore) -> None:
    """The side-car index file is removed by delete_asset."""
    asset = _run(open_store.put_asset(b"indexed", "text/plain", FrozenMetadata()))
    index_path = open_store._asset_index_path(asset.asset_id)
    assert index_path.exists()
    _run(open_store.delete_asset(asset.asset_id))
    assert not index_path.exists()


def test_delete_asset_rejects_non_uuid(open_store: FilesystemBlobStore) -> None:
    """delete_asset raises TypeError for a non-UUID argument."""
    with pytest.raises(TypeError):
        _run(open_store.delete_asset("not-a-uuid"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# contains_hash
# ---------------------------------------------------------------------------


def test_contains_hash_true_after_put(open_store: FilesystemBlobStore) -> None:
    """contains_hash returns True after the blob is stored."""
    data = b"hash check"
    content_hash = _compute_sha256(data)
    _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))
    assert _run(open_store.contains_hash(content_hash)) is True


def test_contains_hash_false_for_unknown(open_store: FilesystemBlobStore) -> None:
    """contains_hash returns False for a hash that was never stored."""
    assert _run(open_store.contains_hash("b" * 64)) is False


def test_contains_hash_false_after_delete(open_store: FilesystemBlobStore) -> None:
    """contains_hash returns False after the blob directory is removed."""
    data = b"will be deleted"
    content_hash = _compute_sha256(data)
    asset = _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))
    _run(open_store.delete_asset(asset.asset_id))
    assert _run(open_store.contains_hash(content_hash)) is False


def test_contains_hash_rejects_bad_hash(open_store: FilesystemBlobStore) -> None:
    """contains_hash raises ValueError for a non-SHA-256 string."""
    with pytest.raises(ValueError):
        _run(open_store.contains_hash("tooshort"))


# ---------------------------------------------------------------------------
# put_parsed_document / get_parsed_document round-trip
# ---------------------------------------------------------------------------


def test_put_get_parsed_document_round_trip(
    open_store: FilesystemBlobStore,
    minimal_parsed_document: ParsedDocument,
    version_id: UUID,
) -> None:
    """Stored ParsedDocument is deserialized to an equal object."""
    _run(open_store.put_parsed_document(version_id, minimal_parsed_document))
    result = _run(open_store.get_parsed_document(version_id))
    assert result is not None
    assert result.language == minimal_parsed_document.language
    assert result.doc_type == minimal_parsed_document.doc_type
    assert result.metadata.content_hash == minimal_parsed_document.metadata.content_hash
    assert len(result.blocks) == len(minimal_parsed_document.blocks)


def test_get_parsed_document_returns_none_for_unknown(
    open_store: FilesystemBlobStore, version_id: UUID
) -> None:
    """get_parsed_document returns None for an unknown version_id."""
    assert _run(open_store.get_parsed_document(version_id)) is None


def test_put_parsed_document_is_idempotent(
    open_store: FilesystemBlobStore,
    minimal_parsed_document: ParsedDocument,
    version_id: UUID,
) -> None:
    """put_parsed_document with identical content is a no-op."""
    _run(open_store.put_parsed_document(version_id, minimal_parsed_document))
    _run(open_store.put_parsed_document(version_id, minimal_parsed_document))  # no error


def test_put_parsed_document_conflict(
    open_store: FilesystemBlobStore, version_id: UUID, content_hash: str
) -> None:
    """put_parsed_document raises ConflictError when content changes."""
    doc1 = ParsedDocument(
        blocks=(TextBlock(ordinal=0, text="First version"),),
        metadata=DocumentMetadata(content_hash=content_hash),
        language="en",
        doc_type=DocType.GENERIC,
    )
    doc2 = ParsedDocument(
        blocks=(TextBlock(ordinal=0, text="Second version — different content"),),
        metadata=DocumentMetadata(content_hash=content_hash),
        language="en",
        doc_type=DocType.GENERIC,
    )
    _run(open_store.put_parsed_document(version_id, doc1))
    with pytest.raises(ConflictError):
        _run(open_store.put_parsed_document(version_id, doc2))


def test_put_parsed_document_ir_path_layout(
    open_store: FilesystemBlobStore,
    minimal_parsed_document: ParsedDocument,
    version_id: UUID,
) -> None:
    """Parsed IR is stored at <root>/parsed/<vid[:8]>/<version_id>.ir.json."""
    _run(open_store.put_parsed_document(version_id, minimal_parsed_document))
    expected_path = open_store._root / "parsed" / str(version_id)[:8] / f"{version_id}.ir.json"
    assert expected_path.exists()


def test_put_parsed_document_rejects_non_uuid(
    open_store: FilesystemBlobStore, minimal_parsed_document: ParsedDocument
) -> None:
    """put_parsed_document raises TypeError for a non-UUID version_id."""
    with pytest.raises(TypeError):
        _run(open_store.put_parsed_document("not-uuid", minimal_parsed_document))  # type: ignore[arg-type]


def test_put_parsed_document_rejects_non_parsed_document(
    open_store: FilesystemBlobStore, version_id: UUID
) -> None:
    """put_parsed_document raises TypeError for a non-ParsedDocument document."""
    with pytest.raises(TypeError):
        _run(open_store.put_parsed_document(version_id, {"not": "a document"}))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# All Block subtypes survive serialization
# ---------------------------------------------------------------------------


def _make_doc(block: Block, content_hash: str = "a" * 64) -> ParsedDocument:
    """Build a single-block ParsedDocument for serialization tests."""
    return ParsedDocument(
        blocks=(block,),
        metadata=DocumentMetadata(content_hash=content_hash),
        language="en",
        doc_type=DocType.GENERIC,
    )


def test_serialization_text_block(content_hash: str) -> None:
    """TextBlock survives a serialize → deserialize round-trip."""
    block = TextBlock(ordinal=0, text="Plain text", language="en", page_number=1)
    doc = _make_doc(block, content_hash=content_hash)
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    assert isinstance(restored.blocks[0], TextBlock)
    assert restored.blocks[0].text == "Plain text"


def test_serialization_heading_block(content_hash: str) -> None:
    """HeadingBlock survives a serialize → deserialize round-trip."""
    block = HeadingBlock(ordinal=0, text="Chapter 1", level=1)
    doc = _make_doc(block, content_hash=content_hash)
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    assert isinstance(restored.blocks[0], HeadingBlock)
    assert restored.blocks[0].level == 1


def test_serialization_table_block(content_hash: str) -> None:
    """TableBlock survives a serialize → deserialize round-trip."""
    block = TableBlock(ordinal=0, rows=(("A", "B"), ("1", "2")), header_row_count=1)
    doc = _make_doc(block, content_hash=content_hash)
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    assert isinstance(restored.blocks[0], TableBlock)
    assert restored.blocks[0].rows == (("A", "B"), ("1", "2"))
    assert restored.blocks[0].header_row_count == 1


def test_serialization_image_block(content_hash: str) -> None:
    """ImageBlock with asset_id survives a round-trip."""
    asset_id = UUID("00000000-0000-4000-8000-000000000099")
    block = ImageBlock(ordinal=0, asset_id=asset_id, alt_text="A diagram")
    doc = _make_doc(block, content_hash=content_hash)
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    assert isinstance(restored.blocks[0], ImageBlock)
    assert restored.blocks[0].asset_id == asset_id
    assert restored.blocks[0].alt_text == "A diagram"


def test_serialization_code_block(content_hash: str) -> None:
    """CodeBlock survives a serialize → deserialize round-trip."""
    block = CodeBlock(ordinal=0, code="print('hello')", code_language="python")
    doc = _make_doc(block, content_hash=content_hash)
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    assert isinstance(restored.blocks[0], CodeBlock)
    assert restored.blocks[0].code_language == "python"


def test_serialization_equation_block(content_hash: str) -> None:
    """EquationBlock survives a serialize → deserialize round-trip."""
    block = EquationBlock(ordinal=0, latex=r"E = mc^2", display=True)
    doc = _make_doc(block, content_hash=content_hash)
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    assert isinstance(restored.blocks[0], EquationBlock)
    assert restored.blocks[0].latex == r"E = mc^2"
    assert restored.blocks[0].display is True


def test_serialization_caption_block(content_hash: str) -> None:
    """CaptionBlock with target_ordinal survives a round-trip."""
    doc = ParsedDocument(
        blocks=(
            TextBlock(ordinal=0, text="Figure 1"),
            CaptionBlock(ordinal=1, text="Caption for figure", target_ordinal=0),
        ),
        metadata=DocumentMetadata(content_hash=content_hash),
        language="en",
        doc_type=DocType.GENERIC,
    )
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    assert isinstance(restored.blocks[1], CaptionBlock)
    assert restored.blocks[1].target_ordinal == 0


def test_serialization_bounding_box(content_hash: str) -> None:
    """A block with a bounding_box survives a round-trip."""
    block = TextBlock(ordinal=0, text="Boxed", page_number=1, bounding_box=(0.1, 0.2, 0.9, 0.8))
    doc = _make_doc(block, content_hash=content_hash)
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    bb = restored.blocks[0].bounding_box
    assert bb is not None
    assert abs(bb[0] - 0.1) < 1e-9


def test_serialization_document_metadata_full(content_hash: str) -> None:
    """Full DocumentMetadata fields survive a round-trip."""
    meta = DocumentMetadata(
        content_hash=content_hash,
        title="Test Title",
        authors=("Author One", "Author Two"),
        publication_date=date(2026, 1, 15),
        url="https://example.test",
        doi="10.9999/test",
        isbn="9780000000001",
        page_count=42,
        metadata=FrozenMetadata({"parser.name": "basic"}),
    )
    doc = ParsedDocument(
        blocks=(TextBlock(ordinal=0, text="content"),),
        metadata=meta,
        language="de",
        doc_type=DocType.PAPER,
    )
    restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
    rm = restored.metadata
    assert rm.title == "Test Title"
    assert rm.authors == ("Author One", "Author Two")
    assert rm.publication_date == date(2026, 1, 15)
    assert rm.url == "https://example.test"
    assert rm.doi == "10.9999/test"
    assert rm.isbn == "9780000000001"
    assert rm.page_count == 42
    assert restored.doc_type == DocType.PAPER
    assert restored.language == "de"


def test_serialization_all_doc_types(content_hash: str) -> None:
    """Every DocType enum value survives a round-trip."""
    for doc_type in DocType:
        doc = ParsedDocument(
            blocks=(TextBlock(ordinal=0, text="x"),),
            metadata=DocumentMetadata(content_hash=content_hash),
            language="en",
            doc_type=doc_type,
        )
        restored = _deserialize_parsed_document(_serialize_parsed_document(doc))
        assert restored.doc_type == doc_type


# ---------------------------------------------------------------------------
# IR integrity
# ---------------------------------------------------------------------------


def test_deserialization_rejects_malformed_json() -> None:
    """_deserialize_parsed_document raises IntegrityError for invalid JSON."""
    with pytest.raises(IntegrityError, match="malformed"):
        _deserialize_parsed_document(b"not json {{{")


def test_deserialization_rejects_wrong_model() -> None:
    """_deserialize_parsed_document raises IntegrityError for wrong model field."""
    payload = json.dumps({"model": "other_model", "schema_version": 1}).encode()
    with pytest.raises(IntegrityError, match="mismatch"):
        _deserialize_parsed_document(payload)


def test_deserialization_rejects_wrong_schema_version() -> None:
    """_deserialize_parsed_document raises IntegrityError for unknown schema_version."""
    payload = json.dumps({"model": "parsed_document", "schema_version": 999}).encode()
    with pytest.raises(IntegrityError, match="schema_version"):
        _deserialize_parsed_document(payload)


def test_get_asset_raises_integrity_error_for_corrupt_blob(
    open_store: FilesystemBlobStore,
) -> None:
    """get_asset raises IntegrityError when the blob file is corrupted."""
    data = b"original content"
    asset = _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))

    # Corrupt the blob by overwriting it with different content
    content_hash = asset.content_hash
    mime_type = asset.mime_type
    blob_path = open_store._blob_path(content_hash, mime_type)
    blob_path.write_bytes(b"CORRUPTED")

    with pytest.raises(IntegrityError, match="integrity"):
        _run(open_store.get_asset(asset.asset_id))


def test_put_asset_integrity_error_on_uuid_collision(
    open_store: FilesystemBlobStore,
) -> None:
    """put_asset raises IntegrityError if the index maps asset_id to a different hash."""
    data = b"original"
    asset = _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))

    # Manually corrupt the index entry to point at a different hash
    index_path = open_store._asset_index_path(asset.asset_id)
    corrupted = {
        "schema_version": 1,
        "asset_id": str(asset.asset_id),
        "content_hash": "b" * 64,  # wrong hash
        "mime_type": "text/plain",
        "storage_uri": "blob://" + "b" * 64,
    }
    index_path.write_text(
        json.dumps(corrupted, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )

    # Now put the same data — asset_id is the same but index says different hash
    with pytest.raises(IntegrityError, match="different content hash"):
        _run(open_store.put_asset(data, "text/plain", FrozenMetadata()))


# ---------------------------------------------------------------------------
# Large blob
# ---------------------------------------------------------------------------


def test_large_blob_round_trip(open_store: FilesystemBlobStore) -> None:
    """A 1 MB blob survives a put → get round-trip unchanged."""
    data = b"x" * (1024 * 1024)
    asset = _run(open_store.put_asset(data, "application/octet-stream", FrozenMetadata()))
    retrieved = _run(open_store.get_asset(asset.asset_id))
    assert retrieved == data
    assert _compute_sha256(retrieved) == asset.content_hash


# ---------------------------------------------------------------------------
# Empty bytes edge case
# ---------------------------------------------------------------------------


def test_empty_bytes_blob(open_store: FilesystemBlobStore) -> None:
    """An empty byte string is a valid blob and produces a valid SHA-256."""
    asset = _run(open_store.put_asset(b"", "application/octet-stream", FrozenMetadata()))
    retrieved = _run(open_store.get_asset(asset.asset_id))
    assert retrieved == b""
    assert len(asset.content_hash) == 64


# ---------------------------------------------------------------------------
# Multiple independent assets
# ---------------------------------------------------------------------------


def test_multiple_assets_independent(open_store: FilesystemBlobStore) -> None:
    """Different content produces different asset_ids; each retrieves correctly."""
    assets = [
        _run(open_store.put_asset(f"content {i}".encode(), "text/plain", FrozenMetadata()))
        for i in range(5)
    ]
    asset_ids = {a.asset_id for a in assets}
    assert len(asset_ids) == 5
    for i, asset in enumerate(assets):
        retrieved = _run(open_store.get_asset(asset.asset_id))
        assert retrieved == f"content {i}".encode()


# ---------------------------------------------------------------------------
# Multiple independent IR documents
# ---------------------------------------------------------------------------


def test_multiple_ir_documents_independent(
    open_store: FilesystemBlobStore, content_hash: str
) -> None:
    """Multiple version_ids store and retrieve independently."""
    version_ids = [uuid4() for _ in range(3)]
    texts = ["Alpha version", "Beta version", "Gamma version"]
    for vid, text in zip(version_ids, texts, strict=True):
        doc = ParsedDocument(
            blocks=(TextBlock(ordinal=0, text=text),),
            metadata=DocumentMetadata(content_hash=content_hash),
            language="en",
            doc_type=DocType.GENERIC,
        )
        _run(open_store.put_parsed_document(vid, doc))
    for vid, text in zip(version_ids, texts, strict=True):
        result = _run(open_store.get_parsed_document(vid))
        assert result is not None
        assert isinstance(result.blocks[0], TextBlock)
        assert result.blocks[0].text == text


# ---------------------------------------------------------------------------
# Storage URI is opaque
# ---------------------------------------------------------------------------


def test_storage_uri_is_opaque(open_store: FilesystemBlobStore) -> None:
    """The storage_uri does not expose filesystem paths."""
    asset = _run(open_store.put_asset(b"uri test", "text/plain", FrozenMetadata()))
    assert "/" not in asset.storage_uri.replace("blob://", "")
    assert "\\" not in asset.storage_uri


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def test_compute_sha256() -> None:
    """_compute_sha256 returns the correct lowercase hex digest."""
    data = b"test"
    expected = hashlib.sha256(data).hexdigest()
    assert _compute_sha256(data) == expected
    assert len(_compute_sha256(b"")) == 64


def test_asset_id_for_hash_deterministic() -> None:
    """_asset_id_for_hash produces the same UUID for the same hash."""
    h = "a" * 64
    uid1 = _asset_id_for_hash(h)
    uid2 = _asset_id_for_hash(h)
    assert uid1 == uid2
    assert isinstance(uid1, UUID)


def test_asset_id_for_hash_differs_for_different_hashes() -> None:
    """_asset_id_for_hash produces different UUIDs for different hashes."""
    assert _asset_id_for_hash("a" * 64) != _asset_id_for_hash("b" * 64)
