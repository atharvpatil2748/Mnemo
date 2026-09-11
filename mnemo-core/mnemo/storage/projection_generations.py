"""Schema-v14 coverage and derived text projections for Phase 8.5 generations."""

# SQL is intentionally explicit for migration and security review.
# ruff: noqa: E501

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import aiosqlite

from mnemo.interfaces.errors import ConflictError, StorageError
from mnemo.models.multilingual import LanguageDerivation
from mnemo.phase85.projections import (
    ProjectionBuildResult,
    ProjectionCompleteness,
    ProjectionCoverage,
)
from mnemo.retrieval.final_qa_snapshot import _decode
from mnemo.storage.vision import _vision_from_payload

PROJECTION_GENERATION_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS index_generation_sources (
        generation_id TEXT NOT NULL REFERENCES index_generations(generation_id) ON DELETE CASCADE,
        source_kind TEXT NOT NULL CHECK(source_kind IN ('generation','version')),
        source_id TEXT NOT NULL,
        PRIMARY KEY(generation_id, source_kind, source_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_index_generation_sources_source ON index_generation_sources(source_kind,source_id,generation_id)",
    """CREATE TABLE IF NOT EXISTS index_generation_coverage (
        generation_id TEXT PRIMARY KEY REFERENCES index_generations(generation_id) ON DELETE CASCADE,
        expected_count INTEGER NOT NULL CHECK(expected_count >= 0),
        succeeded_count INTEGER NOT NULL CHECK(succeeded_count >= 0),
        failed_count INTEGER NOT NULL CHECK(failed_count >= 0),
        skipped_count INTEGER NOT NULL CHECK(skipped_count >= 0),
        completeness TEXT NOT NULL CHECK(completeness IN ('complete','partial')),
        checksum TEXT NOT NULL,
        failure_digest TEXT,
        updated_at TEXT NOT NULL,
        CHECK(expected_count = succeeded_count + failed_count + skipped_count)
    )""",
    """CREATE TABLE IF NOT EXISTS vision_text_projection_rows (
        generation_id TEXT NOT NULL REFERENCES index_generations(generation_id) ON DELETE CASCADE,
        derivation_id TEXT NOT NULL REFERENCES vision_results(derivation_id) ON DELETE RESTRICT,
        document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
        version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
        occurrence_id TEXT NOT NULL REFERENCES asset_occurrences(occurrence_id) ON DELETE RESTRICT,
        source_generation_id TEXT NOT NULL,
        language TEXT,
        text_hash TEXT NOT NULL,
        PRIMARY KEY(generation_id, derivation_id)
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS vision_text_fts USING fts5(
        text, generation_id UNINDEXED, derivation_id UNINDEXED,
        document_id UNINDEXED, version_id UNINDEXED, occurrence_id UNINDEXED
    )""",
    "CREATE INDEX IF NOT EXISTS idx_vision_text_projection_scope ON vision_text_projection_rows(generation_id,document_id,version_id)",
    """CREATE TABLE IF NOT EXISTS language_text_projection_rows (
        generation_id TEXT NOT NULL REFERENCES index_generations(generation_id) ON DELETE CASCADE,
        derivation_id TEXT NOT NULL REFERENCES language_derivations(derivation_id) ON DELETE RESTRICT,
        notebook_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        source_evidence_id TEXT NOT NULL,
        source_generation_id TEXT NOT NULL,
        source_language TEXT NOT NULL,
        target_language TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        PRIMARY KEY(generation_id, derivation_id)
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS language_text_fts USING fts5(
        text, generation_id UNINDEXED, derivation_id UNINDEXED, notebook_id UNINDEXED,
        document_id UNINDEXED, version_id UNINDEXED, source_evidence_id UNINDEXED,
        source_language UNINDEXED, target_language UNINDEXED
    )""",
    "CREATE INDEX IF NOT EXISTS idx_language_text_projection_scope ON language_text_projection_rows(generation_id,notebook_id,document_id,version_id)",
)


@asynccontextmanager
async def _transaction(db: aiosqlite.Connection) -> AsyncIterator[None]:
    try:
        await db.execute("BEGIN IMMEDIATE")
        yield
        await db.commit()
    except BaseException as error:
        await db.rollback()
        if isinstance(error, aiosqlite.Error):
            raise StorageError("projection generation transaction failed") from error
        raise


class SQLiteProjectionGenerationMixin:
    """Add lifecycle coverage and independent Vision/Language FTS projections."""

    _projection_generation_lock: asyncio.Lock

    def _require_open(self) -> aiosqlite.Connection:
        raise NotImplementedError

    async def put_index_generation_coverage(self, coverage: ProjectionCoverage) -> bool:
        db = self._require_open()
        async with self._projection_generation_lock, _transaction(db):
            row = await (
                await db.execute(
                    """SELECT expected_count,succeeded_count,failed_count,skipped_count,
                              completeness,checksum,failure_digest
                       FROM index_generation_coverage WHERE generation_id=?""",
                    (str(coverage.generation_id),),
                )
            ).fetchone()
            material = (
                coverage.expected_count,
                coverage.succeeded_count,
                coverage.failed_count,
                coverage.skipped_count,
                coverage.completeness.value,
                coverage.checksum,
                coverage.failure_digest,
            )
            if row is not None:
                if tuple(row) != material:
                    raise ConflictError("generation coverage is immutable")
                return False
            generation = await (
                await db.execute(
                    "SELECT state FROM index_generations WHERE generation_id=?",
                    (str(coverage.generation_id),),
                )
            ).fetchone()
            if generation is None or generation[0] != "building":
                raise ConflictError("coverage requires a BUILDING generation")
            await db.execute(
                """INSERT INTO index_generation_coverage(
                   generation_id,expected_count,succeeded_count,failed_count,skipped_count,
                   completeness,checksum,failure_digest,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (str(coverage.generation_id), *material, coverage.updated_at.isoformat()),
            )
            return True

    async def get_index_generation_coverage(self, generation_id: UUID) -> ProjectionCoverage | None:
        row = await (
            await self._require_open().execute(
                """SELECT expected_count,succeeded_count,failed_count,skipped_count,
                          completeness,checksum,failure_digest,updated_at
                   FROM index_generation_coverage WHERE generation_id=?""",
                (str(generation_id),),
            )
        ).fetchone()
        if row is None:
            return None
        return ProjectionCoverage(
            generation_id=generation_id,
            expected_count=int(row[0]),
            succeeded_count=int(row[1]),
            failed_count=int(row[2]),
            skipped_count=int(row[3]),
            completeness=ProjectionCompleteness(str(row[4])),
            checksum=str(row[5]),
            failure_digest=None if row[6] is None else str(row[6]),
            updated_at=datetime.fromisoformat(str(row[7])),
        )

    async def put_index_generation_sources(
        self,
        *,
        generation_id: UUID,
        source_generation_ids: tuple[UUID, ...],
        source_version_ids: tuple[UUID, ...],
    ) -> bool:
        expected = tuple(
            sorted(
                (("generation", str(item)) for item in source_generation_ids),
                key=lambda item: item[1],
            )
        ) + tuple(
            sorted(
                (("version", str(item)) for item in source_version_ids),
                key=lambda item: item[1],
            )
        )
        db = self._require_open()
        async with self._projection_generation_lock, _transaction(db):
            generation = await (
                await db.execute(
                    "SELECT state FROM index_generations WHERE generation_id=?",
                    (str(generation_id),),
                )
            ).fetchone()
            if generation is None or generation[0] != "building":
                raise ConflictError("generation sources require a BUILDING generation")
            existing = tuple(
                tuple(row)
                for row in await (
                    await db.execute(
                        """SELECT source_kind,source_id FROM index_generation_sources
                           WHERE generation_id=? ORDER BY source_kind,source_id""",
                        (str(generation_id),),
                    )
                ).fetchall()
            )
            if existing:
                if existing != tuple(sorted(expected)):
                    raise ConflictError("generation source contract is immutable")
                return False
            await db.executemany(
                """INSERT INTO index_generation_sources(generation_id,source_kind,source_id)
                   VALUES(?,?,?)""",
                ((str(generation_id), kind, source_id) for kind, source_id in expected),
            )
            return True

    async def get_index_generation_sources(
        self, generation_id: UUID
    ) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
        rows = await (
            await self._require_open().execute(
                """SELECT source_kind,source_id FROM index_generation_sources
                   WHERE generation_id=? ORDER BY source_kind,source_id""",
                (str(generation_id),),
            )
        ).fetchall()
        generations = tuple(UUID(str(row[1])) for row in rows if row[0] == "generation")
        versions = tuple(UUID(str(row[1])) for row in rows if row[0] == "version")
        return generations, versions

    async def rollback_index_generation(self, generation_id: UUID) -> bool:
        """Atomically restore one retained, complete superseded generation."""
        db = self._require_open()
        async with self._projection_generation_lock, _transaction(db):
            target = await (
                await db.execute(
                    """SELECT capability,profile,state,item_count,checksum
                       FROM index_generations WHERE generation_id=?""",
                    (str(generation_id),),
                )
            ).fetchone()
            if target is None or target[2] != "superseded":
                return False
            coverage = await (
                await db.execute(
                    """SELECT completeness,succeeded_count,checksum
                       FROM index_generation_coverage WHERE generation_id=?""",
                    (str(generation_id),),
                )
            ).fetchone()
            if (
                coverage is None
                or coverage[0] != "complete"
                or int(coverage[1]) != int(target[3])
                or coverage[2] != target[4]
            ):
                raise ConflictError("rollback target does not have complete valid coverage")
            active = await (
                await db.execute(
                    """SELECT generation_id FROM active_index_generations
                       WHERE capability=? AND profile=?""",
                    (target[0], target[1]),
                )
            ).fetchone()
            if active is None:
                return False
            now = datetime.now(UTC).isoformat()
            demoted = await db.execute(
                """UPDATE index_generations SET state='superseded',updated_at=?
                   WHERE generation_id=? AND state='ready'""",
                (now, active[0]),
            )
            restored = await db.execute(
                """UPDATE index_generations SET state='ready',updated_at=?
                   WHERE generation_id=? AND state='superseded'""",
                (now, str(generation_id)),
            )
            if demoted.rowcount != 1 or restored.rowcount != 1:
                raise ConflictError("active generation changed during rollback")
            await db.execute(
                """UPDATE active_index_generations SET generation_id=?,promoted_at=?
                   WHERE capability=? AND profile=?""",
                (str(generation_id), now, target[0], target[1]),
            )
            return True

    async def build_vision_text_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult:
        db = self._require_open()
        async with self._projection_generation_lock, _transaction(db):
            await _require_building_generation(db, generation_id, "vision_text")
            await _require_registered_sources(db, generation_id, source_generation_ids)
            rows = await _rows_for_generations(
                db,
                """SELECT derivation_id,document_id,version_id,occurrence_id,generation_id,
                          completeness,payload FROM vision_results WHERE generation_id IN ({})
                   ORDER BY derivation_id""",
                source_generation_ids,
            )
            projected: list[tuple[str, ...]] = []
            failed = 0
            for row in rows:
                completeness = str(row[5])
                if completeness != "complete":
                    failed += 1
                    continue
                value = _vision_from_payload(str(row[6]))
                captions = getattr(value, "captions", ())
                observations = getattr(value, "observations", ())
                text = "\n".join(
                    item
                    for item in (
                        *(str(caption.text).strip() for caption in captions),
                        *(str(observation.value).strip() for observation in observations),
                    )
                    if item
                )
                if not text:
                    failed += 1
                    continue
                languages = getattr(value, "languages", ())
                language = None if not languages else languages[0].language_code
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                projected.append(
                    (
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        str(row[3]),
                        str(row[4]),
                        "" if language is None else language,
                        text_hash,
                        text,
                    )
                )
            for item in projected:
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO vision_text_projection_rows(
                       generation_id,derivation_id,document_id,version_id,occurrence_id,
                       source_generation_id,language,text_hash) VALUES(?,?,?,?,?,?,?,?)""",
                    (str(generation_id), *item[:7]),
                )
                if cursor.rowcount == 1:
                    await db.execute(
                        "INSERT INTO vision_text_fts(text,generation_id,derivation_id,document_id,version_id,occurrence_id) VALUES(?,?,?,?,?,?)",
                        (item[7], str(generation_id), item[0], item[1], item[2], item[3]),
                    )
            checksum = _projection_checksum(item[:7] for item in projected)
            return ProjectionBuildResult(
                expected_count=len(rows),
                succeeded_count=len(projected),
                failed_count=failed,
                skipped_count=0,
                checksum=checksum,
            )

    async def build_language_text_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult:
        db = self._require_open()
        async with self._projection_generation_lock, _transaction(db):
            await _require_building_generation(db, generation_id, "language_text")
            await _require_registered_sources(db, generation_id, source_generation_ids)
            rows = await _rows_for_generations(
                db,
                """SELECT derivation_id,notebook_id,document_id,version_id,source_evidence_id,
                          generation_id,source_language,target_language,payload
                   FROM language_derivations WHERE generation_id IN ({}) ORDER BY derivation_id""",
                source_generation_ids,
            )
            projected: list[tuple[str, ...]] = []
            failed = 0
            for row in rows:
                value = _decode(str(row[8]))
                if not isinstance(value, LanguageDerivation) or not value.output_text.strip():
                    failed += 1
                    continue
                projected.append(
                    (
                        *(str(item) for item in row[:8]),
                        value.output_hash,
                        value.output_text,
                    )
                )
            for item in projected:
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO language_text_projection_rows(
                       generation_id,derivation_id,notebook_id,document_id,version_id,
                       source_evidence_id,source_generation_id,source_language,target_language,
                       text_hash) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (str(generation_id), *item[:9]),
                )
                if cursor.rowcount == 1:
                    await db.execute(
                        """INSERT INTO language_text_fts(
                       text,generation_id,derivation_id,notebook_id,document_id,version_id,
                       source_evidence_id,source_language,target_language) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (
                            item[9],
                            str(generation_id),
                            item[0],
                            item[1],
                            item[2],
                            item[3],
                            item[4],
                            item[6],
                            item[7],
                        ),
                    )
            checksum = _projection_checksum(item[:9] for item in projected)
            return ProjectionBuildResult(
                expected_count=len(rows),
                succeeded_count=len(projected),
                failed_count=failed,
                skipped_count=0,
                checksum=checksum,
            )

    async def build_multilingual_vector_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult:
        db = self._require_open()
        async with self._projection_generation_lock, _transaction(db):
            await _require_building_generation(db, generation_id, "multilingual_vector")
            await _require_registered_sources(db, generation_id, source_generation_ids)
            rows = await _rows_for_generations(
                db,
                """SELECT embedding_id,notebook_id,source_evidence_id,generation_id,
                          vector_space,payload_hash FROM multilingual_embeddings
                   WHERE generation_id IN ({}) ORDER BY embedding_id""",
                source_generation_ids,
            )
            checksum = _projection_checksum(tuple(str(item) for item in row) for row in rows)
            return ProjectionBuildResult(
                expected_count=len(rows),
                succeeded_count=len(rows),
                failed_count=0,
                skipped_count=0,
                checksum=checksum,
            )


async def _require_building_generation(
    db: aiosqlite.Connection, generation_id: UUID, capability: str
) -> None:
    row = await (
        await db.execute(
            "SELECT capability,state FROM index_generations WHERE generation_id=?",
            (str(generation_id),),
        )
    ).fetchone()
    if row is None or tuple(row) != (capability, "building"):
        raise ConflictError(f"{capability} projection requires its BUILDING generation")


async def _require_registered_sources(
    db: aiosqlite.Connection,
    generation_id: UUID,
    source_generation_ids: tuple[UUID, ...],
) -> None:
    rows = await (
        await db.execute(
            """SELECT source_id FROM index_generation_sources
               WHERE generation_id=? AND source_kind='generation' ORDER BY source_id""",
            (str(generation_id),),
        )
    ).fetchall()
    registered = tuple(UUID(str(row[0])) for row in rows)
    if registered != tuple(sorted(source_generation_ids, key=str)):
        raise ConflictError("projection source generations do not match its immutable contract")


async def _rows_for_generations(
    db: aiosqlite.Connection, query: str, generation_ids: tuple[UUID, ...]
) -> tuple[tuple[object, ...], ...]:
    if not generation_ids:
        return ()
    placeholders = ",".join("?" for _ in generation_ids)
    cursor = await db.execute(
        query.format(placeholders), tuple(str(item) for item in generation_ids)
    )
    return tuple(tuple(row) for row in await cursor.fetchall())


def _projection_checksum(rows: Iterable[Iterable[object]]) -> str:
    material = "\n".join("\x1f".join(str(value) for value in row) for row in rows)
    return hashlib.sha256(material.encode()).hexdigest()
