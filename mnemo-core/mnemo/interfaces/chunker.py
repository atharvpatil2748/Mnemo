"""Chunker contract for parsed documents."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models import Chunk, DocType, ParsedDocument

from .types import ChunkerCapabilities, ChunkingOptions


@runtime_checkable
class ChunkerInterfaceV1(Protocol):  # pragma: no cover
    """Create ordered semantic chunks without embedding or persistence."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the document classifications accepted by this chunker."""
        ...

    def capabilities(self) -> ChunkerCapabilities:
        """Return immutable descriptive chunker capabilities."""
        ...

    def chunk(
        self,
        document: ParsedDocument,
        version_id: UUID,
        options: ChunkingOptions,
    ) -> tuple[Chunk, ...]:
        """Chunk a parsed document synchronously and deterministically."""
        ...


ChunkerInterface = ChunkerInterfaceV1
