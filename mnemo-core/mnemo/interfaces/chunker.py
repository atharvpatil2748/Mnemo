"""Chunker contract for parsed documents."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models import Chunk, ChunkDraft, DocType, ParsedDocument

from .tokenizer import TokenCounterInterfaceV1
from .types import ChunkerCapabilities, ChunkingContext, ChunkingOptions


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


@runtime_checkable
class ChunkerInterfaceV2(Protocol):  # pragma: no cover
    """Produce ordered provenance-bearing drafts for central finalization."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]: ...

    def capabilities(self) -> ChunkerCapabilities: ...

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]: ...
