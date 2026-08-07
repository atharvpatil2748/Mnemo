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
from collections.abc import Coroutine
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces.errors import ConflictError
from mnemo.models import (
    Chunk,
    ChunkPosition,
    ChunkType,
    Citation,
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
from mnemo.storage.sqlite import SQLiteStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    """Return an unopened SQLiteStore."""
    return SQLiteStore(db_path=tmp_path / "mnemo_metadata.db")


@pytest.fixture
def open_store(store: SQLiteStore) -> SQLiteStore:
    """Return an open SQLiteStore ready for queries."""
    asyncio.run(store.open())
    return store


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


def _run(coro: Coroutine[Any, Any, T]) -> T:
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


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_capabilities(store: SQLiteStore) -> None:
    caps = store.capabilities()
    assert caps.supports_blobs is False
    assert caps.supports_sparse_search is True
    assert caps.supports_graph is False


def test_health_check_unopened(store: SQLiteStore) -> None:
    statuses = _run(store.health_check())
    assert len(statuses) == 1
    assert statuses[0].healthy is False


def test_lifecycle(store: SQLiteStore) -> None:
    _run(store.open())
    statuses = _run(store.health_check())
    assert statuses[0].healthy is True
    _run(store.close())
    statuses = _run(store.health_check())
    assert statuses[0].healthy is False


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
        heading_path=("h1",),
    )

    _run(open_store.upsert_chunks((chunk,)))
    assert _run(open_store.get_chunk(c_id)) is not None

    # Sparse search
    results = _run(open_store.search_sparse("alpha", MetadataFilter(), top_k=5))
    assert len(results) == 1
    assert results[0].chunk.id == c_id

    _run(open_store.delete_chunks_for_document(doc_id, ver_id))
    assert _run(open_store.get_chunk(c_id)) is None


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
            open_store.upsert_entity(Entity(name="x", type="y", confidence=1.0, document_id=doc_id))
        )
    with pytest.raises(NotImplementedError):
        _run(open_store.search_dense((0.1, 0.2), MetadataFilter(), 5))
