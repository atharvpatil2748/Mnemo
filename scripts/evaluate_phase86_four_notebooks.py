"""Post-audit, read-only four-notebook DERE runner over the shared scoped service.

This intentionally requires independently declared exact chunk targets. Its
current provider profile is the canonical sparse baseline; the disposable
BGE-M3 alias is not represented as evaluated by this command.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, closing
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NotRequired, TextIO, TypedDict, TypeVar, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import aiosqlite

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mnemo.engine import KnowledgeEngine  # noqa: E402
from mnemo.interfaces import NotFoundError, OperationTimeoutError, PrincipalContextV1  # noqa: E402
from mnemo.interfaces.advanced_retrieval import (  # noqa: E402
    AdvancedRetrievalSourceV1,
    AdvancedSourcePage,
    MultilingualAdvancedStoreV1,
    PrincipalAwareAdvancedRetrievalSourceV2,
)
from mnemo.models.advanced_retrieval import (  # noqa: E402
    AdvancedRetrievalCandidate,
    EvidenceRepresentation,
    RetrievalPlanV2,
)
from mnemo.models.multilingual import (  # noqa: E402
    LanguageEvidenceReferenceV3,
    MultilingualQueryEmbeddingV2,
)
from mnemo.models.multilingual_embeddings import MultilingualEmbeddingV3  # noqa: E402
from mnemo.models.multilingual_index import MultilingualTextProjectionRowV2  # noqa: E402
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1  # noqa: E402
from mnemo.phase85.isolated_v2_identity import (  # noqa: E402
    IsolatedV2ArtifactIdentity,
    IsolatedV2DatabaseIdentityVerifier,
)
from mnemo.phase85.profiles import ModelProfileDocument  # noqa: E402
from mnemo.phase85.rebuild_language_capability import (  # noqa: E402
    load_rebuild_language_capability,
)
from mnemo.phase85.v2_evaluation_runtime import V2RuntimeIdentityV1  # noqa: E402
from mnemo.phase85.v2_readiness import V2GenerationEvidence  # noqa: E402
from mnemo.retrieval.advanced import AdvancedRetrievalService, RetrievalCursorCodec  # noqa: E402
from mnemo.retrieval.advanced_sources import CanonicalTextAdvancedSource  # noqa: E402
from mnemo.retrieval.full_multilingual_v2 import PassThroughV2RerankerV1  # noqa: E402
from mnemo.retrieval.multilingual_providers import (  # noqa: E402
    BGE_M3_DOCUMENT_PREPROCESSING,
    BGE_M3_QUERY_PREPROCESSING,
    BGEM3EmbeddingProvider,
)
from mnemo.retrieval.multimodal_sources import ProjectedMultilingualAdvancedSource  # noqa: E402
from mnemo.retrieval.reranker_candidates import V2TypedCandidateBuilderV1  # noqa: E402
from mnemo.retrieval.sparse import SparseRetriever  # noqa: E402
from mnemo.storage.sqlite import SQLiteStore  # noqa: E402
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore  # noqa: E402
from mnemo_server.config import ServerConfig  # noqa: E402
from mnemo_server.schemas.scope_contract_review import (  # noqa: E402
    ScopeRequestReview,
    SelectedNotebooks,
)
from mnemo_server.services.full_multilingual_v2_production import (  # noqa: E402
    ProductionFullMultilingualV2ServerDependencyAssemblerV1,
    V2ProductionRuntimeSupportV1,
)
from mnemo_server.services.full_multilingual_v2_registration import (  # noqa: E402
    ServerOwnedFullMultilingualV2RegistrationV1,
)
from mnemo_server.services.isolated_full_v2_serving import (  # noqa: E402
    _CommonSpaceAdmission,
    _CommonSpaceQueryLanguageResolver,
)
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority  # noqa: E402
from mnemo_server.services.scoped_search import (  # noqa: E402
    ScopedRankedResult,
    ScopedSearchApplicationService,
)

from scripts.phase86_identity_qrels import BOUND_NAME  # noqa: E402
from scripts.run_phase86_four_notebooks import (  # noqa: E402
    CACHE,
    digest,
    notebook_ids,
    preflight,
    run_paths,
    write_json,
)

COMPACT_VECTOR_DB = ROOT / "scratch/module_894_multimodal/eval-compact-f32-20261111-01/mnemo.db"
COMPACT_VECTOR_DB_SHA256 = "8a662b032b4d12ce3fcd4595d23cba7d52999159dec9207196cc1ec96b315f49"
COMPACT_VECTOR_ENCODING = "float32"
COMPACT_SOURCE_ROWS_SHA256 = "acc855d7e730550c968c123cafcc4dac97c78019e557917085064d1b2c3f0590"
COMPACT_ALIAS_DIGEST = "83b0f6684ffbfc3d3fba3ab2634aedddfa3c3434dfd449c2eb7d1fe61b125c93"
COMPACT_MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
COMPACT_VECTOR_COUNT = 10_931

IDENTITY = ("notebook_id", "source_id", "document_id", "version_id", "evidence_id")
T = TypeVar("T")


class _EvaluationOptions(TypedDict):
    per_notebook_readers: bool
    single_notebook_only: bool
    compact_vector_sidecar: bool
    case_ids: NotRequired[tuple[str, ...]]
    retrieval_modes: NotRequired[tuple[str, ...]]


class EvaluationProgress:
    """Append-only, content-free, durable request receipts for one evaluator attempt."""

    def __init__(
        self,
        logs: Path,
        run_id: str,
        *,
        clock: Callable[[], datetime] | None = None,
        timer: Callable[[], float] | None = None,
    ) -> None:
        self.run_id = run_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timer = timer or time.monotonic
        self._context: ContextVar[tuple[str, str] | None] = ContextVar(
            "evaluation_case", default=None
        )
        self._notebook: ContextVar[UUID | None] = ContextVar("evaluation_notebook", default=None)
        self._stages: dict[tuple[str, str, UUID, str], tuple[dict[str, object], float]] = {}
        self._dense_stages: dict[tuple[str, str, UUID, str], tuple[str, datetime]] = {}
        self.path = logs / (
            f"evaluation-progress-{self._clock().strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex}.jsonl"
        )
        self._stream: TextIO = self.path.open("x", encoding="utf-8")

    def close(self) -> None:
        self._stream.close()

    def _append(self, record: dict[str, object]) -> None:
        self._stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self._stream.flush()
        os.fsync(self._stream.fileno())

    def observe_storage_stage(
        self, stage: str, elapsed_seconds: float, count: int, payload_bytes: int
    ) -> None:
        context = self._context.get()
        notebook = self._notebook.get()
        if context is None or notebook is None:
            return
        self._append(
            {
                "schema": "mnemo.phase86-evaluation-storage-stage/1",
                "run_id": self.run_id,
                "case_id": context[0],
                "retrieval_mode": context[1],
                "notebook_id": str(notebook),
                "stage": stage,
                "elapsed_seconds": elapsed_seconds,
                "result_count": count,
                "payload_bytes": payload_bytes,
                "outcome": "completed",
            }
        )

    def observe_dense_stage(
        self,
        notebook: UUID,
        stage: str,
        outcome: str,
        elapsed_seconds: float | None,
        input_count: int | None,
        result_count: int | None,
        exception_class: str | None,
    ) -> None:
        context = self._context.get()
        if context is None:
            raise RuntimeError("dense stage timing requires an active evaluation request")
        case_id, mode = context
        key = (case_id, mode, notebook, stage)
        if outcome == "started":
            if key in self._dense_stages:
                raise RuntimeError("duplicate dense stage start")
            started_at = self._clock()
            self._dense_stages[key] = (started_at.isoformat(), started_at)
            self._append(
                {
                    "schema": "mnemo.phase86-evaluation-dense-stage/1",
                    "run_id": self.run_id,
                    "case_id": case_id,
                    "retrieval_mode": mode,
                    "notebook_id": str(notebook),
                    "stage": stage,
                    "started_at": started_at.isoformat(),
                    "completed_at": None,
                    "elapsed_seconds": None,
                    "outcome": "started",
                    "input_count": input_count,
                    "result_count": None,
                    "exception_class": None,
                }
            )
            return
        try:
            started_iso, _started = self._dense_stages.pop(key)
        except KeyError as error:
            raise RuntimeError("dense stage terminal event has no start") from error
        self._append(
            {
                "schema": "mnemo.phase86-evaluation-dense-stage/1",
                "run_id": self.run_id,
                "case_id": case_id,
                "retrieval_mode": mode,
                "notebook_id": str(notebook),
                "stage": stage,
                "started_at": started_iso,
                "completed_at": self._clock().isoformat(),
                "elapsed_seconds": elapsed_seconds,
                "outcome": outcome,
                "input_count": input_count,
                "result_count": result_count,
                "exception_class": exception_class,
            }
        )

    def start(
        self, *, case_id: str, mode: str, selected: tuple[UUID, ...]
    ) -> tuple[dict[str, object], float]:
        record: dict[str, object] = {
            "schema": "mnemo.phase86-evaluation-progress/1",
            "run_id": self.run_id,
            "case_id": case_id,
            "retrieval_mode": mode,
            "scope_count": len(selected),
            "scope_digest": hashlib.sha256(
                "|".join(str(value) for value in selected).encode()
            ).hexdigest(),
            "request_started_at": self._clock().isoformat(),
            "request_completed_at": None,
            "elapsed_seconds": None,
            "outcome": "started",
            "exception_class": None,
            "result_count": None,
        }
        started = self._timer()
        self._append(record)
        return record, started

    def observe_child(
        self,
        notebook: UUID,
        stage: str,
        outcome: str,
        count: int | None,
        error: str | None,
        input_count: int | None = None,
    ) -> None:
        context = self._context.get()
        if context is None:
            raise RuntimeError("child timing requires an active evaluation request")
        case_id, mode = context
        key = (case_id, mode, notebook, stage)
        if outcome == "started":
            if key in self._stages:
                raise RuntimeError("duplicate child stage start")
            record: dict[str, object] = {
                "schema": "mnemo.phase86-evaluation-child-timing/1",
                "run_id": self.run_id,
                "case_id": case_id,
                "retrieval_mode": mode,
                "notebook_id": str(notebook),
                "stage": stage,
                "started_at": self._clock().isoformat(),
                "completed_at": None,
                "elapsed_seconds": None,
                "outcome": "started",
                "exception_class": None,
                "result_count": None,
                "input_count": input_count,
            }
            self._stages[key] = (record, self._timer())
            self._append(record)
            return
        record, started = self._stages.pop(key)
        self._append(
            {
                **record,
                "completed_at": self._clock().isoformat(),
                "elapsed_seconds": self._timer() - started,
                "outcome": outcome,
                "exception_class": error,
                "result_count": count,
            }
        )

    async def measure_internal(
        self,
        notebook: UUID | None,
        stage: str,
        operation: Awaitable[T],
        *,
        input_count: int | None = None,
    ) -> T:
        if notebook is None:
            return await operation
        self.observe_child(notebook, stage, "started", None, None, input_count)
        try:
            result = await operation
        except BaseException as error:
            self.observe_child(
                notebook,
                stage,
                "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                None,
                type(error).__name__,
            )
            raise
        self.observe_child(
            notebook, stage, "completed", len(result) if isinstance(result, tuple) else None, None
        )
        return result

    async def execute(
        self,
        service: ScopedSearchApplicationService,
        request: ScopeRequestReview,
        principal: PrincipalContextV1,
        *,
        case_id: str,
        mode: str,
        selected: tuple[UUID, ...],
    ) -> ScopedRankedResult:
        start_record, started = self.start(case_id=case_id, mode=mode, selected=selected)
        context_token = self._context.set((case_id, mode))
        try:
            result = await service.execute_ranked(request, principal)
        except BaseException as error:
            self._append(
                {
                    **start_record,
                    "request_completed_at": self._clock().isoformat(),
                    "elapsed_seconds": self._timer() - started,
                    "outcome": (
                        "timed_out"
                        if isinstance(error, (OperationTimeoutError, TimeoutError))
                        else "failed"
                    ),
                    "exception_class": type(error).__name__,
                }
            )
            raise
        else:
            self._append(
                {
                    **start_record,
                    "request_completed_at": self._clock().isoformat(),
                    "elapsed_seconds": self._timer() - started,
                    "outcome": "completed",
                    "result_count": len(result.items),
                }
            )
            return result
        finally:
            self._context.reset(context_token)


class TimedAdvancedSource:
    """Evaluation-only source wrapper; delegates identity and ordering unchanged."""

    def __init__(
        self, source: AdvancedRetrievalSourceV1, progress: EvaluationProgress, stage: str
    ) -> None:
        self._source = source
        self._progress = progress
        self._stage = stage

    @property
    def representation(self) -> EvidenceRepresentation:
        return self._source.representation

    async def retrieve(
        self, plan: RetrievalPlanV2, *, offset: int, limit: int
    ) -> AdvancedSourcePage:
        notebook = plan.scope.notebook_id
        self._progress.observe_child(notebook, self._stage, "started", None, None)
        try:
            page = await self._source.retrieve(plan, offset=offset, limit=limit)
        except BaseException as error:
            self._progress.observe_child(
                notebook,
                self._stage,
                "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                None,
                type(error).__name__,
            )
            raise
        self._progress.observe_child(notebook, self._stage, "completed", len(page.candidates), None)
        return page

    async def expand(
        self, plan: RetrievalPlanV2, seeds: tuple[AdvancedRetrievalCandidate, ...], *, limit: int
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        return await self._source.expand(plan, seeds, limit=limit)


class TimedAuthorizedAdvancedSource(TimedAdvancedSource):
    """Retain principal-aware dispatch for Full V2; never fall back to unscoped retrieval."""

    def __init__(
        self,
        source: PrincipalAwareAdvancedRetrievalSourceV2,
        progress: EvaluationProgress,
        stage: str,
    ) -> None:
        super().__init__(cast(AdvancedRetrievalSourceV1, source), progress, stage)
        self._authorized_source = source

    async def retrieve_authorized(
        self, *, principal: PrincipalContextV1, plan: RetrievalPlanV2, offset: int, limit: int
    ) -> AdvancedSourcePage:
        notebook = plan.scope.notebook_id
        self._progress.observe_child(notebook, self._stage, "started", None, None)
        notebook_token = self._progress._notebook.set(notebook)
        try:
            page = await self._authorized_source.retrieve_authorized(
                principal=principal, plan=plan, offset=offset, limit=limit
            )
        except BaseException as error:
            self._progress.observe_child(
                notebook,
                self._stage,
                "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                None,
                type(error).__name__,
            )
            raise
        finally:
            self._progress._notebook.reset(notebook_token)
        self._progress.observe_child(notebook, self._stage, "completed", len(page.candidates), None)
        return page


class NotebookReadPartitionSource:
    """Evaluation-only dispatch to four separately pinned, query-only read stores."""

    def __init__(self, sources: dict[UUID, PrincipalAwareAdvancedRetrievalSourceV2]) -> None:
        if len(sources) != 4 or any(
            source.representation is not EvidenceRepresentation.MULTILINGUAL_TEXT
            for source in sources.values()
        ):
            raise ValueError("four compatible notebook read partitions are required")
        self._sources = sources

    @property
    def representation(self) -> EvidenceRepresentation:
        return EvidenceRepresentation.MULTILINGUAL_TEXT

    def _source(self, plan: RetrievalPlanV2) -> PrincipalAwareAdvancedRetrievalSourceV2:
        try:
            return self._sources[plan.scope.notebook_id]
        except KeyError as error:
            raise PermissionError("notebook has no authorized read partition") from error

    async def retrieve_authorized(
        self, *, principal: PrincipalContextV1, plan: RetrievalPlanV2, offset: int, limit: int
    ) -> AdvancedSourcePage:
        return await self._source(plan).retrieve_authorized(
            principal=principal, plan=plan, offset=offset, limit=limit
        )

    async def retrieve(
        self, plan: RetrievalPlanV2, *, offset: int, limit: int
    ) -> AdvancedSourcePage:
        source = self._source(plan)
        return await cast(AdvancedRetrievalSourceV1, source).retrieve(
            plan, offset=offset, limit=limit
        )

    async def expand(
        self, plan: RetrievalPlanV2, seeds: tuple[AdvancedRetrievalCandidate, ...], *, limit: int
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        source = self._source(plan)
        return await cast(AdvancedRetrievalSourceV1, source).expand(plan, seeds, limit=limit)


class ReadOnlyEvaluationStore(SQLiteV2ReadOnlyRuntimeStore):
    """Use query-only V2 reads while observing committed disposable WAL state."""

    async def open(self) -> None:
        if self._db is not None:
            return
        self._db = await aiosqlite.connect(
            f"file:{self._db_path.resolve().as_posix()}?mode=ro", uri=True
        )
        try:
            await self._db.execute("PRAGMA query_only=ON")
            await self._db.execute("BEGIN")
            await self._db.execute("SELECT 1 FROM sqlite_master LIMIT 1")
            await self._inspect_chunk_read_model_if_present()
        except BaseException:
            await self.close()
            raise


class ProfiledReadOnlyEvaluationStore(ReadOnlyEvaluationStore):
    """Diagnostic-only, query-only store that times real Full V2 read boundaries."""

    def __init__(self, database: Path, progress: EvaluationProgress) -> None:
        super().__init__(database)
        self._progress = progress
        self._v2_stage_observer = progress.observe_storage_stage

    async def resolve_active_multilingual_v2_generation_set(self) -> tuple[UUID, ...] | None:
        return await self._progress.measure_internal(
            self._progress._notebook.get(),
            "active_generation_resolution",
            super().resolve_active_multilingual_v2_generation_set(),
        )

    async def inspect_active_v2_generations(
        self, generation_ids: tuple[UUID, ...]
    ) -> tuple[V2GenerationEvidence, ...]:
        return await self._progress.measure_internal(
            self._progress._notebook.get(),
            "generation_record_loading",
            super().inspect_active_v2_generations(generation_ids),
            input_count=len(generation_ids),
        )

    async def list_authorized_v2_semantic_rows(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        generation_id: UUID,
        limit: int,
        offset: int = 0,
    ) -> tuple[MultilingualTextProjectionRowV2, ...]:
        return await self._progress.measure_internal(
            decision.retrieval_scope.notebook_id,
            "authorized_semantic_page",
            super().list_authorized_v2_semantic_rows(
                decision=decision, generation_id=generation_id, limit=limit, offset=offset
            ),
            input_count=limit,
        )

    async def list_authorized_multilingual_embeddings_v3(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        vector_space: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV3, ...],
    ) -> tuple[MultilingualEmbeddingV3, ...]:
        return await self._progress.measure_internal(
            notebook_id,
            "vector_row_loading",
            super().list_authorized_multilingual_embeddings_v3(
                notebook_id=notebook_id,
                generation_id=generation_id,
                vector_space=vector_space,
                authorized_sources=authorized_sources,
            ),
            input_count=len(authorized_sources),
        )

    async def search_authorized_multilingual_text_v2(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        query: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV3, ...],
        page_start: int | None,
        page_end: int | None,
        section_indexes: tuple[int, ...],
        heading_prefix: tuple[str, ...],
        limit: int,
    ) -> tuple[tuple[MultilingualTextProjectionRowV2, float], ...]:
        return await self._progress.measure_internal(
            notebook_id,
            "full_v2_sparse_sql",
            super().search_authorized_multilingual_text_v2(
                notebook_id=notebook_id,
                generation_id=generation_id,
                query=query,
                authorized_sources=authorized_sources,
                page_start=page_start,
                page_end=page_end,
                section_indexes=section_indexes,
                heading_prefix=heading_prefix,
                limit=limit,
            ),
            input_count=len(authorized_sources),
        )


@dataclass(frozen=True, slots=True)
class CompactVectorSidecarAttestation:
    """Invocation-local proof binding the exact source snapshot to its sidecar."""

    source_database: str
    source_signature: tuple[int, int, int, int]
    source_wal_signature: tuple[int, int, int, int] | None
    compact_database: str
    compact_signature: tuple[int, int, int, int]
    source_rows_digest: str
    alias_digest: str
    vector_count: int
    model_revision: str
    dimension: int
    vector_encoding: str


def _readonly_file_signature(path: Path) -> tuple[int, int, int, int] | None:
    try:
        value = path.stat()
    except FileNotFoundError:
        return None
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


class CompactVectorReadOnlyEvaluationStore(ProfiledReadOnlyEvaluationStore):
    """Read the exact verified float64 sidecar only for disposable evaluation.

    Semantic rows, authorization decisions, generation admission and sparse
    retrieval remain bound to the four-notebook runtime database. This adapter
    substitutes only the losslessly encoded vector payload and fails closed
    unless both databases match frozen identities established by an exhaustive
    exact comparison.
    """

    def __init__(
        self,
        database: Path,
        progress: EvaluationProgress,
        *,
        attestation: CompactVectorSidecarAttestation | None = None,
    ) -> None:
        super().__init__(database, progress)
        self._compact_db: aiosqlite.Connection | None = None
        self._attestation = attestation

    @property
    def attestation(self) -> CompactVectorSidecarAttestation | None:
        return self._attestation

    async def open(self) -> None:
        from scripts.benchmark_module_894_compact_vectors import sha256 as file_sha256

        await super().open()
        try:
            if not COMPACT_VECTOR_DB.is_file():
                raise FileNotFoundError("verified disposable compact vector sidecar is missing")
            source_path = self._db_path.resolve()
            compact_path = COMPACT_VECTOR_DB.resolve()
            wal_path = Path(f"{source_path}-wal")
            compact_wal_path = Path(f"{compact_path}-wal")
            source_signature = _readonly_file_signature(source_path)
            source_wal_signature = _readonly_file_signature(wal_path)
            compact_signature = _readonly_file_signature(compact_path)
            compact_wal_signature = _readonly_file_signature(compact_wal_path)
            if source_signature is None or compact_signature is None:
                raise FileNotFoundError("evaluation database identity is incomplete")
            if compact_wal_signature is not None and compact_wal_signature[2] > 0:
                raise ValueError("compact vector sidecar has an uncheckpointed WAL")

            if self._attestation is None:
                if await asyncio.to_thread(file_sha256, compact_path) != COMPACT_VECTOR_DB_SHA256:
                    raise ValueError("compact vector sidecar digest differs from its verified copy")
                digest = hashlib.sha256()
                source_count = 0
                async with self._require_open().execute(
                    "SELECT embedding_id,notebook_id,generation_id,vector_space,"
                    "evidence_reference_digest,payload_hash "
                    "FROM multilingual_embeddings_v2 ORDER BY embedding_id"
                ) as cursor:
                    async for row in cursor:
                        digest.update(("|".join(str(value) for value in row) + "\n").encode())
                        source_count += 1
                alias = await self.resolve_active_multilingual_v2_alias_digest()
                if source_count != COMPACT_VECTOR_COUNT or digest.hexdigest() != (
                    COMPACT_SOURCE_ROWS_SHA256
                ):
                    raise ValueError(
                        "authoritative vector identities changed since sidecar validation"
                    )
                if alias != COMPACT_ALIAS_DIGEST:
                    raise ValueError(
                        "authoritative disposable alias differs from compact vector sidecar"
                    )
                if (
                    _readonly_file_signature(source_path) != source_signature
                    or _readonly_file_signature(wal_path) != source_wal_signature
                    or _readonly_file_signature(compact_path) != compact_signature
                ):
                    raise ValueError("evaluation snapshot changed while sidecar was attested")
                self._attestation = CompactVectorSidecarAttestation(
                    source_database=source_path.as_posix(),
                    source_signature=source_signature,
                    source_wal_signature=source_wal_signature,
                    compact_database=compact_path.as_posix(),
                    compact_signature=compact_signature,
                    source_rows_digest=digest.hexdigest(),
                    alias_digest=alias,
                    vector_count=source_count,
                    model_revision=COMPACT_MODEL_REVISION,
                    dimension=1024,
                    vector_encoding=COMPACT_VECTOR_ENCODING,
                )
            else:
                attestation = self._attestation
                if (
                    source_path.as_posix() != attestation.source_database
                    or compact_path.as_posix() != attestation.compact_database
                    or source_signature != attestation.source_signature
                    or source_wal_signature != attestation.source_wal_signature
                    or compact_signature != attestation.compact_signature
                    or attestation.source_rows_digest != COMPACT_SOURCE_ROWS_SHA256
                    or attestation.alias_digest != COMPACT_ALIAS_DIGEST
                    or attestation.vector_count != COMPACT_VECTOR_COUNT
                    or attestation.model_revision != COMPACT_MODEL_REVISION
                    or attestation.dimension != 1024
                    or attestation.vector_encoding != COMPACT_VECTOR_ENCODING
                ):
                    raise ValueError("invocation-local compact sidecar attestation mismatch")
                if await self.resolve_active_multilingual_v2_alias_digest() != (
                    attestation.alias_digest
                ):
                    raise ValueError("authoritative disposable alias changed during evaluation")

            self._compact_db = await aiosqlite.connect(
                f"file:{compact_path.as_posix()}?mode=ro&immutable=1", uri=True
            )
            await self._compact_db.execute("PRAGMA query_only=ON")
            await self._compact_db.execute("BEGIN")
            alias_row = await (
                await self._compact_db.execute(
                    "SELECT alias_set_digest FROM active_multilingual_v2_alias_set "
                    "WHERE singleton=1"
                )
            ).fetchone()
            count_row = await (
                await self._compact_db.execute(
                    "SELECT count(*) FROM compact_multilingual_embeddings_v1"
                )
            ).fetchone()
            if alias_row != (COMPACT_ALIAS_DIGEST,) or count_row != (COMPACT_VECTOR_COUNT,):
                raise ValueError("compact vector sidecar alias or coverage is incomplete")
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self._compact_db is not None:
            await self._compact_db.close()
            self._compact_db = None
        await super().close()

    async def list_authorized_multilingual_embeddings_v3(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        vector_space: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV3, ...],
    ) -> tuple[MultilingualEmbeddingV3, ...]:
        from scripts.benchmark_module_894_compact_vectors import restore

        if self._compact_db is None:
            raise RuntimeError("compact vector sidecar is not open")
        if len(authorized_sources) > 10_000:
            raise ValueError("authorized multilingual vector set exceeds 10000")
        if any(source.notebook_id != notebook_id for source in authorized_sources):
            raise PermissionError("authorized multilingual sources cross notebook scope")
        by_digest = {source.identity_digest: source for source in authorized_sources}
        if len(by_digest) != len(authorized_sources):
            raise ValueError("authorized multilingual source identities must be unique")
        if not by_digest:
            return ()

        encoded = json.dumps(sorted(by_digest), separators=(",", ":"))
        fetch_started = time.perf_counter()
        async with self._compact_db.execute(
            """SELECT embedding_id,notebook_id,generation_id,vector_space,
                      evidence_reference_digest,metadata_payload,vector_blob,record_hash
               FROM compact_multilingual_embeddings_v1
               WHERE notebook_id=? AND generation_id=? AND vector_space=?
                 AND evidence_reference_digest IN (SELECT value FROM json_each(?))
               ORDER BY evidence_reference_digest,embedding_id LIMIT 10001""",
            (str(notebook_id), str(generation_id), vector_space, encoded),
        ) as cursor:
            rows = tuple(await cursor.fetchall())
        observer = self._v2_stage_observer
        observer(
            "vector_sql_fetch",
            time.perf_counter() - fetch_started,
            len(rows),
            sum(len(row[5]) + len(row[6]) for row in rows),
        )
        if len(rows) > 10_000:
            raise ValueError("authorized multilingual vector enumeration exceeds bound")

        decode_started = time.perf_counter()
        values: list[MultilingualEmbeddingV3] = []
        for row in rows:
            value = restore(row[5], row[6], row[7], encoding=COMPACT_VECTOR_ENCODING)
            if not isinstance(value, MultilingualEmbeddingV3):
                raise ValueError("compact vector record has an invalid type")
            stored_identity = (
                str(value.embedding_id),
                str(value.source.notebook_id),
                str(value.profile.generation_id),
                value.profile.vector_space,
                value.source.identity_digest,
            )
            if stored_identity != tuple(str(item) for item in row[:5]):
                raise ValueError("compact vector metadata identity mismatch")
            if by_digest.get(value.source.identity_digest) != value.source:
                raise PermissionError("compact vector source authorization mismatch")
            if (
                value.profile.generation_id != generation_id
                or value.profile.vector_space != vector_space
                or value.profile.revision != COMPACT_MODEL_REVISION
                or value.profile.dimension != 1024
            ):
                raise ValueError("compact vector generation profile mismatch")
            values.append(value)
        observer("vector_decode_validate", time.perf_counter() - decode_started, len(values), 0)
        return tuple(values)


class ProfiledQueryEmbedder:
    """Time query inference without changing the provider call or its result."""

    def __init__(self, provider: BGEM3EmbeddingProvider, progress: EvaluationProgress) -> None:
        self._provider = provider
        self._progress = progress

    async def embed_query(self, *, query: str, language: str) -> MultilingualQueryEmbeddingV2:
        return await self._progress.measure_internal(
            self._progress._notebook.get(),
            "bge_query_embedding",
            self._provider.embed_query(query=query, language=language),
        )


def _target_key(value: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(value[field]) for field in IDENTITY)


def _ranked_identity(value: dict[str, Any]) -> dict[str, Any]:
    """Resolve the public retrieval item's typed chunk or derived evidence ID."""
    chunk = value.get("chunk_id")
    locator = value.get("locator")
    derived = locator.get("evidence_id") if isinstance(locator, dict) else None
    if chunk is not None and derived is not None and str(chunk) != str(derived):
        raise ValueError("ranked chunk and locator evidence identities disagree")
    evidence = chunk if chunk is not None else derived
    if not isinstance(evidence, str) or not evidence:
        raise ValueError("ranked evidence identity is missing")
    return {**value, "evidence_id": evidence}


def _timed_out_case_result(case: dict[str, Any], selected: tuple[UUID, ...]) -> dict[str, Any]:
    """Keep a bounded request failure visible without inventing ranking metrics."""
    return {
        "case_id": case["case_id"],
        "selected_notebooks": [str(value) for value in selected],
        "ranked": [],
        "metrics": None,
        "completeness": "failed",
        "omissions": ["scoped_search_deadline_expired"],
        "status": "TIMED_OUT",
        "exception_class": "OperationTimeoutError",
    }


def _failed_case_result(
    case: dict[str, Any], selected: tuple[UUID, ...], error: Exception
) -> dict[str, Any]:
    """Keep non-timeout request failures visible without persisting sensitive error text."""
    return {
        "case_id": case["case_id"],
        "selected_notebooks": [str(value) for value in selected],
        "ranked": [],
        "metrics": None,
        "completeness": "failed",
        "omissions": ["scoped_search_request_failed"],
        "status": "FAILED",
        "exception_class": type(error).__name__,
    }


def _select_evaluation_cases(
    cases: list[dict[str, Any]], case_ids: tuple[str, ...] | None
) -> list[dict[str, Any]]:
    """Select an ordered subset without changing or rebinding the frozen QRELs."""
    if case_ids is None:
        return list(cases)
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise ValueError("case selection must be non-empty and unique")
    by_id = {str(case["case_id"]): case for case in cases}
    unknown = set(case_ids) - by_id.keys()
    if unknown:
        raise ValueError(f"case selection contains unknown IDs: {', '.join(sorted(unknown))}")
    selected = set(case_ids)
    return [case for case in cases if str(case["case_id"]) in selected]


def metrics(
    observed: list[dict[str, Any]], targets: set[tuple[str, ...]], k: int
) -> dict[str, float]:
    found: set[tuple[str, ...]] = set()
    ranks: list[int] = []
    for rank, item in enumerate(observed[:k], 1):
        identity = _target_key(item)
        if identity in targets and identity not in found:
            found.add(identity)
            ranks.append(rank)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(targets)) + 1))
    return {
        "recall_at_1": float(any(rank <= 1 for rank in ranks)) / len(targets),
        "recall_at_5": sum(rank <= 5 for rank in ranks) / len(targets),
        "recall_at_10": len(found) / len(targets),
        "precision_at_5": sum(rank <= 5 for rank in ranks) / min(k, 5),
        "precision_at_10": len(found) / k,
        "mrr": 1 / min(ranks) if ranks else 0.0,
        "ndcg_at_10": sum(1 / math.log2(rank + 1) for rank in ranks) / ideal,
    }


def _verify_chunk(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    row = db.execute(
        "SELECT d.current_hash,c.text FROM sources s "
        "JOIN documents d ON d.document_id=s.document_id "
        "JOIN document_versions v ON v.document_id=d.document_id "
        "JOIN chunks c ON c.document_id=d.document_id AND c.version_id=v.version_id "
        "WHERE s.notebook_id=? AND s.source_id=? AND d.document_id=? "
        "AND v.version_id=? AND c.id=?",
        _target_key(value),
    ).fetchone()
    if row is None:
        raise ValueError("unbound notebook/source/document/version/chunk identity")
    if "source_file_sha256" in value and row[0] != value["source_file_sha256"]:
        raise ValueError("target source content hash differs")
    if "evidence_content_sha256" in value:
        actual = hashlib.sha256(str(row[1]).encode()).hexdigest()
        if actual != value["evidence_content_sha256"]:
            raise ValueError("target chunk text hash differs")


def _verify_result_identity(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    notebook, source, document, version, evidence = _target_key(value)
    parent = db.execute(
        "SELECT 1 FROM sources s JOIN document_versions v ON v.document_id=s.document_id "
        "WHERE s.notebook_id=? AND s.source_id=? AND s.document_id=? AND v.version_id=?",
        (notebook, source, document, version),
    ).fetchone()
    if parent is None:
        raise PermissionError("ranked evidence has no authorized source/version ancestry")
    exists = (
        db.execute(
            "SELECT 1 FROM chunks WHERE document_id=? AND version_id=? AND id=?",
            (document, version, evidence),
        ).fetchone()
        or db.execute(
            "SELECT 1 FROM ocr_regions r JOIN ocr_results o USING(derivation_id) "
            "WHERE o.document_id=? AND o.version_id=? AND r.region_id=?",
            (document, version, evidence),
        ).fetchone()
        or db.execute(
            "SELECT 1 FROM vision_results WHERE document_id=? AND version_id=? AND derivation_id=?",
            (document, version, evidence),
        ).fetchone()
    )
    if exists is None:
        raise PermissionError("ranked evidence identity has no persisted ancestry")


def load_qrels(
    path: Path,
    database: Path,
    allowed_notebooks: set[UUID],
    source_hashes: set[str],
) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        document.get("schema") != "mnemo.phase86-four-notebook-dere/1"
        or document.get("judgment_method") != "DETERMINISTIC_ENGINEERING"
        or document.get("human_adjudication_claimed") is not False
        or not document.get("cases")
    ):
        raise ValueError("independently declared engineering QREL cases are required")
    seen: set[str] = set()
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as db:
        for case in document["cases"]:
            if not isinstance(case.get("query"), str) or not case["query"].strip():
                raise ValueError("empty evaluation query")
            if case["case_id"] in seen:
                raise ValueError("duplicate evaluation case ID")
            seen.add(case["case_id"])
            scope = {UUID(value) for value in case["selected_notebooks"]}
            if not scope or not scope.issubset(allowed_notebooks):
                raise ValueError("case requests an unapproved notebook scope")
            if not case.get("targets"):
                raise ValueError("case has no independently declared targets")
            for target in case["targets"]:
                if UUID(target["notebook_id"]) not in scope:
                    raise ValueError("target lies outside selected notebook scope")
                if not {"source_file_sha256", "evidence_content_sha256"}.issubset(target):
                    raise ValueError("target source/chunk hashes are missing")
                if target["source_file_sha256"] not in source_hashes:
                    raise ValueError("target source hash is not in the verified dataset manifest")
                _verify_chunk(db, target)
    return cast(dict[str, Any], document)


def preflight_evaluation(qrels: Path | None = None) -> tuple[dict[str, Any], Path, Path]:
    plan, records = preflight()
    _, runtime, logs = run_paths(plan)
    if not (logs / "ingestion_summary.json").is_file():
        raise RuntimeError("ingestion and independent post-ingestion audit have not completed")
    summary = json.loads((logs / "ingestion_summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != "PASS":
        raise RuntimeError("post-ingestion audit did not pass")
    state_file = logs / "run_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
    if (
        state.get("status") != "SUCCEEDED"
        or state.get("pre_activation_audit_sha256") != summary.get("pre_activation_audit_sha256")
        or state.get("bound_qrels_sha256") != summary.get("bound_qrels_sha256")
    ):
        raise RuntimeError("disposable run was not fully verified after alias promotion")
    bound = logs / BOUND_NAME
    if not bound.is_file() or digest(bound) != state["bound_qrels_sha256"]:
        raise RuntimeError("bound identity QRELs are missing or changed")
    if not (runtime / "mnemo.db").is_file() or not (runtime / "acl.db").is_file():
        raise RuntimeError("four-notebook disposable stores are unavailable")
    from scripts.audit_phase86_four_notebooks import audit

    if audit(plan, records, runtime, logs, write_artifacts=False)["status"] != "PASS":
        raise RuntimeError("current persisted-data audit did not pass")
    allowed = {UUID(str(plan["existing_notebook"]["id"])), *notebook_ids(plan).values()}
    load_qrels(
        qrels or bound,
        runtime / "mnemo.db",
        allowed,
        {row["sha256"] for row in records.values()},
    )
    return plan, runtime, logs


class FourNotebookIdentityVerifier(IsolatedV2DatabaseIdentityVerifier):
    """Bind the retained Full V2 verifier to the exact disposable four-scope census."""

    def __init__(self, runtime: Path, notebook_ids: tuple[UUID, ...]) -> None:
        self._database = runtime / "mnemo.db"
        self._notebook_id = notebook_ids[0]
        self._allowed_notebook_ids = notebook_ids
        self._run_id = uuid5(NAMESPACE_URL, f"mnemo:phase86-four-notebooks:{runtime.name}")
        self._expected = self._read_identity()
        canonical = json.dumps(self._expected, sort_keys=True, separators=(",", ":")).encode()
        self.artifact = IsolatedV2ArtifactIdentity(
            target_path=self._database.relative_to(ROOT).as_posix(),
            notebook_id=self._notebook_id,
            build_run_id=self._run_id,
            profile_fingerprint=str(self._expected["profile_fingerprint"]),
            vector_space_identity=str(self._expected["vector_space"]),
            database_identity=hashlib.sha256(canonical).hexdigest(),
            generation_ids=tuple(
                UUID(item["id"])
                for item in cast(list[dict[str, Any]], self._expected["generations"])
            ),
        )

    def _read_identity(self) -> dict[str, object]:
        with closing(sqlite3.connect(f"file:{self._database.as_posix()}?mode=ro", uri=True)) as db:
            memberships = tuple(
                (str(row[0]), str(row[1]), str(row[2]))
                for row in db.execute(
                    "SELECT s.notebook_id,s.source_id,d.current_hash FROM sources s "
                    "JOIN documents d ON d.document_id=s.document_id "
                    "ORDER BY s.notebook_id,s.source_id"
                )
            )
            self._source_hashes = tuple(
                (source, content_hash) for _notebook, source, content_hash in memberships
            )
        return {**super()._read_identity(), "source_memberships": memberships}


async def attach_full_v2(
    runtime: Path,
    logs: Path,
    plan: dict[str, Any],
    store: SQLiteStore,
    harness: SimpleNamespace,
    canonical: CanonicalTextAdvancedSource,
    stack: AsyncExitStack,
    progress: EvaluationProgress | None = None,
    per_notebook_readers: bool = False,
    compact_vector_sidecar: bool = False,
) -> str:
    if compact_vector_sidecar and progress is None:
        raise ValueError("compact vector evaluation requires append-only timing receipts")
    compact_attestation: CompactVectorSidecarAttestation | None = None
    if compact_vector_sidecar:
        if not isinstance(store, CompactVectorReadOnlyEvaluationStore):
            raise TypeError("compact evaluation must use its attested top-level reader")
        compact_attestation = store.attestation
        if compact_attestation is None:
            raise ValueError("compact sidecar must be attested before child readers are created")
    selected = (UUID(str(plan["existing_notebook"]["id"])), *notebook_ids(plan).values())
    verifier = FourNotebookIdentityVerifier(runtime, selected)
    artifact = verifier.artifact
    activation = json.loads((logs / "provider_activation.json").read_text(encoding="utf-8"))
    if activation["generation_ids"] != [str(value) for value in artifact.generation_ids]:
        raise ValueError("disposable active generation set differs from verified identity")
    read_store = ReadOnlyEvaluationStore(runtime / "mnemo.db")
    await read_store.open()
    try:
        active = await read_store.resolve_active_multilingual_v2_generation_set()
        alias = await read_store.resolve_active_multilingual_v2_alias_digest()
        if active != artifact.generation_ids or alias != activation["alias_set_digest"]:
            raise ValueError("disposable alias changed")
        evidence = await read_store.inspect_active_v2_generations(active)
        profile_id = evidence[0].profile_id
    finally:
        await read_store.close()
    component = (
        ModelProfileDocument.from_file(
            ROOT / "config/model_profiles/full_multilingual_v2_profiles.toml"
        )
        .select("full_multilingual_v2_local_prebuild")
        .models["multilingual_embedding"]
    )
    capability = load_rebuild_language_capability(
        path=ROOT / "config/rebuild/multilingual_embedding_capability.json",
        component=component,
    )
    provider = BGEM3EmbeddingProvider(
        component,
        generation_id=artifact.generation_ids[2],
        cache_folder=CACHE,
        device="cuda",
    )
    stack.push_async_callback(provider.close)
    await provider.initialize()
    profile = await provider.profile()
    if (
        profile.vector_space != artifact.vector_space_identity
        or profile.dimension != 1024
        or profile.revision != activation["model_revision"]
    ):
        raise ValueError("query BGE-M3 provider differs from indexed document space")
    identity = V2RuntimeIdentityV1(
        profile_id=profile_id,
        profile_fingerprint=artifact.profile_fingerprint,
        vector_space_identity=artifact.vector_space_identity,
        build_run_id=artifact.build_run_id,
        database_identity=artifact.database_identity,
        alias_set_digest=activation["alias_set_digest"],
        query_preprocessing_identity=BGE_M3_QUERY_PREPROCESSING,
        document_preprocessing_identity=BGE_M3_DOCUMENT_PREPROCESSING,
        authorization_service_id="mnemo.server.v2-retrieval-authorization-policy/1",
        provenance_validator_id="mnemo.v2-provenance-validator/1",
        reranker_public_protocol_id="multilingual-reranker/3",
        provider_identity=component.provider,
    )
    if not isinstance(store, MultilingualAdvancedStoreV1):
        raise ValueError("disposable storage lacks Full V2 retrieval")
    support = V2ProductionRuntimeSupportV1(
        query_embedder=ProfiledQueryEmbedder(provider, progress) if progress else provider,
        candidate_builder_factory=lambda resolver: V2TypedCandidateBuilderV1(resolver=resolver),
        reranker=PassThroughV2RerankerV1(),
        admission=_CommonSpaceAdmission(capability),
        query_language_resolver=_CommonSpaceQueryLanguageResolver(),
        exhaustive_fallback=ProjectedMultilingualAdvancedSource(store),
        dense_stage_observer=progress.observe_dense_stage if progress is not None else None,
    )
    sources: dict[UUID, PrincipalAwareAdvancedRetrievalSourceV2] = {}
    first_source: PrincipalAwareAdvancedRetrievalSourceV2 | None = None
    for notebook in selected if per_notebook_readers else selected[:1]:
        assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
            workspace_root=ROOT,
            identity_manifest=logs / "provider_activation.json",
            identity=identity,
            support=support,
            isolated_verifier=verifier,
            isolated_database=runtime / "mnemo.db",
            read_store_factory=(
                (
                    lambda database: CompactVectorReadOnlyEvaluationStore(
                        database, progress, attestation=compact_attestation
                    )
                )
                if compact_vector_sidecar and progress is not None
                else (
                    (lambda database: ProfiledReadOnlyEvaluationStore(database, progress))
                    if progress is not None
                    else ReadOnlyEvaluationStore
                )
            ),
        )
        stack.push_async_callback(assembler.close)
        composed = await ServerOwnedFullMultilingualV2RegistrationV1(
            engine=cast(KnowledgeEngine, harness), identity=identity, assembler=assembler
        ).compose_internal_runtime()
        if first_source is None:
            first_source = composed.advanced_source
        sources[notebook] = composed.advanced_source
    assert first_source is not None
    advanced_source: PrincipalAwareAdvancedRetrievalSourceV2 = (
        NotebookReadPartitionSource(sources) if per_notebook_readers else first_source
    )
    harness.advanced_retrieval = AdvancedRetrievalService(
        sources=(
            TimedAdvancedSource(canonical, progress, "canonical_sparse_source")
            if progress is not None
            else canonical,
            TimedAuthorizedAdvancedSource(advanced_source, progress, "full_v2_source")
            if progress is not None
            else cast(AdvancedRetrievalSourceV1, advanced_source),
        ),
        cursor_codec=RetrievalCursorCodec(b"disposable-four-notebook-evaluation-only"),
    )
    harness.full_multilingual_v2_alias_digest = alias
    return component.revision


async def diagnose_case(
    qrels: Path,
    case_id: str,
    *,
    per_notebook_readers: bool = False,
    compact_vector_sidecar: bool = False,
) -> dict[str, object]:
    """Time exactly one bound four-notebook BGE request, never the full benchmark."""
    plan, runtime, logs = preflight_evaluation(qrels)
    allowed = {UUID(str(plan["existing_notebook"]["id"])), *notebook_ids(plan).values()}
    source_manifest = json.loads((ROOT / plan["source_manifest"]).read_text(encoding="utf-8"))
    manifest = load_qrels(
        qrels,
        runtime / "mnemo.db",
        allowed,
        {row["sha256"] for row in source_manifest["sources"]},
    )
    cases = [case for case in manifest["cases"] if case["case_id"] == case_id]
    if len(cases) != 1:
        raise ValueError("exactly one bound diagnostic case is required")
    case = cases[0]
    selected = tuple(UUID(value) for value in case["selected_notebooks"])
    if not selected or len(set(selected)) != len(selected) or not set(selected).issubset(allowed):
        raise ValueError("diagnostic case selects an unverified notebook scope")
    authority = SQLiteNotebookScopeAuthority(runtime / "acl.db")
    actor = UUID(str(plan["disposable_actor_id"]))
    if any(not authority.permits(actor, notebook) for notebook in selected):
        raise PermissionError("disposable owner lost a selected notebook grant")
    progress = EvaluationProgress(logs, run_paths(plan)[0])
    store: ReadOnlyEvaluationStore = (
        CompactVectorReadOnlyEvaluationStore(runtime / "mnemo.db", progress)
        if compact_vector_sidecar
        else ProfiledReadOnlyEvaluationStore(runtime / "mnemo.db", progress)
    )
    async with AsyncExitStack() as stack:
        stack.callback(progress.close)
        await store.open()
        stack.push_async_callback(store.close)
        canonical = CanonicalTextAdvancedSource(
            store=store, ranked_retriever=SparseRetriever(store)
        )
        harness = SimpleNamespace(
            storage=store,
            server_scope_authority=authority,
            advanced_retrieval=AdvancedRetrievalService(
                sources=(canonical,),
                cursor_codec=RetrievalCursorCodec(b"disposable-four-notebook-evaluation-only"),
            ),
            full_multilingual_v2_alias_digest=None,
            config=SimpleNamespace(
                storage=SimpleNamespace(sqlite=SimpleNamespace(path=runtime / "mnemo.db"))
            ),
        )
        revision = await attach_full_v2(
            runtime,
            logs,
            plan,
            store,
            harness,
            canonical,
            stack,
            progress,
            per_notebook_readers=per_notebook_readers,
            compact_vector_sidecar=compact_vector_sidecar,
        )
        service = ScopedSearchApplicationService(
            cast(KnowledgeEngine, harness), ServerConfig(), child_observer=progress.observe_child
        )
        request = ScopeRequestReview(
            query=case["query"],
            mode="ranked",
            limit=10,
            scope=SelectedNotebooks(kind="selected", notebook_ids=selected),
        )
        result = await progress.execute(
            service,
            request,
            PrincipalContextV1(actor, True),
            case_id=case_id,
            mode="canonical_sparse_plus_bge_m3_full_v2",
            selected=selected,
        )
        ranked = [
            {
                **{key: str(_ranked_identity(item)[key]) for key in IDENTITY},
                "representation": str(item["representation"]),
                "score": item.get("score"),
                "fused_score": item.get("fused_score"),
                "reranker_score": item.get("reranker_score"),
            }
            for item in result.items
        ]
        return {
            "status": "COMPLETED",
            "progress_receipt": str(progress.path),
            "result_count": len(result.items),
            "ranking_digest": hashlib.sha256(
                json.dumps(ranked, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
            "ranked": ranked,
            "per_notebook_readers": per_notebook_readers,
            "model_revision": revision,
        }


async def diagnose_q21(qrels: Path) -> dict[str, object]:
    """Preserve the original Q21 diagnostic entry point and its frozen identity."""
    return await diagnose_case(qrels, "PH86-DERE3-Q21-ALL4")


async def evaluate(
    qrels: Path,
    *,
    per_notebook_readers: bool = False,
    single_notebook_only: bool = False,
    compact_vector_sidecar: bool = False,
    case_ids: tuple[str, ...] | None = None,
    retrieval_modes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    plan, runtime, logs = preflight_evaluation(qrels)
    allowed = {UUID(str(plan["existing_notebook"]["id"])), *notebook_ids(plan).values()}
    source_manifest = json.loads((ROOT / plan["source_manifest"]).read_text(encoding="utf-8"))
    manifest = load_qrels(
        qrels,
        runtime / "mnemo.db",
        allowed,
        {row["sha256"] for row in source_manifest["sources"]},
    )
    selected_cases = _select_evaluation_cases(manifest["cases"], case_ids)
    execution_cases = [
        case
        for case in selected_cases
        if not single_notebook_only or len(case["selected_notebooks"]) == 1
    ]
    allowed_modes = ("canonical_sparse_only", "canonical_sparse_plus_bge_m3_full_v2")
    modes_to_run = allowed_modes if retrieval_modes is None else retrieval_modes
    if not modes_to_run or len(set(modes_to_run)) != len(modes_to_run):
        raise ValueError("retrieval mode selection must be non-empty and unique")
    if not set(modes_to_run).issubset(allowed_modes):
        raise ValueError("retrieval mode selection contains an unsupported mode")
    authority = SQLiteNotebookScopeAuthority(runtime / "acl.db")
    actor = UUID(str(plan["disposable_actor_id"]))
    if any(not authority.permits(actor, notebook) for notebook in allowed):
        raise PermissionError("disposable owner no longer has all four notebook grants")
    async with AsyncExitStack() as stack:
        progress = EvaluationProgress(logs, run_paths(plan)[0])
        stack.callback(progress.close)
        store: ReadOnlyEvaluationStore = (
            CompactVectorReadOnlyEvaluationStore(runtime / "mnemo.db", progress)
            if compact_vector_sidecar
            else ReadOnlyEvaluationStore(runtime / "mnemo.db")
        )
        await store.open()
        stack.push_async_callback(store.close)
        canonical = CanonicalTextAdvancedSource(
            store=store, ranked_retriever=SparseRetriever(store)
        )
        retrieval = AdvancedRetrievalService(
            sources=(canonical,),
            cursor_codec=RetrievalCursorCodec(b"disposable-four-notebook-evaluation-only"),
        )
        harness = SimpleNamespace(
            storage=store,
            server_scope_authority=authority,
            advanced_retrieval=retrieval,
            full_multilingual_v2_alias_digest=None,
            config=SimpleNamespace(
                storage=SimpleNamespace(sqlite=SimpleNamespace(path=runtime / "mnemo.db"))
            ),
        )
        principal = PrincipalContextV1(actor, True)
        modes: dict[str, list[dict[str, Any]]] = {}
        for mode in modes_to_run:
            if mode != "canonical_sparse_only":
                await attach_full_v2(
                    runtime,
                    logs,
                    plan,
                    store,
                    harness,
                    canonical,
                    stack,
                    progress=progress,
                    per_notebook_readers=per_notebook_readers,
                    compact_vector_sidecar=compact_vector_sidecar,
                )
            service = ScopedSearchApplicationService(
                cast(KnowledgeEngine, harness),
                ServerConfig(),
                child_observer=progress.observe_child,
            )
            results: list[dict[str, Any]] = []
            with closing(
                sqlite3.connect(f"file:{(runtime / 'mnemo.db').as_posix()}?mode=ro", uri=True)
            ) as db:
                for case in execution_cases:
                    selected = tuple(UUID(value) for value in case["selected_notebooks"])
                    request = ScopeRequestReview(
                        query=case["query"],
                        mode="ranked",
                        limit=10,
                        scope=SelectedNotebooks(kind="selected", notebook_ids=selected),
                    )
                    try:
                        result = await progress.execute(
                            service,
                            request,
                            principal,
                            case_id=str(case["case_id"]),
                            mode=mode,
                            selected=selected,
                        )
                    except OperationTimeoutError:
                        case_result = _timed_out_case_result(case, selected)
                        results.append(case_result)
                        progress._append(
                            {
                                "schema": "mnemo.phase86-evaluation-case-result/1",
                                "run_id": progress.run_id,
                                "retrieval_mode": mode,
                                **case_result,
                            }
                        )
                        continue
                    except Exception as exc:
                        case_result = _failed_case_result(case, selected, exc)
                        results.append(case_result)
                        progress._append(
                            {
                                "schema": "mnemo.phase86-evaluation-case-result/1",
                                "run_id": progress.run_id,
                                "retrieval_mode": mode,
                                **case_result,
                            }
                        )
                        continue
                    ranked: list[dict[str, Any]] = []
                    for rank, item in enumerate(result.items, 1):
                        if UUID(str(item["notebook_id"])) not in selected:
                            raise PermissionError("retrieval escaped selected notebook membership")
                        bound_item = _ranked_identity(item)
                        _verify_result_identity(db, bound_item)
                        ranked.append(
                            {
                                "rank": rank,
                                **{key: str(bound_item[key]) for key in IDENTITY},
                                "representation": str(item["representation"]),
                            }
                        )
                    target_set = {_target_key(value) for value in case["targets"]}
                    case_result = {
                        "case_id": case["case_id"],
                        "selected_notebooks": [str(value) for value in selected],
                        "ranked": ranked,
                        "metrics": metrics(ranked, target_set, 10),
                        "completeness": result.completeness,
                        "omissions": result.omissions,
                    }
                    results.append(case_result)
                    progress._append(
                        {
                            "schema": "mnemo.phase86-evaluation-case-result/1",
                            "run_id": progress.run_id,
                            "retrieval_mode": mode,
                            **case_result,
                        }
                    )
                try:
                    await progress.execute(
                        service,
                        request,
                        PrincipalContextV1(uuid5(actor, "ungranted-four-notebook-eval"), True),
                        case_id="UNGRANTED-PRINCIPAL-CONTROL",
                        mode=mode,
                        selected=selected,
                    )
                except NotFoundError:
                    negative = "PASS"
                else:
                    raise PermissionError("ungranted principal received scoped results")
            modes[mode] = results
        timed_out_cases = [
            (mode, case["case_id"])
            for mode, cases in modes.items()
            for case in cases
            if case.get("status") == "TIMED_OUT"
        ]
        failed_cases = [
            (mode, case["case_id"], case["exception_class"])
            for mode, cases in modes.items()
            for case in cases
            if case.get("status") == "FAILED"
        ]
        expected_cases = len(execution_cases)
        report = {
            "schema": "mnemo.phase86-four-notebook-dere-result/1",
            "status": "PARTIAL" if timed_out_cases or failed_cases else "PASS",
            "judgment_method": "DETERMINISTIC_ENGINEERING",
            "human_adjudication_claimed": False,
            "qrels_sha256": digest(qrels),
            "provider_profiles": modes,
            "ungranted_principal_denial": negative,
            "case_count": len(results),
            "expected_case_count_per_mode": expected_cases,
            "timed_out_case_count": len(timed_out_cases),
            "timed_out_cases": [
                {"retrieval_mode": mode, "case_id": case_id} for mode, case_id in timed_out_cases
            ],
            "failed_case_count": len(failed_cases),
            "failed_cases": [
                {
                    "retrieval_mode": mode,
                    "case_id": case_id,
                    "exception_class": exception_class,
                }
                for mode, case_id, exception_class in failed_cases
            ],
            "scope_filter": "single_notebook" if single_notebook_only else "all_declared_scopes",
            "evaluation_scope": {
                "case_ids": [str(case["case_id"]) for case in execution_cases],
                "retrieval_modes": list(modes_to_run),
                "full_cohort": len(execution_cases) == len(manifest["cases"])
                and modes_to_run == allowed_modes,
            },
            "evaluation_progress_receipt": progress.path.name,
        }
        suffix = "-single-notebook" if single_notebook_only else ""
        if len(selected_cases) != len(manifest["cases"]) or modes_to_run != allowed_modes:
            subset_digest = hashlib.sha256(
                json.dumps(
                    report["evaluation_scope"], sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()[:12]
            suffix += f"-subset-{subset_digest}-{progress.path.stem[-12:]}"
        partial_suffix = f"-partial-{progress.path.stem}" if timed_out_cases or failed_cases else ""
        out = logs / (
            f"evaluation-four-notebooks-{digest(qrels)[:16]}{suffix}{partial_suffix}.json"
        )
        if out.exists():
            raise FileExistsError("evaluation output already exists; preserve previous result")
        write_json(out, report)
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "run", "diagnose-q21", "diagnose-case"))
    parser.add_argument("--qrels", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument(
        "--compact-vector-sidecar",
        action="store_true",
        help="Opt into the exact hash-pinned disposable float64 sidecar; never changes production.",
    )
    parser.add_argument(
        "--per-notebook-readers",
        action="store_true",
        help="Use isolated query-only notebook readers (the full run always uses them).",
    )
    parser.add_argument("--single-notebook-only", action="store_true")
    parser.add_argument(
        "--case-ids",
        nargs="+",
        help="Evaluate only these already-bound QREL case IDs; does not alter the QREL artifact.",
    )
    parser.add_argument(
        "--retrieval-modes",
        nargs="+",
        choices=("canonical_sparse_only", "canonical_sparse_plus_bge_m3_full_v2"),
        help="Run only the listed existing retrieval modes.",
    )
    args = parser.parse_args()
    qrels = args.qrels
    if qrels is None:
        plan, _records = preflight()
        _, _, logs = run_paths(plan)
        qrels = logs / BOUND_NAME
    if args.mode == "preflight":
        _plan, runtime, logs = preflight_evaluation(qrels)
        print(json.dumps({"status": "PASS", "runtime": str(runtime), "logs": str(logs)}))
        return 0
    if args.mode == "diagnose-q21":
        print(json.dumps(asyncio.run(diagnose_q21(qrels)), sort_keys=True))
        return 0
    if args.mode == "diagnose-case":
        if not args.case_id:
            parser.error("diagnose-case requires --case-id")
        print(
            json.dumps(
                asyncio.run(
                    diagnose_case(
                        qrels,
                        args.case_id,
                        per_notebook_readers=args.per_notebook_readers,
                        compact_vector_sidecar=args.compact_vector_sidecar,
                    )
                ),
                sort_keys=True,
            )
        )
        return 0
    evaluate_options: _EvaluationOptions = {
        "per_notebook_readers": args.per_notebook_readers or args.mode == "run",
        "single_notebook_only": args.single_notebook_only,
        "compact_vector_sidecar": args.compact_vector_sidecar,
    }
    if args.case_ids is not None:
        evaluate_options["case_ids"] = tuple(args.case_ids)
    if args.retrieval_modes is not None:
        evaluate_options["retrieval_modes"] = tuple(args.retrieval_modes)
    result = asyncio.run(evaluate(qrels, **evaluate_options))
    status = str(result.get("status", "PASS"))
    print(json.dumps({"status": status, "cases": result["case_count"]}))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
