"""Qdrant-backed dense vector storage."""

from dataclasses import dataclass
from datetime import UTC, date
from typing import cast
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from mnemo.config import QdrantStorageConfig
from mnemo.interfaces.types import (
    EmbeddingVector,
    HealthStatus,
    Page,
    StorageCapabilities,
)
from mnemo.models import (
    Asset,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    Citation,
    DocType,
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

from .retrieval_projection import RetrievalMetadataProjection


@dataclass(frozen=True, slots=True)
class _ProjectedChunkSnapshot:
    chunk: Chunk
    projection: RetrievalMetadataProjection | None


class QdrantStore:
    """Qdrant-backed vector storage for chunks and dense retrieval."""

    def __init__(self, config: QdrantStorageConfig, vector_dimensions: int) -> None:
        """Initialize the storage configuration without connecting."""
        self._config = config
        self._dimensions = vector_dimensions
        self._client: AsyncQdrantClient | None = None

    def _require_open(self) -> AsyncQdrantClient:
        """Assert the storage is open and return the connection."""
        if self._client is None:
            raise RuntimeError("QdrantStore is not open")
        return self._client

    # Lifecycle Methods
    # -------------------------------------------------------------------------

    async def open(self) -> None:
        """Open owned storage resources idempotently."""
        if not self._config.enabled:
            return
        if self._client is not None:
            return

        api_key = self._config.api_key if self._config.api_key else None
        self._client = AsyncQdrantClient(
            url=str(self._config.url),
            api_key=api_key,
        )

        try:
            exists = await self._client.collection_exists(self._config.collection_name)
            if not exists:
                await self._client.create_collection(
                    collection_name=self._config.collection_name,
                    vectors_config=models.VectorParams(
                        size=self._dimensions,
                        distance=models.Distance.COSINE,
                        on_disk=self._config.on_disk,
                    ),
                )
            await self._ensure_retrieval_payload_indexes()
        except Exception as e:
            await self._client.close()
            self._client = None
            raise RuntimeError(f"Failed to initialize Qdrant collection: {e}") from e

    async def close(self) -> None:
        """Close owned storage resources idempotently."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def health_check(self) -> tuple[HealthStatus, ...]:
        """Return health observations for configured storage capabilities."""
        from datetime import datetime

        if not self._config.enabled:
            return (
                HealthStatus(
                    healthy=False,
                    component="qdrant",
                    checked_at=datetime.now(UTC),
                    detail="Qdrant storage is explicitly disabled in config.",
                ),
            )

        if self._client is None:
            return (
                HealthStatus(
                    healthy=False,
                    component="qdrant",
                    checked_at=datetime.now(UTC),
                    detail="Qdrant storage is not open.",
                ),
            )

        try:
            await self._client.get_collections()
            return (
                HealthStatus(
                    healthy=True,
                    component="qdrant",
                    checked_at=datetime.now(UTC),
                ),
            )
        except Exception as e:
            return (
                HealthStatus(
                    healthy=False,
                    component="qdrant",
                    checked_at=datetime.now(UTC),
                    detail=f"Qdrant connection failed: {e}",
                ),
            )

    def capabilities(self) -> StorageCapabilities:
        """Return immutable descriptive storage capabilities."""
        return StorageCapabilities(
            supports_blobs=False,
            supports_dense_search=True,
            supports_sparse_search=False,
            supports_metadata=False,
            supports_graph=False,
            supports_transactions=False,
            supports_health_checks=True,
        )

    # Chunk Search & Storage Methods
    # -------------------------------------------------------------------------

    async def upsert_chunks(self, chunks: tuple[Chunk, ...]) -> None:
        """Atomically persist chunks to every configured index."""
        if not self._config.enabled:
            return
        await self._upsert_chunks(chunks, projection=None)

    async def _upsert_chunks_with_projection(
        self,
        chunks: tuple[Chunk, ...],
        projection: RetrievalMetadataProjection,
    ) -> None:
        """Persist chunks with version-aware derived retrieval metadata."""
        if not self._config.enabled:
            return
        await self._upsert_chunks(chunks, projection=projection)

    async def _upsert_chunks(
        self,
        chunks: tuple[Chunk, ...],
        *,
        projection: RetrievalMetadataProjection | None,
    ) -> None:
        if not self._config.enabled:
            return
        client = self._require_open()
        if not chunks:
            return

        points: list[models.PointStruct] = []
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(f"Chunk {chunk.id} is missing embedding for vector store")

            points.append(
                models.PointStruct(
                    id=_point_id(chunk.id),
                    vector=list(chunk.embedding),
                    payload=_chunk_payload(chunk, projection),
                )
            )

        # Batch upsert
        await client.upsert(
            collection_name=self._config.collection_name,
            points=points,
            wait=True,
        )

    async def _ensure_retrieval_payload_indexes(self) -> None:
        """Create indexes for derived fields used by pre-ANN filtering."""
        client = self._require_open()
        fields = (
            ("doc_type", models.PayloadSchemaType.KEYWORD),
            ("publication_date_ordinal", models.PayloadSchemaType.INTEGER),
            ("source_ids", models.PayloadSchemaType.KEYWORD),
            ("notebook_ids", models.PayloadSchemaType.KEYWORD),
        )
        for field_name, schema in fields:
            await client.create_payload_index(
                collection_name=self._config.collection_name,
                field_name=field_name,
                field_schema=schema,
                wait=True,
            )

    async def _set_document_membership(
        self,
        document_id: UUID,
        *,
        source_ids: tuple[UUID, ...],
        notebook_ids: tuple[UUID, ...],
    ) -> None:
        """Refresh mutable document-level membership on all indexed versions."""
        if not self._config.enabled:
            return
        await self._require_open().set_payload(
            collection_name=self._config.collection_name,
            payload={
                "source_ids": [str(value) for value in source_ids],
                "notebook_ids": [str(value) for value in notebook_ids],
            },
            points=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(document_id)),
                    )
                ]
            ),
            wait=True,
        )

    async def _snapshot_chunks(self, chunk_ids: tuple[str, ...]) -> tuple[Chunk, ...]:
        """Capture affected Qdrant points, including their vectors."""
        if not self._config.enabled or not chunk_ids:
            return ()
        records = await self._require_open().retrieve(
            collection_name=self._config.collection_name,
            ids=[_point_id(chunk_id) for chunk_id in chunk_ids],
            with_payload=True,
            with_vectors=True,
        )
        requested = frozenset(chunk_ids)
        by_id: dict[str, Chunk] = {}
        for record in records:
            chunk = _record_to_chunk(record)
            if chunk.id in requested:
                by_id[chunk.id] = chunk
        return tuple(by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id)

    async def _restore_chunk_snapshot(
        self,
        attempted_ids: tuple[str, ...],
        previous_chunks: tuple[Chunk, ...],
    ) -> None:
        """Restore affected points and delete only identities introduced by an attempt."""
        if not self._config.enabled or not attempted_ids:
            return
        if previous_chunks:
            await self.upsert_chunks(previous_chunks)
        previous_ids = frozenset(chunk.id for chunk in previous_chunks)
        new_ids = tuple(chunk_id for chunk_id in attempted_ids if chunk_id not in previous_ids)
        if new_ids:
            await self._require_open().delete(
                collection_name=self._config.collection_name,
                points_selector=models.PointIdsList(
                    points=[_point_id(chunk_id) for chunk_id in new_ids]
                ),
                wait=True,
            )

    async def _snapshot_chunks_with_projection(
        self, chunk_ids: tuple[str, ...]
    ) -> tuple[_ProjectedChunkSnapshot, ...]:
        """Capture chunks and their derived retrieval payload for exact rollback."""
        if not self._config.enabled or not chunk_ids:
            return ()
        records = await self._require_open().retrieve(
            collection_name=self._config.collection_name,
            ids=[_point_id(chunk_id) for chunk_id in chunk_ids],
            with_payload=True,
            with_vectors=True,
        )
        requested = frozenset(chunk_ids)
        by_id: dict[str, _ProjectedChunkSnapshot] = {}
        for record in records:
            chunk = _record_to_chunk(record)
            if chunk.id in requested:
                by_id[chunk.id] = _ProjectedChunkSnapshot(
                    chunk=chunk,
                    projection=_projection_from_payload(record.payload),
                )
        return tuple(by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id)

    async def _restore_projected_chunk_snapshot(
        self,
        attempted_ids: tuple[str, ...],
        snapshots: tuple[_ProjectedChunkSnapshot, ...],
    ) -> None:
        """Restore projected points exactly and remove newly introduced identities."""
        if not self._config.enabled:
            return
        for snapshot in snapshots:
            await self._upsert_chunks((snapshot.chunk,), projection=snapshot.projection)
        previous_ids = frozenset(snapshot.chunk.id for snapshot in snapshots)
        new_ids = tuple(chunk_id for chunk_id in attempted_ids if chunk_id not in previous_ids)
        if new_ids:
            await self._require_open().delete(
                collection_name=self._config.collection_name,
                points_selector=models.PointIdsList(
                    points=[_point_id(chunk_id) for chunk_id in new_ids]
                ),
                wait=True,
            )

    async def search_dense(
        self,
        embedding: EmbeddingVector,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Run bounded dense retrieval through the atomic facade."""
        if not self._config.enabled:
            return ()

        client = self._require_open()

        qdrant_filters: list[models.Condition] = []

        if filters.doc_types:
            qdrant_filters.append(
                models.FieldCondition(
                    key="doc_type",
                    match=models.MatchAny(any=[t.value for t in filters.doc_types]),
                )
            )
        if filters.notebook_id is not None:
            qdrant_filters.append(
                models.FieldCondition(
                    key="notebook_ids",
                    match=models.MatchValue(value=str(filters.notebook_id)),
                )
            )
        if filters.source_ids:
            qdrant_filters.append(
                models.FieldCondition(
                    key="source_ids",
                    match=models.MatchAny(any=[str(value) for value in filters.source_ids]),
                )
            )
        if filters.date_after is not None or filters.date_before is not None:
            qdrant_filters.append(
                models.FieldCondition(
                    key="publication_date_ordinal",
                    range=models.Range(
                        gte=(filters.date_after.toordinal() if filters.date_after else None),
                        lte=(filters.date_before.toordinal() if filters.date_before else None),
                    ),
                )
            )

        search_filter = None
        if qdrant_filters:
            search_filter = models.Filter(must=qdrant_filters)

        results = await client.query_points(
            collection_name=self._config.collection_name,
            query=list(embedding),
            query_filter=search_filter,
            limit=top_k,
        )
        points = results.points

        scored_chunks: list[ScoredChunk] = []
        for idx, scored_point in enumerate(points):
            payload = scored_point.payload
            if not payload:
                continue

            position_data = payload["position"]
            position = ChunkPosition(
                section_index=position_data["section_index"],
                chunk_index_in_section=position_data["chunk_index_in_section"],
                page_number=position_data.get("page_number"),
                start_offset=position_data.get("start_offset"),
                end_offset=position_data.get("end_offset"),
            )

            chunk = Chunk(
                id=payload["id"],
                text=payload["text"],
                document_id=UUID(payload["document_id"]),
                version_id=UUID(payload["version_id"]),
                chunk_type=ChunkType(payload["chunk_type"]),
                position=position,
                source_span=BlockSpan(
                    start_ordinal=payload["source_span"]["start_ordinal"],
                    end_ordinal=payload["source_span"]["end_ordinal"],
                ),
                heading_path=tuple(payload["heading_path"]),
                parent_chunk_id=payload.get("parent_chunk_id"),
                sibling_ids=tuple(payload.get("sibling_ids", [])),
                metadata=FrozenMetadata(payload.get("metadata", {})),
                embedding=None,  # Exclude embedding from returned chunk to save memory
            )
            scored_chunks.append(
                ScoredChunk(chunk=chunk, score=scored_point.score, source="qdrant", rank=idx + 1)
            )

        return tuple(scored_chunks)

    async def delete_chunks_for_document(
        self,
        document_id: UUID,
        version_id: UUID | None,
    ) -> None:
        """Delete all matching chunks from every configured index."""
        if not self._config.enabled:
            return
        client = self._require_open()

        must_filters: list[models.Condition] = [
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=str(document_id)),
            )
        ]

        if version_id is not None:
            must_filters.append(
                models.FieldCondition(
                    key="version_id",
                    match=models.MatchValue(value=str(version_id)),
                )
            )

        await client.delete(
            collection_name=self._config.collection_name,
            points_selector=models.FilterSelector(filter=models.Filter(must=must_filters)),
        )

    # Stubs for unused interfaces
    # -------------------------------------------------------------------------
    async def put_asset(self, data: bytes, mime_type: str, metadata: FrozenMetadata) -> Asset:
        raise NotImplementedError("QdrantStore does not implement put_asset")

    async def get_asset(self, asset_id: UUID) -> bytes | None:
        raise NotImplementedError("QdrantStore does not implement get_asset")

    async def delete_asset(self, asset_id: UUID) -> bool:
        raise NotImplementedError("QdrantStore does not implement delete_asset")

    async def put_parsed_document(self, version_id: UUID, document: ParsedDocument) -> None:
        raise NotImplementedError("QdrantStore does not implement put_parsed_document")

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        raise NotImplementedError("QdrantStore does not implement get_parsed_document")

    async def contains_hash(self, content_hash: str) -> bool:
        raise NotImplementedError("QdrantStore does not implement contains_hash")

    async def upsert_document(self, document: Document) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_document")

    async def get_document(self, document_id: UUID) -> Document | None:
        raise NotImplementedError("QdrantStore does not implement get_document")

    async def get_document_by_content_hash(self, content_hash: str) -> Document | None:
        raise NotImplementedError("QdrantStore does not implement get_document_by_content_hash")

    async def list_documents(
        self, status: DocumentStatus | None, limit: int, cursor: str | None
    ) -> Page[Document]:
        raise NotImplementedError("QdrantStore does not implement list_documents")

    async def delete_document(self, document_id: UUID, expected_version_id: UUID | None) -> bool:
        raise NotImplementedError("QdrantStore does not implement delete_document")

    async def upsert_notebook(self, notebook: Notebook) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_notebook")

    async def get_notebook(self, notebook_id: UUID) -> Notebook | None:
        raise NotImplementedError("QdrantStore does not implement get_notebook")

    async def delete_notebook(self, notebook_id: UUID) -> bool:
        raise NotImplementedError("QdrantStore does not implement delete_notebook")

    async def list_notebooks(self, limit: int, cursor: str | None) -> Page[Notebook]:
        raise NotImplementedError("QdrantStore does not implement list_notebooks")

    async def upsert_source(self, source: Source) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_source")

    async def get_source(self, source_id: UUID) -> Source | None:
        raise NotImplementedError("QdrantStore does not implement get_source")

    async def delete_source(self, source_id: UUID) -> bool:
        raise NotImplementedError("QdrantStore does not implement delete_source")

    async def list_sources(self, notebook_id: UUID, limit: int, cursor: str | None) -> Page[Source]:
        raise NotImplementedError("QdrantStore does not implement list_sources")

    async def upsert_note(self, note: Note) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_note")

    async def get_note(self, note_id: UUID) -> Note | None:
        raise NotImplementedError("QdrantStore does not implement get_note")

    async def delete_note(self, note_id: UUID) -> bool:
        raise NotImplementedError("QdrantStore does not implement delete_note")

    async def list_notes(self, notebook_id: UUID, limit: int, cursor: str | None) -> Page[Note]:
        raise NotImplementedError("QdrantStore does not implement list_notes")

    async def upsert_insight(self, insight: Insight) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_insight")

    async def get_insight(self, insight_id: UUID) -> Insight | None:
        raise NotImplementedError("QdrantStore does not implement get_insight")

    async def delete_insight(self, insight_id: UUID) -> bool:
        raise NotImplementedError("QdrantStore does not implement delete_insight")

    async def list_insights(
        self, notebook_id: UUID, limit: int, cursor: str | None
    ) -> Page[Insight]:
        raise NotImplementedError("QdrantStore does not implement list_insights")

    async def upsert_session(self, session: Session) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_session")

    async def get_session(self, session_id: UUID) -> Session | None:
        raise NotImplementedError("QdrantStore does not implement get_session")

    async def list_sessions(
        self, notebook_id: UUID, limit: int, cursor: str | None
    ) -> Page[Session]:
        raise NotImplementedError("QdrantStore does not implement list_sessions")

    async def append_turn(self, session_id: UUID, turn: Turn) -> None:
        raise NotImplementedError("QdrantStore does not implement append_turn")

    async def list_turns(
        self, session_id: UUID, after_turn_id: UUID | None, limit: int
    ) -> Page[Turn]:
        raise NotImplementedError("QdrantStore does not implement list_turns")

    async def upsert_citation(self, citation: Citation) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_citation")

    async def get_citations_for_turn(self, turn_id: UUID) -> tuple[Citation, ...]:
        raise NotImplementedError("QdrantStore does not implement get_citations_for_turn")

    async def delete_session(self, session_id: UUID) -> bool:
        raise NotImplementedError("QdrantStore does not implement delete_session")

    async def upsert_entity(self, entity: Entity) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_entity")

    async def upsert_edge(self, edge: GraphEdge) -> None:
        raise NotImplementedError("QdrantStore does not implement upsert_edge")

    async def get_entity(self, entity_id: UUID) -> Entity | None:
        raise NotImplementedError("QdrantStore does not implement get_entity")

    async def find_entities(
        self,
        normalized_name: str,
        entity_type: str | None,
        document_ids: tuple[UUID, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        raise NotImplementedError("QdrantStore does not implement find_entities")

    async def get_related_entities(
        self, entity_id: UUID, hops: int, relations: tuple[str, ...], limit: int
    ) -> tuple[Entity, ...]:
        raise NotImplementedError("QdrantStore does not implement get_related_entities")

    async def delete_graph_for_document(self, document_id: UUID) -> None:
        raise NotImplementedError("QdrantStore does not implement delete_graph_for_document")

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        raise NotImplementedError(
            "QdrantStore does not implement get_chunk directly (use dense search)"
        )

    async def search_sparse(
        self, query: str, filters: MetadataFilter, top_k: int
    ) -> tuple[ScoredChunk, ...]:
        raise NotImplementedError("QdrantStore does not implement sparse search")

    async def delete_document_cascade(self, document_id: UUID) -> None:
        raise NotImplementedError("QdrantStore does not implement delete_document_cascade directly")


def _point_id(chunk_id: str) -> str:
    return str(UUID(chunk_id[:32]))


def _chunk_payload(
    chunk: Chunk,
    projection: RetrievalMetadataProjection | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": chunk.id,
        "text": chunk.text,
        "document_id": str(chunk.document_id),
        "version_id": str(chunk.version_id),
        "chunk_type": chunk.chunk_type.value,
        "position": {
            "section_index": chunk.position.section_index,
            "chunk_index_in_section": chunk.position.chunk_index_in_section,
            "page_number": chunk.position.page_number,
            "start_offset": chunk.position.start_offset,
            "end_offset": chunk.position.end_offset,
        },
        "source_span": {
            "start_ordinal": chunk.source_span.start_ordinal,
            "end_ordinal": chunk.source_span.end_ordinal,
        },
        "heading_path": list(chunk.heading_path),
        "parent_chunk_id": chunk.parent_chunk_id,
        "sibling_ids": list(chunk.sibling_ids),
        "metadata": dict(chunk.metadata),
    }
    if projection is not None:
        payload.update(projection.payload())
    return payload


def _projection_from_payload(
    payload: dict[str, object] | None,
) -> RetrievalMetadataProjection | None:
    if payload is None or "doc_type" not in payload:
        return None
    publication_date_raw = payload.get("publication_date")
    source_values = payload.get("source_ids", [])
    notebook_values = payload.get("notebook_ids", [])
    if not isinstance(source_values, list) or not isinstance(notebook_values, list):
        raise ValueError("invalid retrieval membership payload")
    return RetrievalMetadataProjection(
        doc_type=DocType(str(payload["doc_type"])),
        publication_date=(
            date.fromisoformat(str(publication_date_raw))
            if publication_date_raw is not None
            else None
        ),
        title=(str(payload["document_title"]) if payload.get("document_title") else None),
        source_ids=tuple(sorted((UUID(str(value)) for value in source_values), key=str)),
        notebook_ids=tuple(sorted((UUID(str(value)) for value in notebook_values), key=str)),
    )


def _record_to_chunk(record: models.Record) -> Chunk:
    payload = record.payload
    vector = record.vector
    if (
        payload is None
        or not isinstance(vector, list)
        or not all(isinstance(component, (int, float)) for component in vector)
    ):
        raise ValueError("stored Qdrant chunk snapshot is incomplete")
    values = cast(list[int | float], vector)
    position = cast(dict[str, object], payload["position"])
    source_span = cast(dict[str, object], payload["source_span"])
    return Chunk(
        id=str(payload["id"]),
        text=str(payload["text"]),
        document_id=UUID(str(payload["document_id"])),
        version_id=UUID(str(payload["version_id"])),
        chunk_type=ChunkType(str(payload["chunk_type"])),
        position=ChunkPosition(
            section_index=int(cast(int, position["section_index"])),
            chunk_index_in_section=int(cast(int, position["chunk_index_in_section"])),
            page_number=cast(int | None, position.get("page_number")),
            start_offset=cast(int | None, position.get("start_offset")),
            end_offset=cast(int | None, position.get("end_offset")),
        ),
        source_span=BlockSpan(
            start_ordinal=int(cast(int, source_span["start_ordinal"])),
            end_ordinal=int(cast(int, source_span["end_ordinal"])),
        ),
        heading_path=tuple(cast(list[str], payload["heading_path"])),
        parent_chunk_id=cast(str | None, payload.get("parent_chunk_id")),
        sibling_ids=tuple(cast(list[str], payload.get("sibling_ids", []))),
        metadata=FrozenMetadata(cast(dict[str, object], payload.get("metadata", {}))),
        embedding=tuple(float(component) for component in values),
    )
