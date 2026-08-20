"""SQLite FTS5 storage backend."""

import json
import unicodedata
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import aiosqlite

from mnemo.interfaces.errors import ConflictError, IntegrityError, StorageError
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
from mnemo.models._shared import thaw_json
from mnemo.models.chunks import ChunkPosition, ChunkType
from mnemo.models.documents import DocumentMetadata, DocumentVersion, DocumentVersionStatus
from mnemo.models.final_qa_execution import (
    FinalQAExecution,
    FinalQAExecutionSnapshot,
    FinalQAExecutionSnapshotPhase,
    FinalQAExecutionState,
)
from mnemo.models.notebook import InsightType, NoteOrigin, TurnRole
from mnemo.storage.retrieval_projection import RetrievalMetadataProjection

_SCHEMA_VERSION = 6

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS schema_versions (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Registry Tables
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    current_version_id TEXT NOT NULL,
    current_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_versions (
    version_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    metadata TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    position_section_index INTEGER NOT NULL,
    position_chunk_index INTEGER NOT NULL,
    position_page_number INTEGER,
    position_start_offset INTEGER,
    position_end_offset INTEGER,
    source_start_ordinal INTEGER NOT NULL,
    source_end_ordinal INTEGER NOT NULL,
    heading_path TEXT NOT NULL,
    parent_chunk_id TEXT REFERENCES chunks(id) ON DELETE CASCADE,
    sibling_ids TEXT NOT NULL,
    metadata TEXT NOT NULL
);

-- Version-aware derived metadata for pre-ranking sparse filters. Canonical
-- truth remains ParsedDocument and DocumentVersion.
CREATE TABLE IF NOT EXISTS retrieval_version_metadata (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    doc_type TEXT NOT NULL,
    publication_date TEXT,
    PRIMARY KEY (document_id, version_id)
);

CREATE TABLE IF NOT EXISTS final_qa_executions (
    execution_id TEXT PRIMARY KEY,
    assistant_turn_id TEXT NOT NULL UNIQUE,
    request_fingerprint TEXT NOT NULL,
    notebook_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_turn_id TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    payload_schema_version INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    model_configuration TEXT NOT NULL,
    state TEXT NOT NULL,
    retry_count INTEGER NOT NULL,
    failure_classification TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_final_qa_executions_state_updated
ON final_qa_executions(state, updated_at);
CREATE INDEX IF NOT EXISTS idx_final_qa_executions_session_user
ON final_qa_executions(session_id, user_turn_id);
CREATE TABLE IF NOT EXISTS final_qa_execution_snapshots (
    execution_id TEXT NOT NULL REFERENCES final_qa_executions(execution_id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    payload_schema_version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(execution_id, phase)
);

-- Notebook Tables
CREATE TABLE IF NOT EXISTS notebooks (
    notebook_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    notebook_id TEXT NOT NULL REFERENCES notebooks(notebook_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    notebook_id TEXT NOT NULL REFERENCES notebooks(notebook_id) ON DELETE CASCADE,
    title TEXT,
    content TEXT NOT NULL,
    origin TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS insights (
    insight_id TEXT PRIMARY KEY,
    notebook_id TEXT NOT NULL REFERENCES notebooks(notebook_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL
);

-- Conversation Tables
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    notebook_id TEXT NOT NULL REFERENCES notebooks(notebook_id) ON DELETE CASCADE,
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS citations (
    citation_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turns(turn_id) ON DELETE CASCADE,
    source_number INTEGER NOT NULL,
    chunk_id TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    document_title TEXT NOT NULL,
    verbatim_quote TEXT NOT NULL,
    page_number INTEGER,
    heading_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- FTS5 Virtual Tables (External Content)
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
    text,
    heading_path,
    chunk_type UNINDEXED,
    document_id UNINDEXED,
    content='chunks',
    content_rowid='rowid'
);

-- Non-authoritative exact-version title projection. Canonical titles remain
-- in document_versions.metadata and canonical chunk text is never modified.
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunk_titles USING fts5(
    title,
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    version_id UNINDEXED
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_notes USING fts5(
    title,
    content,
    notebook_id UNINDEXED,
    content='notes',
    content_rowid='rowid'
);

-- Triggers for FTS maintenance (chunks)
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO fts_chunks(rowid, text, heading_path, chunk_type, document_id)
  VALUES (new.rowid, new.text, new.heading_path, new.chunk_type, new.document_id);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO fts_chunks(fts_chunks, rowid, text, heading_path, chunk_type, document_id)
  VALUES ('delete', old.rowid, old.text, old.heading_path, old.chunk_type, old.document_id);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO fts_chunks(fts_chunks, rowid, text, heading_path, chunk_type, document_id)
  VALUES ('delete', old.rowid, old.text, old.heading_path, old.chunk_type, old.document_id);
  INSERT INTO fts_chunks(rowid, text, heading_path, chunk_type, document_id)
  VALUES (new.rowid, new.text, new.heading_path, new.chunk_type, new.document_id);
END;

-- Triggers for FTS maintenance (notes)
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO fts_notes(rowid, title, content, notebook_id)
  VALUES (new.rowid, new.title, new.content, new.notebook_id);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO fts_notes(fts_notes, rowid, title, content, notebook_id)
  VALUES ('delete', old.rowid, old.title, old.content, old.notebook_id);
END;

CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO fts_notes(fts_notes, rowid, title, content, notebook_id)
  VALUES ('delete', old.rowid, old.title, old.content, old.notebook_id);
  INSERT INTO fts_notes(rowid, title, content, notebook_id)
  VALUES (new.rowid, new.title, new.content, new.notebook_id);
END;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_document_versions_document_id ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_version_id ON chunks(version_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_version_metadata_type
ON retrieval_version_metadata(doc_type);
CREATE INDEX IF NOT EXISTS idx_retrieval_version_metadata_date
ON retrieval_version_metadata(publication_date);
CREATE INDEX IF NOT EXISTS idx_chunks_parent_id ON chunks(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_sources_notebook_id ON sources(notebook_id);
CREATE INDEX IF NOT EXISTS idx_sources_document_id ON sources(document_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sources_notebook_document
ON sources(notebook_id, document_id);
CREATE INDEX IF NOT EXISTS idx_notes_notebook_id ON notes(notebook_id);
CREATE INDEX IF NOT EXISTS idx_insights_notebook_id ON insights(notebook_id);
CREATE INDEX IF NOT EXISTS idx_insights_source_id ON insights(source_id);
CREATE INDEX IF NOT EXISTS idx_sessions_notebook_id ON sessions(notebook_id);
CREATE INDEX IF NOT EXISTS idx_turns_session_id ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_citations_turn_id ON citations(turn_id);
"""


def _dt_to_iso(dt: datetime) -> str:
    return dt.isoformat()


@asynccontextmanager
async def _transaction(db: aiosqlite.Connection) -> AsyncIterator[None]:
    await db.execute("BEGIN IMMEDIATE")
    try:
        yield
        await db.commit()
    except Exception:
        await db.rollback()
        raise


def _iso_to_dt(iso_str: str) -> datetime:
    return datetime.fromisoformat(iso_str)


def _final_qa_execution_from_row(row: Sequence[Any]) -> FinalQAExecution:
    return FinalQAExecution(
        execution_id=UUID(row[0]),
        assistant_turn_id=UUID(row[1]),
        request_fingerprint=row[2],
        notebook_id=UUID(row[3]),
        session_id=UUID(row[4]),
        user_turn_id=UUID(row[5]),
        contract_version=row[6],
        payload_schema_version=int(row[7]),
        provider=row[8],
        model=row[9],
        model_configuration=row[10],
        state=FinalQAExecutionState(row[11]),
        retry_count=int(row[12]),
        failure_classification=row[13],
        created_at=_iso_to_dt(row[14]),
        updated_at=_iso_to_dt(row[15]),
        completed_at=None if row[16] is None else _iso_to_dt(row[16]),
    )


def _fts_terms(query: str) -> tuple[str, ...]:
    """Split user text into Unicode letter/mark/number runs without FTS syntax."""
    terms: list[str] = []
    current: list[str] = []
    for character in query:
        if unicodedata.category(character)[0] in {"L", "M", "N"}:
            current.append(character)
        elif current:
            terms.append("".join(current))
            current = []
    if current:
        terms.append("".join(current))
    return tuple(terms)


class SQLiteStore:
    """SQLite-backed metadata, registry, and FTS5 storage."""

    def __init__(self, db_path: Path) -> None:
        """Initialize the storage configuration without connecting."""
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    def _require_open(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage is not open")
        return self._db

    async def open(self) -> None:
        """Open the database connection and apply migrations idempotently."""
        if self._db is not None:
            return

        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self._db_path)
        # Enable WAL mode and foreign keys per connection
        await self._db.execute("PRAGMA foreign_keys = ON;")
        await self._db.execute("PRAGMA journal_mode = WAL;")

        await self._migrate()

    async def _migrate(self) -> None:
        """Apply schema migrations to the latest version."""
        db = self._require_open()
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_versions'"
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                # First run, initialize schema
                await db.executescript(_SCHEMA_SQL)
                await db.execute(
                    "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
                    (_SCHEMA_VERSION, datetime.now().isoformat()),
                )
                await db.commit()
                return
        async with db.execute("SELECT MAX(version) FROM schema_versions") as cursor:
            version_row = await cursor.fetchone()
        current_version = (
            0 if version_row is None or version_row[0] is None else int(version_row[0])
        )
        if current_version < 2:
            await db.execute("ALTER TABLE chunks ADD COLUMN source_start_ordinal INTEGER")
            await db.execute("ALTER TABLE chunks ADD COLUMN source_end_ordinal INTEGER")
            await db.execute(
                "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
                (2, datetime.now().isoformat()),
            )
            await db.commit()
        if current_version < 3:
            async with db.execute(
                """
                SELECT notebook_id, document_id, COUNT(*)
                FROM sources
                GROUP BY notebook_id, document_id
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            ) as cursor:
                duplicate = await cursor.fetchone()
            if duplicate is not None:
                raise StorageError(
                    "SQLite migration 3 cannot enforce unique Source membership: "
                    f"notebook {duplicate[0]} and document {duplicate[1]} have "
                    f"{duplicate[2]} associations"
                )
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sources_notebook_document "
                "ON sources(notebook_id, document_id)"
            )
            await db.execute(
                "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
                (3, datetime.now().isoformat()),
            )
            await db.commit()
        if current_version < 4:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS retrieval_version_metadata (
                    document_id TEXT NOT NULL
                        REFERENCES documents(document_id) ON DELETE CASCADE,
                    version_id TEXT NOT NULL
                        REFERENCES document_versions(version_id) ON DELETE CASCADE,
                    doc_type TEXT NOT NULL,
                    publication_date TEXT,
                    PRIMARY KEY (document_id, version_id)
                );
                CREATE INDEX IF NOT EXISTS idx_retrieval_version_metadata_type
                    ON retrieval_version_metadata(doc_type);
                CREATE INDEX IF NOT EXISTS idx_retrieval_version_metadata_date
                    ON retrieval_version_metadata(publication_date);
                """
            )
            await db.execute(
                "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
                (4, datetime.now().isoformat()),
            )
            await db.commit()
        if current_version < 5:
            async with _transaction(db):
                await db.execute(
                    """CREATE TABLE IF NOT EXISTS final_qa_executions (
                        execution_id TEXT PRIMARY KEY,
                        assistant_turn_id TEXT NOT NULL UNIQUE,
                        request_fingerprint TEXT NOT NULL,
                        notebook_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        user_turn_id TEXT NOT NULL,
                        contract_version TEXT NOT NULL,
                        payload_schema_version INTEGER NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        model_configuration TEXT NOT NULL,
                        state TEXT NOT NULL,
                        retry_count INTEGER NOT NULL,
                        failure_classification TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        completed_at TEXT
                    )"""
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_final_qa_executions_state_updated "
                    "ON final_qa_executions(state, updated_at)"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_final_qa_executions_session_user "
                    "ON final_qa_executions(session_id, user_turn_id)"
                )
                await db.execute(
                    """CREATE TABLE IF NOT EXISTS final_qa_execution_snapshots (
                        execution_id TEXT NOT NULL
                            REFERENCES final_qa_executions(execution_id) ON DELETE CASCADE,
                        phase TEXT NOT NULL,
                        payload_schema_version INTEGER NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY(execution_id, phase)
                    )"""
                )
                await db.execute(
                    "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
                    (5, datetime.now(UTC).isoformat()),
                )
        if current_version < 6:
            async with _transaction(db):
                await db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunk_titles USING fts5("
                    "title, chunk_id UNINDEXED, document_id UNINDEXED, version_id UNINDEXED)"
                )
                async with db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chunks'"
                ) as cursor:
                    chunks_present = await cursor.fetchone()
                if chunks_present is not None:
                    await db.execute(
                        """
                        INSERT INTO fts_chunk_titles(title, chunk_id, document_id, version_id)
                        SELECT json_extract(v.metadata, '$.title'), c.id,
                               c.document_id, c.version_id
                        FROM chunks c JOIN document_versions v ON v.version_id = c.version_id
                        WHERE json_extract(v.metadata, '$.title') IS NOT NULL
                          AND trim(json_extract(v.metadata, '$.title')) <> ''
                        """
                    )
                await db.execute(
                    "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
                    (6, datetime.now(UTC).isoformat()),
                )

    async def close(self) -> None:
        """Close the database connection idempotently."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def health_check(self) -> tuple[HealthStatus, ...]:
        """Return health observations for the SQLite store."""
        if self._db is None:
            return (
                HealthStatus(
                    healthy=False, component="sqlite", checked_at=datetime.now(UTC), detail="closed"
                ),
            )

        try:
            async with self._db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
            return (HealthStatus(healthy=True, component="sqlite", checked_at=datetime.now(UTC)),)
        except Exception as e:
            return (
                HealthStatus(
                    healthy=False, component="sqlite", checked_at=datetime.now(UTC), detail=str(e)
                ),
            )

    def capabilities(self) -> StorageCapabilities:
        """Return immutable descriptive storage capabilities."""
        return StorageCapabilities(
            supports_blobs=False,
            supports_dense_search=False,
            supports_sparse_search=True,
            supports_metadata=True,
            supports_graph=False,
            supports_transactions=True,
            supports_health_checks=True,
        )

    # Blob operations unsupported by this backend (should be routed to FilesystemBlobStore)
    async def put_asset(self, data: bytes, mime_type: str, metadata: FrozenMetadata) -> Asset:
        raise NotImplementedError("SQLiteStore does not store assets.")

    async def get_asset(self, asset_id: UUID) -> bytes | None:
        raise NotImplementedError("SQLiteStore does not store assets.")

    async def delete_asset(self, asset_id: UUID) -> bool:
        raise NotImplementedError("SQLiteStore does not store assets.")

    async def put_parsed_document(self, version_id: UUID, document: ParsedDocument) -> None:
        raise NotImplementedError("SQLiteStore does not store parsed documents.")

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        raise NotImplementedError("SQLiteStore does not store parsed documents.")

    async def contains_hash(self, content_hash: str) -> bool:
        raise NotImplementedError("SQLiteStore does not store blob content hashes.")

    # -------------------------------------------------------------------------
    # DocumentRepository Methods
    # -------------------------------------------------------------------------

    async def upsert_document(self, document: Document) -> None:
        """Insert or replace a document registry snapshot."""
        db = self._require_open()

        async with _transaction(db):
            # Upsert document
            await db.execute(
                """
                INSERT INTO documents (document_id, current_version_id, current_hash, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    current_version_id=excluded.current_version_id,
                    current_hash=excluded.current_hash,
                    status=excluded.status,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at
                """,  # noqa: E501
                (
                    str(document.document_id),
                    str(document.current_version_id),
                    document.current_hash,
                    document.status.value,
                    _dt_to_iso(document.created_at),
                    _dt_to_iso(document.updated_at),
                ),
            )

            # Insert document versions
            for version in document.versions:
                metadata_dict = {
                    "content_hash": version.metadata.content_hash,
                    "title": version.metadata.title,
                    "authors": version.metadata.authors,
                    "publication_date": version.metadata.publication_date.isoformat()
                    if version.metadata.publication_date
                    else None,
                    "url": version.metadata.url,
                    "doi": version.metadata.doi,
                    "isbn": version.metadata.isbn,
                    "page_count": version.metadata.page_count,
                    "metadata": thaw_json(version.metadata.metadata),
                }

                await db.execute(
                    """
                    INSERT INTO document_versions (version_id, document_id, content_hash, metadata, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(version_id) DO UPDATE SET
                        content_hash=excluded.content_hash,
                        metadata=excluded.metadata,
                        status=excluded.status,
                        created_at=excluded.created_at
                    """,  # noqa: E501
                    (
                        str(version.version_id),
                        str(version.document_id),
                        version.content_hash,
                        json.dumps(metadata_dict),
                        version.status.value,
                        _dt_to_iso(version.created_at),
                    ),
                )
                await db.execute(
                    "DELETE FROM fts_chunk_titles WHERE document_id = ? AND version_id = ?",
                    (str(version.document_id), str(version.version_id)),
                )
                if version.metadata.title:
                    await db.execute(
                        """
                        INSERT INTO fts_chunk_titles(title, chunk_id, document_id, version_id)
                        SELECT ?, id, document_id, version_id FROM chunks
                        WHERE document_id = ? AND version_id = ?
                        """,
                        (version.metadata.title, str(version.document_id), str(version.version_id)),
                    )

    async def get_document(self, document_id: UUID) -> Document | None:
        """Return a document registry snapshot when present."""
        db = self._require_open()

        async with db.execute(
            "SELECT document_id, current_version_id, current_hash, status, created_at, updated_at FROM documents WHERE document_id = ?",  # noqa: E501
            (str(document_id),),
        ) as cursor:
            doc_row = await cursor.fetchone()
            if doc_row is None:
                return None

        async with db.execute(
            "SELECT version_id, document_id, content_hash, metadata, status, created_at FROM document_versions WHERE document_id = ? ORDER BY created_at ASC",  # noqa: E501
            (str(document_id),),
        ) as cursor:
            version_rows = list(await cursor.fetchall())

        versions = []
        for v_row in version_rows:
            meta_dict = json.loads(v_row[3])
            pub_date_str = meta_dict.get("publication_date")
            from datetime import date

            pub_date = date.fromisoformat(pub_date_str) if pub_date_str else None

            doc_meta = DocumentMetadata(
                content_hash=meta_dict["content_hash"],
                title=meta_dict.get("title"),
                authors=tuple(meta_dict.get("authors", ())),
                publication_date=pub_date,
                url=meta_dict.get("url"),
                doi=meta_dict.get("doi"),
                isbn=meta_dict.get("isbn"),
                page_count=meta_dict.get("page_count"),
                metadata=FrozenMetadata(meta_dict.get("metadata", {})),
            )

            version = DocumentVersion(
                version_id=UUID(v_row[0]),
                document_id=UUID(v_row[1]),
                content_hash=v_row[2],
                metadata=doc_meta,
                status=DocumentVersionStatus(v_row[4]),
                created_at=_iso_to_dt(v_row[5]),
            )
            versions.append(version)

        return Document(
            document_id=UUID(doc_row[0]),
            current_version_id=UUID(doc_row[1]),
            current_hash=doc_row[2],
            status=DocumentStatus(doc_row[3]),
            created_at=_iso_to_dt(doc_row[4]),
            updated_at=_iso_to_dt(doc_row[5]),
            versions=tuple(versions),
        )

    async def get_document_by_content_hash(self, content_hash: str) -> Document | None:
        """Return a document registry snapshot by content hash when present."""
        db = self._require_open()

        async with db.execute(
            "SELECT document_id FROM document_versions WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return await self.get_document(UUID(row[0]))

    async def list_documents(
        self,
        status: DocumentStatus | None,
        limit: int,
        cursor: str | None,
    ) -> Page[Document]:
        """Return a stable page of document registry snapshots."""
        db = self._require_open()

        query = "SELECT document_id FROM documents"
        params: list[Any] = []
        conditions: list[str] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)

        if cursor is not None:
            conditions.append("document_id > ?")
            params.append(cursor)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY document_id ASC LIMIT ?"
        params.append(limit + 1)

        async with db.execute(query, params) as db_cursor:
            rows = list(await db_cursor.fetchall())

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = []
        for row in page_rows:
            doc = await self.get_document(UUID(row[0]))
            if doc is not None:
                items.append(doc)

        next_cursor = str(page_rows[-1][0]) if has_next and page_rows else None
        return Page(items=tuple(items), next_cursor=next_cursor)

    async def delete_document(
        self,
        document_id: UUID,
        expected_version_id: UUID | None,
    ) -> bool:
        """Delete one registry record with an optional version precondition."""
        db = self._require_open()

        async with _transaction(db):
            if expected_version_id is not None:
                async with db.execute(
                    "SELECT current_version_id FROM documents WHERE document_id = ?",
                    (str(document_id),),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row is None:
                        return False
                    if row[0] != str(expected_version_id):
                        raise ConflictError("Document version mismatch during deletion.")

            # The title index is a contentless FTS5 projection and therefore
            # cannot participate in SQLite foreign-key cascades. Remove its
            # exact document rows in the same transaction as canonical data.
            await db.execute(
                "DELETE FROM fts_chunk_titles WHERE document_id = ?",
                (str(document_id),),
            )

            async with db.execute(
                "DELETE FROM documents WHERE document_id = ?", (str(document_id),)
            ) as cursor:
                return cursor.rowcount > 0

    async def delete_document_cascade(self, document_id: UUID) -> None:
        """Atomically delete a document and all facade-owned derived records."""
        # Canonical dependents use ON DELETE CASCADE; delete_document also
        # removes the contentless title projection transactionally.
        await self.delete_document(document_id, expected_version_id=None)

    # -------------------------------------------------------------------------
    # NotebookRepository Methods
    # -------------------------------------------------------------------------

    async def upsert_notebook(self, notebook: Notebook) -> None:
        """Insert or replace a notebook snapshot."""
        db = self._require_open()

        async with db.execute(
            """
            INSERT INTO notebooks (notebook_id, title, description, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(notebook_id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                metadata=excluded.metadata
            """,  # noqa: E501
            (
                str(notebook.notebook_id),
                notebook.title,
                notebook.description,
                _dt_to_iso(notebook.created_at),
                _dt_to_iso(notebook.updated_at),
                json.dumps(thaw_json(notebook.metadata)),
            ),
        ):
            await db.commit()

    async def get_notebook(self, notebook_id: UUID) -> Notebook | None:
        """Return a notebook when present."""
        db = self._require_open()

        async with db.execute(
            "SELECT notebook_id, title, description, created_at, updated_at, metadata FROM notebooks WHERE notebook_id = ?",  # noqa: E501
            (str(notebook_id),),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None

            return Notebook(
                notebook_id=UUID(row[0]),
                title=row[1],
                description=row[2],
                created_at=_iso_to_dt(row[3]),
                updated_at=_iso_to_dt(row[4]),
                metadata=FrozenMetadata(json.loads(row[5])),
            )

    async def delete_notebook(self, notebook_id: UUID) -> bool:
        """Delete a notebook and report whether it existed."""
        db = self._require_open()

        async with db.execute(
            "DELETE FROM notebooks WHERE notebook_id = ?", (str(notebook_id),)
        ) as cursor:
            await db.commit()
            return cursor.rowcount > 0

    async def list_notebooks(self, limit: int, cursor: str | None) -> Page[Notebook]:
        """Return a stable page of notebooks."""
        db = self._require_open()

        query = "SELECT notebook_id, title, description, created_at, updated_at, metadata FROM notebooks"  # noqa: E501
        params: list[Any] = []

        if cursor is not None:
            query += " WHERE notebook_id > ?"
            params.append(cursor)

        query += " ORDER BY notebook_id ASC LIMIT ?"
        params.append(limit + 1)

        async with db.execute(query, params) as db_cursor:
            rows = list(await db_cursor.fetchall())

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = [
            Notebook(
                notebook_id=UUID(row[0]),
                title=row[1],
                description=row[2],
                created_at=_iso_to_dt(row[3]),
                updated_at=_iso_to_dt(row[4]),
                metadata=FrozenMetadata(json.loads(row[5])),
            )
            for row in page_rows
        ]
        next_cursor = str(page_rows[-1][0]) if has_next and page_rows else None
        return Page(items=tuple(items), next_cursor=next_cursor)

    async def upsert_source(self, source: Source) -> None:
        """Insert or replace a source association."""
        db = self._require_open()

        try:
            async with db.execute(
                """
                INSERT INTO sources (source_id, notebook_id, document_id, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    notebook_id=excluded.notebook_id,
                    document_id=excluded.document_id,
                    created_at=excluded.created_at
                """,
                (
                    str(source.source_id),
                    str(source.notebook_id),
                    str(source.document_id),
                    _dt_to_iso(source.created_at),
                ),
            ):
                await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise ConflictError(
                "a notebook cannot contain duplicate Source associations for one document"
            ) from exc

    async def get_source(self, source_id: UUID) -> Source | None:
        """Return a source association when present."""
        db = self._require_open()

        async with db.execute(
            "SELECT source_id, notebook_id, document_id, created_at FROM sources WHERE source_id = ?",  # noqa: E501
            (str(source_id),),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None

            return Source(
                source_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                document_id=UUID(row[2]),
                created_at=_iso_to_dt(row[3]),
            )

    async def _list_sources_for_document(self, document_id: UUID) -> tuple[Source, ...]:
        """Return all canonical notebook associations for one logical document."""
        db = self._require_open()
        async with db.execute(
            """
            SELECT source_id, notebook_id, document_id, created_at
            FROM sources
            WHERE document_id = ?
            ORDER BY source_id ASC
            """,
            (str(document_id),),
        ) as cursor:
            rows = await cursor.fetchall()
        return tuple(
            Source(
                source_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                document_id=UUID(row[2]),
                created_at=_iso_to_dt(row[3]),
            )
            for row in rows
        )

    async def _list_sources_for_notebook(self, notebook_id: UUID) -> tuple[Source, ...]:
        """Return all canonical source associations owned by one notebook."""
        db = self._require_open()
        async with db.execute(
            """
            SELECT source_id, notebook_id, document_id, created_at
            FROM sources
            WHERE notebook_id = ?
            ORDER BY source_id ASC
            """,
            (str(notebook_id),),
        ) as cursor:
            rows = await cursor.fetchall()
        return tuple(
            Source(
                source_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                document_id=UUID(row[2]),
                created_at=_iso_to_dt(row[3]),
            )
            for row in rows
        )

    async def delete_source(self, source_id: UUID) -> bool:
        """Delete a source association and report whether it existed."""
        db = self._require_open()

        async with db.execute(
            "DELETE FROM sources WHERE source_id = ?", (str(source_id),)
        ) as cursor:
            await db.commit()
            return cursor.rowcount > 0

    async def list_sources(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Source]:
        """Return a stable page of notebook sources."""
        db = self._require_open()

        query = "SELECT source_id, notebook_id, document_id, created_at FROM sources WHERE notebook_id = ?"  # noqa: E501
        params: list[Any] = [str(notebook_id)]

        if cursor is not None:
            query += " AND source_id > ?"
            params.append(cursor)

        query += " ORDER BY source_id ASC LIMIT ?"
        params.append(limit + 1)

        async with db.execute(query, params) as db_cursor:
            rows = list(await db_cursor.fetchall())

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = [
            Source(
                source_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                document_id=UUID(row[2]),
                created_at=_iso_to_dt(row[3]),
            )
            for row in page_rows
        ]
        next_cursor = str(page_rows[-1][0]) if has_next and page_rows else None
        return Page(items=tuple(items), next_cursor=next_cursor)

    async def upsert_note(self, note: Note) -> None:
        """Insert or replace a note snapshot."""
        db = self._require_open()

        async with db.execute(
            """
            INSERT INTO notes (note_id, notebook_id, title, content, origin, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(note_id) DO UPDATE SET
                notebook_id=excluded.notebook_id,
                title=excluded.title,
                content=excluded.content,
                origin=excluded.origin,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                metadata=excluded.metadata
            """,  # noqa: E501
            (
                str(note.note_id),
                str(note.notebook_id),
                note.title,
                note.content,
                note.origin.value,
                _dt_to_iso(note.created_at),
                _dt_to_iso(note.updated_at),
                json.dumps(thaw_json(note.metadata)),
            ),
        ):
            await db.commit()

    async def get_note(self, note_id: UUID) -> Note | None:
        """Return a note when present."""
        db = self._require_open()

        async with db.execute(
            "SELECT note_id, notebook_id, title, content, origin, created_at, updated_at, metadata FROM notes WHERE note_id = ?",  # noqa: E501
            (str(note_id),),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None

            return Note(
                note_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                title=row[2],
                content=row[3],
                origin=NoteOrigin(row[4]),
                created_at=_iso_to_dt(row[5]),
                updated_at=_iso_to_dt(row[6]),
                metadata=FrozenMetadata(json.loads(row[7])),
            )

    async def delete_note(self, note_id: UUID) -> bool:
        """Delete a note and report whether it existed."""
        db = self._require_open()

        async with db.execute("DELETE FROM notes WHERE note_id = ?", (str(note_id),)) as cursor:
            await db.commit()
            return cursor.rowcount > 0

    async def list_notes(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Note]:
        """Return a stable page of notebook notes."""
        db = self._require_open()

        query = "SELECT note_id, notebook_id, title, content, origin, created_at, updated_at, metadata FROM notes WHERE notebook_id = ?"  # noqa: E501
        params: list[Any] = [str(notebook_id)]

        if cursor is not None:
            query += " AND note_id > ?"
            params.append(cursor)

        query += " ORDER BY note_id ASC LIMIT ?"
        params.append(limit + 1)

        async with db.execute(query, params) as db_cursor:
            rows = list(await db_cursor.fetchall())

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = [
            Note(
                note_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                title=row[2],
                content=row[3],
                origin=NoteOrigin(row[4]),
                created_at=_iso_to_dt(row[5]),
                updated_at=_iso_to_dt(row[6]),
                metadata=FrozenMetadata(json.loads(row[7])),
            )
            for row in page_rows
        ]
        next_cursor = str(page_rows[-1][0]) if has_next and page_rows else None
        return Page(items=tuple(items), next_cursor=next_cursor)

    async def upsert_insight(self, insight: Insight) -> None:
        """Insert or replace an insight snapshot."""
        db = self._require_open()

        async with db.execute(
            """
            INSERT INTO insights (insight_id, notebook_id, source_id, type, content, confidence, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(insight_id) DO UPDATE SET
                notebook_id=excluded.notebook_id,
                source_id=excluded.source_id,
                type=excluded.type,
                content=excluded.content,
                confidence=excluded.confidence,
                created_at=excluded.created_at,
                metadata=excluded.metadata
            """,  # noqa: E501
            (
                str(insight.insight_id),
                str(insight.notebook_id),
                str(insight.source_id),
                insight.type.value,
                insight.content,
                insight.confidence,
                _dt_to_iso(insight.created_at),
                json.dumps(thaw_json(insight.metadata)),
            ),
        ):
            await db.commit()

    async def get_insight(self, insight_id: UUID) -> Insight | None:
        """Return an insight when present."""
        db = self._require_open()

        async with db.execute(
            "SELECT insight_id, notebook_id, source_id, type, content, confidence, created_at, metadata FROM insights WHERE insight_id = ?",  # noqa: E501
            (str(insight_id),),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None

            return Insight(
                insight_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                source_id=UUID(row[2]),
                type=InsightType(row[3]),
                content=row[4],
                confidence=row[5],
                created_at=_iso_to_dt(row[6]),
                metadata=FrozenMetadata(json.loads(row[7])),
            )

    async def delete_insight(self, insight_id: UUID) -> bool:
        """Delete an insight and report whether it existed."""
        db = self._require_open()

        async with db.execute(
            "DELETE FROM insights WHERE insight_id = ?", (str(insight_id),)
        ) as cursor:
            await db.commit()
            return cursor.rowcount > 0

    async def list_insights(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Insight]:
        """Return a stable page of notebook insights."""
        db = self._require_open()

        query = "SELECT insight_id, notebook_id, source_id, type, content, confidence, created_at, metadata FROM insights WHERE notebook_id = ?"  # noqa: E501
        params: list[Any] = [str(notebook_id)]

        if cursor is not None:
            query += " AND insight_id > ?"
            params.append(cursor)

        query += " ORDER BY insight_id ASC LIMIT ?"
        params.append(limit + 1)

        async with db.execute(query, params) as db_cursor:
            rows = list(await db_cursor.fetchall())

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = [
            Insight(
                insight_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                source_id=UUID(row[2]),
                type=InsightType(row[3]),
                content=row[4],
                confidence=row[5],
                created_at=_iso_to_dt(row[6]),
                metadata=FrozenMetadata(json.loads(row[7])),
            )
            for row in page_rows
        ]
        next_cursor = str(page_rows[-1][0]) if has_next and page_rows else None
        return Page(items=tuple(items), next_cursor=next_cursor)

    # -------------------------------------------------------------------------
    # SessionRepository Methods
    # -------------------------------------------------------------------------

    async def upsert_session(self, session: Session) -> None:
        """Insert or replace a conversational session."""
        db = self._require_open()

        async with _transaction(db):
            await db.execute(
                """
                INSERT INTO sessions (session_id, notebook_id, title, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    notebook_id=excluded.notebook_id,
                    title=excluded.title,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    metadata=excluded.metadata
                """,  # noqa: E501
                (
                    str(session.session_id),
                    str(session.notebook_id),
                    session.title,
                    _dt_to_iso(session.created_at),
                    _dt_to_iso(session.updated_at),
                    json.dumps(thaw_json(session.metadata)),
                ),
            )

            # Insert turns
            for turn in session.turns:
                await db.execute(
                    """
                    INSERT INTO turns (turn_id, session_id, sequence, role, content, created_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(turn_id) DO UPDATE SET
                        sequence=excluded.sequence,
                        role=excluded.role,
                        content=excluded.content,
                        created_at=excluded.created_at,
                        metadata=excluded.metadata
                    """,  # noqa: E501
                    (
                        str(turn.turn_id),
                        str(turn.session_id),
                        turn.sequence,
                        turn.role.value,
                        turn.content,
                        _dt_to_iso(turn.created_at),
                        json.dumps(thaw_json(turn.metadata)),
                    ),
                )

    async def get_session(self, session_id: UUID) -> Session | None:
        """Return a session with its turns when present."""
        db = self._require_open()

        async with db.execute(
            "SELECT session_id, notebook_id, title, created_at, updated_at, metadata FROM sessions WHERE session_id = ?",  # noqa: E501
            (str(session_id),),
        ) as cursor:
            session_row = await cursor.fetchone()
            if session_row is None:
                return None

        async with db.execute(
            "SELECT turn_id, session_id, sequence, role, content, created_at, metadata FROM turns WHERE session_id = ? ORDER BY sequence ASC",  # noqa: E501
            (str(session_id),),
        ) as cursor:
            turn_rows = list(await cursor.fetchall())

        turns = [
            Turn(
                turn_id=UUID(row[0]),
                session_id=UUID(row[1]),
                sequence=row[2],
                role=TurnRole(row[3]),
                content=row[4],
                created_at=_iso_to_dt(row[5]),
                metadata=FrozenMetadata(json.loads(row[6])),
            )
            for row in turn_rows
        ]

        return Session(
            session_id=UUID(session_row[0]),
            notebook_id=UUID(session_row[1]),
            title=session_row[2],
            created_at=_iso_to_dt(session_row[3]),
            updated_at=_iso_to_dt(session_row[4]),
            metadata=FrozenMetadata(json.loads(session_row[5])),
            turns=tuple(turns),
        )

    async def list_sessions(
        self,
        notebook_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> Page[Session]:
        """Return a stable page of notebook sessions without turns."""
        db = self._require_open()

        query = "SELECT session_id, notebook_id, title, created_at, updated_at, metadata FROM sessions WHERE notebook_id = ?"  # noqa: E501
        params: list[Any] = [str(notebook_id)]

        if cursor is not None:
            query += " AND session_id > ?"
            params.append(cursor)

        query += " ORDER BY session_id ASC LIMIT ?"
        params.append(limit + 1)

        async with db.execute(query, params) as db_cursor:
            rows = list(await db_cursor.fetchall())

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = [
            Session(
                session_id=UUID(row[0]),
                notebook_id=UUID(row[1]),
                title=row[2],
                created_at=_iso_to_dt(row[3]),
                updated_at=_iso_to_dt(row[4]),
                metadata=FrozenMetadata(json.loads(row[5])),
                turns=(),  # Contract says returns without turns
            )
            for row in page_rows
        ]
        next_cursor = str(page_rows[-1][0]) if has_next and page_rows else None
        return Page(items=tuple(items), next_cursor=next_cursor)

    async def delete_session(self, session_id: UUID) -> bool:
        """Delete a session, including all its turns and citations."""
        db = self._require_open()

        async with db.execute(
            "DELETE FROM sessions WHERE session_id = ?", (str(session_id),)
        ) as cursor:
            await db.commit()
            return cursor.rowcount > 0

    async def upsert_citation(self, citation: Citation) -> None:
        """Insert or replace a citation tied to a turn."""
        db = self._require_open()

        async with db.execute(
            """
            INSERT INTO citations (
                citation_id, turn_id, source_number, chunk_id, document_id, version_id,
                document_title, verbatim_quote, page_number, heading_path, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(citation_id) DO UPDATE SET
                turn_id=excluded.turn_id,
                source_number=excluded.source_number,
                chunk_id=excluded.chunk_id,
                document_id=excluded.document_id,
                version_id=excluded.version_id,
                document_title=excluded.document_title,
                verbatim_quote=excluded.verbatim_quote,
                page_number=excluded.page_number,
                heading_path=excluded.heading_path,
                created_at=excluded.created_at
            """,
            (
                str(citation.citation_id),
                str(citation.turn_id),
                citation.source_number,
                citation.chunk_id,
                str(citation.document_id),
                str(citation.version_id),
                citation.document_title,
                citation.verbatim_quote,
                citation.page_number,
                json.dumps(list(citation.heading_path)),
                _dt_to_iso(citation.created_at),
            ),
        ):
            await db.commit()

    async def get_citation(self, citation_id: UUID) -> Citation | None:
        """Return a citation when present."""
        db = self._require_open()

        async with db.execute(
            """
            SELECT citation_id, turn_id, source_number, chunk_id, document_id, version_id,
                   document_title, verbatim_quote, page_number, heading_path, created_at
            FROM citations WHERE citation_id = ?
            """,
            (str(citation_id),),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None

            return Citation(
                citation_id=UUID(row[0]),
                turn_id=UUID(row[1]),
                source_number=row[2],
                chunk_id=row[3],
                document_id=UUID(row[4]),
                version_id=UUID(row[5]),
                document_title=row[6],
                verbatim_quote=row[7],
                page_number=row[8],
                heading_path=tuple(json.loads(row[9])),
                created_at=_iso_to_dt(row[10]),
            )

    async def list_citations(self, turn_id: UUID) -> tuple[Citation, ...]:
        """Return all citations for a specific turn, sorted by source number."""
        db = self._require_open()

        async with db.execute(
            """
            SELECT citation_id, turn_id, source_number, chunk_id, document_id, version_id,
                   document_title, verbatim_quote, page_number, heading_path, created_at
            FROM citations WHERE turn_id = ? ORDER BY source_number ASC
            """,
            (str(turn_id),),
        ) as cursor:
            rows = list(await cursor.fetchall())

        return tuple(
            Citation(
                citation_id=UUID(row[0]),
                turn_id=UUID(row[1]),
                source_number=row[2],
                chunk_id=row[3],
                document_id=UUID(row[4]),
                version_id=UUID(row[5]),
                document_title=row[6],
                verbatim_quote=row[7],
                page_number=row[8],
                heading_path=tuple(json.loads(row[9])),
                created_at=_iso_to_dt(row[10]),
            )
            for row in rows
        )

    # -------------------------------------------------------------------------
    # Conversation Methods (Missing from earlier)
    # -------------------------------------------------------------------------

    async def append_turn(self, session_id: UUID, turn: Turn) -> None:
        """Append one turn idempotently to a session."""
        db = self._require_open()

        await db.execute(
            """
            INSERT INTO turns (turn_id, session_id, sequence, role, content, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(turn_id) DO UPDATE SET
                sequence=excluded.sequence,
                role=excluded.role,
                content=excluded.content,
                created_at=excluded.created_at,
                metadata=excluded.metadata
            """,
            (
                str(turn.turn_id),
                str(turn.session_id),
                turn.sequence,
                turn.role.value,
                turn.content,
                _dt_to_iso(turn.created_at),
                json.dumps(thaw_json(turn.metadata)),
            ),
        )
        await db.commit()

    # -------------------------------------------------------------------------
    # ADR-0056 Final-QA immutable execution snapshots
    # -------------------------------------------------------------------------

    async def create_final_qa_execution(self, execution: FinalQAExecution) -> bool:
        """Atomically claim the caller-owned assistant publication slot."""
        db = self._require_open()
        try:
            async with _transaction(db):
                cursor = await db.execute(
                    """
                    INSERT INTO final_qa_executions (
                        execution_id, assistant_turn_id, request_fingerprint,
                        notebook_id, session_id, user_turn_id, contract_version,
                        payload_schema_version, provider, model, model_configuration,
                        state, retry_count, failure_classification, created_at,
                        updated_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(assistant_turn_id) DO NOTHING
                    """,
                    (
                        str(execution.execution_id),
                        str(execution.assistant_turn_id),
                        execution.request_fingerprint,
                        str(execution.notebook_id),
                        str(execution.session_id),
                        str(execution.user_turn_id),
                        execution.contract_version,
                        execution.payload_schema_version,
                        execution.provider,
                        execution.model,
                        execution.model_configuration,
                        execution.state.value,
                        execution.retry_count,
                        execution.failure_classification,
                        _dt_to_iso(execution.created_at),
                        _dt_to_iso(execution.updated_at),
                        None
                        if execution.completed_at is None
                        else _dt_to_iso(execution.completed_at),
                    ),
                )
                return cursor.rowcount == 1
        except aiosqlite.Error as error:
            raise StorageError("could not create final-QA execution") from error

    async def get_final_qa_execution(self, assistant_turn_id: UUID) -> FinalQAExecution | None:
        db = self._require_open()
        async with db.execute(
            """
            SELECT execution_id, assistant_turn_id, request_fingerprint, notebook_id,
                   session_id, user_turn_id, contract_version, payload_schema_version,
                   provider, model, model_configuration, state, retry_count,
                   failure_classification, created_at, updated_at, completed_at
            FROM final_qa_executions WHERE assistant_turn_id = ?
            """,
            (str(assistant_turn_id),),
        ) as cursor:
            row = await cursor.fetchone()
        return None if row is None else _final_qa_execution_from_row(row)

    async def put_final_qa_execution_snapshot(self, snapshot: FinalQAExecutionSnapshot) -> None:
        """Store an immutable phase snapshot; conflicting rewrites are rejected."""
        db = self._require_open()
        try:
            async with _transaction(db):
                await db.execute(
                    """
                    INSERT INTO final_qa_execution_snapshots (
                        execution_id, phase, payload_schema_version, payload, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(snapshot.execution_id),
                        snapshot.phase.value,
                        snapshot.payload_schema_version,
                        snapshot.payload,
                        _dt_to_iso(snapshot.created_at),
                    ),
                )
        except aiosqlite.IntegrityError as error:
            raise ConflictError("final-QA execution snapshot is immutable") from error
        except aiosqlite.Error as error:
            raise StorageError("could not persist final-QA execution snapshot") from error

    async def get_final_qa_execution_snapshot(
        self, execution_id: UUID, phase: FinalQAExecutionSnapshotPhase
    ) -> FinalQAExecutionSnapshot | None:
        db = self._require_open()
        async with db.execute(
            """
            SELECT execution_id, phase, payload_schema_version, payload, created_at
            FROM final_qa_execution_snapshots WHERE execution_id = ? AND phase = ?
            """,
            (str(execution_id), phase.value),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return FinalQAExecutionSnapshot(
            execution_id=UUID(row[0]),
            phase=FinalQAExecutionSnapshotPhase(row[1]),
            payload_schema_version=int(row[2]),
            payload=row[3],
            created_at=_iso_to_dt(row[4]),
        )

    async def transition_final_qa_execution(
        self,
        execution_id: UUID,
        expected: FinalQAExecutionState,
        target: FinalQAExecutionState,
        *,
        retry_count: int | None = None,
        failure_classification: str | None = None,
    ) -> bool:
        """Compare-and-swap an execution state without mutating snapshots."""
        db = self._require_open()
        now = datetime.now(UTC)
        completed_at = (
            _dt_to_iso(now)
            if target
            in {
                FinalQAExecutionState.PUBLISHED,
                FinalQAExecutionState.REJECTED_CITATION_COMPLIANCE,
            }
            else None
        )
        try:
            async with _transaction(db):
                cursor = await db.execute(
                    """
                    UPDATE final_qa_executions
                    SET state = ?, retry_count = COALESCE(?, retry_count),
                        failure_classification = COALESCE(?, failure_classification),
                        updated_at = ?, completed_at = COALESCE(?, completed_at)
                    WHERE execution_id = ? AND state = ?
                    """,
                    (
                        target.value,
                        retry_count,
                        failure_classification,
                        _dt_to_iso(now),
                        completed_at,
                        str(execution_id),
                        expected.value,
                    ),
                )
                return cursor.rowcount == 1
        except aiosqlite.Error as error:
            raise StorageError("could not transition final-QA execution") from error

    async def list_turns(
        self,
        session_id: UUID,
        after_turn_id: UUID | None,
        limit: int,
    ) -> Page[Turn]:
        """Return an ordered page of conversation turns."""
        db = self._require_open()

        # In a real implementation we would look up the sequence of after_turn_id,
        # but for simplicity assuming sequence ordering.
        query = "SELECT turn_id, session_id, sequence, role, content, created_at, metadata FROM turns WHERE session_id = ?"  # noqa: E501
        params: list[Any] = [str(session_id)]

        if after_turn_id is not None:
            query += " AND sequence > (SELECT sequence FROM turns WHERE turn_id = ?)"
            params.append(str(after_turn_id))

        query += " ORDER BY sequence ASC LIMIT ?"
        params.append(limit + 1)

        async with db.execute(query, params) as cursor:
            rows = list(await cursor.fetchall())

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = [
            Turn(
                turn_id=UUID(row[0]),
                session_id=UUID(row[1]),
                sequence=row[2],
                role=TurnRole(row[3]),
                content=row[4],
                created_at=_iso_to_dt(row[5]),
                metadata=FrozenMetadata(json.loads(row[6])),
            )
            for row in page_rows
        ]
        next_cursor = str(page_rows[-1][0]) if has_next and page_rows else None
        return Page(items=tuple(items), next_cursor=next_cursor)

    async def get_citations_for_turn(self, turn_id: UUID) -> tuple[Citation, ...]:
        """Return the citations attached to a turn."""
        return await self.list_citations(turn_id)

    # -------------------------------------------------------------------------
    # ChunkRepository Methods
    # -------------------------------------------------------------------------

    async def upsert_chunks(self, chunks: tuple[Chunk, ...]) -> None:
        """Atomically persist chunks to every configured index."""
        db = self._require_open()

        async with _transaction(db):
            await self._upsert_chunk_rows(db, chunks)
            await self._upsert_title_projection(db, chunks)

    async def _upsert_chunks_with_projection(
        self,
        chunks: tuple[Chunk, ...],
        projection: RetrievalMetadataProjection,
    ) -> None:
        """Atomically persist chunks and their exact-version derived metadata."""
        if not chunks:
            return
        document_id = chunks[0].document_id
        version_id = chunks[0].version_id
        if any(
            chunk.document_id != document_id or chunk.version_id != version_id for chunk in chunks
        ):
            raise ValueError("projected chunk batches must share one document version")
        db = self._require_open()
        async with _transaction(db):
            await db.execute(
                """
                INSERT INTO retrieval_version_metadata (
                    document_id, version_id, doc_type, publication_date
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id, version_id) DO UPDATE SET
                    doc_type=excluded.doc_type,
                    publication_date=excluded.publication_date
                """,
                (
                    str(document_id),
                    str(version_id),
                    projection.doc_type.value,
                    projection.publication_date.isoformat()
                    if projection.publication_date is not None
                    else None,
                ),
            )
            await self._upsert_chunk_rows(db, chunks)
            await self._upsert_title_projection(db, chunks, projection.title)

    async def _upsert_title_projection(
        self, db: aiosqlite.Connection, chunks: tuple[Chunk, ...], title: str | None = None
    ) -> None:
        """Refresh derived title rows for an exact canonical document version."""
        if not chunks:
            return
        document_id, version_id = chunks[0].document_id, chunks[0].version_id
        if title is None:
            async with db.execute(
                "SELECT metadata FROM document_versions WHERE version_id = ?", (str(version_id),)
            ) as cursor:
                row = await cursor.fetchone()
            title = None if row is None else json.loads(row[0]).get("title")
        await db.execute(
            "DELETE FROM fts_chunk_titles WHERE document_id = ? AND version_id = ?",
            (str(document_id), str(version_id)),
        )
        if isinstance(title, str) and title.strip():
            await db.executemany(
                "INSERT INTO fts_chunk_titles(title, chunk_id, document_id, version_id) "
                "VALUES (?, ?, ?, ?)",
                [(title, chunk.id, str(document_id), str(version_id)) for chunk in chunks],
            )

    async def _snapshot_retrieval_projection(
        self, document_id: UUID, version_id: UUID
    ) -> tuple[str, str | None] | None:
        """Capture derived version metadata for compensating a failed index write."""
        db = self._require_open()
        async with db.execute(
            """
            SELECT doc_type, publication_date
            FROM retrieval_version_metadata
            WHERE document_id = ? AND version_id = ?
            """,
            (str(document_id), str(version_id)),
        ) as cursor:
            row = await cursor.fetchone()
        return None if row is None else (str(row[0]), row[1])

    async def _restore_retrieval_projection(
        self,
        document_id: UUID,
        version_id: UUID,
        snapshot: tuple[str, str | None] | None,
    ) -> None:
        """Restore or remove one derived projection during compensation."""
        db = self._require_open()
        async with _transaction(db):
            if snapshot is None:
                await db.execute(
                    "DELETE FROM retrieval_version_metadata "
                    "WHERE document_id = ? AND version_id = ?",
                    (str(document_id), str(version_id)),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO retrieval_version_metadata (
                        document_id, version_id, doc_type, publication_date
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(document_id, version_id) DO UPDATE SET
                        doc_type=excluded.doc_type,
                        publication_date=excluded.publication_date
                    """,
                    (str(document_id), str(version_id), snapshot[0], snapshot[1]),
                )

    async def _snapshot_chunks(self, chunk_ids: tuple[str, ...]) -> tuple[Chunk, ...]:
        """Capture the current SQLite values for affected chunk identities."""
        if not chunk_ids:
            return ()
        db = self._require_open()
        placeholders = ",".join("?" for _ in chunk_ids)
        async with db.execute(
            f"""
            SELECT id, document_id, version_id, text, chunk_type,
                   position_section_index, position_chunk_index, position_page_number,
                   position_start_offset, position_end_offset,
                   source_start_ordinal, source_end_ordinal,
                   heading_path, parent_chunk_id, sibling_ids, metadata
            FROM chunks WHERE id IN ({placeholders})
            """,
            chunk_ids,
        ) as cursor:
            rows = await cursor.fetchall()
        by_id = {str(row[0]): self._chunk_from_row(row) for row in rows}
        return tuple(by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id)

    async def _restore_chunk_snapshot(
        self,
        attempted_ids: tuple[str, ...],
        previous_chunks: tuple[Chunk, ...],
    ) -> None:
        """Restore affected rows and remove only identities introduced by an attempt."""
        if not attempted_ids:
            return
        db = self._require_open()
        previous_ids = frozenset(chunk.id for chunk in previous_chunks)
        new_ids = tuple(chunk_id for chunk_id in attempted_ids if chunk_id not in previous_ids)
        async with _transaction(db):
            # Restore old relationships before removing newly introduced parents.
            await self._upsert_chunk_rows(db, previous_chunks)
            if new_ids:
                placeholders = ",".join("?" for _ in new_ids)
                await db.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", new_ids)

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Return one chunk by its stable SHA-256 identity."""
        db = self._require_open()

        async with db.execute(
            """
            SELECT id, document_id, version_id, text, chunk_type,
                   position_section_index, position_chunk_index, position_page_number,
                   position_start_offset, position_end_offset,
                   source_start_ordinal, source_end_ordinal,
                   heading_path, parent_chunk_id, sibling_ids, metadata
            FROM chunks WHERE id = ?
            """,
            (chunk_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None

            return self._chunk_from_row(row)

    async def _upsert_chunk_rows(
        self,
        db: aiosqlite.Connection,
        chunks: tuple[Chunk, ...],
    ) -> None:
        for chunk in chunks:
            await db.execute(
                """
                INSERT INTO chunks (
                    id, document_id, version_id, text, chunk_type,
                    position_section_index, position_chunk_index, position_page_number,
                    position_start_offset, position_end_offset,
                    source_start_ordinal, source_end_ordinal,
                    heading_path, parent_chunk_id, sibling_ids, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    document_id=excluded.document_id,
                    version_id=excluded.version_id,
                    text=excluded.text,
                    chunk_type=excluded.chunk_type,
                    position_section_index=excluded.position_section_index,
                    position_chunk_index=excluded.position_chunk_index,
                    position_page_number=excluded.position_page_number,
                    position_start_offset=excluded.position_start_offset,
                    position_end_offset=excluded.position_end_offset,
                    source_start_ordinal=excluded.source_start_ordinal,
                    source_end_ordinal=excluded.source_end_ordinal,
                    heading_path=excluded.heading_path,
                    parent_chunk_id=excluded.parent_chunk_id,
                    sibling_ids=excluded.sibling_ids,
                    metadata=excluded.metadata
                """,
                (
                    chunk.id,
                    str(chunk.document_id),
                    str(chunk.version_id),
                    chunk.text,
                    chunk.chunk_type.value,
                    chunk.position.section_index,
                    chunk.position.chunk_index_in_section,
                    chunk.position.page_number,
                    chunk.position.start_offset,
                    chunk.position.end_offset,
                    chunk.source_span.start_ordinal,
                    chunk.source_span.end_ordinal,
                    json.dumps(list(chunk.heading_path)),
                    chunk.parent_chunk_id,
                    json.dumps(list(chunk.sibling_ids)),
                    json.dumps(thaw_json(chunk.metadata)),
                ),
            )

    @staticmethod
    def _chunk_from_row(row: Sequence[Any]) -> Chunk:
        return Chunk(
            id=row[0],
            document_id=UUID(row[1]),
            version_id=UUID(row[2]),
            text=row[3],
            chunk_type=ChunkType(row[4]),
            position=ChunkPosition(
                section_index=row[5],
                chunk_index_in_section=row[6],
                page_number=row[7],
                start_offset=row[8],
                end_offset=row[9],
            ),
            source_span=BlockSpan(start_ordinal=row[10], end_ordinal=row[11]),
            heading_path=tuple(json.loads(row[12])),
            parent_chunk_id=row[13],
            sibling_ids=tuple(json.loads(row[14])),
            metadata=FrozenMetadata(json.loads(row[15])),
        )

    async def delete_chunks_for_document(
        self,
        document_id: UUID,
        version_id: UUID | None,
    ) -> None:
        """Delete all matching chunks from every configured index."""
        db = self._require_open()

        query = "DELETE FROM chunks WHERE document_id = ?"
        title_query = "DELETE FROM fts_chunk_titles WHERE document_id = ?"
        params: list[Any] = [str(document_id)]

        if version_id is not None:
            query += " AND version_id = ?"
            title_query += " AND version_id = ?"
            params.append(str(version_id))

        async with _transaction(db):
            await db.execute(title_query, params)
            await db.execute(query, params)

    # -------------------------------------------------------------------------
    # Retrieval Methods
    # -------------------------------------------------------------------------

    async def search_sparse(
        self,
        query: str,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Run bounded sparse retrieval utilizing FTS5 BM25."""
        db = self._require_open()

        if not isinstance(query, str):
            raise TypeError("query must be a string")
        terms = _fts_terms(query)
        if not terms:
            raise ValueError("query must contain searchable text")
        if not isinstance(filters, MetadataFilter):
            raise TypeError("filters must be MetadataFilter")
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        # Quoted OR terms prevent user text from becoming FTS syntax while allowing
        # natural-language questions to retrieve rows without requiring an exact phrase.
        fts_query = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)

        sql = """
        WITH sparse_candidates AS (
            SELECT c.id AS chunk_id, -bm25(fts_chunks) AS score, 0 AS title_match
            FROM fts_chunks JOIN chunks c ON fts_chunks.rowid = c.rowid
            WHERE fts_chunks MATCH ?
            UNION ALL
            SELECT t.chunk_id AS chunk_id, -bm25(fts_chunk_titles, 3.0) AS score, 1 AS title_match
            FROM fts_chunk_titles t
            WHERE fts_chunk_titles MATCH ?
        )
        , ranked_candidates AS (
        SELECT c.id AS chunk_id, MAX(sparse_candidates.score) AS score,
               MAX(sparse_candidates.title_match) AS title_match,
               json_extract(dv.metadata, '$.title') AS document_title
        FROM sparse_candidates
        JOIN chunks c ON c.id = sparse_candidates.chunk_id
        JOIN document_versions dv
          ON dv.document_id = c.document_id AND dv.version_id = c.version_id
        LEFT JOIN retrieval_version_metadata rvm
          ON rvm.document_id = c.document_id AND rvm.version_id = c.version_id
        WHERE 1 = 1
        """
        params: list[Any] = [fts_query, fts_query]

        if filters.notebook_id is not None or filters.source_ids:
            sql += " AND EXISTS (SELECT 1 FROM sources s WHERE s.document_id = c.document_id"
            if filters.notebook_id is not None:
                sql += " AND s.notebook_id = ?"
                params.append(str(filters.notebook_id))
            if filters.source_ids:
                source_placeholders = ",".join(["?"] * len(filters.source_ids))
                sql += f" AND s.source_id IN ({source_placeholders})"
                params.extend([str(source_id) for source_id in filters.source_ids])
            sql += ")"

        if filters.doc_types:
            type_placeholders = ",".join(["?"] * len(filters.doc_types))
            sql += f" AND rvm.doc_type IN ({type_placeholders})"
            params.extend([t.value for t in filters.doc_types])

        if filters.date_after is not None:
            sql += " AND rvm.publication_date IS NOT NULL AND rvm.publication_date >= ?"
            params.append(filters.date_after.isoformat())

        if filters.date_before is not None:
            sql += " AND rvm.publication_date IS NOT NULL AND rvm.publication_date <= ?"
            params.append(filters.date_before.isoformat())

        # ADR-0053 title evidence is applied while selecting the bounded candidate
        # set.  The outer ordering restores the ScoredChunk raw-score contract;
        # ADR-0057 then applies the retained title-evidence tier during reranking.
        sql += (
            " GROUP BY c.id ORDER BY title_match DESC, score DESC, c.id ASC LIMIT ?) "
            "SELECT chunk_id, score, title_match, document_title FROM ranked_candidates "
            "ORDER BY score DESC, chunk_id ASC"
        )
        params.append(top_k)

        async with db.execute(sql, params) as cursor:
            rows = list(await cursor.fetchall())

        results: list[ScoredChunk] = []
        for chunk_id, score, title_match, document_title in rows:
            chunk = await self.get_chunk(chunk_id)
            if chunk is None:
                raise IntegrityError("FTS result does not have a canonical chunk row")
            if isinstance(document_title, str) and document_title:
                from dataclasses import replace

                chunk = replace(
                    chunk,
                    metadata=FrozenMetadata(
                        {
                            **dict(chunk.metadata),
                            "document_title": document_title,
                            "retrieval_title_match": bool(title_match),
                        }
                    ),
                )
            results.append(
                ScoredChunk(
                    chunk=chunk,
                    score=float(score),
                    source="sqlite-fts5",
                    rank=len(results) + 1,
                )
            )

        return tuple(results)

    async def search_dense(
        self,
        embedding: EmbeddingVector,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Run bounded dense retrieval through the atomic facade."""
        raise NotImplementedError("SQLiteStore does not support dense search.")

    # -------------------------------------------------------------------------
    # Graph Methods (NO-OP / Unsupported)
    # -------------------------------------------------------------------------

    async def upsert_entity(self, entity: Entity) -> None:
        raise NotImplementedError("SQLiteStore does not store graph entities.")

    async def upsert_edge(self, edge: GraphEdge) -> None:
        raise NotImplementedError("SQLiteStore does not store graph edges.")

    async def get_entity(self, entity_id: UUID) -> Entity | None:
        raise NotImplementedError("SQLiteStore does not store graph entities.")

    async def find_entities(
        self,
        normalized_name: str,
        entity_type: str | None,
        document_ids: tuple[UUID, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        raise NotImplementedError("SQLiteStore does not store graph entities.")

    async def get_related_entities(
        self,
        entity_id: UUID,
        hops: int,
        relations: tuple[str, ...],
        limit: int,
    ) -> tuple[Entity, ...]:
        raise NotImplementedError("SQLiteStore does not store graph entities.")

    async def delete_graph_for_document(self, document_id: UUID) -> None:
        # Gracefully handle the intent by doing nothing, as this is expected during cascade delete
        pass
