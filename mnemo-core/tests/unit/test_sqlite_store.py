"""Tests for Phase 2, Module 2.2: SQLite FTS5 Store.

Coverage targets:
- Lifecycle (open, close, health_check, capabilities)
- DocumentRegistry (CRUD, cascading deletes)
- Notebooks, Sources, Notes, Insights
- Sessions, Turns, Citations
- Chunks and BM25 Sparse Search
- Graph NO-OP handlers
"""

import asyncio
import sqlite3
from collections.abc import Coroutine, Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid4

import aiosqlite
import pytest
from mnemo.interfaces.errors import ConflictError
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    Citation,
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    Entity,
    FrozenMetadata,
    Insight,
    InsightType,
    MetadataFilter,
    Note,
    Notebook,
    NoteOrigin,
    Session,
    Source,
    Turn,
    TurnRole,
)
from mnemo.storage.retrieval_projection import RetrievalMetadataProjection
from mnemo.storage.sqlite import SQLiteStore

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    """Return an unopened SQLiteStore."""
    return SQLiteStore(db_path=tmp_path / "mnemo_metadata.db")


@pytest.fixture
def open_store(store: SQLiteStore) -> Iterator[SQLiteStore]:
    """Return an open SQLiteStore ready for queries."""
    asyncio.run(store.open())
    yield store
    asyncio.run(store.close())


@pytest.fixture
def doc_id() -> UUID:
    return uuid4()


@pytest.fixture
def ver_id() -> UUID:
    return uuid4()


@pytest.fixture
def nb_id() -> UUID:
    return uuid4()


@pytest.fixture
def dt() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def make_doc(doc_id: UUID, ver_id: UUID, dt: datetime) -> Document:
    meta = DocumentMetadata(content_hash="a" * 64)
    version = DocumentVersion(
        version_id=ver_id,
        document_id=doc_id,
        content_hash="a" * 64,
        metadata=meta,
        status=DocumentVersionStatus.CURRENT,
        created_at=dt,
    )
    return Document(
        document_id=doc_id,
        versions=(version,),
        current_version_id=ver_id,
        current_hash="a" * 64,
        status=DocumentStatus.INDEXED,
        created_at=dt,
        updated_at=dt,
    )


def _search_chunk(document_id: UUID, version_id: UUID, index: int, text: str) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        document_id=document_id,
        version_id=version_id,
        text=text,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=(),
        metadata=FrozenMetadata(),
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_capabilities(store: SQLiteStore) -> None:
    caps = store.capabilities()
    assert caps.supports_blobs is False
    assert caps.supports_sparse_search is True
    assert caps.supports_graph is False


def test_sparse_projection_is_version_aware_and_filters_before_top_k(
    open_store: SQLiteStore, dt: datetime
) -> None:
    document_id = uuid4()
    old_version, new_version = uuid4(), uuid4()
    versions = (
        DocumentVersion(
            version_id=old_version,
            document_id=document_id,
            content_hash="a" * 64,
            metadata=DocumentMetadata(content_hash="a" * 64, publication_date=date(2020, 1, 1)),
            status=DocumentVersionStatus.SUPERSEDED,
            created_at=dt,
        ),
        DocumentVersion(
            version_id=new_version,
            document_id=document_id,
            content_hash="b" * 64,
            metadata=DocumentMetadata(content_hash="b" * 64, publication_date=date(2024, 1, 1)),
            status=DocumentVersionStatus.CURRENT,
            created_at=dt,
        ),
    )
    _run(
        open_store.upsert_document(
            Document(
                document_id=document_id,
                versions=versions,
                current_version_id=new_version,
                current_hash="b" * 64,
                status=DocumentStatus.INDEXED,
                created_at=dt,
                updated_at=dt,
            )
        )
    )
    old = _search_chunk(document_id, old_version, 9001, "duty duty duty action")
    new = _search_chunk(document_id, new_version, 9002, "duty action")
    _run(
        open_store._upsert_chunks_with_projection(
            (old,),
            RetrievalMetadataProjection(doc_type=DocType.BOOK, publication_date=date(2020, 1, 1)),
        )
    )
    _run(
        open_store._upsert_chunks_with_projection(
            (new,),
            RetrievalMetadataProjection(doc_type=DocType.PAPER, publication_date=date(2024, 1, 1)),
        )
    )

    paper = _run(
        open_store.search_sparse(
            "duty",
            MetadataFilter(
                doc_types=(DocType.PAPER,),
                date_after=date(2024, 1, 1),
                date_before=date(2024, 1, 1),
            ),
            top_k=1,
        )
    )
    assert tuple(result.chunk.id for result in paper) == (new.id,)
    book = _run(
        open_store.search_sparse("duty", MetadataFilter(doc_types=(DocType.BOOK,)), top_k=1)
    )
    assert tuple(result.chunk.id for result in book) == (old.id,)
    assert paper[0].score >= 0 and book[0].score >= 0
    unfiltered = _run(open_store.search_sparse("duty", MetadataFilter(), top_k=2))
    assert tuple(result.chunk.id for result in unfiltered) == (old.id, new.id)
    assert unfiltered[0].score > unfiltered[1].score


def test_sparse_missing_date_and_unprojected_metadata_fail_closed(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    _run(open_store.upsert_document(make_doc(doc_id, ver_id, dt)))
    chunk = _search_chunk(doc_id, ver_id, 9010, "wisdom duty")
    _run(
        open_store._upsert_chunks_with_projection(
            (chunk,), RetrievalMetadataProjection(doc_type=DocType.BOOK, publication_date=None)
        )
    )
    assert len(_run(open_store.search_sparse("duty", MetadataFilter(), 5))) == 1
    assert (
        _run(open_store.search_sparse("duty", MetadataFilter(date_after=date(2000, 1, 1)), 5)) == ()
    )
    unprojected = _search_chunk(doc_id, ver_id, 9011, "wisdom duty")
    _run(open_store.upsert_chunks((unprojected,)))
    assert (
        _run(open_store.search_sparse("duty", MetadataFilter(doc_types=(DocType.PAPER,)), 5)) == ()
    )


def test_health_check_unopened(store: SQLiteStore) -> None:
    statuses = _run(store.health_check())
    assert len(statuses) == 1
    assert statuses[0].healthy is False


def test_sparse_notebook_source_filters_use_set_semantics(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    _run(open_store.upsert_document(make_doc(doc_id, ver_id, dt)))
    notebook_a, notebook_b = uuid4(), uuid4()
    source_a, source_b = uuid4(), uuid4()
    for notebook_id in (notebook_a, notebook_b):
        _run(
            open_store.upsert_notebook(
                Notebook(
                    notebook_id=notebook_id,
                    title="Sparse acceptance",
                    created_at=dt,
                    updated_at=dt,
                    metadata=FrozenMetadata(),
                )
            )
        )
    _run(
        open_store.upsert_source(
            Source(
                source_id=source_a,
                notebook_id=notebook_a,
                document_id=doc_id,
                created_at=dt,
            )
        )
    )
    _run(
        open_store.upsert_source(
            Source(
                source_id=source_b,
                notebook_id=notebook_b,
                document_id=doc_id,
                created_at=dt,
            )
        )
    )
    chunk = _search_chunk(doc_id, ver_id, 9020, "deterministic duty")
    _run(
        open_store._upsert_chunks_with_projection(
            (chunk,),
            RetrievalMetadataProjection(doc_type=DocType.BOOK, publication_date=None),
        )
    )

    matches = _run(
        open_store.search_sparse(
            "duty",
            MetadataFilter(
                notebook_id=notebook_a,
                source_ids=(uuid4(), source_a, source_b),
                doc_types=(DocType.BOOK,),
            ),
            5,
        )
    )
    assert tuple(result.chunk.id for result in matches) == (chunk.id,)
    assert (
        _run(
            open_store.search_sparse(
                "duty", MetadataFilter(notebook_id=notebook_a, source_ids=(source_b,)), 5
            )
        )
        == ()
    )


def test_sparse_unicode_punctuation_and_multi_term_query(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    _run(open_store.upsert_document(make_doc(doc_id, ver_id, dt)))
    chunk = _search_chunk(doc_id, ver_id, 9030, "कर्तव्य और धर्म duty action")
    _run(open_store.upsert_chunks((chunk,)))

    for query in ("कर्तव्य", "duty, action!", "duty duty"):
        matches = _run(open_store.search_sparse(query, MetadataFilter(), 1))
        assert tuple(result.chunk.id for result in matches) == (chunk.id,)


def test_lifecycle(store: SQLiteStore) -> None:
    _run(store.open())
    statuses = _run(store.health_check())
    assert statuses[0].healthy is True
    _run(store.close())
    statuses = _run(store.health_check())
    assert statuses[0].healthy is False


def test_schema_migration_4_upgrades_v3_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "v3.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE schema_versions (version INTEGER PRIMARY KEY, applied_at TEXT)")
        db.execute("INSERT INTO schema_versions VALUES (3, '2026-08-13T00:00:00+00:00')")
    store = SQLiteStore(path)
    _run(store.open())
    _run(store.close())
    _run(store.open())
    _run(store.close())
    with sqlite3.connect(path) as db:
        version = db.execute("SELECT MAX(version) FROM schema_versions").fetchone()
        table = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='retrieval_version_metadata'"
        ).fetchone()
    assert version == (4,)
    assert table == ("retrieval_version_metadata",)


def test_multiple_open_close(store: SQLiteStore) -> None:
    _run(store.open())
    _run(store.open())
    _run(store.close())
    _run(store.close())


# ---------------------------------------------------------------------------
# DocumentRegistry
# ---------------------------------------------------------------------------


def test_document_crud(open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime) -> None:
    doc = make_doc(doc_id, ver_id, dt)
    _run(open_store.upsert_document(doc))

    retrieved = _run(open_store.get_document(doc_id))
    assert retrieved is not None
    assert retrieved.document_id == doc_id
    assert retrieved.current_version_id == ver_id

    page = _run(open_store.list_documents(status=None, limit=10, cursor=None))
    assert len(page.items) == 1

    _run(open_store.delete_document(doc_id, expected_version_id=ver_id))
    assert _run(open_store.get_document(doc_id)) is None


def test_document_by_content_hash(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    doc = make_doc(doc_id, ver_id, dt)
    _run(open_store.upsert_document(doc))

    # Valid hash should return the document
    retrieved = _run(open_store.get_document_by_content_hash(doc.current_hash))
    assert retrieved is not None
    assert retrieved.document_id == doc_id
    assert retrieved.current_hash == doc.current_hash

    # Invalid hash should return None
    assert _run(open_store.get_document_by_content_hash("deadbeef" * 8)) is None


def test_document_conflict_delete(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    doc = make_doc(doc_id, ver_id, dt)
    _run(open_store.upsert_document(doc))

    with pytest.raises(ConflictError):
        _run(open_store.delete_document(doc_id, expected_version_id=uuid4()))


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------


def test_notebook_crud(open_store: SQLiteStore, nb_id: UUID, dt: datetime) -> None:
    nb = Notebook(
        notebook_id=nb_id,
        title="My Notebook",
        description="desc",
        created_at=dt,
        updated_at=dt,
        metadata=FrozenMetadata(),
    )
    _run(open_store.upsert_notebook(nb))
    assert _run(open_store.get_notebook(nb_id)) is not None
    page = _run(open_store.list_notebooks(10, None))
    assert len(page.items) == 1

    _run(open_store.delete_notebook(nb_id))
    assert _run(open_store.get_notebook(nb_id)) is None


def test_source_crud(
    open_store: SQLiteStore, nb_id: UUID, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    nb = Notebook(notebook_id=nb_id, title="Test", description="desc", created_at=dt, updated_at=dt)
    _run(open_store.upsert_notebook(nb))

    doc = make_doc(doc_id, ver_id, dt)
    _run(open_store.upsert_document(doc))

    src_id = uuid4()
    src = Source(source_id=src_id, notebook_id=nb_id, document_id=doc_id, created_at=dt)
    _run(open_store.upsert_source(src))

    assert _run(open_store.get_source(src_id)) is not None
    assert len(_run(open_store.list_sources(nb_id, 10, None)).items) == 1
    _run(open_store.delete_source(src_id))
    assert _run(open_store.get_source(src_id)) is None


def test_source_membership_pair_is_unique(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    notebook_id = uuid4()
    _run(
        open_store.upsert_notebook(
            Notebook(
                notebook_id=notebook_id,
                title="Unique membership",
                created_at=dt,
                updated_at=dt,
            )
        )
    )
    _run(open_store.upsert_document(make_doc(doc_id, ver_id, dt)))
    _run(
        open_store.upsert_source(
            Source(
                source_id=uuid4(),
                notebook_id=notebook_id,
                document_id=doc_id,
                created_at=dt,
            )
        )
    )

    with pytest.raises(ConflictError, match="duplicate Source associations"):
        _run(
            open_store.upsert_source(
                Source(
                    source_id=uuid4(),
                    notebook_id=notebook_id,
                    document_id=doc_id,
                    created_at=dt,
                )
            )
        )


def test_note_crud(open_store: SQLiteStore, nb_id: UUID, dt: datetime) -> None:
    nb = Notebook(notebook_id=nb_id, title="Test", description="desc", created_at=dt, updated_at=dt)
    _run(open_store.upsert_notebook(nb))

    note_id = uuid4()
    note = Note(
        note_id=note_id,
        notebook_id=nb_id,
        title="a",
        content="b",
        origin=NoteOrigin.USER,
        created_at=dt,
        updated_at=dt,
    )
    _run(open_store.upsert_note(note))
    assert _run(open_store.get_note(note_id)) is not None
    assert len(_run(open_store.list_notes(nb_id, 10, None)).items) == 1
    _run(open_store.delete_note(note_id))


def test_insight_crud(
    open_store: SQLiteStore, nb_id: UUID, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    nb = Notebook(notebook_id=nb_id, title="Test", description="desc", created_at=dt, updated_at=dt)
    _run(open_store.upsert_notebook(nb))

    doc = make_doc(doc_id, ver_id, dt)
    _run(open_store.upsert_document(doc))

    src_id = uuid4()
    src = Source(source_id=src_id, notebook_id=nb_id, document_id=doc_id, created_at=dt)
    _run(open_store.upsert_source(src))

    ins_id = uuid4()
    ins = Insight(
        insight_id=ins_id,
        notebook_id=nb_id,
        source_id=src_id,
        type=InsightType.KEY_FACT,
        content="a",
        confidence=0.9,
        created_at=dt,
    )
    _run(open_store.upsert_insight(ins))
    assert _run(open_store.get_insight(ins_id)) is not None
    assert len(_run(open_store.list_insights(nb_id, 10, None)).items) == 1
    _run(open_store.delete_insight(ins_id))


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_session_crud(
    open_store: SQLiteStore, nb_id: UUID, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    nb = Notebook(notebook_id=nb_id, title="Test", description="desc", created_at=dt, updated_at=dt)
    _run(open_store.upsert_notebook(nb))

    sess_id = uuid4()
    turn = Turn(
        turn_id=uuid4(),
        session_id=sess_id,
        sequence=0,
        role=TurnRole.USER,
        content="hello",
        created_at=dt,
    )
    sess = Session(
        session_id=sess_id,
        notebook_id=nb_id,
        title="x",
        created_at=dt,
        updated_at=dt,
        turns=(turn,),
    )

    _run(open_store.upsert_session(sess))
    retrieved = _run(open_store.get_session(sess_id))
    assert retrieved is not None
    assert len(retrieved.turns) == 1

    new_turn = Turn(
        turn_id=uuid4(),
        session_id=sess_id,
        sequence=1,
        role=TurnRole.ASSISTANT,
        content="hi",
        created_at=dt,
    )
    _run(open_store.append_turn(sess_id, new_turn))

    turns = _run(open_store.list_turns(sess_id, None, 10)).items
    assert len(turns) == 2

    # Needs a document and chunk for Citation foreign keys
    doc = make_doc(doc_id, ver_id, dt)
    _run(open_store.upsert_document(doc))

    c_id = "a" * 64
    chunk = Chunk(
        id=c_id,
        text="t",
        document_id=doc_id,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
    )
    _run(open_store.upsert_chunks((chunk,)))

    cit = Citation(
        citation_id=uuid4(),
        turn_id=new_turn.turn_id,
        source_number=1,
        chunk_id=c_id,
        document_id=doc_id,
        version_id=ver_id,
        document_title="t",
        verbatim_quote="q",
        page_number=None,
        heading_path=("h1",),
        created_at=dt,
    )
    _run(open_store.upsert_citation(cit))
    assert len(_run(open_store.get_citations_for_turn(new_turn.turn_id))) == 1

    _run(open_store.delete_session(sess_id))
    assert _run(open_store.get_session(sess_id)) is None


# ---------------------------------------------------------------------------
# Chunks and Search
# ---------------------------------------------------------------------------


def test_chunk_crud_and_search(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    doc = make_doc(doc_id, ver_id, dt)
    _run(open_store.upsert_document(doc))

    c_id = "a" * 64
    chunk = Chunk(
        id=c_id,
        text="This is a test document containing keyword alpha",
        document_id=doc_id,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=("h1",),
    )

    _run(open_store.upsert_chunks((chunk,)))
    stored = _run(open_store.get_chunk(c_id))
    assert stored is not None
    assert stored.source_span == chunk.source_span

    # Sparse search
    results = _run(open_store.search_sparse("alpha", MetadataFilter(), top_k=5))
    assert len(results) == 1
    assert results[0].chunk.id == c_id

    _run(open_store.delete_chunks_for_document(doc_id, ver_id))
    assert _run(open_store.get_chunk(c_id)) is None


def test_chunk_snapshot_restore_preserves_replaced_rows(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    """Affected-key restoration replaces old rows and removes only new identities."""
    _run(open_store.upsert_document(make_doc(doc_id, ver_id, dt)))
    original = Chunk(
        id="a" * 64,
        text="original alpha",
        document_id=doc_id,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=("original",),
        metadata=FrozenMetadata({"parser.source": "old"}),
    )
    introduced = replace(original, id="b" * 64, text="introduced")
    _run(open_store.upsert_chunks((original,)))
    snapshot = _run(open_store._snapshot_chunks((original.id, introduced.id)))

    _run(open_store.upsert_chunks((replace(original, text="replacement"), introduced)))
    _run(open_store._restore_chunk_snapshot((original.id, introduced.id), snapshot))

    restored = _run(open_store.get_chunk(original.id))
    assert restored is not None
    assert restored.text == original.text
    assert restored.heading_path == original.heading_path
    assert restored.source_span == original.source_span
    assert dict(restored.metadata) == dict(original.metadata)
    assert _run(open_store.get_chunk(introduced.id)) is None


def test_chunk_batch_failure_rolls_back_replacement(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, dt: datetime
) -> None:
    """SQLite's native batch transaction preserves a replaced row on failure."""
    _run(open_store.upsert_document(make_doc(doc_id, ver_id, dt)))
    original = Chunk(
        id="a" * 64,
        text="original",
        document_id=doc_id,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
    )
    invalid = replace(original, id="b" * 64, document_id=uuid4())
    _run(open_store.upsert_chunks((original,)))

    with pytest.raises(aiosqlite.IntegrityError):
        _run(open_store.upsert_chunks((replace(original, text="replacement"), invalid)))

    restored = _run(open_store.get_chunk(original.id))
    assert restored is not None
    assert restored.text == original.text


# ---------------------------------------------------------------------------
# Cascade Deletes
# ---------------------------------------------------------------------------


def test_cascade_delete(
    open_store: SQLiteStore, doc_id: UUID, ver_id: UUID, nb_id: UUID, dt: datetime
) -> None:
    # Setup document, notebook, source, chunk
    doc = make_doc(doc_id, ver_id, dt)
    _run(open_store.upsert_document(doc))

    nb = Notebook(notebook_id=nb_id, title="Test", description="desc", created_at=dt, updated_at=dt)
    _run(open_store.upsert_notebook(nb))

    src_id = uuid4()
    src = Source(source_id=src_id, notebook_id=nb_id, document_id=doc_id, created_at=dt)
    _run(open_store.upsert_source(src))

    c_id = "b" * 64
    chunk = Chunk(
        id=c_id,
        text="test",
        document_id=doc_id,
        version_id=ver_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=("h1",),
    )
    _run(open_store.upsert_chunks((chunk,)))

    # Cascade delete document
    _run(open_store.delete_document_cascade(doc_id))

    # Verify everything related is gone
    assert _run(open_store.get_document(doc_id)) is None
    assert _run(open_store.get_chunk(c_id)) is None
    assert _run(open_store.get_source(src_id)) is None


# ---------------------------------------------------------------------------
# Graph NO-OPs
# ---------------------------------------------------------------------------


def test_graph_unsupported(open_store: SQLiteStore, doc_id: UUID) -> None:
    with pytest.raises(NotImplementedError):
        _run(
            open_store.upsert_entity(
                Entity(
                    entity_id=uuid4(),
                    canonical_name="x",
                    type="y",
                    confidence=1.0,
                    document_id=doc_id,
                )
            )
        )
    with pytest.raises(NotImplementedError):
        _run(open_store.search_dense((0.1, 0.2), MetadataFilter(), 5))
