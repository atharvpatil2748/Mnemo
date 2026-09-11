"""SQLite Final-QA V2 immutable execution, snapshot, and citation storage."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import aiosqlite

from mnemo.interfaces.errors import ConflictError, StorageError
from mnemo.models.final_qa_execution import (
    FinalQAExecutionSnapshotPhase,
    FinalQAExecutionState,
)
from mnemo.models.multimodal import (
    EvidenceCitationV2,
    FinalQAExecutionSnapshotV2,
    FinalQAExecutionV2,
)
from mnemo.retrieval.final_qa_snapshot import _encode

MULTIMODAL_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS final_qa_v2_executions (
        execution_id TEXT PRIMARY KEY,
        assistant_turn_id TEXT NOT NULL UNIQUE,
        request_fingerprint TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        notebook_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        user_turn_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        provider_profile TEXT NOT NULL,
        state TEXT NOT NULL,
        retry_count INTEGER NOT NULL CHECK(retry_count BETWEEN 0 AND 1),
        failure_classification TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT
    )""",
    """CREATE INDEX IF NOT EXISTS idx_final_qa_v2_state_updated
       ON final_qa_v2_executions(state,updated_at)""",
    """CREATE INDEX IF NOT EXISTS idx_final_qa_v2_scope
       ON final_qa_v2_executions(actor_id,notebook_id,session_id)""",
    """CREATE TABLE IF NOT EXISTS final_qa_v2_snapshots (
        execution_id TEXT NOT NULL
            REFERENCES final_qa_v2_executions(execution_id) ON DELETE CASCADE,
        phase TEXT NOT NULL,
        payload_schema_version INTEGER NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(execution_id,phase)
    )""",
    """CREATE TABLE IF NOT EXISTS evidence_citations_v2 (
        citation_id TEXT PRIMARY KEY,
        execution_id TEXT NOT NULL
            REFERENCES final_qa_v2_executions(execution_id) ON DELETE RESTRICT,
        source_number INTEGER NOT NULL CHECK(source_number > 0),
        candidate_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(execution_id,source_number)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_evidence_citations_v2_candidate
       ON evidence_citations_v2(candidate_id)""",
)


@asynccontextmanager
async def _transaction(db: aiosqlite.Connection) -> AsyncIterator[None]:
    try:
        await db.execute("BEGIN IMMEDIATE")
        yield
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


class SQLiteMultimodalMixin:
    _multimodal_lock: asyncio.Lock

    def _require_open(self) -> aiosqlite.Connection:
        raise NotImplementedError

    async def create_final_qa_v2_execution(self, execution: FinalQAExecutionV2) -> bool:
        db = self._require_open()
        try:
            async with self._multimodal_lock, _transaction(db):
                cursor = await db.execute(
                    """INSERT INTO final_qa_v2_executions(
                        execution_id,assistant_turn_id,request_fingerprint,actor_id,notebook_id,
                        session_id,user_turn_id,provider,model,provider_profile,state,retry_count,
                        failure_classification,created_at,updated_at,completed_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(assistant_turn_id) DO NOTHING""",
                    (
                        str(execution.execution_id),
                        str(execution.assistant_turn_id),
                        execution.request_fingerprint,
                        str(execution.actor_id),
                        str(execution.notebook_id),
                        str(execution.session_id),
                        str(execution.user_turn_id),
                        execution.provider,
                        execution.model,
                        execution.provider_profile,
                        execution.state.value,
                        execution.retry_count,
                        execution.failure_classification,
                        execution.created_at.isoformat(),
                        execution.updated_at.isoformat(),
                        None
                        if execution.completed_at is None
                        else execution.completed_at.isoformat(),
                    ),
                )
                return cursor.rowcount == 1
        except aiosqlite.Error as error:
            raise StorageError("could not create Final-QA V2 execution") from error

    async def get_final_qa_v2_execution(self, assistant_turn_id: UUID) -> FinalQAExecutionV2 | None:
        db = self._require_open()
        async with db.execute(
            """SELECT execution_id,assistant_turn_id,request_fingerprint,actor_id,notebook_id,
                      session_id,user_turn_id,provider,model,provider_profile,state,retry_count,
                      failure_classification,created_at,updated_at,completed_at
               FROM final_qa_v2_executions WHERE assistant_turn_id=?""",
            (str(assistant_turn_id),),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return FinalQAExecutionV2(
            execution_id=UUID(row[0]),
            assistant_turn_id=UUID(row[1]),
            request_fingerprint=row[2],
            actor_id=UUID(row[3]),
            notebook_id=UUID(row[4]),
            session_id=UUID(row[5]),
            user_turn_id=UUID(row[6]),
            provider=row[7],
            model=row[8],
            provider_profile=row[9],
            state=FinalQAExecutionState(row[10]),
            retry_count=int(row[11]),
            failure_classification=row[12],
            created_at=datetime.fromisoformat(row[13]),
            updated_at=datetime.fromisoformat(row[14]),
            completed_at=None if row[15] is None else datetime.fromisoformat(row[15]),
        )

    async def put_final_qa_v2_snapshot(self, snapshot: FinalQAExecutionSnapshotV2) -> None:
        db = self._require_open()
        try:
            async with self._multimodal_lock, _transaction(db):
                await db.execute(
                    """INSERT INTO final_qa_v2_snapshots(
                        execution_id,phase,payload_schema_version,payload,payload_hash,created_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (
                        str(snapshot.execution_id),
                        snapshot.phase.value,
                        snapshot.payload_schema_version,
                        snapshot.payload,
                        snapshot.payload_hash,
                        snapshot.created_at.isoformat(),
                    ),
                )
        except aiosqlite.IntegrityError as error:
            raise ConflictError("Final-QA V2 snapshot is immutable") from error
        except aiosqlite.Error as error:
            raise StorageError("could not persist Final-QA V2 snapshot") from error

    async def get_final_qa_v2_snapshot(
        self, execution_id: UUID, phase: FinalQAExecutionSnapshotPhase
    ) -> FinalQAExecutionSnapshotV2 | None:
        db = self._require_open()
        async with db.execute(
            """SELECT execution_id,phase,payload_schema_version,payload,payload_hash,created_at
               FROM final_qa_v2_snapshots WHERE execution_id=? AND phase=?""",
            (str(execution_id), phase.value),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        try:
            return FinalQAExecutionSnapshotV2(
                execution_id=UUID(row[0]),
                phase=FinalQAExecutionSnapshotPhase(row[1]),
                payload_schema_version=int(row[2]),
                payload=row[3],
                payload_hash=row[4],
                created_at=datetime.fromisoformat(row[5]),
            )
        except ValueError as error:
            raise StorageError("Final-QA V2 snapshot integrity check failed") from error

    async def transition_final_qa_v2_execution(
        self,
        execution_id: UUID,
        expected: FinalQAExecutionState,
        target: FinalQAExecutionState,
        *,
        retry_count: int | None = None,
        failure_classification: str | None = None,
    ) -> bool:
        db = self._require_open()
        now = datetime.now(UTC)
        completed = (
            now.isoformat()
            if target
            in {
                FinalQAExecutionState.PUBLISHED,
                FinalQAExecutionState.REJECTED_CITATION_COMPLIANCE,
            }
            else None
        )
        try:
            async with self._multimodal_lock, _transaction(db):
                cursor = await db.execute(
                    """UPDATE final_qa_v2_executions
                       SET state=?,retry_count=COALESCE(?,retry_count),
                           failure_classification=COALESCE(?,failure_classification),
                           updated_at=?,completed_at=COALESCE(?,completed_at)
                       WHERE execution_id=? AND state=?""",
                    (
                        target.value,
                        retry_count,
                        failure_classification,
                        now.isoformat(),
                        completed,
                        str(execution_id),
                        expected.value,
                    ),
                )
                return cursor.rowcount == 1
        except aiosqlite.Error as error:
            raise StorageError("could not transition Final-QA V2 execution") from error

    async def put_final_qa_v2_citations(self, citations: tuple[EvidenceCitationV2, ...]) -> None:
        db = self._require_open()
        try:
            async with self._multimodal_lock, _transaction(db):
                for citation in citations:
                    payload = _encode({"kind": "evidence_citation_v2", "citation": citation})
                    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                    async with db.execute(
                        "SELECT payload_hash FROM evidence_citations_v2 WHERE citation_id=?",
                        (str(citation.citation_id),),
                    ) as cursor:
                        existing = await cursor.fetchone()
                    if existing is not None:
                        if existing[0] != digest:
                            raise ConflictError("EvidenceCitationV2 is immutable")
                        continue
                    await db.execute(
                        """INSERT INTO evidence_citations_v2(
                            citation_id,execution_id,source_number,candidate_id,payload,payload_hash,
                            created_at
                        ) VALUES(?,?,?,?,?,?,?)""",
                        (
                            str(citation.citation_id),
                            str(citation.execution_id),
                            citation.source_number,
                            str(citation.candidate.candidate_id),
                            payload,
                            digest,
                            citation.created_at.isoformat(),
                        ),
                    )
        except ConflictError:
            raise
        except aiosqlite.Error as error:
            raise StorageError("could not persist EvidenceCitationV2") from error
