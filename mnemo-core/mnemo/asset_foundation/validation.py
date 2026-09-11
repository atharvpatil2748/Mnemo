"""Bounded validation for authoritative asset bytes."""

from __future__ import annotations

import hashlib
import io
import mimetypes
import zipfile
from dataclasses import dataclass
from pathlib import Path

from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.parsers.router import _magic_from_buffer

_OOXML_TYPES = {
    "word/document.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt/presentation.xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    "xl/workbook.xml": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True, slots=True)
class AssetPayloadValidation:
    """Verified immutable facts about one bounded payload."""

    content_hash: str
    media_type: str
    byte_size: int


def sanitize_asset_filename(filename: str) -> str:
    """Validate and return a display-only basename without accepting paths."""
    if not isinstance(filename, str):
        raise TypeError("filename must be a string")
    if "\x00" in filename or any(ord(character) < 32 for character in filename):
        raise ContractValidationError("filename contains control characters")
    stripped = filename.strip()
    safe = Path(stripped).name
    if not safe or safe in {".", ".."}:
        raise ContractValidationError("filename must identify a file")
    if safe != stripped or Path(stripped).is_absolute() or "/" in stripped or "\\" in stripped:
        raise ContractValidationError("filename must not contain a filesystem path")
    return safe


def validate_asset_payload(
    data: bytes,
    declared_media_type: str,
    *,
    max_bytes: int,
    filename: str | None = None,
) -> AssetPayloadValidation:
    """Validate size, content identity, and a conservative MIME observation."""
    if not isinstance(data, bytes) or not data:
        raise ContractValidationError("asset payload must be non-empty bytes")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ContractValidationError("max_bytes must be a positive integer")
    if len(data) > max_bytes:
        raise ContractValidationError("asset payload exceeds configured byte limit")
    declared = _canonical_media_type(declared_media_type)
    safe_filename = None if filename is None else sanitize_asset_filename(filename)
    observed = _sniff_media_type(data, safe_filename)
    if observed is not None and not _media_types_compatible(declared, observed):
        raise IntegrityError(f"asset MIME mismatch: declared {declared!r}, observed {observed!r}")
    retained_media_type = (
        declared
        if observed is not None and declared.startswith("text/") and observed.startswith("text/")
        else observed or declared
    )
    return AssetPayloadValidation(
        content_hash=hashlib.sha256(data).hexdigest(),
        media_type=retained_media_type,
        byte_size=len(data),
    )


def _canonical_media_type(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError("declared_media_type must not be empty")
    media_type = value.split(";", 1)[0].strip().lower()
    if "/" not in media_type or any(character.isspace() for character in media_type):
        raise ContractValidationError("declared_media_type is invalid")
    return media_type


def _sniff_media_type(data: bytes, filename: str | None) -> str | None:
    signature = _signature_media_type(data)
    if signature is not None:
        return signature
    magic = _magic_from_buffer(data)
    if magic and magic != "application/octet-stream":
        return _canonical_media_type(magic)
    if filename is not None:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return _canonical_media_type(guessed)
    return None


def _signature_media_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if data.startswith((b"II\xbc\x01", b"MM\x01\xbc")):
        return "image/vnd.ms-photo"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = frozenset(archive.namelist())
        except (OSError, zipfile.BadZipFile):
            return "application/zip"
        for marker, media_type in _OOXML_TYPES.items():
            if marker in names:
                return media_type
        return "application/zip"
    return None


def _media_types_compatible(declared: str, observed: str) -> bool:
    if declared == observed:
        return True
    if declared.startswith("text/") and observed.startswith("text/"):
        return True
    return declared == "application/octet-stream"
