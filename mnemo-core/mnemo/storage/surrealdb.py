"""SurrealDB storage backend for graph persistence."""

from typing import Any
from uuid import UUID

from surrealdb import AsyncSurreal as Surreal

from mnemo.config import SurrealDBStorageConfig
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.interfaces.types import (
    EmbeddingVector,
    HealthStatus,
    Page,
    StorageCapabilities,
)
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


class SurrealDBStore(StorageInterfaceV1):
    """Storage backend implementing graph persistence with SurrealDB."""

    def __init__(self, config: SurrealDBStorageConfig) -> None:
        """Initialize the SurrealDB store with its validated configuration."""
        self._config = config
        self._client: Any | None = None
        self._connected = False

    def _require_open(self) -> Any:
        if not self._connected or self._client is None:
            raise RuntimeError("SurrealDBStore is not open")
        return self._client

    async def open(self) -> None:
        """Open the SurrealDB connection."""
        if self._connected:
            return
        # surrealdb 2.x exposes separate blocking and asynchronous factories.
        # Its asynchronous HTTP transport does not implement the connection
        # lifecycle, while the websocket transport does. Preserve the public
        # HTTP(S) configuration contract and adapt it at this backend boundary.
        endpoint = str(self._config.url).rstrip("/")
        if endpoint.endswith("/rpc"):
            endpoint = endpoint.removesuffix("/rpc")
        if endpoint.startswith("https://"):
            endpoint = "wss://" + endpoint.removeprefix("https://")
        elif endpoint.startswith("http://"):
            endpoint = "ws://" + endpoint.removeprefix("http://")
        self._client = Surreal(endpoint)
        await self._client.connect()  # type: ignore
        await self._client.signin(
            {
                "user": self._config.username,
                "pass": self._config.password,
            }
        )
        await self._client.use(self._config.namespace, self._config.database)
        self._connected = True

    async def close(self) -> None:
        """Close the SurrealDB connection."""
        if not self._connected or self._client is None:
            return
        await self._client.close()
        self._client = None
        self._connected = False

    async def health_check(self) -> tuple[HealthStatus, ...]:
        """Return health observations for configured storage capabilities."""
        if not self._config.enabled:
            return ()
        try:
            client = self._require_open()
            await client.query("RETURN true;")
            from datetime import UTC, datetime

            return (
                HealthStatus(
                    healthy=True,
                    component="surrealdb",
                    checked_at=datetime.now(UTC),
                    detail="Connected",
                ),
            )
        except Exception as error:
            from datetime import UTC, datetime

            return (
                HealthStatus(
                    healthy=False,
                    component="surrealdb",
                    checked_at=datetime.now(UTC),
                    detail=str(error),
                ),
            )

    def capabilities(self) -> StorageCapabilities:
        """Return immutable descriptive storage capabilities."""
        return StorageCapabilities(
            supports_blobs=False,
            supports_dense_search=False,
            supports_sparse_search=False,
            supports_metadata=False,
            supports_graph=self._config.enabled,
            supports_transactions=True,
            supports_health_checks=True,
        )

    async def upsert_entity(self, entity: Entity) -> None:
        """Insert or replace a graph entity."""
        client = self._require_open()
        await client.query(
            "UPSERT type::thing('entity', $id) CONTENT $content;",
            {
                "id": str(entity.entity_id),
                "content": {
                    "canonical_name": entity.canonical_name,
                    "type": entity.type,
                    "confidence": entity.confidence,
                    "document_id": str(entity.document_id),
                    "aliases": list(entity.aliases),
                },
            },
        )

    async def upsert_edge(self, edge: GraphEdge) -> None:
        """Insert or replace a graph edge."""
        client = self._require_open()

        edge_id = f"{edge.source_id}_{edge.relation}_{edge.target_id}"

        await client.query(
            """
            UPSERT type::thing('graph_edge', $edge_id) CONTENT {
                in: type::thing('entity', $source_id),
                out: type::thing('entity', $target_id),
                relation: $relation,
                weight: $weight
            };
            """,
            {
                "edge_id": edge_id,
                "source_id": str(edge.source_id),
                "target_id": str(edge.target_id),
                "relation": edge.relation,
                "weight": edge.weight,
            },
        )

    async def get_entity(self, entity_id: UUID) -> Entity | None:
        """Return a graph entity when present."""
        client = self._require_open()
        result = await client.query(
            "SELECT * FROM type::thing('entity', $id);",
            {"id": str(entity_id)},
        )
        if not result or not result[0].get("result"):
            return None

        items = result[0]["result"]
        if not items:
            return None

        record = items[0]
        return Entity(
            entity_id=UUID(record["id"].split(":")[1]),
            canonical_name=record["canonical_name"],
            type=record["type"],
            confidence=float(record["confidence"]),
            document_id=UUID(record["document_id"]),
            aliases=tuple(record.get("aliases", [])),
        )

    async def find_entities(
        self,
        canonical_name: str,
        entity_type: str | None,
        document_ids: tuple[UUID, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        """Find bounded entities by canonical name and optional constraints."""
        client = self._require_open()

        where_clauses = ["canonical_name = $name"]
        params: dict[str, Any] = {"name": canonical_name, "limit": limit}

        if entity_type is not None:
            where_clauses.append("type = $type")
            params["type"] = entity_type

        if document_ids:
            where_clauses.append("document_id IN $docs")
            params["docs"] = [str(d) for d in document_ids]

        where_sql = " AND ".join(where_clauses)

        query = f"SELECT * FROM entity WHERE {where_sql} LIMIT $limit;"
        result = await client.query(query, params)

        if not result or not result[0].get("result"):
            return ()

        entities = []
        for record in result[0]["result"]:
            entities.append(
                Entity(
                    entity_id=UUID(record["id"].split(":")[1]),
                    canonical_name=record["canonical_name"],
                    type=record["type"],
                    confidence=float(record["confidence"]),
                    document_id=UUID(record["document_id"]),
                    aliases=tuple(record.get("aliases", [])),
                )
            )
        return tuple(entities)

    async def get_related_entities(
        self,
        entity_id: UUID,
        hops: int,
        relations: tuple[str, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        """Traverse a bounded number of graph hops."""
        client = self._require_open()

        if hops < 1:
            return ()

        edge_filter = ""
        params: dict[str, Any] = {"id": str(entity_id), "limit": limit}

        if relations:
            edge_filter = "[WHERE relation IN $rels]"
            params["rels"] = list(relations)

        path = "->graph_edge" + edge_filter + "->entity"
        full_path = "".join([path for _ in range(hops)])

        query = f"SELECT VALUE {full_path} FROM type::thing('entity', $id);"
        result = await client.query(query, params)

        if not result or not result[0].get("result"):
            return ()

        related_nodes = result[0]["result"]

        def flatten(lst: list[Any]) -> list[Any]:
            flat = []
            for item in lst:
                if isinstance(item, list):
                    flat.extend(flatten(item))
                else:
                    flat.append(item)
            return flat

        flat_nodes = flatten(related_nodes)

        seen = set()
        unique_nodes = []
        for node in flat_nodes:
            if isinstance(node, dict) and "id" in node and node["id"] not in seen:
                seen.add(node["id"])
                unique_nodes.append(node)

        unique_nodes = unique_nodes[:limit]

        entities = []
        for record in unique_nodes:
            if "canonical_name" in record:
                entities.append(
                    Entity(
                        entity_id=UUID(record["id"].split(":")[1]),
                        canonical_name=record["canonical_name"],
                        type=record["type"],
                        confidence=float(record["confidence"]),
                        document_id=UUID(record["document_id"]),
                        aliases=tuple(record.get("aliases", [])),
                    )
                )

        return tuple(entities)

    async def delete_graph_for_document(self, document_id: UUID) -> None:
        """Delete graph records derived from one document."""
        client = self._require_open()
        await client.query(
            "DELETE entity WHERE document_id = $doc_id;", {"doc_id": str(document_id)}
        )

    # -------------------------------------------------------------------------
    # Stubs for unused interfaces
    # -------------------------------------------------------------------------

    async def put_asset(self, data: bytes, mime_type: str, metadata: FrozenMetadata) -> Asset:
        raise NotImplementedError("SurrealDBStore does not implement put_asset")

    async def get_asset(self, asset_id: UUID) -> bytes | None:
        raise NotImplementedError("SurrealDBStore does not implement get_asset")

    async def delete_asset(self, asset_id: UUID) -> bool:
        raise NotImplementedError("SurrealDBStore does not implement delete_asset")

    async def put_parsed_document(self, version_id: UUID, document: ParsedDocument) -> None:
        raise NotImplementedError("SurrealDBStore does not implement put_parsed_document")

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        raise NotImplementedError("SurrealDBStore does not implement get_parsed_document")

    async def contains_hash(self, content_hash: str) -> bool:
        raise NotImplementedError("SurrealDBStore does not implement contains_hash")

    async def upsert_document(self, document: Document) -> None:
        raise NotImplementedError("SurrealDBStore does not implement upsert_document")

    async def get_document(self, document_id: UUID) -> Document | None:
        raise NotImplementedError("SurrealDBStore does not implement get_document")

    async def get_document_by_content_hash(self, content_hash: str) -> Document | None:
        raise NotImplementedError("SurrealDBStore does not implement get_document_by_content_hash")

    async def list_documents(
        self, status: DocumentStatus | None, limit: int, cursor: str | None
    ) -> Page[Document]:
        raise NotImplementedError("SurrealDBStore does not implement list_documents")

    async def delete_document(self, document_id: UUID, expected_version_id: UUID | None) -> bool:
        raise NotImplementedError("SurrealDBStore does not implement delete_document")

    async def upsert_notebook(self, notebook: Notebook) -> None:
        raise NotImplementedError("SurrealDBStore does not implement upsert_notebook")

    async def get_notebook(self, notebook_id: UUID) -> Notebook | None:
        raise NotImplementedError("SurrealDBStore does not implement get_notebook")

    async def delete_notebook(self, notebook_id: UUID) -> bool:
        raise NotImplementedError("SurrealDBStore does not implement delete_notebook")

    async def list_notebooks(self, limit: int, cursor: str | None) -> Page[Notebook]:
        raise NotImplementedError("SurrealDBStore does not implement list_notebooks")

    async def upsert_source(self, source: Source) -> None:
        raise NotImplementedError("SurrealDBStore does not implement upsert_source")

    async def get_source(self, source_id: UUID) -> Source | None:
        raise NotImplementedError("SurrealDBStore does not implement get_source")

    async def delete_source(self, source_id: UUID) -> bool:
        raise NotImplementedError("SurrealDBStore does not implement delete_source")

    async def list_sources(self, notebook_id: UUID, limit: int, cursor: str | None) -> Page[Source]:
        raise NotImplementedError("SurrealDBStore does not implement list_sources")

    async def upsert_note(self, note: Note) -> None:
        raise NotImplementedError("SurrealDBStore does not implement upsert_note")

    async def get_note(self, note_id: UUID) -> Note | None:
        raise NotImplementedError("SurrealDBStore does not implement get_note")

    async def delete_note(self, note_id: UUID) -> bool:
        raise NotImplementedError("SurrealDBStore does not implement delete_note")

    async def list_notes(self, notebook_id: UUID, limit: int, cursor: str | None) -> Page[Note]:
        raise NotImplementedError("SurrealDBStore does not implement list_notes")

    async def upsert_insight(self, insight: Insight) -> None:
        raise NotImplementedError("SurrealDBStore does not implement upsert_insight")

    async def get_insight(self, insight_id: UUID) -> Insight | None:
        raise NotImplementedError("SurrealDBStore does not implement get_insight")

    async def delete_insight(self, insight_id: UUID) -> bool:
        raise NotImplementedError("SurrealDBStore does not implement delete_insight")

    async def list_insights(
        self, notebook_id: UUID, limit: int, cursor: str | None
    ) -> Page[Insight]:
        raise NotImplementedError("SurrealDBStore does not implement list_insights")

    async def upsert_session(self, session: Session) -> None:
        raise NotImplementedError("SurrealDBStore does not implement upsert_session")

    async def get_session(self, session_id: UUID) -> Session | None:
        raise NotImplementedError("SurrealDBStore does not implement get_session")

    async def list_sessions(
        self, notebook_id: UUID, limit: int, cursor: str | None
    ) -> Page[Session]:
        raise NotImplementedError("SurrealDBStore does not implement list_sessions")

    async def append_turn(self, session_id: UUID, turn: Turn) -> None:
        raise NotImplementedError("SurrealDBStore does not implement append_turn")

    async def list_turns(
        self, session_id: UUID, after_turn_id: UUID | None, limit: int
    ) -> Page[Turn]:
        raise NotImplementedError("SurrealDBStore does not implement list_turns")

    async def upsert_citation(self, citation: Citation) -> None:
        raise NotImplementedError("SurrealDBStore does not implement upsert_citation")

    async def get_citations_for_turn(self, turn_id: UUID) -> tuple[Citation, ...]:
        raise NotImplementedError("SurrealDBStore does not implement get_citations_for_turn")

    async def delete_session(self, session_id: UUID) -> bool:
        raise NotImplementedError("SurrealDBStore does not implement delete_session")

    async def upsert_chunks(self, chunks: tuple[Chunk, ...]) -> None:
        raise NotImplementedError("SurrealDBStore does not implement upsert_chunks")

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        raise NotImplementedError("SurrealDBStore does not implement get_chunk")

    async def delete_chunks_for_document(self, document_id: UUID, version_id: UUID | None) -> None:
        raise NotImplementedError("SurrealDBStore does not implement delete_chunks_for_document")

    async def search_dense(
        self, embedding: EmbeddingVector, filters: MetadataFilter, top_k: int
    ) -> tuple[ScoredChunk, ...]:
        raise NotImplementedError("SurrealDBStore does not implement search_dense")

    async def search_sparse(
        self, query: str, filters: MetadataFilter, top_k: int
    ) -> tuple[ScoredChunk, ...]:
        raise NotImplementedError("SurrealDBStore does not implement search_sparse")

    async def delete_document_cascade(self, document_id: UUID) -> None:
        raise NotImplementedError("SurrealDBStore does not implement delete_document_cascade")
