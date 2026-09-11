"""SQLite derived-table projections for Phase 8.5.7 structured retrieval."""

# SQL remains deliberately explicit for migration review.
# ruff: noqa: E501

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid5

import aiosqlite

from mnemo.interfaces.errors import ConflictError, StorageError
from mnemo.models import Chunk, FrozenMetadata, ParsedDocument, TableBlock
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    EvidenceRepresentation,
    RetrievalPathEvidenceV2,
    RetrievalScopeV2,
    advanced_candidate_id,
)
from mnemo.models.structured_datasets import (
    StructuredDatasetCatalog,
    StructuredDatasetDescriptor,
    StructuredDatasetField,
    StructuredDatasetReadiness,
)
from mnemo.models.structured_retrieval import ExtractedStructuredRecord, StructuredField

STRUCTURED_PROJECTION_SCHEMA_VERSION = 2
_GENERATION_NAMESPACE = UUID("5c8df9ed-8476-5f63-b60f-04ab34b3b2ea")
_TABLE_NAMESPACE = UUID("d265187f-c0db-5d21-900f-1ea613483d10")


class _ChunkReader(Protocol):
    async def get_chunk(self, chunk_id: str) -> Chunk | None: ...


STRUCTURED_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS structured_table_projections (
        table_id TEXT PRIMARY KEY,
        generation_id TEXT NOT NULL REFERENCES index_generations(generation_id) ON DELETE RESTRICT,
        document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
        version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
        block_ordinal INTEGER NOT NULL CHECK(block_ordinal >= 0),
        page_number INTEGER,
        headers TEXT NOT NULL,
        header_row_count INTEGER NOT NULL CHECK(header_row_count > 0),
        row_count INTEGER NOT NULL CHECK(row_count >= 0),
        checksum TEXT NOT NULL,
        UNIQUE(version_id, block_ordinal)
    )""",
    """CREATE TABLE IF NOT EXISTS structured_table_cells (
        table_id TEXT NOT NULL REFERENCES structured_table_projections(table_id) ON DELETE CASCADE,
        row_ordinal INTEGER NOT NULL CHECK(row_ordinal >= 0),
        column_index INTEGER NOT NULL CHECK(column_index >= 0),
        raw_value TEXT NOT NULL,
        PRIMARY KEY(table_id, row_ordinal, column_index)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_structured_projection_scope ON structured_table_projections(document_id, version_id, block_ordinal)",
    "CREATE INDEX IF NOT EXISTS idx_structured_cells_row ON structured_table_cells(table_id, row_ordinal)",
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
            raise StorageError("structured projection transaction failed") from error
        raise


class SQLiteStructuredProjectionMixin:
    """Additive exact-version table projection mixed into ``SQLiteStore``."""

    _structured_lock: asyncio.Lock

    def _require_open(self) -> aiosqlite.Connection:
        raise NotImplementedError

    async def project_structured_document(self, version_id: UUID, document: ParsedDocument) -> bool:
        """Build one immutable ready generation from canonical IR, idempotently."""
        db = self._require_open()
        async with self._structured_lock, _transaction(db):
            async with db.execute(
                "SELECT document_id FROM document_versions WHERE version_id=?", (str(version_id),)
            ) as cursor:
                identity = await cursor.fetchone()
            if identity is None:
                return False
            document_id = UUID(identity[0])
            tables = tuple(
                block
                for block in document.blocks
                if isinstance(block, TableBlock) and block.header_row_count > 0
            )
            material = [_table_material(block) for block in tables]
            checksum = hashlib.sha256(
                json.dumps(
                    material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            generation_id = uuid5(
                _GENERATION_NAMESPACE,
                f"{version_id}:structured-table:{STRUCTURED_PROJECTION_SCHEMA_VERSION}",
            )
            async with db.execute(
                "SELECT state,checksum FROM index_generations WHERE generation_id=?",
                (str(generation_id),),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing is not None and existing[0] == "ready":
                if existing[1] != checksum:
                    raise ConflictError("structured projection generation is immutable")
                await _activate_structured_generation(
                    db,
                    generation_id=generation_id,
                    version_id=version_id,
                    item_count=sum(len(block.rows) - block.header_row_count for block in tables),
                    checksum=checksum,
                    now=datetime.now(UTC).isoformat(),
                )
                return False
            if existing is not None:
                await db.execute(
                    "DELETE FROM active_index_generations WHERE generation_id=?",
                    (str(generation_id),),
                )
                await db.execute(
                    "DELETE FROM structured_table_cells WHERE table_id IN (SELECT table_id FROM structured_table_projections WHERE generation_id=?)",
                    (str(generation_id),),
                )
                await db.execute(
                    "DELETE FROM structured_table_projections WHERE generation_id=?",
                    (str(generation_id),),
                )
                await db.execute(
                    "DELETE FROM index_generations WHERE generation_id=?", (str(generation_id),)
                )
            now = datetime.now(UTC).isoformat()
            await db.execute(
                """INSERT INTO index_generations(
                    generation_id,capability,profile,schema_version,input_scope,
                    provider_identity,model_identity,configuration_digest,dimensions,
                    state,item_count,checksum,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(generation_id),
                    "structured_table",
                    f"canonical-ir-v2:{version_id}",
                    STRUCTURED_PROJECTION_SCHEMA_VERSION,
                    str(version_id),
                    "mnemo.parser",
                    "canonical-table-ir",
                    hashlib.sha256(b"structured-table-projection/v1").hexdigest(),
                    None,
                    "building",
                    0,
                    None,
                    now,
                    now,
                ),
            )
            row_count = 0
            for block in tables:
                table_id = uuid5(_TABLE_NAMESPACE, f"{version_id}:{block.ordinal}")
                headers = _headers(block)
                rows = block.rows[block.header_row_count :]
                table_checksum = hashlib.sha256(
                    json.dumps(
                        _table_material(block), ensure_ascii=False, separators=(",", ":")
                    ).encode()
                ).hexdigest()
                await db.execute(
                    """INSERT INTO structured_table_projections(
                        table_id,generation_id,document_id,version_id,block_ordinal,page_number,
                        headers,header_row_count,row_count,checksum
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(table_id),
                        str(generation_id),
                        str(document_id),
                        str(version_id),
                        block.ordinal,
                        block.page_number,
                        json.dumps(headers, ensure_ascii=False, separators=(",", ":")),
                        block.header_row_count,
                        len(rows),
                        table_checksum,
                    ),
                )
                for row_ordinal, row in enumerate(rows, start=block.header_row_count):
                    await db.executemany(
                        "INSERT INTO structured_table_cells(table_id,row_ordinal,column_index,raw_value) VALUES(?,?,?,?)",
                        tuple(
                            (str(table_id), row_ordinal, column_index, value)
                            for column_index, value in enumerate(row)
                        ),
                    )
                row_count += len(rows)
            await db.execute(
                "UPDATE index_generations SET state='ready',item_count=?,checksum=?,updated_at=? WHERE generation_id=? AND state='building'",
                (row_count, checksum, now, str(generation_id)),
            )
            await _activate_structured_generation(
                db,
                generation_id=generation_id,
                version_id=version_id,
                item_count=row_count,
                checksum=checksum,
                now=now,
            )
            return True

    async def extract_projected_structured_records(
        self,
        candidate: AdvancedRetrievalCandidate,
        fields: tuple[StructuredField, ...],
        *,
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]:
        """Read only allowlisted columns using bound values and a fixed SQL shape."""
        if candidate.chunk is None or limit < 1:
            return ()
        db = self._require_open()
        async with db.execute(
            """SELECT p.table_id,p.headers,p.page_number,p.block_ordinal
               FROM structured_table_projections p
               JOIN index_generations g ON g.generation_id=p.generation_id
               JOIN active_index_generations a ON a.generation_id=g.generation_id
               WHERE p.version_id=? AND p.block_ordinal BETWEEN ? AND ? AND g.state='ready'
               ORDER BY p.block_ordinal""",
            (
                str(candidate.version_id),
                candidate.chunk.source_span.start_ordinal,
                candidate.chunk.source_span.end_ordinal,
            ),
        ) as cursor:
            tables = tuple(await cursor.fetchall())
        if len(tables) != 1:
            return ()
        table_id, raw_headers, page_number, block_ordinal = tables[0]
        headers = tuple(json.loads(raw_headers))
        indexes = {header.casefold(): index for index, header in enumerate(headers)}
        requested = {
            field.name: indexes[source]
            for field in fields
            if (source := (field.source_name or field.name).casefold()) in indexes
        }
        if not requested:
            return ()
        async with db.execute(
            """SELECT row_ordinal,column_index,raw_value
               FROM structured_table_cells
               WHERE table_id=? ORDER BY row_ordinal,column_index LIMIT ?""",
            (table_id, limit * len(headers)),
        ) as cursor:
            cells = await cursor.fetchall()
        by_row: dict[int, dict[int, str]] = {}
        for row_ordinal, column_index, value in cells:
            by_row.setdefault(int(row_ordinal), {})[int(column_index)] = value
        return tuple(
            ExtractedStructuredRecord(
                candidate_id=candidate.candidate_id,
                row_ordinal=row_ordinal,
                values=FrozenMetadata(
                    {name: row.get(column, "") for name, column in requested.items()}
                ),
                cell_locators=FrozenMetadata(
                    {
                        name: {
                            "block_ordinal": int(block_ordinal),
                            "page": page_number,
                            "row": row_ordinal,
                            "column": column,
                            "header": headers[column],
                        }
                        for name, column in requested.items()
                    }
                ),
                extraction_method="sqlite_structured_projection/v1",
            )
            for row_ordinal, row in sorted(by_row.items())
        )

    async def list_structured_datasets(
        self, *, scope: RetrievalScopeV2, schema_scan_limit: int
    ) -> StructuredDatasetCatalog:
        """Return occurrence-safe exact-version dataset metadata without internal names."""
        if not isinstance(scope, RetrievalScopeV2):
            raise TypeError("structured dataset scope must be typed")
        if schema_scan_limit < 1 or schema_scan_limit > 100_000:
            raise ValueError("schema_scan_limit must be from 1 through 100000")
        db = self._require_open()
        sql = """SELECT p.table_id,p.generation_id,p.document_id,p.version_id,
                        p.block_ordinal,p.page_number,p.headers,p.row_count,p.checksum,
                        g.state,CASE WHEN a.generation_id IS NULL THEN 0 ELSE 1 END,
                        MIN(s.source_id),dv.metadata,
                        (SELECT c.id FROM chunks c
                         WHERE c.document_id=p.document_id AND c.version_id=p.version_id
                           AND p.block_ordinal BETWEEN c.source_start_ordinal AND c.source_end_ordinal
                         ORDER BY c.source_start_ordinal,c.source_end_ordinal,c.id LIMIT 1),
                        CASE WHEN EXISTS (
                          SELECT 1 FROM index_generation_coverage cov
                          WHERE cov.generation_id=g.generation_id
                            AND cov.completeness='complete' AND cov.failed_count=0
                        ) THEN 1 ELSE 0 END
                 FROM structured_table_projections p
                 JOIN index_generations g ON g.generation_id=p.generation_id
                 LEFT JOIN active_index_generations a ON a.generation_id=g.generation_id
                 JOIN sources s ON s.document_id=p.document_id
                 JOIN document_versions dv ON dv.version_id=p.version_id
                 WHERE s.notebook_id=?"""
        params: list[object] = [str(scope.notebook_id)]
        for values, expression in (
            (scope.source_ids, "s.source_id"),
            (scope.document_ids, "p.document_id"),
            (scope.version_ids, "p.version_id"),
        ):
            if values:
                placeholders = ",".join("?" for _ in values)
                sql += f" AND {expression} IN ({placeholders})"
                params.extend(str(value) for value in values)
        sql += " GROUP BY p.table_id ORDER BY p.document_id,p.version_id,p.block_ordinal,p.table_id"
        async with db.execute(sql, params) as cursor:
            rows = tuple(await cursor.fetchall())

        from mnemo.retrieval.structured import observe_table_schema

        datasets: list[StructuredDatasetDescriptor] = []
        for row in rows:
            headers = tuple(str(item) for item in json.loads(row[6]))
            async with db.execute(
                """SELECT row_ordinal,column_index,raw_value FROM structured_table_cells
                   WHERE table_id=? ORDER BY row_ordinal,column_index LIMIT ?""",
                (row[0], schema_scan_limit * max(1, len(headers))),
            ) as cursor:
                raw_cells = tuple(await cursor.fetchall())
            by_row: dict[int, dict[int, str]] = {}
            for row_ordinal, column_index, value in raw_cells:
                by_row.setdefault(int(row_ordinal), {})[int(column_index)] = str(value)
            table_rows = tuple(
                tuple(values.get(index, "") for index in range(len(headers)))
                for _, values in sorted(by_row.items())
            )
            try:
                observed = observe_table_schema(
                    TableBlock(ordinal=int(row[4]), rows=(headers, *table_rows), header_row_count=1)
                )
            except Exception:
                continue
            chunk_id = row[13]
            reader = cast(_ChunkReader, self)
            chunk = None if chunk_id is None else await reader.get_chunk(str(chunk_id))
            if chunk is None:
                continue
            metadata = json.loads(row[12])
            title = metadata.get("title") if isinstance(metadata, dict) else None
            candidate = AdvancedRetrievalCandidate(
                candidate_id=advanced_candidate_id(
                    representation=EvidenceRepresentation.CANONICAL_TEXT,
                    document_id=UUID(row[2]),
                    version_id=UUID(row[3]),
                    chunk_id=chunk.id,
                    occurrence_id=None,
                    derivation_id=None,
                ),
                notebook_id=scope.notebook_id,
                source_id=UUID(row[11]),
                document_id=UUID(row[2]),
                version_id=UUID(row[3]),
                representation=EvidenceRepresentation.CANONICAL_TEXT,
                chunk=chunk,
                occurrence_id=None,
                derivation_id=None,
                locator=FrozenMetadata(
                    {"block_ordinal": int(row[4]), "page": row[5], "dataset_id": row[0]}
                ),
                document_title=title if isinstance(title, str) else None,
                content=None,
                paths=(
                    RetrievalPathEvidenceV2(
                        path="structured-dataset-catalog", source_rank=1, source_score=None
                    ),
                ),
            )
            state = str(row[9])
            active = bool(row[10])
            coverage_ready = bool(row[14])
            readiness = (
                StructuredDatasetReadiness.READY
                if state == "ready" and active and coverage_ready
                else StructuredDatasetReadiness.FAILED
                if state == "failed"
                else StructuredDatasetReadiness.STALE
                if state in {"stale", "superseded"}
                else StructuredDatasetReadiness.INACTIVE
            )
            fields = tuple(
                StructuredDatasetField(
                    field=StructuredField(
                        name=column.name,
                        source_name=column.name,
                        field_type=column.observed_type,
                    ),
                    confidence=column.confidence,
                    non_missing_count=column.non_missing_count,
                )
                for column in observed.columns
            )
            datasets.append(
                StructuredDatasetDescriptor(
                    dataset_id=UUID(row[0]),
                    generation_id=UUID(row[1]),
                    schema_identity=observed.generation,
                    checksum=str(row[8]),
                    notebook_id=scope.notebook_id,
                    source_id=UUID(row[11]),
                    document_id=UUID(row[2]),
                    version_id=UUID(row[3]),
                    block_ordinal=int(row[4]),
                    page_number=None if row[5] is None else int(row[5]),
                    row_count=int(row[7]),
                    fields=fields,
                    readiness=readiness,
                    candidate=candidate,
                )
            )
        requested = scope.version_ids or tuple(
            sorted({item.version_id for item in datasets}, key=str)
        )
        ready = tuple(
            version_id
            for version_id in requested
            if any(
                item.version_id == version_id and item.readiness is StructuredDatasetReadiness.READY
                for item in datasets
            )
        )
        unavailable = tuple(item for item in requested if item not in set(ready))
        snapshot_material = [
            (str(item.dataset_id), str(item.generation_id), item.checksum, item.readiness.value)
            for item in datasets
        ]
        snapshot = hashlib.sha256(
            json.dumps(snapshot_material, separators=(",", ":")).encode()
        ).hexdigest()
        return StructuredDatasetCatalog(
            scope=scope,
            snapshot_identity=snapshot,
            datasets=tuple(datasets),
            requested_version_ids=tuple(requested),
            ready_version_ids=ready,
            unavailable_version_ids=unavailable,
        )

    async def structured_projection_ready(self) -> bool:
        """Report whether at least one complete ready structured generation is active."""
        async with self._require_open().execute(
            """SELECT 1 FROM active_index_generations a
               JOIN index_generations g ON g.generation_id=a.generation_id
               JOIN index_generation_coverage c ON c.generation_id=g.generation_id
               WHERE g.capability='structured_table' AND g.state='ready'
                 AND c.completeness='complete' AND c.failed_count=0 LIMIT 1"""
        ) as cursor:
            return await cursor.fetchone() is not None

    async def active_structured_generation_identity(self) -> str | None:
        """Identify the exact complete active generation set used by the runtime."""
        async with self._require_open().execute(
            """SELECT g.generation_id FROM active_index_generations a
               JOIN index_generations g ON g.generation_id=a.generation_id
               JOIN index_generation_coverage c ON c.generation_id=g.generation_id
               WHERE g.capability='structured_table' AND g.state='ready'
                 AND c.completeness='complete' AND c.failed_count=0
               ORDER BY g.generation_id"""
        ) as cursor:
            rows = tuple(await cursor.fetchall())
        if not rows:
            return None
        material = json.dumps([str(row[0]) for row in rows], separators=(",", ":"))
        return hashlib.sha256(material.encode()).hexdigest()

    async def extract_structured_dataset_records(
        self,
        *,
        notebook_id: UUID,
        dataset_id: UUID,
        candidate_id: UUID,
        fields: tuple[StructuredField, ...],
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]:
        """Read one authorized active dataset through fixed-shape, bound SQL."""
        if limit < 1 or limit > 100_000:
            raise ValueError("structured dataset read limit is invalid")
        db = self._require_open()
        async with db.execute(
            """SELECT p.headers,p.page_number,p.block_ordinal
               FROM structured_table_projections p
               JOIN index_generations g ON g.generation_id=p.generation_id
               JOIN active_index_generations a ON a.generation_id=g.generation_id
               JOIN sources s ON s.document_id=p.document_id
               WHERE p.table_id=? AND s.notebook_id=? AND g.state='ready'
               GROUP BY p.table_id""",
            (str(dataset_id), str(notebook_id)),
        ) as cursor:
            table = await cursor.fetchone()
        if table is None:
            return ()
        headers = tuple(str(item) for item in json.loads(table[0]))
        indexes = {header.casefold(): index for index, header in enumerate(headers)}
        requested: dict[str, int] = {}
        for field in fields:
            source = (field.source_name or field.name).casefold()
            if source not in indexes:
                raise ValueError("structured field is absent from the authorized dataset")
            requested[field.name] = indexes[source]
        async with db.execute(
            """SELECT row_ordinal,column_index,raw_value FROM structured_table_cells
               WHERE table_id=? ORDER BY row_ordinal,column_index LIMIT ?""",
            (str(dataset_id), limit * max(1, len(headers))),
        ) as cursor:
            cells = tuple(await cursor.fetchall())
        by_row: dict[int, dict[int, str]] = {}
        for row_ordinal, column_index, value in cells:
            by_row.setdefault(int(row_ordinal), {})[int(column_index)] = str(value)
        return tuple(
            ExtractedStructuredRecord(
                candidate_id=candidate_id,
                row_ordinal=row_ordinal,
                values=FrozenMetadata(
                    {name: values.get(column, "") for name, column in requested.items()}
                ),
                cell_locators=FrozenMetadata(
                    {
                        name: {
                            "dataset_id": str(dataset_id),
                            "block_ordinal": int(table[2]),
                            "page": table[1],
                            "row": row_ordinal,
                            "column": column,
                            "header": headers[column],
                        }
                        for name, column in requested.items()
                    }
                ),
                extraction_method="sqlite-structured-dataset/v1",
            )
            for row_ordinal, values in sorted(by_row.items())
        )


async def _activate_structured_generation(
    db: aiosqlite.Connection,
    *,
    generation_id: UUID,
    version_id: UUID,
    item_count: int,
    checksum: str,
    now: str,
) -> None:
    """Persist complete coverage and a per-version active alias transactionally."""
    await db.execute(
        """INSERT OR IGNORE INTO index_generation_sources(
           generation_id,source_kind,source_id) VALUES(?,?,?)""",
        (str(generation_id), "version", str(version_id)),
    )
    await db.execute(
        """INSERT OR IGNORE INTO index_generation_coverage(
           generation_id,expected_count,succeeded_count,failed_count,skipped_count,
           completeness,checksum,failure_digest,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
        (str(generation_id), item_count, item_count, 0, 0, "complete", checksum, None, now),
    )
    generation = await (
        await db.execute(
            "SELECT capability,profile FROM index_generations WHERE generation_id=?",
            (str(generation_id),),
        )
    ).fetchone()
    if generation is None:
        raise ConflictError("structured generation disappeared before activation")
    active = await (
        await db.execute(
            """SELECT generation_id FROM active_index_generations
               WHERE capability=? AND profile=?""",
            (generation[0], generation[1]),
        )
    ).fetchone()
    if active is not None and active[0] != str(generation_id):
        await db.execute(
            """UPDATE index_generations SET state='superseded',updated_at=?
               WHERE generation_id=? AND state='ready'""",
            (now, active[0]),
        )
    await db.execute(
        """INSERT INTO active_index_generations(capability,profile,generation_id,promoted_at)
           VALUES(?,?,?,?) ON CONFLICT(capability,profile) DO UPDATE SET
           generation_id=excluded.generation_id,promoted_at=excluded.promoted_at""",
        (generation[0], generation[1], str(generation_id), now),
    )


def _headers(block: TableBlock) -> tuple[str, ...]:
    return tuple(
        " / ".join(
            row[column].strip()
            for row in block.rows[: block.header_row_count]
            if row[column].strip()
        )
        for column in range(len(block.rows[0]))
    )


def _table_material(block: TableBlock) -> dict[str, object]:
    return {
        "ordinal": block.ordinal,
        "page": block.page_number,
        "headers": _headers(block),
        "rows": block.rows[block.header_row_count :],
    }
