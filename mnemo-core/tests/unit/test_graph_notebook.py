"""Tests for graph, notebook, conversation, citation, note, and insight models."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from mnemo.models import (
    Citation,
    Entity,
    GraphEdge,
    Insight,
    InsightType,
    Note,
    Notebook,
    NoteOrigin,
    Session,
    Source,
    Turn,
    TurnRole,
)


def test_entity_aliases_and_graph_edge(document_id: UUID) -> None:
    """Entity aliases are deterministic and graph edges retain direction."""
    ent_id = uuid4()
    entity = Entity(
        entity_id=ent_id,
        canonical_name="Krishna",
        type="person",
        confidence=0.9,
        document_id=document_id,
        aliases=("Kṛṣṇa", "Lord Krishna", "Sri Krishna"),
    )
    edge = GraphEdge(
        source_id=ent_id,
        target_id=ent_id,
        relation="is identical to",
        weight=1.0,
    )
    assert entity.aliases[0] == "Kṛṣṇa"
    assert entity.canonical_name == "Krishna"
    assert entity == replace(entity)
    assert hash(entity) == hash(replace(entity))
    assert edge != replace(edge, source_id=uuid4(), target_id=uuid4())


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Entity(
            entity_id=uuid4(), canonical_name="", type="person", confidence=1.0, document_id=uuid4()
        ),
        lambda: Entity(
            entity_id=uuid4(), canonical_name="x", type="", confidence=1.0, document_id=uuid4()
        ),
        lambda: Entity(
            entity_id=uuid4(),
            canonical_name="x",
            type="person",
            confidence=-0.1,
            document_id=uuid4(),
        ),
        lambda: Entity(
            entity_id=uuid4(), canonical_name="x", type="person", confidence=1.0, document_id="bad"
        ),  # type: ignore[arg-type]
        lambda: Entity(
            entity_id=uuid4(),
            canonical_name="x",
            type="person",
            confidence=1.0,
            document_id=uuid4(),
            aliases=("x",),
        ),
        lambda: Entity(
            entity_id=uuid4(),
            canonical_name="x",
            type="person",
            confidence=1.0,
            document_id=uuid4(),
            aliases=("alias", "alias"),
        ),
        lambda: Entity(
            entity_id=uuid4(),
            canonical_name="x",
            type="person",
            confidence=1.0,
            document_id=uuid4(),
            aliases=["alias"],  # type: ignore[arg-type]
        ),
        lambda: GraphEdge(source_id="bad", target_id=uuid4(), relation="r", weight=1.0),  # type: ignore[arg-type]
        lambda: GraphEdge(source_id=uuid4(), target_id="bad", relation="r", weight=1.0),  # type: ignore[arg-type]
        lambda: GraphEdge(source_id=uuid4(), target_id=uuid4(), relation="", weight=1.0),
        lambda: GraphEdge(source_id=uuid4(), target_id=uuid4(), relation="self", weight=2.0),
    ],
)
def test_graph_validation(factory: object) -> None:
    """Graph values enforce names, aliases, UUIDs, and unit scores."""
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


def _turn(session_id: UUID, timestamp: datetime, *, sequence: int = 0) -> Turn:
    return Turn(
        turn_id=uuid4(),
        session_id=session_id,
        sequence=sequence,
        role=TurnRole.USER if sequence % 2 == 0 else TurnRole.ASSISTANT,
        content="Question" if sequence % 2 == 0 else "Answer",
        created_at=timestamp + timedelta(seconds=sequence),
    )


def test_session_turn_and_enum_semantics(timestamp: datetime) -> None:
    """A session owns ordered immutable user and assistant turn snapshots."""
    session_id = uuid4()
    first = _turn(session_id, timestamp)
    second = _turn(session_id, timestamp, sequence=1)
    session = Session(
        session_id=session_id,
        notebook_id=uuid4(),
        title="Research",
        turns=(first, second),
        created_at=timestamp,
        updated_at=timestamp + timedelta(seconds=2),
    )

    assert TurnRole("assistant") is TurnRole.ASSISTANT
    assert session.turns == (first, second)
    assert first == replace(first, content="Changed snapshot")
    assert hash(first) == hash(replace(first, content="Changed snapshot"))
    assert first != object()
    assert session == replace(session, title="Renamed")
    assert hash(session) == hash(replace(session, title="Renamed"))
    assert session != object()
    with pytest.raises(FrozenInstanceError):
        session.title = "Changed"  # type: ignore[misc]


def test_turn_and_session_validation(timestamp: datetime) -> None:
    """Conversation records reject malformed identity, order, and timestamps."""
    session_id = uuid4()
    turn = _turn(session_id, timestamp)
    turn_cases: tuple[dict[str, Any], ...] = (
        {"turn_id": "bad"},
        {"session_id": "bad"},
        {"sequence": -1},
        {"role": "user"},
        {"content": " "},
        {"created_at": timestamp.replace(tzinfo=None)},
        {"metadata": {}},
    )
    for overrides in turn_cases:
        with pytest.raises((TypeError, ValueError)):
            replace(turn, **overrides)

    base: dict[str, object] = {
        "session_id": session_id,
        "notebook_id": uuid4(),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    session_cases: tuple[dict[str, Any], ...] = (
        {"session_id": "bad"},
        {"notebook_id": "bad"},
        {"title": " "},
        {"turns": (object(),)},
        {"turns": [turn]},
        {"turns": (replace(turn, session_id=uuid4()),)},
        {"turns": (replace(turn, sequence=1),)},
        {"turns": (replace(turn, created_at=timestamp + timedelta(seconds=2)), turn)},
        {"updated_at": timestamp - timedelta(seconds=1)},
        {"metadata": {}},
    )
    for overrides in session_cases:
        with pytest.raises((TypeError, ValueError)):
            Session(**(base | overrides))  # type: ignore[arg-type]


def test_versioned_citation(timestamp: datetime) -> None:
    """Citations preserve exact chunk, document, and document-version identity."""
    citation_id = uuid4()
    citation = Citation(
        citation_id=citation_id,
        turn_id=uuid4(),
        source_number=1,
        chunk_id="a" * 64,
        document_id=uuid4(),
        version_id=uuid4(),
        document_title="Source",
        page_number=4,
        heading_path=("Section",),
        verbatim_quote="Exact evidence",
        created_at=timestamp,
    )

    assert citation.version_id
    assert citation == replace(citation, document_title="Snapshot title")
    assert hash(citation) == hash(replace(citation, document_title="Snapshot title"))
    assert citation != object()

    for overrides in (
        {"citation_id": "bad"},
        {"turn_id": "bad"},
        {"source_number": 0},
        {"chunk_id": "bad"},
        {"document_id": "bad"},
        {"version_id": "bad"},
        {"document_title": ""},
        {"verbatim_quote": ""},
        {"created_at": timestamp.replace(tzinfo=None)},
        {"page_number": 0},
        {"heading_path": ("",)},
        {"heading_path": ["Heading"]},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(citation, **overrides)


def test_notebook_source_note_and_insight(timestamp: datetime) -> None:
    """Notebook records preserve Source-only document membership and provenance."""
    notebook_id = uuid4()
    notebook = Notebook(
        notebook_id=notebook_id,
        title="Knowledge",
        description="Local research",
        created_at=timestamp,
        updated_at=timestamp,
    )
    source = Source(
        source_id=uuid4(),
        notebook_id=notebook_id,
        document_id=uuid4(),
        created_at=timestamp,
    )
    note = Note(
        note_id=uuid4(),
        notebook_id=notebook_id,
        title="Finding",
        content="A grounded note",
        origin=NoteOrigin.USER,
        created_at=timestamp,
        updated_at=timestamp,
    )
    insight = Insight(
        insight_id=uuid4(),
        notebook_id=notebook_id,
        source_id=source.source_id,
        type=InsightType.KEY_FACT,
        content="A fact",
        confidence=0.75,
        created_at=timestamp,
    )

    for model, changed in (
        (notebook, replace(notebook, title="Renamed")),
        (source, replace(source, document_id=uuid4())),
        (note, replace(note, content="Changed")),
        (insight, replace(insight, content="Changed")),
    ):
        assert model == changed
        assert hash(model) == hash(changed)
        assert model != object()
    assert NoteOrigin("generated") is NoteOrigin.GENERATED
    assert InsightType("claim") is InsightType.CLAIM


def test_notebook_family_validation(timestamp: datetime) -> None:
    """Notebook-family models enforce their complete approved local invariants."""
    notebook = Notebook(notebook_id=uuid4(), title="N", created_at=timestamp, updated_at=timestamp)
    source = Source(
        source_id=uuid4(),
        notebook_id=notebook.notebook_id,
        document_id=uuid4(),
        created_at=timestamp,
    )
    note = Note(
        note_id=uuid4(),
        notebook_id=notebook.notebook_id,
        content="N",
        origin=NoteOrigin.USER,
        created_at=timestamp,
        updated_at=timestamp,
    )
    insight = Insight(
        insight_id=uuid4(),
        notebook_id=notebook.notebook_id,
        source_id=source.source_id,
        type=InsightType.CLAIM,
        content="I",
        created_at=timestamp,
    )
    invalid_replacements: tuple[tuple[object, dict[str, Any]], ...] = (
        (notebook, {"notebook_id": "bad"}),
        (notebook, {"title": ""}),
        (notebook, {"description": " "}),
        (notebook, {"updated_at": timestamp - timedelta(seconds=1)}),
        (notebook, {"metadata": {}}),
        (source, {"source_id": "bad"}),
        (source, {"notebook_id": "bad"}),
        (source, {"document_id": "bad"}),
        (source, {"created_at": timestamp.replace(tzinfo=None)}),
        (note, {"note_id": "bad"}),
        (note, {"notebook_id": "bad"}),
        (note, {"title": " "}),
        (note, {"content": ""}),
        (note, {"origin": "user"}),
        (note, {"metadata": {}}),
        (insight, {"insight_id": "bad"}),
        (insight, {"notebook_id": "bad"}),
        (insight, {"source_id": "bad"}),
        (insight, {"type": "claim"}),
        (insight, {"content": ""}),
        (insight, {"confidence": 2.0}),
        (insight, {"created_at": timestamp.replace(tzinfo=None)}),
        (insight, {"metadata": {}}),
    )
    for model, overrides in invalid_replacements:
        with pytest.raises((TypeError, ValueError)):
            replace(model, **overrides)
