"""Atomic storage facade composing disparate backends."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from uuid import UUID

from mnemo.interfaces.advanced_retrieval import (
    CanonicalEvidenceRecord,
    MultilingualEvidencePage,
    MultimodalEvidencePage,
    VisualQueryVector,
)
from mnemo.interfaces.errors import ContractValidationError, IntegrityError, StorageError
from mnemo.interfaces.types import (
    EmbeddingVector,
    HealthStatus,
    Page,
    StorageCapabilities,
)
from mnemo.models import (
    Asset,
    AssetDerivation,
    AssetDerivationDescriptor,
    AssetDerivationStatus,
    AssetOccurrence,
    Chunk,
    Citation,
    Document,
    DocumentBinaryAvailability,
    DocumentBinaryReference,
    DocumentBinaryRole,
    DocumentStatus,
    Entity,
    FrozenMetadata,
    GraphEdge,
    IndexGeneration,
    IndexGenerationState,
    Insight,
    LanguageDerivation,
    LanguageObservation,
    MetadataFilter,
    MultilingualEmbedding,
    Note,
    Notebook,
    OCRResult,
    ParsedDocument,
    ProcessingAttempt,
    ProcessingCheckpoint,
    ProcessingClaim,
    ProcessingFailureClass,
    ProcessingJob,
    ProcessingLedgerEntry,
    ProcessingManifest,
    ProcessingProgressEvent,
    ProcessingResult,
    ScoredChunk,
    Session,
    Source,
    Turn,
    VisionResult,
    VisualEmbedding,
)
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    EvidenceRepresentation,
    PositionalScopeV2,
    RetrievalScopeV2,
)
from mnemo.models.final_qa_execution import (
    FinalQAExecution,
    FinalQAExecutionSnapshot,
    FinalQAExecutionSnapshotPhase,
    FinalQAExecutionState,
)
from mnemo.models.multimodal import (
    EvidenceCitationV2,
    FinalQAExecutionSnapshotV2,
    FinalQAExecutionV2,
)
from mnemo.models.structured_datasets import StructuredDatasetCatalog
from mnemo.models.structured_retrieval import ExtractedStructuredRecord, StructuredField
from mnemo.phase85.projections import ProjectionBuildResult, ProjectionCoverage

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
        self._asset_gc_lock = asyncio.Lock()

    async def active_multimodal_generation_identity(
        self, representation: EvidenceRepresentation, *, profile_id: str | None = None
    ) -> str | None:
        return await self._sql.active_multimodal_generation_identity(
            representation, profile_id=profile_id
        )

    async def retrieve_multimodal_evidence(
        self,
        *,
        representation: EvidenceRepresentation,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        ranked: bool,
        offset: int,
        limit: int,
        query_vector: VisualQueryVector | None = None,
    ) -> MultimodalEvidencePage:
        return await self._sql.retrieve_multimodal_evidence(
            representation=representation,
            scope=scope,
            position=position,
            query=query,
            ranked=ranked,
            offset=offset,
            limit=limit,
            query_vector=query_vector,
        )

    async def active_multilingual_generation_identity(self) -> str | None:
        """Delegate the governed multilingual generation identity to SQLite."""
        return await self._sql.active_multilingual_generation_identity()

    async def retrieve_multilingual_evidence(
        self,
        *,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        offset: int,
        limit: int,
    ) -> MultilingualEvidencePage:
        """Expose SQLite multilingual evidence through the primary storage facade."""
        return await self._sql.retrieve_multilingual_evidence(
            scope=scope,
            position=position,
            query=query,
            offset=offset,
            limit=limit,
        )

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

    async def get_asset_record(self, asset_id: UUID) -> Asset | None:
        """Return catalog metadata, falling back to the verified blob sidecar."""
        catalogued = await self._sql.get_asset_record(asset_id)
        return catalogued if catalogued is not None else await self._fs.get_asset_record(asset_id)

    async def delete_asset(self, asset_id: UUID) -> bool:
        return await self._fs.delete_asset(asset_id)

    async def put_parsed_document(self, version_id: UUID, document: ParsedDocument) -> None:
        await self._fs.put_parsed_document(version_id, document)
        await self._sql.project_structured_document(version_id, document)

    async def project_structured_document(self, version_id: UUID, document: ParsedDocument) -> bool:
        return await self._sql.project_structured_document(version_id, document)

    async def extract_projected_structured_records(
        self,
        candidate: AdvancedRetrievalCandidate,
        fields: tuple[StructuredField, ...],
        *,
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]:
        return await self._sql.extract_projected_structured_records(candidate, fields, limit=limit)

    async def list_structured_datasets(
        self, *, scope: RetrievalScopeV2, schema_scan_limit: int
    ) -> StructuredDatasetCatalog:
        return await self._sql.list_structured_datasets(
            scope=scope, schema_scan_limit=schema_scan_limit
        )

    async def structured_projection_ready(self) -> bool:
        return await self._sql.structured_projection_ready()

    async def active_structured_generation_identity(self) -> str | None:
        return await self._sql.active_structured_generation_identity()

    async def extract_structured_dataset_records(
        self,
        *,
        notebook_id: UUID,
        dataset_id: UUID,
        candidate_id: UUID,
        fields: tuple[StructuredField, ...],
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]:
        return await self._sql.extract_structured_dataset_records(
            notebook_id=notebook_id,
            dataset_id=dataset_id,
            candidate_id=candidate_id,
            fields=fields,
            limit=limit,
        )

    async def create_final_qa_v2_execution(self, execution: FinalQAExecutionV2) -> bool:
        return await self._sql.create_final_qa_v2_execution(execution)

    async def get_final_qa_v2_execution(self, assistant_turn_id: UUID) -> FinalQAExecutionV2 | None:
        return await self._sql.get_final_qa_v2_execution(assistant_turn_id)

    async def put_final_qa_v2_snapshot(self, snapshot: FinalQAExecutionSnapshotV2) -> None:
        await self._sql.put_final_qa_v2_snapshot(snapshot)

    async def get_final_qa_v2_snapshot(
        self, execution_id: UUID, phase: FinalQAExecutionSnapshotPhase
    ) -> FinalQAExecutionSnapshotV2 | None:
        return await self._sql.get_final_qa_v2_snapshot(execution_id, phase)

    async def transition_final_qa_v2_execution(
        self,
        execution_id: UUID,
        expected: FinalQAExecutionState,
        target: FinalQAExecutionState,
        *,
        retry_count: int | None = None,
        failure_classification: str | None = None,
    ) -> bool:
        return await self._sql.transition_final_qa_v2_execution(
            execution_id,
            expected,
            target,
            retry_count=retry_count,
            failure_classification=failure_classification,
        )

    async def put_final_qa_v2_citations(self, citations: tuple[EvidenceCitationV2, ...]) -> None:
        await self._sql.put_final_qa_v2_citations(citations)

    async def put_language_observation(self, observation: LanguageObservation) -> bool:
        return await self._sql.put_language_observation(observation)

    async def get_authorized_language_observation(
        self, *, actor_id: UUID, notebook_id: UUID, observation_id: UUID
    ) -> LanguageObservation | None:
        return await self._sql.get_authorized_language_observation(
            actor_id=actor_id, notebook_id=notebook_id, observation_id=observation_id
        )

    async def put_language_derivation(self, derivation: LanguageDerivation) -> bool:
        return await self._sql.put_language_derivation(derivation)

    async def get_authorized_language_derivation(
        self, *, actor_id: UUID, notebook_id: UUID, derivation_id: UUID
    ) -> LanguageDerivation | None:
        return await self._sql.get_authorized_language_derivation(
            actor_id=actor_id, notebook_id=notebook_id, derivation_id=derivation_id
        )

    async def get_authorized_language_derivation_by_cache_key(
        self, *, actor_id: UUID, notebook_id: UUID, cache_key: str
    ) -> LanguageDerivation | None:
        return await self._sql.get_authorized_language_derivation_by_cache_key(
            actor_id=actor_id, notebook_id=notebook_id, cache_key=cache_key
        )

    async def put_multilingual_embedding(self, embedding: MultilingualEmbedding) -> bool:
        return await self._sql.put_multilingual_embedding(embedding)

    async def get_authorized_multilingual_embedding(
        self, *, notebook_id: UUID, embedding_id: UUID
    ) -> MultilingualEmbedding | None:
        return await self._sql.get_authorized_multilingual_embedding(
            notebook_id=notebook_id, embedding_id=embedding_id
        )

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        return await self._fs.get_parsed_document(version_id)

    async def contains_hash(self, content_hash: str) -> bool:
        return await self._fs.contains_hash(content_hash)

    async def delete_unreferenced_asset(self, asset_id: UUID) -> bool:
        """Garbage-collect bytes only after the additive catalog proves no references."""
        async with self._asset_gc_lock:
            deleted_record = await self._sql.delete_asset_catalog_record(asset_id)
            if not deleted_record:
                return False
            return await self._fs.delete_asset(asset_id)

    # -------------------------------------------------------------------------
    # SQLite operations
    # -------------------------------------------------------------------------
    async def register_asset_ingestion(
        self,
        *,
        assets: tuple[Asset, ...],
        binary_reference: DocumentBinaryReference,
        occurrences: tuple[AssetOccurrence, ...],
    ) -> None:
        return await self._sql.register_asset_ingestion(
            assets=assets,
            binary_reference=binary_reference,
            occurrences=occurrences,
        )

    async def get_document_binary_reference(
        self,
        version_id: UUID,
        role: DocumentBinaryRole = DocumentBinaryRole.ORIGINAL,
    ) -> DocumentBinaryReference | None:
        return await self._sql.get_document_binary_reference(version_id, role)

    async def get_document_binary_availability(
        self,
        version_id: UUID,
        role: DocumentBinaryRole = DocumentBinaryRole.ORIGINAL,
    ) -> DocumentBinaryAvailability:
        return await self._sql.get_document_binary_availability(version_id, role)

    async def get_asset_occurrence(self, occurrence_id: UUID) -> AssetOccurrence | None:
        return await self._sql.get_asset_occurrence(occurrence_id)

    async def list_asset_occurrences(self, version_id: UUID) -> tuple[AssetOccurrence, ...]:
        return await self._sql.list_asset_occurrences(version_id)

    async def get_authorized_asset_occurrence(
        self,
        *,
        notebook_id: UUID,
        occurrence_id: UUID,
    ) -> AssetOccurrence | None:
        return await self._sql.get_authorized_asset_occurrence(
            notebook_id=notebook_id,
            occurrence_id=occurrence_id,
        )

    async def list_authorized_asset_derivations(
        self, *, notebook_id: UUID, occurrence_id: UUID
    ) -> tuple[AssetDerivationDescriptor, ...]:
        return await self._sql.list_authorized_asset_derivations(
            notebook_id=notebook_id, occurrence_id=occurrence_id
        )

    async def create_asset_derivation(self, derivation: AssetDerivation) -> bool:
        return await self._sql.create_asset_derivation(derivation)

    async def get_asset_derivation(self, derivation_id: UUID) -> AssetDerivation | None:
        return await self._sql.get_asset_derivation(derivation_id)

    async def transition_asset_derivation(
        self,
        derivation_id: UUID,
        expected: AssetDerivationStatus,
        target: AssetDerivationStatus,
        *,
        output_asset_id: UUID | None = None,
        output_payload_json: str | None = None,
        confidence: float | None = None,
        language: str | None = None,
    ) -> bool:
        return await self._sql.transition_asset_derivation(
            derivation_id,
            expected,
            target,
            output_asset_id=output_asset_id,
            output_payload_json=output_payload_json,
            confidence=confidence,
            language=language,
        )

    async def create_index_generation(self, generation: IndexGeneration) -> bool:
        return await self._sql.create_index_generation(generation)

    async def get_index_generation(self, generation_id: UUID) -> IndexGeneration | None:
        return await self._sql.get_index_generation(generation_id)

    async def transition_index_generation(
        self,
        generation_id: UUID,
        expected: IndexGenerationState,
        target: IndexGenerationState,
        *,
        item_count: int | None = None,
        checksum: str | None = None,
    ) -> bool:
        return await self._sql.transition_index_generation(
            generation_id,
            expected,
            target,
            item_count=item_count,
            checksum=checksum,
        )

    async def promote_index_generation(self, generation_id: UUID) -> bool:
        return await self._sql.promote_index_generation(generation_id)

    async def get_active_index_generation(
        self, capability: str, profile: str
    ) -> IndexGeneration | None:
        return await self._sql.get_active_index_generation(capability, profile)

    async def put_index_generation_coverage(self, coverage: ProjectionCoverage) -> bool:
        return await self._sql.put_index_generation_coverage(coverage)

    async def get_index_generation_coverage(self, generation_id: UUID) -> ProjectionCoverage | None:
        return await self._sql.get_index_generation_coverage(generation_id)

    async def put_index_generation_sources(
        self,
        *,
        generation_id: UUID,
        source_generation_ids: tuple[UUID, ...],
        source_version_ids: tuple[UUID, ...],
    ) -> bool:
        return await self._sql.put_index_generation_sources(
            generation_id=generation_id,
            source_generation_ids=source_generation_ids,
            source_version_ids=source_version_ids,
        )

    async def get_index_generation_sources(
        self, generation_id: UUID
    ) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
        return await self._sql.get_index_generation_sources(generation_id)

    async def rollback_index_generation(self, generation_id: UUID) -> bool:
        return await self._sql.rollback_index_generation(generation_id)

    async def build_vision_text_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult:
        return await self._sql.build_vision_text_projection(
            generation_id=generation_id,
            source_generation_ids=source_generation_ids,
        )

    async def build_language_text_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult:
        return await self._sql.build_language_text_projection(
            generation_id=generation_id,
            source_generation_ids=source_generation_ids,
        )

    async def build_multilingual_vector_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult:
        return await self._sql.build_multilingual_vector_projection(
            generation_id=generation_id,
            source_generation_ids=source_generation_ids,
        )

    async def add_asset_gc_reference(
        self, asset_id: UUID, reference_kind: str, reference_id: str
    ) -> None:
        return await self._sql.add_asset_gc_reference(asset_id, reference_kind, reference_id)

    async def remove_asset_gc_reference(
        self, asset_id: UUID, reference_kind: str, reference_id: str
    ) -> None:
        return await self._sql.remove_asset_gc_reference(asset_id, reference_kind, reference_id)

    async def is_asset_referenced(self, asset_id: UUID) -> bool:
        return await self._sql.is_asset_referenced(asset_id)

    async def delete_asset_catalog_record(self, asset_id: UUID) -> bool:
        return await self._sql.delete_asset_catalog_record(asset_id)

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

    async def list_sources_for_document(self, document_id: UUID) -> tuple[Source, ...]:
        return await self._sql._list_sources_for_document(document_id)

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

    # ADR-0060 additive durable processing persistence remains SQLite-owned.
    async def submit_processing_job(
        self, manifest: ProcessingManifest, *, now: datetime
    ) -> tuple[ProcessingJob, bool]:
        return await self._sql.submit_processing_job(manifest, now=now)

    async def get_processing_job(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingJob | None:
        return await self._sql.get_processing_job(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id
        )

    async def list_processing_jobs(
        self, *, actor_id: str, notebook_id: UUID, limit: int
    ) -> tuple[ProcessingJob, ...]:
        return await self._sql.list_processing_jobs(
            actor_id=actor_id, notebook_id=notebook_id, limit=limit
        )

    async def claim_processing_job(
        self,
        *,
        actor_id: str,
        notebook_id: UUID,
        worker_id: str,
        lease_duration: timedelta,
        now: datetime,
    ) -> ProcessingClaim | None:
        return await self._sql.claim_processing_job(
            actor_id=actor_id,
            notebook_id=notebook_id,
            worker_id=worker_id,
            lease_duration=lease_duration,
            now=now,
        )

    async def start_processing_attempt(
        self, *, job_id: UUID, lease_token: UUID, now: datetime
    ) -> ProcessingJob:
        return await self._sql.start_processing_attempt(
            job_id=job_id, lease_token=lease_token, now=now
        )

    async def renew_processing_lease(
        self, *, job_id: UUID, lease_token: UUID, lease_duration: timedelta, now: datetime
    ) -> bool:
        return await self._sql.renew_processing_lease(
            job_id=job_id, lease_token=lease_token, lease_duration=lease_duration, now=now
        )

    async def put_processing_checkpoint(
        self, checkpoint: ProcessingCheckpoint, *, lease_token: UUID
    ) -> bool:
        return await self._sql.put_processing_checkpoint(checkpoint, lease_token=lease_token)

    async def get_latest_processing_checkpoint(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingCheckpoint | None:
        return await self._sql.get_latest_processing_checkpoint(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id
        )

    async def request_processing_cancellation(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID, now: datetime
    ) -> ProcessingJob:
        return await self._sql.request_processing_cancellation(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id, now=now
        )

    async def acknowledge_processing_cancellation(
        self, *, job_id: UUID, lease_token: UUID, now: datetime
    ) -> ProcessingJob:
        return await self._sql.acknowledge_processing_cancellation(
            job_id=job_id, lease_token=lease_token, now=now
        )

    async def fail_processing_job(
        self,
        *,
        job_id: UUID,
        lease_token: UUID,
        classification: ProcessingFailureClass,
        retryable: bool,
        now: datetime,
    ) -> ProcessingJob:
        return await self._sql.fail_processing_job(
            job_id=job_id,
            lease_token=lease_token,
            classification=classification,
            retryable=retryable,
            now=now,
        )

    async def resume_processing_job(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID, now: datetime
    ) -> ProcessingJob:
        return await self._sql.resume_processing_job(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id, now=now
        )

    async def recover_expired_processing_leases(self, *, now: datetime) -> tuple[UUID, ...]:
        return await self._sql.recover_expired_processing_leases(now=now)

    async def complete_processing_job(
        self, *, result: ProcessingResult, lease_token: UUID, now: datetime
    ) -> ProcessingJob:
        return await self._sql.complete_processing_job(
            result=result, lease_token=lease_token, now=now
        )

    async def get_processing_result(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingResult | None:
        return await self._sql.get_processing_result(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id
        )

    async def list_processing_attempts(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> tuple[ProcessingAttempt, ...]:
        return await self._sql.list_processing_attempts(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id
        )

    async def append_processing_ledger(
        self, entry: ProcessingLedgerEntry, *, lease_token: UUID
    ) -> bool:
        return await self._sql.append_processing_ledger(entry, lease_token=lease_token)

    async def list_processing_ledger(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> tuple[ProcessingLedgerEntry, ...]:
        return await self._sql.list_processing_ledger(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id
        )

    async def append_processing_progress(
        self, event: ProcessingProgressEvent, *, lease_token: UUID | None = None
    ) -> bool:
        return await self._sql.append_processing_progress(event, lease_token=lease_token)

    async def list_processing_progress(
        self,
        *,
        actor_id: str,
        notebook_id: UUID,
        job_id: UUID,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[ProcessingProgressEvent, ...]:
        return await self._sql.list_processing_progress(
            actor_id=actor_id,
            notebook_id=notebook_id,
            job_id=job_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    async def cleanup_processing_records(self, *, before: datetime, limit: int) -> tuple[UUID, ...]:
        return await self._sql.cleanup_processing_records(before=before, limit=limit)

    # -------------------------------------------------------------------------
    # Additive OCR derivation operations
    # -------------------------------------------------------------------------
    async def put_ocr_result(self, result: OCRResult) -> bool:
        return await self._sql.put_ocr_result(result)

    async def get_authorized_ocr_result(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> OCRResult | None:
        return await self._sql.get_authorized_ocr_result(
            notebook_id=notebook_id, derivation_id=derivation_id
        )

    async def get_authorized_ocr_result_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> OCRResult | None:
        return await self._sql.get_authorized_ocr_result_by_cache_key(
            notebook_id=notebook_id, cache_key=cache_key
        )

    async def project_ocr_result(self, *, generation_id: UUID, result: OCRResult) -> int:
        return await self._sql.project_ocr_result(generation_id=generation_id, result=result)

    async def list_ocr_projection_regions(
        self, *, generation_id: UUID, derivation_id: UUID
    ) -> tuple[UUID, ...]:
        return await self._sql.list_ocr_projection_regions(
            generation_id=generation_id, derivation_id=derivation_id
        )

    # -------------------------------------------------------------------------
    # Additive vision and visual-vector derivation operations
    # -------------------------------------------------------------------------
    async def put_vision_result(self, result: VisionResult) -> bool:
        return await self._sql.put_vision_result(result)

    async def get_authorized_vision_result(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> VisionResult | None:
        return await self._sql.get_authorized_vision_result(
            notebook_id=notebook_id, derivation_id=derivation_id
        )

    async def get_authorized_vision_result_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> VisionResult | None:
        return await self._sql.get_authorized_vision_result_by_cache_key(
            notebook_id=notebook_id, cache_key=cache_key
        )

    async def put_visual_embedding(self, embedding: VisualEmbedding) -> bool:
        return await self._sql.put_visual_embedding(embedding)

    async def get_authorized_visual_embedding(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> VisualEmbedding | None:
        return await self._sql.get_authorized_visual_embedding(
            notebook_id=notebook_id, derivation_id=derivation_id
        )

    async def get_authorized_visual_embedding_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> VisualEmbedding | None:
        return await self._sql.get_authorized_visual_embedding_by_cache_key(
            notebook_id=notebook_id, cache_key=cache_key
        )

    async def project_visual_embedding(
        self, *, generation_id: UUID, embedding: VisualEmbedding
    ) -> bool:
        return await self._sql.project_visual_embedding(
            generation_id=generation_id, embedding=embedding
        )

    async def list_visual_projection_derivations(self, *, generation_id: UUID) -> tuple[UUID, ...]:
        return await self._sql.list_visual_projection_derivations(generation_id=generation_id)

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

    async def list_exact_document_chunks(
        self, *, document_id: UUID, version_id: UUID
    ) -> tuple[Chunk, ...]:
        """Delegate additive exact-version physical chunk enumeration to SQLite."""
        return await self._sql.list_exact_document_chunks(
            document_id=document_id, version_id=version_id
        )

    async def advanced_canonical_snapshot(
        self, *, scope: RetrievalScopeV2, position: PositionalScopeV2, query: str
    ) -> str:
        return await self._sql.advanced_canonical_snapshot(
            scope=scope, position=position, query=query
        )

    async def enumerate_advanced_canonical(
        self,
        *,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        offset: int,
        limit: int,
    ) -> tuple[CanonicalEvidenceRecord, ...]:
        return await self._sql.enumerate_advanced_canonical(
            scope=scope, position=position, query=query, offset=offset, limit=limit
        )

    async def get_advanced_canonical_records(
        self,
        *,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        chunk_ids: tuple[str, ...],
    ) -> tuple[CanonicalEvidenceRecord, ...]:
        return await self._sql.get_advanced_canonical_records(
            scope=scope, position=position, chunk_ids=chunk_ids
        )

    async def expand_advanced_canonical(
        self,
        *,
        scope: RetrievalScopeV2,
        seed_chunk_ids: tuple[str, ...],
        include_parents: bool,
        limit: int,
    ) -> tuple[CanonicalEvidenceRecord, ...]:
        return await self._sql.expand_advanced_canonical(
            scope=scope,
            seed_chunk_ids=seed_chunk_ids,
            include_parents=include_parents,
            limit=limit,
        )

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
            document = await self._sql.get_document(document_id)
            version_ids = (
                ()
                if document is None
                else tuple(version.version_id for version in document.versions)
            )
            # Dependent deletes are idempotent, so a failed cascade can be retried safely.
            await self._qdr.delete_chunks_for_document(document_id, None)
            await self._sur.delete_graph_for_document(document_id)

            await self._sql.delete_document_cascade(document_id)
            for version_id in version_ids:
                await self._fs.delete_parsed_document(version_id)
        except Exception as e:
            if isinstance(e, StorageError):
                raise
            raise StorageError(f"cascade delete failed: {e}") from e
