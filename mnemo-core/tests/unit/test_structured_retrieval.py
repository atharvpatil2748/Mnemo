"""Phase 8.5.7 structured retrieval, aggregation, security, and bounds tests."""

from __future__ import annotations

import asyncio
import functools
import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from mnemo.interfaces import ConflictError, ContractValidationError, IntegrityError
from mnemo.models import (
    AdvancedRetrievalCandidate,
    AdvancedRetrievalMode,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DeduplicationPolicy,
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    EvidenceRepresentation,
    ExpansionPolicy,
    ExtractedStructuredRecord,
    FrozenMetadata,
    Notebook,
    ParsedDocument,
    PositionalScopeV2,
    RankingPolicyV2,
    RepresentationReportV2,
    RepresentationSearchStatus,
    RetrievalBudgetsV2,
    RetrievalCompleteness,
    RetrievalDiagnosticsV2,
    RetrievalPathEvidenceV2,
    RetrievalPlanV2,
    RetrievalResultSetV1,
    RetrievalScopeV2,
    Source,
    StructuredAggregation,
    StructuredAggregationOperation,
    StructuredBudgets,
    StructuredColumnObservation,
    StructuredDiagnostics,
    StructuredEvidence,
    StructuredField,
    StructuredFieldType,
    StructuredFilter,
    StructuredFilterOperator,
    StructuredNullOrder,
    StructuredQueryV1,
    StructuredResult,
    StructuredResultMetadata,
    StructuredSchemaConfidence,
    StructuredSchemaObservation,
    StructuredSort,
    StructuredSortDirection,
    StructuredValue,
    StructuredValueStatus,
    TableBlock,
    TextBlock,
    advanced_candidate_id,
    structured_record_id,
)
from mnemo.retrieval import (
    CanonicalTableEvidenceExtractor,
    DelimitedTableEvidenceExtractor,
    ProjectedTableEvidenceExtractor,
    StructuredRetrievalService,
    compare_structured_values,
    observe_table_schema,
)
from mnemo.storage.sqlite import SQLiteStore
from pydantic import ValidationError

NOTEBOOK = UUID(int=1)


def async_test(function):  # type: ignore[no-untyped-def]
    @functools.wraps(function)
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        return asyncio.run(function(*args, **kwargs))

    return wrapper


def _plan(*, scope: RetrievalScopeV2 | None = None) -> RetrievalPlanV2:
    return RetrievalPlanV2(
        query="students and CPI",
        mode=AdvancedRetrievalMode.RANKED,
        scope=scope or RetrievalScopeV2(notebook_id=NOTEBOOK),
        position=PositionalScopeV2(),
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        budgets=RetrievalBudgetsV2(
            recall_limit=20,
            expansion_limit=0,
            fusion_limit=20,
            rerank_limit=20,
            result_limit=20,
            max_serialized_bytes=100_000,
            max_content_characters=100_000,
        ),
        expansion_policy=ExpansionPolicy.NONE,
        deduplication_policy=DeduplicationPolicy.AUTHORITATIVE_IDENTITY,
        ranking_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
    )


def _candidate(
    index: int,
    content: str = "Name\tCPI\nAsha\t8.74 CPI",
    *,
    notebook_id: UUID = NOTEBOOK,
    document_id: UUID | None = None,
    version_id: UUID | None = None,
    source_id: UUID | None = None,
    locator: FrozenMetadata | None = None,
) -> AdvancedRetrievalCandidate:
    document_id = document_id or UUID(int=100 + index)
    version_id = version_id or UUID(int=200 + index)
    source_id = source_id or UUID(int=300 + index)
    chunk = Chunk(
        id=f"{index:064x}",
        document_id=document_id,
        version_id=version_id,
        text=content,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index, page_number=1),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Records",),
        metadata=FrozenMetadata(),
    )
    return AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            document_id=document_id,
            version_id=version_id,
            chunk_id=chunk.id,
            occurrence_id=None,
            derivation_id=None,
        ),
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        chunk=chunk,
        occurrence_id=None,
        derivation_id=None,
        locator=locator or FrozenMetadata({"page": 1, "block": index}),
        document_title=f"Dataset {index}",
        content=content,
        paths=(
            RetrievalPathEvidenceV2(
                path="sparse", source_rank=index, source_score=1 / index, title_match=index == 1
            ),
        ),
        fused_score=1 / index,
        final_rank=index,
    )


def _retrieval(
    candidates: tuple[AdvancedRetrievalCandidate, ...],
    *,
    plan: RetrievalPlanV2 | None = None,
    completeness: RetrievalCompleteness = RetrievalCompleteness.COMPLETE,
) -> RetrievalResultSetV1:
    active = plan or _plan()
    ranked = tuple(
        replace(candidate, final_rank=index) for index, candidate in enumerate(candidates, 1)
    )
    return RetrievalResultSetV1(
        query_fingerprint=active.fingerprint,
        snapshot_identity="a" * 64,
        ordering_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
        completeness=completeness,
        results=ranked,
        examined_count=len(ranked),
        returned_count=len(ranked),
        next_cursor="cursor" if completeness is RetrievalCompleteness.TRUNCATED else None,
        diagnostics=RetrievalDiagnosticsV2(
            mode=AdvancedRetrievalMode.RANKED,
            recalled=len(ranked),
            expanded=0,
            deduplicated=len(ranked),
            fused=len(ranked),
            reranked=len(ranked),
            returned=len(ranked),
            serialized_bytes=100,
            content_characters=sum(len(item.content or "") for item in ranked),
            truncated=completeness is RetrievalCompleteness.TRUNCATED,
            truncation_reason=(
                "candidate_budget" if completeness is RetrievalCompleteness.TRUNCATED else None
            ),
            elapsed_milliseconds=1,
            representation_reports=(
                RepresentationReportV2(
                    representation=EvidenceRepresentation.CANONICAL_TEXT,
                    status=RepresentationSearchStatus.SEARCHED,
                    examined=len(ranked),
                    returned=len(ranked),
                    exhausted=completeness is not RetrievalCompleteness.TRUNCATED,
                ),
            ),
        ),
    )


def _fields() -> tuple[StructuredField, ...]:
    return (
        StructuredField(name="student", source_name="Name", field_type=StructuredFieldType.STRING),
        StructuredField(
            name="cpi", source_name="CPI", field_type=StructuredFieldType.DECIMAL, unit="CPI"
        ),
    )


def _query(**changes: object) -> StructuredQueryV1:
    values: dict[str, object] = {"retrieval_plan": _plan(), "fields": _fields()}
    values.update(changes)
    return StructuredQueryV1(**values)


class MappingExtractor:
    def __init__(self, records: dict[UUID, tuple[ExtractedStructuredRecord, ...]]) -> None:
        self.records = records
        self.calls: list[tuple[UUID, int]] = []

    async def extract(self, candidate, fields, *, limit):  # type: ignore[no-untyped-def]
        del fields
        self.calls.append((candidate.candidate_id, limit))
        return self.records.get(candidate.candidate_id, ())[:limit]


def _raw(
    candidate: AdvancedRetrievalCandidate, ordinal: int, **values: object
) -> ExtractedStructuredRecord:
    return ExtractedStructuredRecord(
        candidate_id=candidate.candidate_id,
        row_ordinal=ordinal,
        values=FrozenMetadata(values),
        cell_locators=FrozenMetadata(
            {
                name: {"row": ordinal, "cell": f"{chr(65 + index)}{ordinal + 1}"}
                for index, name in enumerate(values)
            }
        ),
        extraction_method="synthetic_table/v1",
    )


@async_test
async def test_delimited_extraction_normalization_filter_sort_group_and_aggregate() -> None:
    candidate = _candidate(
        1, "Name\tCPI\tDepartment\nAsha\t8.74 CPI\tME\nBela\t9.20 CPI\tEE\nCara\t"
    )
    fields = (
        *_fields(),
        StructuredField(
            name="department", source_name="Department", field_type=StructuredFieldType.STRING
        ),
    )
    query = _query(
        fields=fields,
        filters=(
            StructuredFilter(field="cpi", operator=StructuredFilterOperator.GT, value="8.5 CPI"),
        ),
        group_by=("department",),
        aggregations=(
            StructuredAggregation(name="students", operation=StructuredAggregationOperation.COUNT),
            StructuredAggregation(
                name="average", operation=StructuredAggregationOperation.AVG, field="cpi"
            ),
        ),
        order_by=(StructuredSort(field="cpi", direction=StructuredSortDirection.DESC),),
    )
    result = await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
        query, _retrieval((candidate,))
    )
    assert [record.value_for("student").value for record in result.records] == ["Bela", "Asha"]
    assert [group.keys[0].value for group in result.groups] == ["EE", "ME"]
    assert result.groups[0].aggregates[1].value == Decimal("9.20")
    assert result.records[0].value_for("cpi").unit == "CPI"
    assert result.records[0].value_for("cpi").evidence[0].locator["column"] == 1
    assert result.records[0].value_for("cpi").evidence[0].locator["row"] == 2
    assert result.completeness is RetrievalCompleteness.COMPLETE
    assert result.metadata.candidate_universe_count == 1
    assert result.metadata.extracted_row_universe_count == 3
    assert result.metadata.operations == (
        "extract",
        "normalize",
        "validate",
        "filter",
        "sort",
        "group",
        "aggregate",
    )


@async_test
async def test_canonical_table_ir_extractor_uses_exact_version_and_parser_provenance() -> None:
    candidate = _candidate(1, "rendered text remains unchanged")
    parsed = ParsedDocument(
        blocks=(
            TextBlock(ordinal=0, text="Introduction"),
            TableBlock(
                ordinal=1,
                page_number=4,
                rows=(("Name", "CPI"), ("Asha", "8.74 CPI"), ("Bela", "9 CPI")),
                header_row_count=1,
            ),
        ),
        metadata=DocumentMetadata(content_hash="b" * 64, page_count=4),
        language="en",
        doc_type=DocType.GENERIC,
    )

    class Reader:
        async def get_parsed_document(self, version_id):  # type: ignore[no-untyped-def]
            assert version_id == candidate.version_id
            return parsed

    result = await StructuredRetrievalService(CanonicalTableEvidenceExtractor(Reader())).execute(
        _query(), _retrieval((candidate,))
    )
    assert [item.value_for("student").value for item in result.records] == ["Asha", "Bela"]
    locator = result.records[0].value_for("cpi").evidence[0].locator
    assert locator["page"] == 4 and locator["block_ordinal"] == 1 and locator["column"] == 1
    assert candidate.chunk is not None and candidate.chunk.text == "rendered text remains unchanged"


@async_test
async def test_canonical_table_ir_extractor_refuses_missing_ambiguous_or_headerless_ir() -> None:
    candidate = _candidate(1)

    class Reader:
        def __init__(self, parsed):  # type: ignore[no-untyped-def]
            self.parsed = parsed

        async def get_parsed_document(self, version_id):  # type: ignore[no-untyped-def]
            del version_id
            return self.parsed

    assert not (
        await CanonicalTableEvidenceExtractor(Reader(None)).extract(candidate, _fields(), limit=10)
    )
    headerless = ParsedDocument(
        blocks=(
            TextBlock(ordinal=0, text="x"),
            TableBlock(ordinal=1, rows=(("A", "8"),), header_row_count=0),
        ),
        metadata=DocumentMetadata(content_hash="c" * 64),
        language="en",
        doc_type=DocType.GENERIC,
    )
    assert not (
        await CanonicalTableEvidenceExtractor(Reader(headerless)).extract(
            candidate, _fields(), limit=10
        )
    )
    no_chunk = replace(
        candidate,
        chunk=None,
        occurrence_id=UUID(int=999),
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            document_id=candidate.document_id,
            version_id=candidate.version_id,
            chunk_id=None,
            occurrence_id=UUID(int=999),
            derivation_id=None,
        ),
    )
    assert not (
        await CanonicalTableEvidenceExtractor(Reader(headerless)).extract(
            no_chunk, _fields(), limit=0
        )
    )


@async_test
async def test_sqlite_projection_is_versioned_idempotent_and_parameterized(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "structured.db")
    await store.open()
    candidate = _candidate(1)
    now = datetime(2026, 8, 25, tzinfo=UTC)
    metadata = DocumentMetadata(content_hash="d" * 64)
    version = DocumentVersion(
        version_id=candidate.version_id,
        document_id=candidate.document_id,
        content_hash="d" * 64,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    await store.upsert_document(
        Document(
            document_id=candidate.document_id,
            versions=(version,),
            current_version_id=version.version_id,
            current_hash=version.content_hash,
            status=DocumentStatus.INDEXED,
            created_at=now,
            updated_at=now,
        )
    )
    parsed = ParsedDocument(
        blocks=(
            TextBlock(ordinal=0, text="intro"),
            TableBlock(
                ordinal=1,
                page_number=2,
                rows=(("Name", "CPI"), ("O'Reilly", "8.75 CPI")),
                header_row_count=1,
            ),
        ),
        metadata=metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )
    assert await store.project_structured_document(version.version_id, parsed)
    assert not await store.project_structured_document(version.version_id, parsed)
    result = await StructuredRetrievalService(ProjectedTableEvidenceExtractor(store)).execute(
        _query(), _retrieval((candidate,))
    )
    assert result.records[0].value_for("student").value == "O'Reilly"
    assert result.records[0].value_for("cpi").value == Decimal("8.75")
    assert result.records[0].evidence[0].version_id == version.version_id
    await store.close()


@async_test
async def test_wp08_catalog_is_authorized_generation_bound_and_path_safe(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "wp08-catalog.db")
    await store.open()
    candidate = _candidate(1)
    now = datetime(2026, 8, 27, tzinfo=UTC)
    await store.upsert_notebook(
        Notebook(notebook_id=NOTEBOOK, title="Structured", created_at=now, updated_at=now)
    )
    metadata = DocumentMetadata(content_hash="9" * 64, title="Students")
    version = DocumentVersion(
        version_id=candidate.version_id,
        document_id=candidate.document_id,
        content_hash="9" * 64,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    await store.upsert_document(
        Document(
            document_id=candidate.document_id,
            versions=(version,),
            current_version_id=version.version_id,
            current_hash=version.content_hash,
            status=DocumentStatus.INDEXED,
            created_at=now,
            updated_at=now,
        )
    )
    await store.upsert_source(
        Source(
            source_id=candidate.source_id,
            notebook_id=NOTEBOOK,
            document_id=candidate.document_id,
            created_at=now,
        )
    )
    assert candidate.chunk is not None
    await store.upsert_chunks((candidate.chunk,))
    parsed = ParsedDocument(
        blocks=(
            TextBlock(ordinal=0, text="intro"),
            TableBlock(
                ordinal=1,
                page_number=2,
                rows=(("Name", "CPI"), ("Asha", "8.95"), ("Atharv", "9.20")),
                header_row_count=1,
            ),
        ),
        metadata=metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )
    assert await store.project_structured_document(version.version_id, parsed)
    scope = RetrievalScopeV2(
        notebook_id=NOTEBOOK,
        document_ids=(candidate.document_id,),
        version_ids=(candidate.version_id,),
    )
    catalog = await store.list_structured_datasets(scope=scope, schema_scan_limit=100)
    assert await store.structured_projection_ready()
    assert await store.active_structured_generation_identity()
    assert len(catalog.datasets) == 1
    dataset = catalog.datasets[0]
    assert dataset.readiness.value == "ready"
    assert [(item.field.name, item.field.field_type.value) for item in dataset.fields] == [
        ("Name", "string"),
        ("CPI", "decimal"),
    ]
    records = await store.extract_structured_dataset_records(
        notebook_id=NOTEBOOK,
        dataset_id=dataset.dataset_id,
        candidate_id=dataset.candidate.candidate_id,
        fields=tuple(item.field for item in dataset.fields),
        limit=10,
    )
    assert [item.values["Name"] for item in records] == ["Asha", "Atharv"]
    db = store._require_open()
    await db.execute(
        "UPDATE index_generation_coverage SET completeness='partial' WHERE generation_id=?",
        (str(dataset.generation_id),),
    )
    await db.commit()
    incomplete = await store.list_structured_datasets(scope=scope, schema_scan_limit=1)
    assert incomplete.datasets[0].readiness.value == "inactive"
    assert not await store.structured_projection_ready()
    foreign = await store.list_structured_datasets(
        scope=RetrievalScopeV2(notebook_id=UUID(int=999), version_ids=(candidate.version_id,)),
        schema_scan_limit=100,
    )
    assert not foreign.datasets and foreign.unavailable_version_ids == (candidate.version_id,)
    await store.close()


def test_schema_11_migration_is_repeated_and_rollback_safe(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import mnemo.storage.sqlite as sqlite_module

    path = tmp_path / "migration.db"
    store = SQLiteStore(path)
    asyncio.run(store.open())
    asyncio.run(store.close())
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (16,)
        db.execute("DROP TABLE structured_table_cells")
        db.execute("DROP TABLE structured_table_projections")
        db.execute("UPDATE schema_versions SET version=10 WHERE version=16")
        db.commit()
    repeated = SQLiteStore(path)
    asyncio.run(repeated.open())
    asyncio.run(repeated.close())
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (16,)
        db.execute("DROP TABLE structured_table_cells")
        db.execute("DROP TABLE structured_table_projections")
        db.execute("DELETE FROM schema_versions WHERE version>=11")
        db.commit()
    monkeypatch.setattr(
        sqlite_module,
        "STRUCTURED_SCHEMA_STATEMENTS",
        (*sqlite_module.STRUCTURED_SCHEMA_STATEMENTS, "CREATE TABL broken"),
    )
    failing = SQLiteStore(path)
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(failing.open())
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (10,)
        assert db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'structured_table_%'"
        ).fetchone() == (0,)


def test_schema_discovery_is_typed_conservative_and_rejects_ambiguous_headers() -> None:
    observed = observe_table_schema(
        TableBlock(
            ordinal=0,
            rows=(
                ("Count", "CPI", "Active", "Date", "At", "Notes", "Optional"),
                ("2", "8.75", "true", "2026-08-25", "2026-08-25T10:30:00", "ok", ""),
                ("3", "9.00", "false", "2026-08-26", "2026-08-26T11:30:00", "good", ""),
            ),
            header_row_count=1,
        )
    )
    assert tuple(column.observed_type for column in observed.columns) == (
        StructuredFieldType.INTEGER,
        StructuredFieldType.DECIMAL,
        StructuredFieldType.BOOLEAN,
        StructuredFieldType.DATE,
        StructuredFieldType.DATETIME,
        StructuredFieldType.STRING,
        StructuredFieldType.STRING,
    )
    assert observed.columns[0].confidence is StructuredSchemaConfidence.EXACT
    assert observed.columns[5].confidence is StructuredSchemaConfidence.OBSERVED
    assert observed.columns[6].confidence is StructuredSchemaConfidence.AMBIGUOUS
    assert observed.row_count == 2
    with pytest.raises(ContractValidationError):
        observe_table_schema(TableBlock(ordinal=0, rows=(("x",),), header_row_count=0))
    with pytest.raises(ContractValidationError):
        observe_table_schema(
            TableBlock(ordinal=0, rows=(("Name", "name"), ("a", "b")), header_row_count=1)
        )


@async_test
async def test_structured_projection_failure_recovery_and_read_bounds(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import mnemo.storage.structured as structured_storage

    store = SQLiteStore(tmp_path / "projection-recovery.db")
    await store.open()
    missing_version = UUID(int=777)
    parsed = ParsedDocument(
        blocks=(
            TableBlock(
                ordinal=0,
                rows=(("Name", "CPI"), ("Asha", "8.74")),
                header_row_count=1,
            ),
        ),
        metadata=DocumentMetadata(content_hash="e" * 64),
        language="en",
        doc_type=DocType.GENERIC,
    )
    assert not await store.project_structured_document(missing_version, parsed)

    candidate = _candidate(77)
    now = datetime(2026, 8, 25, tzinfo=UTC)
    version = DocumentVersion(
        version_id=candidate.version_id,
        document_id=candidate.document_id,
        content_hash="e" * 64,
        metadata=parsed.metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    await store.upsert_document(
        Document(
            document_id=candidate.document_id,
            versions=(version,),
            current_version_id=version.version_id,
            current_hash=version.content_hash,
            status=DocumentStatus.INDEXED,
            created_at=now,
            updated_at=now,
        )
    )
    original = structured_storage._table_material
    monkeypatch.setattr(
        structured_storage,
        "_table_material",
        lambda block: (_ for _ in ()).throw(RuntimeError("injected")),
    )
    with pytest.raises(RuntimeError, match="injected"):
        await store.project_structured_document(version.version_id, parsed)
    monkeypatch.setattr(structured_storage, "_table_material", original)
    assert await store.project_structured_document(version.version_id, parsed)

    db = store._require_open()
    await db.execute(
        "UPDATE index_generations SET state='failed' WHERE capability='structured_table'"
    )
    await db.commit()
    assert await store.project_structured_document(version.version_id, parsed)
    changed = replace(
        parsed,
        blocks=(
            TableBlock(
                ordinal=0,
                rows=(("Name", "CPI"), ("Asha", "9.00")),
                header_row_count=1,
            ),
        ),
    )
    with pytest.raises(ConflictError):
        await store.project_structured_document(version.version_id, changed)
    occurrence_id = UUID(int=778)
    no_chunk = replace(
        candidate,
        chunk=None,
        occurrence_id=occurrence_id,
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            document_id=candidate.document_id,
            version_id=candidate.version_id,
            chunk_id=None,
            occurrence_id=occurrence_id,
            derivation_id=None,
        ),
    )
    assert not await store.extract_projected_structured_records(no_chunk, _fields(), limit=10)
    assert not await store.extract_projected_structured_records(candidate, _fields(), limit=0)
    assert not await store.extract_projected_structured_records(
        candidate,
        (StructuredField(name="unknown", field_type=StructuredFieldType.STRING),),
        limit=10,
    )
    await store.close()


@async_test
async def test_multi_document_provenance_and_document_grouping() -> None:
    first, second = _candidate(1), _candidate(2)
    extractor = MappingExtractor(
        {
            first.candidate_id: (_raw(first, 1, student="A", cpi="8.0 CPI"),),
            second.candidate_id: (_raw(second, 1, student="B", cpi="9.0 CPI"),),
        }
    )
    result = await StructuredRetrievalService(extractor).execute(
        _query(
            aggregations=(
                StructuredAggregation(
                    name="average", operation=StructuredAggregationOperation.AVG, field="cpi"
                ),
            )
        ),
        _retrieval((first, second)),
    )
    aggregate = result.groups[0].aggregates[0]
    assert aggregate.value == Decimal("8.5")
    assert {item.document_id for item in aggregate.evidence} == {
        first.document_id,
        second.document_id,
    }
    assert {item.version_id for item in aggregate.evidence} == {first.version_id, second.version_id}


@async_test
async def test_document_source_version_and_position_are_typed_group_fields() -> None:
    first = _candidate(1, locator=FrozenMetadata({"page": 7, "sheet": "Data"}))
    second = _candidate(2, locator=FrozenMetadata({"page": 8, "sheet": "Archive"}))
    fields = (
        StructuredField(name="student", field_type=StructuredFieldType.STRING),
        StructuredField(
            name="document", source_name="$document_id", field_type=StructuredFieldType.STRING
        ),
        StructuredField(
            name="source", source_name="$source_id", field_type=StructuredFieldType.STRING
        ),
        StructuredField(
            name="version", source_name="$version_id", field_type=StructuredFieldType.STRING
        ),
        StructuredField(name="page", source_name="$page", field_type=StructuredFieldType.INTEGER),
    )
    extractor = MappingExtractor(
        {
            first.candidate_id: (_raw(first, 1, student="A"),),
            second.candidate_id: (_raw(second, 1, student="B"),),
        }
    )
    result = await StructuredRetrievalService(extractor).execute(
        _query(
            fields=fields,
            group_by=("document",),
            aggregations=(
                StructuredAggregation(name="count", operation=StructuredAggregationOperation.COUNT),
            ),
        ),
        _retrieval((first, second)),
    )
    assert {item.keys[0].value for item in result.groups} == {
        str(first.document_id),
        str(second.document_id),
    }
    assert result.records[0].value_for("page").value == 7
    assert result.records[0].value_for("source").value == str(first.source_id)


@async_test
async def test_missing_invalid_uncertain_and_unavailable_are_not_zero() -> None:
    candidate = _candidate(1)
    extractor = MappingExtractor(
        {
            candidate.candidate_id: (
                _raw(candidate, 1, student="missing", cpi=""),
                _raw(candidate, 2, student="invalid", cpi="excellent"),
                _raw(
                    candidate,
                    3,
                    student="uncertain",
                    cpi={"status": "value_uncertain", "reason": "blurred"},
                ),
                _raw(candidate, 4, student="unavailable", cpi={"status": "value_unavailable"}),
            )
        }
    )
    result = await StructuredRetrievalService(extractor).execute(
        _query(
            aggregations=(
                StructuredAggregation(
                    name="sum", operation=StructuredAggregationOperation.SUM, field="cpi"
                ),
            )
        ),
        _retrieval((candidate,)),
    )
    assert [record.value_for("cpi").status for record in result.records] == [
        StructuredValueStatus.VALUE_MISSING,
        StructuredValueStatus.VALUE_INVALID,
        StructuredValueStatus.VALUE_UNCERTAIN,
        StructuredValueStatus.VALUE_UNAVAILABLE,
    ]
    aggregate = result.groups[0].aggregates[0]
    assert aggregate.status is StructuredValueStatus.VALUE_MISSING and aggregate.value is None


@async_test
async def test_distinct_collapses_value_but_preserves_all_evidence() -> None:
    first, second = _candidate(1), _candidate(2)
    extractor = MappingExtractor(
        {
            first.candidate_id: (_raw(first, 1, student="C++", cpi="8 CPI"),),
            second.candidate_id: (_raw(second, 1, student="C++", cpi="9 CPI"),),
        }
    )
    result = await StructuredRetrievalService(extractor).execute(
        _query(distinct_fields=("student",)), _retrieval((first, second))
    )
    assert len(result.records) == 1
    assert {item.document_id for item in result.records[0].value_for("student").evidence} == {
        first.document_id,
        second.document_id,
    }


@async_test
async def test_duplicate_extraction_path_deduplicates_by_record_identity() -> None:
    candidate = _candidate(1)
    record = _raw(candidate, 1, student="A", cpi="8 CPI")
    result = await StructuredRetrievalService(
        MappingExtractor({candidate.candidate_id: (record, record)})
    ).execute(_query(), _retrieval((candidate,)))
    assert len(result.records) == 1
    assert result.records[0].record_id == structured_record_id(candidate.candidate_id, 1)


@async_test
@pytest.mark.parametrize(
    ("incoming", "expected"),
    [
        (RetrievalCompleteness.COMPLETE, RetrievalCompleteness.COMPLETE),
        (RetrievalCompleteness.PARTIAL, RetrievalCompleteness.PARTIAL),
        (RetrievalCompleteness.UNKNOWN, RetrievalCompleteness.UNKNOWN),
        (RetrievalCompleteness.TRUNCATED, RetrievalCompleteness.TRUNCATED),
    ],
)
async def test_retrieval_completeness_is_never_upgraded(incoming, expected) -> None:  # type: ignore[no-untyped-def]
    candidate = _candidate(1)
    result = await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
        _query(), _retrieval((candidate,), completeness=incoming)
    )
    assert result.retrieval_completeness is incoming
    assert result.completeness is expected


@async_test
async def test_empty_extraction_reports_empty_only_for_complete_retrieval() -> None:
    candidate = _candidate(1, "ordinary prose without a table")
    complete = await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
        _query(), _retrieval((candidate,))
    )
    partial = await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
        _query(), _retrieval((candidate,), completeness=RetrievalCompleteness.PARTIAL)
    )
    assert complete.completeness is RetrievalCompleteness.EMPTY
    assert partial.completeness is RetrievalCompleteness.PARTIAL


@async_test
async def test_pagination_and_output_budget_report_truncation() -> None:
    candidate = _candidate(1, "Name\tCPI\nA\t8 CPI\nB\t9 CPI\nC\t10 CPI")
    paged = await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
        _query(limit=1), _retrieval((candidate,))
    )
    assert paged.completeness is RetrievalCompleteness.TRUNCATED
    assert paged.next_offset == 1
    tiny = await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
        _query(budgets=StructuredBudgets(max_output_bytes=256, max_output_tokens=64)),
        _retrieval((candidate,)),
    )
    assert tiny.completeness is RetrievalCompleteness.TRUNCATED
    assert "max_output_size" in tiny.diagnostics.truncation_reasons


@async_test
async def test_extractor_record_budget_prevents_full_materialization() -> None:
    candidates = (_candidate(1), _candidate(2))
    extractor = MappingExtractor(
        {
            candidate.candidate_id: tuple(
                _raw(candidate, i, student=str(i), cpi="8 CPI") for i in range(20)
            )
            for candidate in candidates
        }
    )
    result = await StructuredRetrievalService(extractor).execute(
        _query(budgets=StructuredBudgets(max_records=3)), _retrieval(candidates)
    )
    assert result.diagnostics.extracted_records == 3
    assert extractor.calls == [(candidates[0].candidate_id, 3)]


@async_test
async def test_hostile_extractor_cannot_inject_candidate_or_exceed_limit() -> None:
    candidate, foreign = _candidate(1), _candidate(2)

    class ForeignExtractor:
        async def extract(self, candidate, fields, *, limit):  # type: ignore[no-untyped-def]
            del candidate, fields, limit
            return (_raw(foreign, 1, student="X", cpi="9 CPI"),)

    with pytest.raises(IntegrityError, match="changed candidate"):
        await StructuredRetrievalService(ForeignExtractor()).execute(
            _query(), _retrieval((candidate,))
        )

    class OverflowExtractor:
        async def extract(self, current, fields, *, limit):  # type: ignore[no-untyped-def]
            del fields
            return tuple(_raw(current, i, student="X", cpi="9 CPI") for i in range(limit + 1))

    with pytest.raises(IntegrityError, match="exceeded"):
        await StructuredRetrievalService(OverflowExtractor()).execute(
            _query(budgets=StructuredBudgets(max_records=2)), _retrieval((candidate,))
        )


@async_test
async def test_notebook_and_allowlisted_scope_are_enforced() -> None:
    foreign = _candidate(1, notebook_id=UUID(int=999))
    with pytest.raises(IntegrityError, match="notebook"):
        await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
            _query(), _retrieval((foreign,))
        )
    candidate = _candidate(1)
    scoped = _plan(scope=RetrievalScopeV2(notebook_id=NOTEBOOK, document_ids=(UUID(int=999),)))
    with pytest.raises(IntegrityError, match="document"):
        await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
            _query(retrieval_plan=scoped), _retrieval((candidate,), plan=scoped)
        )


@async_test
async def test_retrieval_fingerprint_mismatch_fails_closed() -> None:
    candidate = _candidate(1)
    with pytest.raises(ContractValidationError, match="does not match"):
        await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
            _query(),
            _retrieval((candidate,), plan=_plan(scope=RetrievalScopeV2(notebook_id=UUID(int=2)))),
        )


def test_typed_ast_rejects_unknown_fields_duplicate_names_and_executable_nodes() -> None:
    with pytest.raises(ValidationError, match="unknown fields"):
        _query(
            filters=(
                StructuredFilter(field="unknown", operator=StructuredFilterOperator.EQ, value="x"),
            )
        )
    with pytest.raises(ValidationError, match="uniquely named"):
        _query(fields=(_fields()[0], _fields()[0]))
    with pytest.raises(ValidationError, match="extra_forbidden"):
        StructuredQueryV1.model_validate(
            {**_query().model_dump(), "expression": "__import__('os').system('bad')"}
        )
    with pytest.raises(ValidationError):
        StructuredFilter.model_validate({"field": "cpi", "operator": "eval", "value": "1"})


def test_query_validates_filter_aggregation_and_field_contracts() -> None:
    with pytest.raises(ValidationError):
        StructuredFilter(field="cpi", operator=StructuredFilterOperator.IS_PRESENT, value=1)
    with pytest.raises(ValidationError):
        StructuredFilter(field="cpi", operator=StructuredFilterOperator.IN, value="1")
    with pytest.raises(ValidationError):
        StructuredAggregation(name="sum", operation=StructuredAggregationOperation.SUM)
    with pytest.raises(ValidationError):
        StructuredField(name="kind", field_type=StructuredFieldType.ENUM)
    with pytest.raises(ValidationError):
        StructuredField(name="kind", field_type=StructuredFieldType.STRING, enum_values=("x",))
    assert _query().fingerprint == _query().fingerprint
    assert _query(limit=1).fingerprint != _query(limit=2).fingerprint


@async_test
async def test_invalid_filter_type_and_unsupported_contains_are_typed_errors() -> None:
    candidate = _candidate(1)
    with pytest.raises(ContractValidationError, match="incompatible"):
        await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
            _query(
                filters=(
                    StructuredFilter(
                        field="cpi", operator=StructuredFilterOperator.GT, value="excellent"
                    ),
                )
            ),
            _retrieval((candidate,)),
        )
    with pytest.raises(ContractValidationError, match="CONTAINS"):
        await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
            _query(
                filters=(
                    StructuredFilter(
                        field="cpi", operator=StructuredFilterOperator.CONTAINS, value="8"
                    ),
                )
            ),
            _retrieval((candidate,)),
        )


@async_test
async def test_all_aggregations_have_deterministic_missing_aware_semantics() -> None:
    candidate = _candidate(1)
    extractor = MappingExtractor(
        {
            candidate.candidate_id: tuple(
                _raw(candidate, i, student=name, cpi=cpi)
                for i, (name, cpi) in enumerate((("A", "8 CPI"), ("B", "9 CPI"), ("B", "")), 1)
            )
        }
    )
    operations = tuple(
        StructuredAggregation(
            name=operation.value,
            operation=operation,
            field=None if operation is StructuredAggregationOperation.COUNT else "cpi",
        )
        for operation in StructuredAggregationOperation
    )
    result = await StructuredRetrievalService(extractor).execute(
        _query(aggregations=operations), _retrieval((candidate,))
    )
    values = {item.name: item.value for item in result.groups[0].aggregates}
    assert values == {
        "count": 3,
        "distinct_count": 2,
        "sum": Decimal("17"),
        "min": Decimal("8"),
        "max": Decimal("9"),
        "avg": Decimal("8.5"),
    }


@async_test
async def test_non_numeric_aggregation_is_rejected() -> None:
    candidate = _candidate(1)
    with pytest.raises(ContractValidationError, match="numeric"):
        await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
            _query(
                aggregations=(
                    StructuredAggregation(
                        name="sum", operation=StructuredAggregationOperation.SUM, field="student"
                    ),
                )
            ),
            _retrieval((candidate,)),
        )


@async_test
async def test_sort_null_order_and_stable_tie_break() -> None:
    candidate = _candidate(1)
    extractor = MappingExtractor(
        {
            candidate.candidate_id: (
                _raw(candidate, 1, student="missing", cpi=""),
                _raw(candidate, 2, student="B", cpi="8 CPI"),
                _raw(candidate, 3, student="A", cpi="8 CPI"),
            )
        }
    )
    result = await StructuredRetrievalService(extractor).execute(
        _query(order_by=(StructuredSort(field="cpi", null_order=StructuredNullOrder.FIRST),)),
        _retrieval((candidate,)),
    )
    assert result.records[0].value_for("student").value == "missing"
    assert [item.record_id for item in result.records[1:]] == sorted(
        item.record_id for item in result.records[1:]
    )


def test_comparison_requires_present_compatible_types_and_units() -> None:
    evidence = StructuredEvidence(
        candidate_id=UUID(int=1),
        notebook_id=NOTEBOOK,
        source_id=UUID(int=2),
        document_id=UUID(int=3),
        version_id=UUID(int=4),
        chunk_id="a" * 64,
        occurrence_id=None,
        derivation_id=None,
        locator=FrozenMetadata(),
        retrieval_paths=("sparse",),
        extraction_method="test",
    )
    left = StructuredValue(
        field="cpi",
        field_type=StructuredFieldType.DECIMAL,
        status=StructuredValueStatus.VALUE_PRESENT,
        value=Decimal("8.7"),
        unit="CPI",
        evidence=(evidence,),
    )
    right = replace(left, value=Decimal("9.0"))
    assert compare_structured_values(left, right) == -1
    with pytest.raises(ContractValidationError, match="types"):
        compare_structured_values(
            left, replace(right, field_type=StructuredFieldType.STRING, value="excellent")
        )
    with pytest.raises(ContractValidationError, match="units"):
        compare_structured_values(left, replace(right, unit="GPA"))
    with pytest.raises(ContractValidationError, match="present"):
        compare_structured_values(
            left,
            replace(right, status=StructuredValueStatus.VALUE_MISSING, value=None, evidence=()),
        )


def test_structured_contract_models_reject_invalid_identity_and_count_boundaries() -> None:
    """Structured evidence objects fail closed on malformed ordinals, counts, and paging."""
    evidence = StructuredEvidence(
        candidate_id=UUID(int=1),
        notebook_id=NOTEBOOK,
        source_id=UUID(int=2),
        document_id=UUID(int=3),
        version_id=UUID(int=4),
        chunk_id="a" * 64,
        occurrence_id=None,
        derivation_id=None,
        locator=FrozenMetadata(),
        retrieval_paths=("sparse",),
        extraction_method="test",
    )
    column = StructuredColumnObservation(
        name="value",
        column_index=0,
        observed_type=StructuredFieldType.STRING,
        confidence=StructuredSchemaConfidence.EXACT,
        non_missing_count=1,
    )
    schema = StructuredSchemaObservation(
        generation="b" * 64,
        columns=(column,),
        row_count=1,
    )
    present = StructuredValue(
        field="value",
        field_type=StructuredFieldType.STRING,
        status=StructuredValueStatus.VALUE_PRESENT,
        value="ok",
        unit=None,
        evidence=(evidence,),
    )
    metadata = StructuredResultMetadata(
        schema_generation=schema.generation,
        retrieval_snapshot_identity="c" * 64,
        candidate_universe_count=1,
        extracted_row_universe_count=1,
        matched_count=1,
        returned_count=0,
        operations=("select",),
        provenance_truncated=False,
    )
    diagnostics = StructuredDiagnostics(
        candidates_examined=1,
        extracted_records=1,
        deduplicated_records=1,
        filtered_records=0,
        returned_records=0,
        group_count=0,
        evidence_references=1,
        output_bytes=1,
        truncated=False,
        truncation_reasons=(),
        stage_milliseconds=FrozenMetadata(),
    )
    result = StructuredResult(
        query_fingerprint="d" * 64,
        retrieval_fingerprint="e" * 64,
        retrieval_completeness=RetrievalCompleteness.COMPLETE,
        completeness=RetrievalCompleteness.COMPLETE,
        records=(),
        groups=(),
        matched_count=1,
        returned_count=0,
        next_offset=None,
        metadata=metadata,
        diagnostics=diagnostics,
    )

    invalid_cases = (
        lambda: replace(column, column_index=True),
        lambda: replace(column, non_missing_count=-1),
        lambda: replace(schema, row_count=True),
        lambda: replace(schema, columns=()),
        lambda: replace(evidence, retrieval_paths=()),
        lambda: replace(present, value=None),
        lambda: replace(
            present,
            status=StructuredValueStatus.VALUE_MISSING,
            value="unexpected",
        ),
        lambda: replace(present, reason=" "),
        lambda: ExtractedStructuredRecord(
            candidate_id=UUID(int=1), row_ordinal=True, values=FrozenMetadata()
        ),
        lambda: replace(metadata, candidate_universe_count=True),
        lambda: replace(result, returned_count=1),
        lambda: replace(result, next_offset=1),
        lambda: structured_record_id(UUID(int=1), True),
    )
    for construct in invalid_cases:
        with pytest.raises((TypeError, ValueError)):
            construct()


@async_test
async def test_normalizes_date_datetime_boolean_duration_enum_list_and_object() -> None:
    candidate = _candidate(1)
    fields = (
        StructuredField(name="day", field_type=StructuredFieldType.DATE),
        StructuredField(name="at", field_type=StructuredFieldType.DATETIME),
        StructuredField(name="active", field_type=StructuredFieldType.BOOLEAN),
        StructuredField(name="elapsed", field_type=StructuredFieldType.DURATION),
        StructuredField(
            name="kind", field_type=StructuredFieldType.ENUM, enum_values=("lab", "lecture")
        ),
        StructuredField(name="tags", field_type=StructuredFieldType.LIST),
        StructuredField(name="meta", field_type=StructuredFieldType.OBJECT),
    )
    extractor = MappingExtractor(
        {
            candidate.candidate_id: (
                _raw(
                    candidate,
                    1,
                    day="2026-08-25",
                    at="2026-08-25T10:00:00Z",
                    active="true",
                    elapsed="PT2.5S",
                    kind="lab",
                    tags=("a", "b"),
                    meta={"x": 1},
                ),
            )
        }
    )
    result = await StructuredRetrievalService(extractor).execute(
        _query(fields=fields), _retrieval((candidate,))
    )
    values = {item.field: item.value for item in result.records[0].values}
    assert values == {
        "day": date(2026, 8, 25),
        "at": datetime(2026, 8, 25, 10, tzinfo=UTC),
        "active": True,
        "elapsed": timedelta(seconds=2.5),
        "kind": "lab",
        "tags": ("a", "b"),
        "meta": FrozenMetadata({"x": 1}),
    }


@async_test
@pytest.mark.parametrize(
    "locator",
    [
        {"format": "csv", "row": 2},
        {"format": "xlsx", "sheet": "Data", "cell_range": "A2:B2"},
        {"format": "pdf", "page": 3, "block": 4},
        {"format": "docx", "section": 1, "block": 2},
        {"format": "code", "declaration": "Config"},
    ],
)
async def test_cross_format_positional_provenance_survives(locator) -> None:  # type: ignore[no-untyped-def]
    candidate = _candidate(1, locator=FrozenMetadata(locator))
    result = await StructuredRetrievalService(DelimitedTableEvidenceExtractor()).execute(
        _query(), _retrieval((candidate,))
    )
    evidence = result.records[0].evidence[0]
    assert all(evidence.locator[key] == value for key, value in locator.items())
    assert evidence.source_id == candidate.source_id and evidence.chunk_id == candidate.chunk.id


@async_test
async def test_group_distinct_nesting_and_aggregation_budgets_fail_closed() -> None:
    candidate = _candidate(1)
    extractor = MappingExtractor(
        {
            candidate.candidate_id: tuple(
                _raw(candidate, i, student=str(i), cpi=f"{i} CPI") for i in range(3)
            )
        }
    )
    with pytest.raises(ContractValidationError, match="group budget"):
        await StructuredRetrievalService(extractor).execute(
            _query(group_by=("student",), budgets=StructuredBudgets(max_groups=1)),
            _retrieval((candidate,)),
        )
    with pytest.raises(ContractValidationError, match="distinct budget"):
        await StructuredRetrievalService(extractor).execute(
            _query(distinct_fields=("student",), budgets=StructuredBudgets(max_distinct_values=1)),
            _retrieval((candidate,)),
        )
    with pytest.raises(ContractValidationError, match="aggregation row"):
        await StructuredRetrievalService(extractor).execute(
            _query(
                aggregations=(
                    StructuredAggregation(
                        name="count", operation=StructuredAggregationOperation.COUNT
                    ),
                ),
                budgets=StructuredBudgets(max_aggregation_rows=1),
            ),
            _retrieval((candidate,)),
        )
    nested = MappingExtractor(
        {candidate.candidate_id: (_raw(candidate, 1, student={"a": {"b": {"c": 1}}}, cpi="8 CPI"),)}
    )
    with pytest.raises(ContractValidationError, match="nesting"):
        await StructuredRetrievalService(nested).execute(
            _query(budgets=StructuredBudgets(max_nesting_depth=2)), _retrieval((candidate,))
        )


@async_test
async def test_result_is_deterministic_and_does_not_mutate_candidate_text() -> None:
    candidate = _candidate(1)
    service = StructuredRetrievalService(DelimitedTableEvidenceExtractor())
    first = await service.execute(_query(), _retrieval((candidate,)))
    second = await service.execute(_query(), _retrieval((candidate,)))
    assert [(item.record_id, item.values) for item in first.records] == [
        (item.record_id, item.values) for item in second.records
    ]
    assert candidate.chunk is not None and candidate.chunk.text == "Name\tCPI\nAsha\t8.74 CPI"
