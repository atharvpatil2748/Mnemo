"""Content-addressed filesystem blob store for Mnemo Phase 2, Module 2.1.

Layout
------
<root>/
    <hash[:2]>/<hash[2:]>/
        raw.<ext>          — original asset bytes
    parsed/<vid[:8]>/
        <version_id>.ir.json  — ParsedDocument intermediate representation
    _index/assets/
        <asset_uuid>.json  — side-car: UUID → content_hash mapping

Design rules
------------
- All writes are atomic: temp file in same directory, then os.replace().
- Content-addressed by SHA-256; identical bytes share one blob.
- ParsedDocument IR uses a versioned canonical JSON envelope.
- No network I/O, no database dependencies, stdlib + project models only.
- FilesystemBlobStore implements the BlobStore contract (ADR-0002 §5.2),
  not the full StorageInterfaceV1.  CompositeStorage (Module 2.5) composes it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo.interfaces.errors import (
    ConflictError,
    IntegrityError,
    LifecycleError,
    StorageError,
)
from mnemo.interfaces.types import HealthStatus, StorageCapabilities
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

# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------

_IR_SCHEMA_VERSION: int = 1
_ASSET_INDEX_SCHEMA_VERSION: int = 1

# UUID namespace for deterministic asset_id derivation from content_hash.
# Stable; must never change once data is on disk.
_BLOB_NAMESPACE = uuid.UUID("7f000001-0000-4d6d-b000-000000000001")

# MIME → file extension mapping (non-exhaustive, extensible).
_MIME_EXTENSIONS: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/json": ".json",
    "application/zip": ".zip",
    "application/octet-stream": ".bin",
    "text/plain": ".txt",
    "text/html": ".html",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "text/xml": ".xml",
    "application/xml": ".xml",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


# ------------------------------------------------------------------
# Internal path helpers
# ------------------------------------------------------------------


def _mime_to_extension(mime_type: str) -> str:
    """Return the preferred file extension for a MIME type, or '.bin'."""
    return _MIME_EXTENSIONS.get(mime_type.lower().split(";")[0].strip(), ".bin")


def _compute_sha256(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def _asset_id_for_hash(content_hash: str) -> UUID:
    """Derive a deterministic asset UUID from a content hash.

    UUID5 of the stable blob namespace and the hex content hash.  Identical
    bytes always produce the same asset_id, making put_asset idempotent.
    """
    return uuid.uuid5(_BLOB_NAMESPACE, content_hash)


def _atomic_write(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically using a sibling temp file.

    Creates all parent directories.  On POSIX, os.replace() is atomic.
    On Windows, os.replace() handles overwrite safely since Python 3.3.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        try:
            os.replace(tmp_path, path)
        except PermissionError:  # pragma: no cover
            import time

            for attempt in range(4):
                time.sleep(0.2)
                try:
                    os.replace(tmp_path, path)
                    break
                except PermissionError:
                    if attempt == 3:
                        raise
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


# ------------------------------------------------------------------
# ParsedDocument serializer / deserializer
# ------------------------------------------------------------------


def _serialize_block(block: Block) -> dict[str, Any]:
    """Convert a concrete Block subclass to a JSON-serializable dict."""
    common: dict[str, Any] = {
        "ordinal": block.ordinal,
        "page_number": block.page_number,
        "language": block.language,
        "metadata": dict(block.metadata),
    }
    if block.bounding_box is not None:
        common["bounding_box"] = list(block.bounding_box)

    if isinstance(block, TextBlock):
        return {"type": "text", **common, "text": block.text}
    if isinstance(block, HeadingBlock):
        return {"type": "heading", **common, "text": block.text, "level": block.level}
    if isinstance(block, TableBlock):
        return {
            "type": "table",
            **common,
            "rows": [list(row) for row in block.rows],
            "header_row_count": block.header_row_count,
        }
    if isinstance(block, ImageBlock):
        return {
            "type": "image",
            **common,
            "asset_id": str(block.asset_id),
            "alt_text": block.alt_text,
        }
    if isinstance(block, CodeBlock):
        return {
            "type": "code",
            **common,
            "code": block.code,
            "code_language": block.code_language,
        }
    if isinstance(block, EquationBlock):
        return {"type": "equation", **common, "latex": block.latex, "display": block.display}
    if isinstance(block, CaptionBlock):
        return {
            "type": "caption",
            **common,
            "text": block.text,
            "target_ordinal": block.target_ordinal,
        }
    raise StorageError(f"unknown block type: {type(block).__name__}")


def _deserialize_block(raw: dict[str, Any]) -> Block:
    """Reconstruct a typed Block from its serialized dict."""
    btype = raw["type"]
    common_kw: dict[str, Any] = {
        "ordinal": raw["ordinal"],
        "page_number": raw.get("page_number"),
        "language": raw.get("language"),
        "metadata": FrozenMetadata(raw.get("metadata") or {}),
    }
    bb = raw.get("bounding_box")
    if bb is not None:
        common_kw["bounding_box"] = tuple(float(v) for v in bb)

    if btype == "text":
        return TextBlock(**common_kw, text=raw["text"])
    if btype == "heading":
        return HeadingBlock(**common_kw, text=raw["text"], level=raw["level"])
    if btype == "table":
        return TableBlock(
            **common_kw,
            rows=tuple(tuple(cell for cell in row) for row in raw["rows"]),
            header_row_count=raw.get("header_row_count", 0),
        )
    if btype == "image":
        return ImageBlock(
            **common_kw,
            asset_id=UUID(raw["asset_id"]),
            alt_text=raw.get("alt_text"),
        )
    if btype == "code":
        return CodeBlock(
            **common_kw,
            code=raw["code"],
            code_language=raw.get("code_language"),
        )
    if btype == "equation":
        return EquationBlock(
            **common_kw,
            latex=raw["latex"],
            display=bool(raw.get("display", True)),
        )
    if btype == "caption":
        return CaptionBlock(
            **common_kw,
            text=raw["text"],
            target_ordinal=raw.get("target_ordinal"),
        )
    raise StorageError(f"unknown block type in IR: {btype!r}")


def _serialize_document_metadata(meta: DocumentMetadata) -> dict[str, Any]:
    """Serialize DocumentMetadata to a JSON-compatible dict."""
    return {
        "content_hash": meta.content_hash,
        "title": meta.title,
        "authors": list(meta.authors),
        "publication_date": meta.publication_date.isoformat() if meta.publication_date else None,
        "url": meta.url,
        "doi": meta.doi,
        "isbn": meta.isbn,
        "page_count": meta.page_count,
        "metadata": dict(meta.metadata),
    }


def _deserialize_document_metadata(raw: dict[str, Any]) -> DocumentMetadata:
    """Reconstruct DocumentMetadata from a serialized dict."""
    from datetime import date

    pub_date_raw = raw.get("publication_date")
    pub_date = date.fromisoformat(pub_date_raw) if pub_date_raw else None
    return DocumentMetadata(
        content_hash=raw["content_hash"],
        title=raw.get("title"),
        authors=tuple(raw.get("authors") or []),
        publication_date=pub_date,
        url=raw.get("url"),
        doi=raw.get("doi"),
        isbn=raw.get("isbn"),
        page_count=raw.get("page_count"),
        metadata=FrozenMetadata(raw.get("metadata") or {}),
    )


def _serialize_parsed_document(document: ParsedDocument) -> bytes:
    """Serialize a ParsedDocument to canonical UTF-8 JSON bytes.

    The envelope includes ``model`` and ``schema_version`` per ADR-0002 §4.7.
    """
    envelope: dict[str, Any] = {
        "model": "parsed_document",
        "schema_version": _IR_SCHEMA_VERSION,
        "language": document.language,
        "doc_type": document.doc_type.value,
        "metadata": _serialize_document_metadata(document.metadata),
        "blocks": [_serialize_block(block) for block in document.blocks],
    }
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _deserialize_parsed_document(data: bytes) -> ParsedDocument:
    """Reconstruct a ParsedDocument from canonical UTF-8 JSON bytes."""
    try:
        envelope = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IntegrityError(f"IR JSON is malformed: {exc}") from exc

    if not isinstance(envelope, dict):
        raise IntegrityError("IR JSON root must be an object")
    model = envelope.get("model")
    if model != "parsed_document":
        raise IntegrityError(f"IR model field mismatch: expected 'parsed_document', got {model!r}")
    schema_ver = envelope.get("schema_version")
    if schema_ver != _IR_SCHEMA_VERSION:
        raise IntegrityError(
            f"IR schema_version {schema_ver!r} not supported; expected {_IR_SCHEMA_VERSION}"
        )

    try:
        blocks_raw = envelope.get("blocks") or []
        blocks = tuple(_deserialize_block(b) for b in blocks_raw)
        metadata = _deserialize_document_metadata(envelope["metadata"])
        doc_type = DocType(envelope["doc_type"])
        language = envelope["language"]
    except (KeyError, TypeError, ValueError) as exc:
        raise IntegrityError(f"IR deserialization failed: {exc}") from exc

    return ParsedDocument(
        blocks=blocks,
        metadata=metadata,
        language=language,
        doc_type=doc_type,
    )


# ------------------------------------------------------------------
# FilesystemBlobStore
# ------------------------------------------------------------------


class FilesystemBlobStore:
    """Content-addressed filesystem store for blobs and parsed IR.

    Implements the BlobStore contract from ADR-0002 §5.2.

    Parameters
    ----------
    root:
        Absolute directory that will contain all stored data.  Configuration
        loading creates and validates this directory; FilesystemBlobStore
        accepts any resolved absolute Path.
    """

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("root must be a Path")
        if not root.is_absolute():
            raise ValueError(f"root must be an absolute path, got: {root}")
        self._root = root
        self._open = False

    # ------------------------------------------------------------------
    # Internal path helpers
    # ------------------------------------------------------------------

    def _blob_dir(self, content_hash: str) -> Path:
        """Return the content-addressed shard directory for *content_hash*."""
        return self._root / content_hash[:2] / content_hash[2:]

    def _blob_path(self, content_hash: str, mime_type: str) -> Path:
        """Return the path for the raw asset file."""
        ext = _mime_to_extension(mime_type)
        return self._blob_dir(content_hash) / f"raw{ext}"

    def _asset_index_path(self, asset_id: UUID) -> Path:
        """Return the side-car index path for *asset_id*."""
        return self._root / "_index" / "assets" / f"{asset_id}.json"

    def _ir_path(self, version_id: UUID) -> Path:
        """Return the parsed IR path for *version_id*."""
        prefix = str(version_id)[:8]
        return self._root / "parsed" / prefix / f"{version_id}.ir.json"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """Open the store: ensure required directories exist.

        Idempotent; safe to call multiple times.
        """
        try:
            for subdir in ("_index/assets", "parsed"):
                (self._root / subdir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"could not initialize blob store at {self._root}: {exc}") from exc
        self._open = True

    async def close(self) -> None:
        """Close the store.  Idempotent; no I/O resources to release."""
        self._open = False

    def _require_open(self) -> None:
        """Raise a lifecycle error if the store is not open."""
        if not self._open:
            raise LifecycleError("FilesystemBlobStore is not open; call open() first")

    # ------------------------------------------------------------------
    # BlobStore: blob operations
    # ------------------------------------------------------------------

    async def put_asset(
        self,
        data: bytes,
        mime_type: str,
        metadata: FrozenMetadata,
    ) -> Asset:
        """Persist *data* content-addressed and return an immutable Asset.

        Idempotent: identical bytes always produce the same Asset record.
        Raises IntegrityError if the same asset_id exists with different content.
        """
        self._require_open()
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data must be bytes")
        if not mime_type or not mime_type.strip():
            raise ValueError("mime_type must not be empty")
        if not isinstance(metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")

        content_hash = _compute_sha256(data)
        asset_id = _asset_id_for_hash(content_hash)
        blob_path = self._blob_path(content_hash, mime_type)
        index_path = self._asset_index_path(asset_id)

        # --- integrity check for existing index entry ---
        if index_path.exists():
            try:
                existing_raw = index_path.read_text(encoding="utf-8")
                existing = json.loads(existing_raw)
                stored_hash = existing.get("content_hash")
            except (OSError, json.JSONDecodeError) as exc:
                raise StorageError(f"could not read asset index {index_path}: {exc}") from exc
            if stored_hash != content_hash:
                raise IntegrityError(
                    f"asset_id {asset_id} already maps to a different content hash"
                )

        # --- write blob (idempotent) ---
        try:
            _atomic_write(blob_path, bytes(data))
        except OSError as exc:
            raise StorageError(f"could not write blob {blob_path}: {exc}") from exc

        # --- write index entry ---
        index_entry = {
            "schema_version": _ASSET_INDEX_SCHEMA_VERSION,
            "asset_id": str(asset_id),
            "content_hash": content_hash,
            "mime_type": mime_type,
            "storage_uri": f"blob://{content_hash}",
        }
        index_bytes = json.dumps(index_entry, ensure_ascii=False, sort_keys=True).encode("utf-8")
        try:
            _atomic_write(index_path, index_bytes)
        except OSError as exc:
            raise StorageError(f"could not write asset index {index_path}: {exc}") from exc

        return Asset(
            asset_id=asset_id,
            mime_type=mime_type,
            content_hash=content_hash,
            storage_uri=f"blob://{content_hash}",
            metadata=metadata,
        )

    async def get_asset(self, asset_id: UUID) -> bytes | None:
        """Return asset bytes, or None if the asset does not exist.

        Raises IntegrityError if the stored bytes fail the content hash check.
        """
        self._require_open()
        if not isinstance(asset_id, UUID):
            raise TypeError("asset_id must be a UUID")

        index_path = self._asset_index_path(asset_id)
        if not index_path.exists():
            return None

        try:
            index_raw = index_path.read_text(encoding="utf-8")
            index = json.loads(index_raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"could not read asset index {index_path}: {exc}") from exc

        content_hash = index.get("content_hash")
        mime_type = index.get("mime_type", "application/octet-stream")
        if not content_hash:
            raise IntegrityError(f"asset index for {asset_id} is missing content_hash")

        blob_path = self._blob_path(content_hash, mime_type)
        if not blob_path.exists():
            return None

        try:
            data = blob_path.read_bytes()
        except OSError as exc:
            raise StorageError(f"could not read blob {blob_path}: {exc}") from exc

        actual_hash = _compute_sha256(data)
        if actual_hash != content_hash:
            raise IntegrityError(
                f"blob integrity failure for asset {asset_id}: "
                f"expected {content_hash}, got {actual_hash}"
            )

        return data

    async def delete_asset(self, asset_id: UUID) -> bool:
        """Delete one asset; returns True if it existed, False otherwise."""
        self._require_open()
        if not isinstance(asset_id, UUID):
            raise TypeError("asset_id must be a UUID")

        index_path = self._asset_index_path(asset_id)
        if not index_path.exists():
            return False

        try:
            index_raw = index_path.read_text(encoding="utf-8")
            index = json.loads(index_raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"could not read asset index {index_path}: {exc}") from exc

        # Remove the index entry first so partial failure leaves the blob
        try:
            index_path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"could not remove asset index {index_path}: {exc}") from exc

        # Remove the blob file (best-effort; we do not check for shared content)
        content_hash = index.get("content_hash", "")
        mime_type = index.get("mime_type", "application/octet-stream")
        if content_hash:
            blob_path = self._blob_path(content_hash, mime_type)
            try:
                blob_path.unlink(missing_ok=True)
                # Clean up the shard directory if it is now empty
                blob_dir = self._blob_dir(content_hash)
                try:
                    blob_dir.rmdir()
                    blob_dir.parent.rmdir()
                except OSError:
                    pass
            except OSError as exc:
                raise StorageError(f"could not remove blob {blob_path}: {exc}") from exc

        return True

    async def contains_hash(self, content_hash: str) -> bool:
        """Return True if any blob with *content_hash* exists on disk."""
        self._require_open()
        if not isinstance(content_hash, str) or len(content_hash) != 64:
            raise ValueError("content_hash must be a 64-character hex SHA-256 digest")
        return self._blob_dir(content_hash).exists()

    # ------------------------------------------------------------------
    # BlobStore: parsed IR operations
    # ------------------------------------------------------------------

    async def put_parsed_document(
        self,
        version_id: UUID,
        document: ParsedDocument,
    ) -> None:
        """Persist a ParsedDocument IR atomically by *version_id*.

        Idempotent: writing the same content for the same version_id succeeds.
        Raises ConflictError if a different document is already stored for
        this version_id.
        """
        self._require_open()
        if not isinstance(version_id, UUID):
            raise TypeError("version_id must be a UUID")
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")

        ir_path = self._ir_path(version_id)
        new_bytes = _serialize_parsed_document(document)

        if ir_path.exists():
            try:
                existing_bytes = ir_path.read_bytes()
            except OSError as exc:
                raise StorageError(f"could not read existing IR {ir_path}: {exc}") from exc
            if existing_bytes == new_bytes:
                return  # idempotent
            raise ConflictError(f"version_id {version_id} already has a different parsed IR stored")

        try:
            _atomic_write(ir_path, new_bytes)
        except OSError as exc:
            raise StorageError(f"could not write parsed IR {ir_path}: {exc}") from exc

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        """Return the ParsedDocument IR for *version_id*, or None if absent."""
        self._require_open()
        if not isinstance(version_id, UUID):
            raise TypeError("version_id must be a UUID")

        ir_path = self._ir_path(version_id)
        if not ir_path.exists():
            return None

        try:
            data = ir_path.read_bytes()
        except OSError as exc:
            raise StorageError(f"could not read IR {ir_path}: {exc}") from exc

        return _deserialize_parsed_document(data)

    # ------------------------------------------------------------------
    # Lifecycle inspection
    # ------------------------------------------------------------------

    async def health_check(self) -> tuple[HealthStatus, ...]:
        """Return health observations for the filesystem backend."""
        checked_at = datetime.now(UTC)
        healthy = self._open and self._root.is_dir() and os.access(self._root, os.W_OK)
        detail = None if healthy else "filesystem root is not a writable directory"
        return (
            HealthStatus(
                healthy=healthy,
                component="storage.filesystem",
                checked_at=checked_at,
                detail=detail,
            ),
        )

    def capabilities(self) -> StorageCapabilities:
        """Return immutable capabilities for the filesystem backend."""
        return StorageCapabilities(
            supports_blobs=True,
            supports_dense_search=False,
            supports_sparse_search=False,
            supports_metadata=False,
            supports_graph=False,
            supports_transactions=False,
            supports_health_checks=True,
        )
