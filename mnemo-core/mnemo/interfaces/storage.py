"""Atomic storage facade contract."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models import (
    Asset,
    Chunk,
    Citation,
    Document,
    DocumentStatus,
    Entity,
    FrozenMetadata,
    GraphEdge,
    Insight,
    MetadataFilter,
    Note,
    Notebook,
    ParsedDocument,
    ScoredChunk,
    Session,
    Source,
    Turn,
)

from .types import (
    EmbeddingVector,
    HealthStatus,
    Page,
    StorageCapabilities,
)


@runtime_checkable
class StorageInterfaceV1(Protocol):  # pragma: no cover
    """Provide one atomic facade over every configured local storage backend."""

    async def open(self) -> None:
        """Open owned storage resources idempotently."""
        ...

    async def close(self) -> None:
        """Close owned storage resources idempotently."""
        ...

    async def health_check(self) -> tuple[HealthStatus, ...]:
        """Return health observations for configured storage capabilities."""
        ...

    def capabilities(self) -> StorageCapabilities:
        """Return immutable descriptive storage capabilities."""
        ...

    async def put_asset(
        self,
        data: bytes,
        mime_type: str,
        metadata: FrozenMetadata,
    ) -> Asset:
        """Persist content-addressed bytes and return their asset record."""
        ...

    async def get_asset(self, asset_id: UUID) -> bytes | None:
        """Return asset bytes when the identity exists."""
        ...

    async def delete_asset(self, asset_id: UUID) -> bool:
        """Delete one asset and report whether it existed."""
        ...

    async def put_parsed_document(
        self,
        version_id: UUID,
        document: ParsedDocument,
    ) -> None:
        """Persist a parsed intermediate representation atomically."""
        ...

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        """Return a parsed intermediate representation when present."""
        ...

    async def contains_hash(self, content_hash: str) -> bool:
        """Return whether content with a SHA-256 digest is present."""
        ...

    async def upsert_document(self, document: Document) -> None:
        """Insert or replace a document registry snapshot."""
        ...

    async def get_document(self, document_id: UUID) -> Document | None:
        """Return a document registry snapshot when present."""
        ...

    async def list_documents(
        self,
        status: DocumentStatus | None,
        limit: int,
        cursor: str | None,
    ) -> Page[Document]:
        """Return a stable page of document registry snapshots."""
        ...

    async def delete_document(
        self,
        document_id: UUID,
        expected_version_id: UUID | None,
    ) -> bool:
        """Delete one registry record with an optional version precondition."""
        ...

    async def upsert_notebook(self, notebook: Notebook) -> None:
        """Insert or replace a notebook snapshot."""
        ...

    async def get_notebook(self, notebook_id: UUID) -> Notebook | None:
        """Return a notebook when present."""
        ...

    async def delete_notebook(self, notebook_id: UUID) -> bool:
        """Delete a notebook and report whether it existed."""
        ...

    async def list_notebooks(self, limit: int, cursor: str | None) -> Page[Notebook]:
        """Return a stable page of notebooks."""
        ...

    async def upsert_source(self, source: Source) -> None:
        """Insert or replace a source association."""
        ...

    async def get_source(self, source_id: UUID) -> Source | None:
        """Return a source association when present."""
        ...

    async def delete_source(self, source_id: UUID) -> bool:
        """Delete a source association and report whether it existed."""
        ...

    async def list_sources(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Source]:
        """Return a stable page of notebook sources."""
        ...

    async def upsert_note(self, note: Note) -> None:
        """Insert or replace a note snapshot."""
        ...

    async def get_note(self, note_id: UUID) -> Note | None:
        """Return a note when present."""
        ...

    async def delete_note(self, note_id: UUID) -> bool:
        """Delete a note and report whether it existed."""
        ...

    async def list_notes(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Note]:
        """Return a stable page of notebook notes."""
        ...

    async def upsert_insight(self, insight: Insight) -> None:
        """Insert or replace an insight snapshot."""
        ...

    async def get_insight(self, insight_id: UUID) -> Insight | None:
        """Return an insight when present."""
        ...

    async def delete_insight(self, insight_id: UUID) -> bool:
        """Delete an insight and report whether it existed."""
        ...

    async def list_insights(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Insight]:
        """Return a stable page of notebook insights."""
        ...

    async def upsert_session(self, session: Session) -> None:
        """Insert or replace a conversation session."""
        ...

    async def get_session(self, session_id: UUID) -> Session | None:
        """Return a conversation session when present."""
        ...

    async def list_sessions(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Session]:
        """Return a stable page of notebook sessions."""
        ...

    async def append_turn(self, session_id: UUID, turn: Turn) -> None:
        """Append one turn idempotently to a session."""
        ...

    async def list_turns(
        self,
        session_id: UUID,
        after_turn_id: UUID | None,
        limit: int,
    ) -> Page[Turn]:
        """Return an ordered page of conversation turns."""
        ...

    async def upsert_citation(self, citation: Citation) -> None:
        """Insert or replace a versioned citation."""
        ...

    async def get_citations_for_turn(self, turn_id: UUID) -> tuple[Citation, ...]:
        """Return the citations attached to a turn."""
        ...

    async def delete_session(self, session_id: UUID) -> bool:
        """Delete a session and report whether it existed."""
        ...

    async def upsert_entity(self, entity: Entity) -> None:
        """Insert or replace a graph entity."""
        ...

    async def upsert_edge(self, edge: GraphEdge) -> None:
        """Insert or replace a graph edge."""
        ...

    async def get_entity(self, entity_id: UUID) -> Entity | None:
        """Return a graph entity when present."""
        ...

    async def find_entities(
        self,
        canonical_name: str,
        entity_type: str | None,
        document_ids: tuple[UUID, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        """Find bounded entities by normalized name and optional constraints."""
        ...

    async def get_related_entities(
        self,
        entity_id: UUID,
        hops: int,
        relations: tuple[str, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        """Traverse a bounded number of graph hops."""
        ...

    async def delete_graph_for_document(self, document_id: UUID) -> None:
        """Delete graph records derived from one document."""
        ...

    async def upsert_chunks(self, chunks: tuple[Chunk, ...]) -> None:
        """Atomically persist chunks to every configured index."""
        ...

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Return one chunk by its stable SHA-256 identity."""
        ...

    async def delete_chunks_for_document(
        self,
        document_id: UUID,
        version_id: UUID | None,
    ) -> None:
        """Delete all matching chunks from every configured index."""
        ...

    async def search_dense(
        self,
        embedding: EmbeddingVector,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Run bounded dense retrieval through the atomic facade."""
        ...

    async def search_sparse(
        self,
        query: str,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Run bounded sparse retrieval through the atomic facade."""
        ...

    async def delete_document_cascade(self, document_id: UUID) -> None:
        """Atomically delete a document and all facade-owned derived records."""
        ...


StorageInterface = StorageInterfaceV1
