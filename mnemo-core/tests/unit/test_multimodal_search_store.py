from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import aiosqlite
import pytest
from mnemo.interfaces.advanced_retrieval import VisualQueryVector, VisualVectorMetric
from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.models.advanced_retrieval import (
    EvidenceRepresentation,
    PositionalScopeV2,
    RetrievalScopeV2,
)
from mnemo.storage import multimodal_search as subject


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    async def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _Connection:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, object]] = []

    async def execute(self, sql: str, params: object = ()) -> _Cursor:
        self.calls.append((sql, params))
        return _Cursor(self.rows)


class _Store(subject.SQLiteMultimodalSearchMixin):
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.connection = _Connection(rows)

    def _require_open(self) -> _Connection:
        return self.connection


def _scope() -> RetrievalScopeV2:
    return RetrievalScopeV2(notebook_id=uuid4())


@pytest.mark.anyio
async def test_generation_identities_cover_asset_unknown_empty_and_profile_paths() -> None:
    store = _Store([("generation", "profile", "checksum")])
    assert (
        await store.active_multimodal_generation_identity(EvidenceRepresentation.ASSET_METADATA)
        == "asset-catalog-v1"
    )
    assert (
        await store.active_multimodal_generation_identity(EvidenceRepresentation.CANONICAL_TEXT)
        is None
    )
    assert await store.active_multimodal_generation_identity(
        EvidenceRepresentation.VISUAL_VECTOR, profile_id="clip"
    )
    assert "g.profile=?" in store.connection.calls[-1][0]
    store.connection.rows = []
    assert (
        await store.active_multimodal_generation_identity(EvidenceRepresentation.OCR_TEXT) is None
    )
    assert await store.active_multilingual_generation_identity() is None


@pytest.mark.anyio
async def test_multilingual_retrieval_validates_bounds_position_scope_and_pages() -> None:
    store = _Store([])
    with pytest.raises(ValueError, match="bounds"):
        await store.retrieve_multilingual_evidence(
            scope=_scope(), position=PositionalScopeV2(), query="q", offset=-1, limit=1
        )
    with pytest.raises(ContractValidationError, match="positional"):
        await store.retrieve_multilingual_evidence(
            scope=_scope(), position=PositionalScopeV2(page_start=1), query="q", offset=0, limit=1
        )
    with pytest.raises(ContractValidationError, match="unavailable"):
        await store.retrieve_multilingual_evidence(
            scope=_scope(), position=PositionalScopeV2(), query="q", offset=0, limit=1
        )

    ids = [uuid4() for _ in range(5)]
    scope = RetrievalScopeV2(notebook_id=uuid4(), source_ids=(ids[4],))
    store.connection.rows = [
        (
            str(ids[0]),
            "n",
            str(ids[1]),
            str(ids[2]),
            "evidence",
            "hi",
            "en",
            "text",
            -0.5,
            str(ids[4]),
        ),
        (
            str(ids[0]),
            "n",
            str(ids[1]),
            str(ids[2]),
            "evidence2",
            "hi",
            "en",
            "text2",
            -0.25,
            str(ids[4]),
        ),
    ]
    page = await store.retrieve_multilingual_evidence(
        scope=scope, position=PositionalScopeV2(), query="Hindi query", offset=0, limit=1
    )
    assert page.records[0].source_id == ids[4]
    assert page.records[0].source_score == 0.5
    assert page.next_offset == 1 and not page.exhausted


@pytest.mark.anyio
async def test_multimodal_dispatch_and_asset_metadata_filter_ranking_and_pagination() -> None:
    ids = [uuid4() for _ in range(5)]
    row = (
        str(ids[0]),
        str(ids[1]),
        str(ids[2]),
        str(ids[3]),
        str(ids[4]),
        json.dumps({"title": "Diagram"}),
        json.dumps({"page_number": 2, "ordinal": 1, "section_path": ["Results"]}),
        "Heat transfer diagram",
        "image/png",
        json.dumps({"caption": "gradient"}),
        "a" * 64,
    )
    store = _Store([row, row])
    scope = RetrievalScopeV2(notebook_id=uuid4())
    page = await store.retrieve_multimodal_evidence(
        representation=EvidenceRepresentation.ASSET_METADATA,
        scope=scope,
        position=PositionalScopeV2(page_start=2, page_end=2, heading_prefix=("Results",)),
        query="heat diagram",
        ranked=True,
        offset=0,
        limit=1,
    )
    assert page.records[0].asset_id == ids[1]
    assert page.records[0].document_title == "Diagram"
    assert page.records[0].source_score == 1.0
    assert page.next_offset == 1

    empty = await store.retrieve_multimodal_evidence(
        representation=EvidenceRepresentation.ASSET_METADATA,
        scope=scope,
        position=PositionalScopeV2(page_start=3),
        query="missing",
        ranked=False,
        offset=0,
        limit=10,
    )
    assert empty.records == () and empty.exhausted

    with pytest.raises(ContractValidationError, match="not a multimodal"):
        await store.retrieve_multimodal_evidence(
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            scope=scope,
            position=PositionalScopeV2(),
            query="q",
            ranked=False,
            offset=0,
            limit=1,
        )


@pytest.mark.anyio
async def test_derived_text_builds_ocr_and_vision_records(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ids = [uuid4() for _ in range(7)]
    base = (
        str(ids[0]),
        str(ids[1]),
        str(ids[2]),
        str(ids[3]),
        str(ids[4]),
        str(ids[5]),
        json.dumps({"title": "Evidence"}),
        json.dumps({"page_number": 1}),
        "recognized text",
        "r1,r2",
        -0.75,
        "profile",
        str(ids[6]),
    )
    store = _Store([base])
    monkeypatch.setattr(
        store, "active_multimodal_generation_identity", lambda *_args, **_kwargs: None
    )

    async def identity(*_args: object, **_kwargs: object) -> str:
        return "generation-snapshot"

    monkeypatch.setattr(store, "active_multimodal_generation_identity", identity)
    scope = RetrievalScopeV2(notebook_id=uuid4())
    ocr = await store.retrieve_multimodal_evidence(
        representation=EvidenceRepresentation.OCR_TEXT,
        scope=scope,
        position=PositionalScopeV2(),
        query="recognized",
        ranked=True,
        offset=0,
        limit=10,
    )
    assert ocr.records[0].locator["evidence_kind"] == "derived_ocr"
    assert ocr.records[0].locator["region_ids"] == ["r1", "r2"]
    vision_row = list(base)
    vision_row[9] = None
    store.connection.rows = [tuple(vision_row)]
    vision = await store.retrieve_multimodal_evidence(
        representation=EvidenceRepresentation.VISION_ANALYSIS,
        scope=scope,
        position=PositionalScopeV2(),
        query="",
        ranked=False,
        offset=0,
        limit=10,
    )
    assert vision.records[0].locator["evidence_kind"] == "derived_vision"
    assert vision.records[0].locator["region_ids"] == []


@pytest.mark.anyio
async def test_ocr_keeps_distinct_sources_for_one_document_in_one_notebook(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "multimodal.db"
    notebook, document, version, occurrence, asset, derivation, generation = (
        uuid4() for _ in range(7)
    )
    source_a, source_b = uuid4(), uuid4()
    visual_generation, visual_derivation = uuid4(), uuid4()
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE VIRTUAL TABLE ocr_fts USING fts5("
            "generation_id UNINDEXED,region_id UNINDEXED,text);"
            "CREATE TABLE ocr_projection_rows(generation_id TEXT,region_id TEXT,derivation_id TEXT,"
            "occurrence_id TEXT,document_id TEXT,version_id TEXT);"
            "CREATE TABLE active_index_generations(generation_id TEXT);"
            "CREATE TABLE index_generations("
            "generation_id TEXT,capability TEXT,state TEXT,profile TEXT);"
            "CREATE TABLE index_generation_coverage("
            "generation_id TEXT,completeness TEXT,failed_count INTEGER,checksum TEXT);"
            "CREATE TABLE asset_occurrences(occurrence_id TEXT,asset_id TEXT,"
            "document_id TEXT,version_id TEXT,locator TEXT,authored_alt_text TEXT);"
            "CREATE TABLE asset_catalog(asset_id TEXT,mime_type TEXT,metadata TEXT,"
            "content_hash TEXT);"
            "CREATE TABLE sources(source_id TEXT,notebook_id TEXT,document_id TEXT);"
            "CREATE TABLE document_versions(version_id TEXT,metadata TEXT);"
            "CREATE TABLE visual_vector_projection_rows("
            "generation_id TEXT,derivation_id TEXT,occurrence_id TEXT,"
            "document_id TEXT,version_id TEXT);"
            "CREATE TABLE visual_embeddings(derivation_id TEXT,occurrence_id TEXT,"
            "asset_id TEXT,document_id TEXT,version_id TEXT,payload TEXT);"
        )
        db.execute("INSERT INTO ocr_fts VALUES(?,?,?)", (str(generation), "region", "recognized"))
        db.execute(
            "INSERT INTO ocr_projection_rows VALUES(?,?,?,?,?,?)",
            (
                str(generation),
                "region",
                str(derivation),
                str(occurrence),
                str(document),
                str(version),
            ),
        )
        db.execute("INSERT INTO active_index_generations VALUES(?)", (str(generation),))
        db.execute(
            "INSERT INTO index_generations VALUES(?,?,?,?)",
            (str(generation), "ocr_text", "ready", "ocr"),
        )
        db.execute(
            "INSERT INTO index_generation_coverage VALUES(?,?,?,?)",
            (str(generation), "complete", 0, "digest"),
        )
        db.execute(
            "INSERT INTO asset_occurrences VALUES(?,?,?,?,?,?)",
            (str(occurrence), str(asset), str(document), str(version), "{}", None),
        )
        db.execute(
            "INSERT INTO asset_catalog VALUES(?,?,?,?)",
            (str(asset), "image/png", "{}", "a" * 64),
        )
        db.execute("INSERT INTO document_versions VALUES(?,?)", (str(version), "{}"))
        db.execute(
            "INSERT INTO visual_vector_projection_rows VALUES(?,?,?,?,?)",
            (
                str(visual_generation),
                str(visual_derivation),
                str(occurrence),
                str(document),
                str(version),
            ),
        )
        db.execute(
            "INSERT INTO visual_embeddings VALUES(?,?,?,?,?,?)",
            (
                str(visual_derivation),
                str(occurrence),
                str(asset),
                str(document),
                str(version),
                "{}",
            ),
        )
        db.execute("INSERT INTO active_index_generations VALUES(?)", (str(visual_generation),))
        db.execute(
            "INSERT INTO index_generations VALUES(?,?,?,?)",
            (str(visual_generation), "visual_vector", "ready", "clip"),
        )
        db.execute(
            "INSERT INTO index_generation_coverage VALUES(?,?,?,?)",
            (str(visual_generation), "complete", 0, "visual-digest"),
        )
        db.executemany(
            "INSERT INTO sources VALUES(?,?,?)",
            ((str(source), str(notebook), str(document)) for source in (source_a, source_b)),
        )

    class _RealStore(subject.SQLiteMultimodalSearchMixin):
        def __init__(self, connection: aiosqlite.Connection) -> None:
            self.connection = connection

        def _require_open(self) -> aiosqlite.Connection:
            return self.connection

    async with aiosqlite.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        store = _RealStore(connection)
        monkeypatch.setattr(
            subject,
            "_embedding_from_payload",
            lambda _payload: SimpleNamespace(
                dimensions=2,
                shared_space_id="space",
                metric=VisualVectorMetric.COSINE,
                vector=(1.0, 0.0),
            ),
        )
        page = await store.retrieve_multimodal_evidence(
            representation=EvidenceRepresentation.OCR_TEXT,
            scope=RetrievalScopeV2(notebook_id=notebook),
            position=PositionalScopeV2(),
            query="recognized",
            ranked=True,
            offset=0,
            limit=10,
        )
        assert {record.source_id for record in page.records} == {source_a, source_b}
        assert {record.derivation_id for record in page.records} == {derivation}
        asset_page = await store.retrieve_multimodal_evidence(
            representation=EvidenceRepresentation.ASSET_METADATA,
            scope=RetrievalScopeV2(notebook_id=notebook),
            position=PositionalScopeV2(),
            query="",
            ranked=True,
            offset=0,
            limit=10,
        )
        assert {record.source_id for record in asset_page.records} == {source_a, source_b}
        assert {record.occurrence_id for record in asset_page.records} == {occurrence}
        restricted = await store.retrieve_multimodal_evidence(
            representation=EvidenceRepresentation.OCR_TEXT,
            scope=RetrievalScopeV2(notebook_id=notebook, source_ids=(source_b,)),
            position=PositionalScopeV2(),
            query="recognized",
            ranked=True,
            offset=0,
            limit=10,
        )
        assert [record.source_id for record in restricted.records] == [source_b]
        visual = await store.retrieve_multimodal_evidence(
            representation=EvidenceRepresentation.VISUAL_VECTOR,
            scope=RetrievalScopeV2(notebook_id=notebook),
            position=PositionalScopeV2(),
            query="image",
            ranked=True,
            offset=0,
            limit=10,
            query_vector=VisualQueryVector(
                profile_id="clip",
                shared_space_id="space",
                dimensions=2,
                metric=VisualVectorMetric.COSINE,
                values=(1.0, 0.0),
            ),
        )
        assert {record.source_id for record in visual.records} == {source_a, source_b}
        assert {record.derivation_id for record in visual.records} == {visual_derivation}


@pytest.mark.anyio
async def test_visual_vector_similarity_and_contract_failures(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ids = [uuid4() for _ in range(8)]
    row = (
        str(ids[0]),
        str(ids[1]),
        str(ids[2]),
        str(ids[3]),
        str(ids[4]),
        str(ids[5]),
        json.dumps({"title": "Visual"}),
        json.dumps({"slide_number": 1}),
        "payload",
        str(ids[6]),
    )
    store = _Store([row])

    async def identity(*_args: object, **_kwargs: object) -> str:
        return "visual-snapshot"

    monkeypatch.setattr(store, "active_multimodal_generation_identity", identity)
    monkeypatch.setattr(
        subject,
        "_embedding_from_payload",
        lambda _payload: SimpleNamespace(
            dimensions=2,
            shared_space_id="space",
            metric=SimpleNamespace(value="cosine"),
            vector=(1.0, 0.0),
        ),
    )
    vector = VisualQueryVector(
        profile_id="clip",
        shared_space_id="space",
        dimensions=2,
        metric=VisualVectorMetric.COSINE,
        values=(1.0, 0.0),
    )
    page = await store.retrieve_multimodal_evidence(
        representation=EvidenceRepresentation.VISUAL_VECTOR,
        scope=RetrievalScopeV2(notebook_id=uuid4()),
        position=PositionalScopeV2(),
        query="",
        ranked=True,
        offset=0,
        limit=1,
        query_vector=vector,
    )
    assert page.records[0].source_score == 1.0
    assert page.records[0].locator["evidence_kind"] == "visual_vector_match"

    with pytest.raises(ContractValidationError, match="requires a query vector"):
        await store.retrieve_multimodal_evidence(
            representation=EvidenceRepresentation.VISUAL_VECTOR,
            scope=_scope(),
            position=PositionalScopeV2(),
            query="",
            ranked=True,
            offset=0,
            limit=1,
        )
    incompatible = SimpleNamespace(
        dimensions=3,
        shared_space_id="space",
        metric=SimpleNamespace(value="cosine"),
        vector=(1.0, 0.0, 0.0),
    )
    monkeypatch.setattr(subject, "_embedding_from_payload", lambda _payload: incompatible)
    with pytest.raises(IntegrityError, match="incompatible"):
        await store._visual_vectors(_scope(), PositionalScopeV2(), vector, 0, 1)


def test_multimodal_helpers_cover_scopes_positions_titles_and_metrics() -> None:
    ids = tuple(uuid4() for _ in range(4))
    scope = RetrievalScopeV2(
        notebook_id=ids[0], source_ids=(ids[1],), document_ids=(ids[2],), version_ids=(ids[3],)
    )
    sql, params = subject._scope_sql(scope, "record", "source")
    assert sql.count(" IN (") == 3
    assert params == [str(value) for value in ids]
    assert subject._fts_query("hello हिंदी") == '"hello" OR "ह" OR "द"'
    assert subject._fts_query("---") is None
    assert subject._position_matches(
        {"page_number": 2, "section_path": ["A", "B"]},
        PositionalScopeV2(page_start=1, page_end=2, heading_prefix=("A",)),
    )
    assert not subject._position_matches({}, PositionalScopeV2(page_start=1))
    assert not subject._position_matches({"page_number": 3}, PositionalScopeV2(page_end=2))
    assert not subject._position_matches(
        {"page_number": 1, "section_path": "A"}, PositionalScopeV2(heading_prefix=("A",))
    )
    assert subject._title(json.dumps({"title": "Title"})) == "Title"
    assert subject._title(json.dumps({"title": "  "})) is None
    dot = VisualQueryVector(
        profile_id="p",
        shared_space_id="s",
        dimensions=2,
        metric=VisualVectorMetric.DOT,
        values=(1.0, 2.0),
    )
    assert subject._similarity(dot, (3.0, 4.0)) == 11.0
    cosine = VisualQueryVector(
        profile_id="p",
        shared_space_id="s",
        dimensions=2,
        metric=VisualVectorMetric.COSINE,
        values=(1.0, 0.0),
    )
    assert subject._similarity(cosine, (1.0, 0.0)) == 1.0
    with pytest.raises(IntegrityError, match="zero magnitude"):
        subject._similarity(cosine, (0.0, 0.0))
