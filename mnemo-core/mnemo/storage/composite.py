"""Atomic storage facade composing disparate backends."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from mnemo.interfaces.errors import ContractValidationError, IntegrityError, StorageError
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
from mnemo.models.final_qa_execution import (
    FinalQAExecution,
    FinalQAExecutionSnapshot,
    FinalQAExecutionSnapshotPhase,
    FinalQAExecutionState,
)

from .filesystem import FilesystemBlobStore
from .qdrant import QdrantStore
from .retrieval_projection import RetrievalMetadataProjection
from .sqlite import SQLiteStore
from .surrealdb import SurrealDBStore

logger = logging.getLogger(__name__)


class _Compensator:
    """Records and executes compensating actions on failure."""

    def __init__(self) -> None:
        self._actions: list[Callable[[], Awaitable[None]]] = []

    def add(self, action: Callable[[], Awaitable[None]]) -> None:
        self._actions.append(action)

    async def rollback(self) -> tuple[Exception, ...]:
        """Execute compensating actions in reverse order and report failures."""
        failures: list[Exception] = []
        for action in reversed(self._actions):
            try:
                await action()
            except Exception as exc:
                failures.append(exc)
                logger.critical("Rollback action failed, consistency compromised: %s", exc)
        return tuple(failures)


class CompositeStorage:
    """The central storage router coordinating all backends."""

    def __init__(
        self,
        filesystem: FilesystemBlobStore,
        sqlite: SQLiteStore,
        qdrant: QdrantStore,
        surrealdb: SurrealDBStore,
    ) -> None:
        self._fs = filesystem
        self._sql = sqlite
        self._qdr = qdrant
        self._sur = surrealdb
        self._chunk_write_lock = asyncio.Lock()
        self._projection_lock = asyncio.Lock()

    async def open(self) -> None:
        try:
            await self._fs.open()
            await self._sql.open()
            await self._qdr.open()
            await self._sur.open()
        except Exception as e:
            logger.error("Failed to open CompositeStorage backends; closing initialized resources")
            # Ensure partial initialization is closed
            await self.close()
            if isinstance(e, StorageError):
                raise
            raise StorageError("Failed to open composite storage") from e

    async def close(self) -> None:
        errors = []
        for backend in (self._fs, self._sql, self._qdr, self._sur):
            try:
                await backend.close()
            except Exception as e:
                errors.append(e)
        if errors:
            logger.error("Errors occurred during close: %s", errors)

    async def health_check(self) -> tuple[HealthStatus, ...]:
        results: list[HealthStatus] = []
        for backend in (self._fs, self._sql, self._qdr, self._sur):
            results.extend(await backend.health_check())
        return tuple(results)

    def capabilities(self) -> StorageCapabilities:
        fs_cap = self._fs.capabilities()
        sql_cap = self._sql.capabilities()
        qdr_cap = self._qdr.capabilities()
        sur_cap = self._sur.capabilities()

        return StorageCapabilities(
            supports_blobs=fs_cap.supports_blobs or sql_cap.supports_blobs,
            supports_dense_search=qdr_cap.supports_dense_search,
            supports_sparse_search=sql_cap.supports_sparse_search,
            supports_metadata=sql_cap.supports_metadata,
            supports_graph=sur_cap.supports_graph,
            supports_transactions=sql_cap.supports_transactions,
            supports_health_checks=True,
        )

    # -------------------------------------------------------------------------
    # Filesystem operations
    # -------------------------------------------------------------------------
    async def put_asset(self, data: bytes, mime_type: str, metadata: FrozenMetadata) -> Asset:
        try:
            return await self._fs.put_asset(data, mime_type, metadata)
        except Exception as e:
            if isinstance(e, StorageError):
                raise
            raise StorageError("Failed to put asset") from e

    async def get_asset(self, asset_id: UUID) -> bytes | None:
        return await self._fs.get_asset(asset_id)

    async def delete_asset(self, asset_id: UUID) -> bool:
        return await self._fs.delete_asset(asset_id)

    async def put_parsed_document(self, version_id: UUID, document: ParsedDocument) -> None:
        return await self._fs.put_parsed_document(version_id, document)

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        return await self._fs.get_parsed_document(version_id)

    async def contains_hash(self, content_hash: str) -> bool:
        return await self._fs.contains_hash(content_hash)

    # -------------------------------------------------------------------------
    # SQLite operations
    # -------------------------------------------------------------------------
    async def upsert_document(self, document: Document) -> None:
        return await self._sql.upsert_document(document)

    async def get_document(self, document_id: UUID) -> Document | None:
        return await self._sql.get_document(document_id)

    async def get_document_by_content_hash(self, content_hash: str) -> Document | None:
        return await self._sql.get_document_by_content_hash(content_hash)

    async def list_documents(
        self,
        status: DocumentStatus | None,
        limit: int,
        cursor: str | None,
    ) -> Page[Document]:
        return await self._sql.list_documents(status, limit, cursor)

    async def delete_document(
        self,
        document_id: UUID,
        expected_version_id: UUID | None,
    ) -> bool:
        return await self._sql.delete_document(document_id, expected_version_id)

    async def upsert_notebook(self, notebook: Notebook) -> None:
        return await self._sql.upsert_notebook(notebook)

    async def get_notebook(self, notebook_id: UUID) -> Notebook | None:
        return await self._sql.get_notebook(notebook_id)

    async def delete_notebook(self, notebook_id: UUID) -> bool:
        async with self._projection_lock:
            if await self._sql.get_notebook(notebook_id) is None:
                return False
            sources = await self._sql._list_sources_for_notebook(notebook_id)
            affected = tuple(source.document_id for source in sources)
            try:
                await self._refresh_memberships_excluding_notebook(affected, notebook_id)
            except Exception as error:
                failures = await self._compensate_memberships(affected)
                if failures:
                    raise StorageError(
                        "notebook delete pre-projection failed and compensation was incomplete"
                    ) from error
                raise StorageError("notebook delete pre-projection failed") from error
            try:
                return await self._sql.delete_notebook(notebook_id)
            except Exception as error:
                failures = await self._compensate_memberships(affected)
                if failures:
                    raise StorageError(
                        "notebook delete failed and projection compensation was incomplete"
                    ) from error
                raise StorageError("notebook delete failed; projection restored") from error

    async def list_notebooks(self, limit: int, cursor: str | None) -> Page[Notebook]:
        return await self._sql.list_notebooks(limit, cursor)

    async def upsert_source(self, source: Source) -> None:
        async with self._projection_lock:
            previous = await self._sql.get_source(source.source_id)
            await self._sql.upsert_source(source)
            affected: tuple[UUID, ...] = (source.document_id,)
            if previous is not None and previous.document_id != source.document_id:
                affected = (previous.document_id, source.document_id)
            try:
                await self._refresh_memberships(affected)
            except Exception as error:
                failures = await self._restore_source(source.source_id, previous, affected)
                if failures:
                    raise StorageError(
                        "source upsert projection failed and compensation was incomplete"
                    ) from error
                raise StorageError(
                    "source upsert projection failed; canonical write rolled back"
                ) from error

    async def get_source(self, source_id: UUID) -> Source | None:
        return await self._sql.get_source(source_id)

    async def delete_source(self, source_id: UUID) -> bool:
        async with self._projection_lock:
            previous = await self._sql.get_source(source_id)
            if previous is None:
                return False
            deleted = await self._sql.delete_source(source_id)
            try:
                await self._refresh_memberships((previous.document_id,))
            except Exception as error:
                failures = await self._restore_source(source_id, previous, (previous.document_id,))
                if failures:
                    raise StorageError(
                        "source delete projection failed and compensation was incomplete"
                    ) from error
                raise StorageError(
                    "source delete projection failed; canonical write rolled back"
                ) from error
            return deleted

    async def list_sources(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Source]:
        return await self._sql.list_sources(notebook_id, limit, cursor)

    async def upsert_note(self, note: Note) -> None:
        return await self._sql.upsert_note(note)

    async def get_note(self, note_id: UUID) -> Note | None:
        return await self._sql.get_note(note_id)

    async def delete_note(self, note_id: UUID) -> bool:
        return await self._sql.delete_note(note_id)

    async def list_notes(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Note]:
        return await self._sql.list_notes(notebook_id, limit, cursor)

    async def upsert_insight(self, insight: Insight) -> None:
        return await self._sql.upsert_insight(insight)

    async def get_insight(self, insight_id: UUID) -> Insight | None:
        return await self._sql.get_insight(insight_id)

    async def delete_insight(self, insight_id: UUID) -> bool:
        return await self._sql.delete_insight(insight_id)

    async def list_insights(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Insight]:
        return await self._sql.list_insights(notebook_id, limit, cursor)

    async def upsert_session(self, session: Session) -> None:
        return await self._sql.upsert_session(session)

    async def get_session(self, session_id: UUID) -> Session | None:
        return await self._sql.get_session(session_id)

    async def list_sessions(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Session]:
        return await self._sql.list_sessions(notebook_id, limit, cursor)

    async def append_turn(self, session_id: UUID, turn: Turn) -> None:
        return await self._sql.append_turn(session_id, turn)

    async def list_turns(
        self,
        session_id: UUID,
        after_turn_id: UUID | None,
        limit: int,
    ) -> Page[Turn]:
        return await self._sql.list_turns(session_id, after_turn_id, limit)

    async def upsert_citation(self, citation: Citation) -> None:
        return await self._sql.upsert_citation(citation)

    async def get_citations_for_turn(self, turn_id: UUID) -> tuple[Citation, ...]:
        return await self._sql.get_citations_for_turn(turn_id)

    async def delete_session(self, session_id: UUID) -> bool:
        return await self._sql.delete_session(session_id)

    # ADR-0056 additive execution persistence remains SQLite-owned.
    async def create_final_qa_execution(self, execution: FinalQAExecution) -> bool:
        return await self._sql.create_final_qa_execution(execution)

    async def get_final_qa_execution(self, assistant_turn_id: UUID) -> FinalQAExecution | None:
        return await self._sql.get_final_qa_execution(assistant_turn_id)

    async def put_final_qa_execution_snapshot(self, snapshot: FinalQAExecutionSnapshot) -> None:
        return await self._sql.put_final_qa_execution_snapshot(snapshot)

    async def get_final_qa_execution_snapshot(
        self, execution_id: UUID, phase: FinalQAExecutionSnapshotPhase
    ) -> FinalQAExecutionSnapshot | None:
        return await self._sql.get_final_qa_execution_snapshot(execution_id, phase)

    async def transition_final_qa_execution(
        self,
        execution_id: UUID,
        expected: FinalQAExecutionState,
        target: FinalQAExecutionState,
        *,
        retry_count: int | None = None,
        failure_classification: str | None = None,
    ) -> bool:
        return await self._sql.transition_final_qa_execution(
            execution_id,
            expected,
            target,
            retry_count=retry_count,
            failure_classification=failure_classification,
        )

    # -------------------------------------------------------------------------
    # SurrealDB operations
    # -------------------------------------------------------------------------
    async def upsert_entity(self, entity: Entity) -> None:
        return await self._sur.upsert_entity(entity)

    async def upsert_edge(self, edge: GraphEdge) -> None:
        return await self._sur.upsert_edge(edge)

    async def get_entity(self, entity_id: UUID) -> Entity | None:
        return await self._sur.get_entity(entity_id)

    async def find_entities(
        self,
        canonical_name: str,
        entity_type: str | None,
        document_ids: tuple[UUID, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        return await self._sur.find_entities(canonical_name, entity_type, document_ids, limit)

    async def get_related_entities(
        self,
        entity_id: UUID,
        hops: int,
        relations: tuple[str, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        return await self._sur.get_related_entities(entity_id, hops, relations, limit)

    async def delete_graph_for_document(self, document_id: UUID) -> None:
        return await self._sur.delete_graph_for_document(document_id)

    # -------------------------------------------------------------------------
    # Composite Multi-backend operations
    # -------------------------------------------------------------------------
    async def upsert_chunks(self, chunks: tuple[Chunk, ...]) -> None:
        if not chunks:
            return

        document_id = chunks[0].document_id
        version_id = chunks[0].version_id
        if any(
            chunk.document_id != document_id or chunk.version_id != version_id
            for chunk in chunks[1:]
        ):
            raise ContractValidationError("chunk batches must share one document_id and version_id")
        chunk_ids = tuple(chunk.id for chunk in chunks)
        if len(frozenset(chunk_ids)) != len(chunk_ids):
            raise ContractValidationError("chunk batches must not contain duplicate chunk IDs")

        async with self._projection_lock, self._chunk_write_lock:
            try:
                projection = await self._build_retrieval_projection(document_id, version_id)
                sqlite_snapshot = await self._sql._snapshot_chunks(chunk_ids)
                sqlite_projection = await self._sql._snapshot_retrieval_projection(
                    document_id, version_id
                )
                qdrant_snapshot = await self._qdr._snapshot_chunks_with_projection(chunk_ids)
                await self._sql._upsert_chunks_with_projection(chunks, projection)
            except Exception as e:
                if isinstance(e, StorageError):
                    raise
                raise StorageError(f"multi-store write failed: {e}") from e

            compensator = _Compensator()
            compensator.add(
                lambda: self._sql._restore_retrieval_projection(
                    document_id, version_id, sqlite_projection
                )
            )
            compensator.add(lambda: self._sql._restore_chunk_snapshot(chunk_ids, sqlite_snapshot))
            # Register before the vector write because Qdrant may partially apply a batch.
            compensator.add(
                lambda: self._qdr._restore_projected_chunk_snapshot(chunk_ids, qdrant_snapshot)
            )
            try:
                await self._qdr._upsert_chunks_with_projection(chunks, projection)
            except Exception as e:
                rollback_failures = await compensator.rollback()
                if rollback_failures:
                    raise StorageError("multi-store write and compensating rollback failed") from e
                if isinstance(e, StorageError):
                    raise
                raise StorageError(f"multi-store write failed: {e}") from e

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        return await self._sql.get_chunk(chunk_id)

    async def delete_chunks_for_document(
        self,
        document_id: UUID,
        version_id: UUID | None,
    ) -> None:
        async with self._chunk_write_lock:
            try:
                await self._qdr.delete_chunks_for_document(document_id, version_id)
                await self._sql.delete_chunks_for_document(document_id, version_id)
            except Exception as e:
                if isinstance(e, StorageError):
                    raise
                raise StorageError(f"multi-store delete failed: {e}") from e

    async def search_dense(
        self,
        embedding: EmbeddingVector,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        return await self._qdr.search_dense(embedding, filters, top_k)

    async def _build_retrieval_projection(
        self,
        document_id: UUID,
        version_id: UUID,
    ) -> RetrievalMetadataProjection:
        """Derive one exact-version vector payload from canonical stores."""
        document = await self._sql.get_document(document_id)
        if document is None:
            raise IntegrityError("cannot index chunks without their canonical document")
        version = next(
            (candidate for candidate in document.versions if candidate.version_id == version_id),
            None,
        )
        if version is None:
            raise IntegrityError("chunk version does not belong to its canonical document")
        parsed = await self._fs.get_parsed_document(version_id)
        if parsed is None:
            raise IntegrityError("cannot index chunks without exact-version parsed IR")
        if parsed.metadata.content_hash != version.content_hash:
            raise IntegrityError("parsed IR content hash does not match document version")
        sources = await self._sql._list_sources_for_document(document_id)
        return RetrievalMetadataProjection(
            doc_type=parsed.doc_type,
            publication_date=version.metadata.publication_date,
            title=version.metadata.title,
            source_ids=tuple(sorted({source.source_id for source in sources}, key=str)),
            notebook_ids=tuple(sorted({source.notebook_id for source in sources}, key=str)),
        )

    async def _refresh_memberships(self, document_ids: tuple[UUID, ...]) -> None:
        """Rebuild mutable membership payloads from canonical Source rows."""
        for document_id in tuple(dict.fromkeys(document_ids)):
            sources = await self._sql._list_sources_for_document(document_id)
            await self._qdr._set_document_membership(
                document_id,
                source_ids=tuple(sorted({source.source_id for source in sources}, key=str)),
                notebook_ids=tuple(sorted({source.notebook_id for source in sources}, key=str)),
            )

    async def _refresh_memberships_excluding_notebook(
        self,
        document_ids: tuple[UUID, ...],
        notebook_id: UUID,
    ) -> None:
        """Project post-delete membership before a notebook cascade."""
        for document_id in tuple(dict.fromkeys(document_ids)):
            sources = tuple(
                source
                for source in await self._sql._list_sources_for_document(document_id)
                if source.notebook_id != notebook_id
            )
            await self._qdr._set_document_membership(
                document_id,
                source_ids=tuple(sorted({source.source_id for source in sources}, key=str)),
                notebook_ids=tuple(sorted({source.notebook_id for source in sources}, key=str)),
            )

    async def _compensate_memberships(
        self, document_ids: tuple[UUID, ...]
    ) -> tuple[Exception, ...]:
        try:
            await self._refresh_memberships(document_ids)
        except Exception as error:
            return (error,)
        return ()

    async def _restore_source(
        self,
        source_id: UUID,
        previous: Source | None,
        affected: tuple[UUID, ...],
    ) -> tuple[Exception, ...]:
        compensator = _Compensator()
        compensator.add(lambda: self._refresh_memberships(affected))
        if previous is None:
            compensator.add(lambda: self._delete_source_for_compensation(source_id))
        else:
            compensator.add(lambda: self._sql.upsert_source(previous))
        return await compensator.rollback()

    async def _delete_source_for_compensation(self, source_id: UUID) -> None:
        await self._sql.delete_source(source_id)

    async def search_sparse(
        self,
        query: str,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        return await self._sql.search_sparse(query, filters, top_k)

    async def delete_document_cascade(self, document_id: UUID) -> None:
        try:
            # Dependent deletes are idempotent, so a failed cascade can be retried safely.
            await self._qdr.delete_chunks_for_document(document_id, None)
            await self._sur.delete_graph_for_document(document_id)

            await self._sql.delete_document_cascade(document_id)
        except Exception as e:
            if isinstance(e, StorageError):
                raise
            raise StorageError(f"cascade delete failed: {e}") from e
