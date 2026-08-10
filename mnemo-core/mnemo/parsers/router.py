import hashlib
import importlib
import mimetypes
import warnings
from pathlib import Path
from typing import Protocol, cast

from mnemo.interfaces.errors import UnsupportedError
from mnemo.interfaces.parser_models import ParseResult
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.interfaces.types import FileMetadata
from mnemo.models import Document, FrozenMetadata
from mnemo.registry import PluginRegistry


class _MagicModule(Protocol):
    def from_buffer(self, data: bytes, *, mime: bool) -> object: ...


def _magic_from_buffer(data: bytes) -> str | None:
    """Return libmagic's MIME result when the optional native runtime is usable."""
    try:
        module = cast(_MagicModule, importlib.import_module("magic"))
        result = module.from_buffer(data, mime=True)
    except (ImportError, OSError, AttributeError):
        return None
    return result if isinstance(result, str) else None


class ParserRouter:
    """Orchestrates parsing by delegating to the appropriate ParserInterface.

    Responsibilities:
    - Compute SHA-256 for deduplication
    - Resolve MIME types using python-magic and mimetypes
    - Find the best parser via the PluginRegistry
    - Delegate parsing to the resolved parser
    """

    def __init__(self, registry: PluginRegistry, storage: StorageInterfaceV1) -> None:
        """Initialize the ParserRouter with a registry and storage."""
        self.registry = registry
        self.storage = storage

    def register_builtins(self) -> None:
        """Compatibility shim; the engine registers built-ins during initialization."""
        warnings.warn(
            "ParserRouter.register_builtins() is deprecated; KnowledgeEngine owns registration",
            DeprecationWarning,
            stacklevel=2,
        )

    def _detect_mime(self, data: bytes, filename: str) -> str:
        """Detect the MIME type of the input bytes.

        Uses python-magic to inspect the bytes. If magic fails or returns
        a generic octet-stream, falls back to the file extension via mimetypes.

        Args:
            data: The raw file bytes.
            filename: The original filename to use for fallback.

        Returns:
            The detected MIME type string.
        """
        try:
            mime = _magic_from_buffer(data)
            if mime and mime != "application/octet-stream":
                return mime
        except Exception:
            # If magic fails for any reason, fallback to mimetypes
            pass

        # Fallback to extension matching
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            return mime_type

        return "application/octet-stream"

    async def route(self, data: bytes, filename: str) -> Document | ParseResult:
        """Route the given bytes to the correct parser, or deduplicate.

        Args:
            data: The raw file bytes.
            filename: The original filename.

        Returns:
            A Document if the file was deduplicated, otherwise a ParseResult.

        Raises:
            UnsupportedError: If no parser can handle the detected MIME type or extension.
        """
        # 1. Compute SHA-256 for deduplication
        sha256_hash = hashlib.sha256(data).hexdigest()

        # 2. Duplicate check
        existing_doc = await self.storage.get_document_by_content_hash(sha256_hash)
        if existing_doc is not None:
            return existing_doc

        # 3. MIME/Extension Resolution
        mime_type = self._detect_mime(data, filename)
        extension = Path(filename).suffix.lower()

        # 4. Parser Resolution
        parser = self.registry.resolve_parser(mime_type)
        if not parser and extension:
            parser = self.registry.resolve_parser(extension)

        if not parser:
            raise UnsupportedError(
                f"No parser found for MIME type '{mime_type}' or extension '{extension}'"
            )

        # 5. Dispatch
        metadata = FileMetadata(
            content_hash=sha256_hash,
            size_bytes=len(data),
            mime_type=mime_type,
            modified_at=None,
            metadata=FrozenMetadata(),
        )

        return parser.parse(data, filename, metadata)
