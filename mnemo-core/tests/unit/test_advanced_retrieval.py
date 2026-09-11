"""Phase 8.5.6 advanced retrieval, completeness, security, and bounds tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces import (
    AdvancedRetrievalInterfaceV1,
    AdvancedSourcePage,
    ConflictError,
    ContractValidationError,
    IntegrityError,
    PrincipalContextV1,
    RetrieverCapabilities,
)
from mnemo.models import (
    AdvancedRetrievalCandidate,
    AdvancedRetrievalMode,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DeduplicationPolicy,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    EvidenceRepresentation,
    ExpansionPolicy,
    FrozenMetadata,
    Notebook,
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
    ScoredChunk,
    Source,
    advanced_candidate_id,
)
from mnemo.retrieval import AdvancedRetrievalService, RetrievalCursorCodec
from mnemo.retrieval.advanced_sources import CanonicalAdvancedReranker, CanonicalTextAdvancedSource
from mnemo.storage.composite import CompositeStorage
from mnemo.storage.sqlite import SQLiteStore

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def test_advanced_service_satisfies_runtime_interface() -> None:
    service = AdvancedRetrievalService(
        sources=(),
        cursor_codec=RetrievalCursorCodec(b"x" * 32),
    )

    assert isinstance(service, AdvancedRetrievalInterfaceV1)
    assert service.profile_id == "advanced-retrieval-v1"


def test_principal_aware_source_cannot_be_reached_through_legacy_execute() -> None:
    class Source:
        representation = EvidenceRepresentation.MULTILINGUAL_TEXT

        def __init__(self) -> None:
            self.authorized_calls = 0

        async def retrieve(self, plan, *, offset: int, limit: int):  # type: ignore[no-untyped-def]
            del plan, offset, limit
            raise PermissionError("legacy entry point is prohibited")

        async def retrieve_authorized(  # type: ignore[no-untyped-def]
            self, *, principal, plan, offset: int, limit: int
        ):
            del principal, plan, offset, limit
            self.authorized_calls += 1
            return AdvancedSourcePage(
                representation=self.representation,
                snapshot_identity="a" * 64,
                candidates=(),
                examined=0,
                next_offset=None,
                exhausted=True,
            )

        async def expand(self, plan, seeds, *, limit: int):  # type: ignore[no-untyped-def]
            del plan, seeds, limit
            return ()

    async def run() -> None:
        source = Source()
        service = AdvancedRetrievalService(
            sources=(source,),
            cursor_codec=RetrievalCursorCodec(b"p" * 32),
        )
        plan = _plan(uuid4(), representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,))
        legacy = await service.execute(plan)
        assert legacy.results == ()
        assert source.authorized_calls == 0
        principal = PrincipalContextV1(actor_id=uuid4(), authenticated=True)
        await service.execute_authorized(principal=principal, plan=plan)
        assert source.authorized_calls == 1

    asyncio.run(run())


def _budgets(**changes: int) -> RetrievalBudgetsV2:
    values = {
        "recall_limit": 20,
        "expansion_limit": 4,
        "fusion_limit": 20,
        "rerank_limit": 10,
        "result_limit": 5,
        "max_serialized_bytes": 100_000,
        "max_content_characters": 20_000,
    }
    values.update(changes)
    return RetrievalBudgetsV2(**values)


def _plan(
    notebook_id: UUID,
    *,
    mode: AdvancedRetrievalMode = AdvancedRetrievalMode.RANKED,
    scope: RetrievalScopeV2 | None = None,
    representations: tuple[EvidenceRepresentation, ...] = (EvidenceRepresentation.CANONICAL_TEXT,),
    budgets: RetrievalBudgetsV2 | None = None,
    position: PositionalScopeV2 | None = None,
    expansion: ExpansionPolicy = ExpansionPolicy.NONE,
    query: str = "target evidence",
) -> RetrievalPlanV2:
    return RetrievalPlanV2(
        query=query,
        mode=mode,
        scope=scope or RetrievalScopeV2(notebook_id=notebook_id),
        position=position or PositionalScopeV2(),
        representations=representations,
        budgets=budgets or _budgets(),
        expansion_policy=expansion,
        deduplication_policy=DeduplicationPolicy.AUTHORITATIVE_IDENTITY,
        ranking_policy=(
            RankingPolicyV2.SOURCE_RANK_FUSION
            if mode is AdvancedRetrievalMode.RANKED
            else RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER
        ),
    )


def _chunk(index: int, document_id: UUID, version_id: UUID, text: str) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        document_id=document_id,
        version_id=version_id,
        text=text,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(
            section_index=index // 10,
            chunk_index_in_section=index % 10,
            page_number=max(1, index),
        ),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=(f"Section {index // 10}",),
        metadata=FrozenMetadata(),
    )


def _candidate(
    *,
    notebook_id: UUID,
    representation: EvidenceRepresentation,
    index: int,
    title_match: bool = False,
    content: str | None = None,
    document_id: UUID | None = None,
    version_id: UUID | None = None,
    source_id: UUID | None = None,
    occurrence_id: UUID | None = None,
    derivation_id: UUID | None = None,
    path: str | None = None,
    rank: int = 1,
) -> AdvancedRetrievalCandidate:
    document_id = document_id or UUID(int=100 + index)
    version_id = version_id or UUID(int=200 + index)
    source_id = source_id or UUID(int=300 + index)
    canonical = (
        _chunk(index, document_id, version_id, content or f"evidence {index}")
        if representation is EvidenceRepresentation.CANONICAL_TEXT
        else None
    )
    if canonical is None and occurrence_id is None and derivation_id is None:
        occurrence_id = UUID(int=400 + index)
    return AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=representation,
            document_id=document_id,
            version_id=version_id,
            chunk_id=None if canonical is None else canonical.id,
            occurrence_id=occurrence_id,
            derivation_id=derivation_id,
        ),
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        representation=representation,
        chunk=canonical,
        occurrence_id=occurrence_id,
        derivation_id=derivation_id,
        locator=FrozenMetadata({"page": index, "format": "synthetic"}),
        document_title=f"Document {index}",
        content=content or f"evidence {index}",
        paths=(
            RetrievalPathEvidenceV2(
                path=path or representation.value,
                source_rank=rank,
                source_score=1.0 / rank,
                title_match=title_match,
            ),
        ),
    )


class FakeSource:
    def __init__(
        self,
        representation: EvidenceRepresentation,
        candidates: tuple[AdvancedRetrievalCandidate, ...],
        *,
        snapshot: str = "a" * 64,
        expansions: tuple[AdvancedRetrievalCandidate, ...] = (),
    ) -> None:
        self._representation = representation
        self.candidates = candidates
        self.snapshot = snapshot
        self.expansions = expansions

    @property
    def representation(self) -> EvidenceRepresentation:
        return self._representation

    async def retrieve(
        self, plan: RetrievalPlanV2, *, offset: int, limit: int
    ) -> AdvancedSourcePage:
        del plan
        values = self.candidates[offset : offset + limit]
        next_offset = offset + len(values) if offset + len(values) < len(self.candidates) else None
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity=self.snapshot,
            candidates=values,
            examined=len(values),
            next_offset=next_offset,
            exhausted=next_offset is None,
        )

    async def expand(
        self,
        plan: RetrievalPlanV2,
        seeds: tuple[AdvancedRetrievalCandidate, ...],
        *,
        limit: int,
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        del plan, seeds
        return self.expansions[:limit]


class ReverseReranker:
    async def rerank(
        self, query: str, candidates: tuple[AdvancedRetrievalCandidate, ...]
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        assert query
        return tuple(reversed(candidates))


def _service(*sources: FakeSource, reranker=None) -> AdvancedRetrievalService:  # type: ignore[no-untyped-def]
    return AdvancedRetrievalService(
        sources=tuple(sources),
        cursor_codec=RetrievalCursorCodec(b"cursor-test-key" * 4),
        reranker=reranker,
        clock=lambda: NOW,
    )


def test_ranked_fusion_expansion_dedup_and_reranking_preserve_provenance() -> None:
    notebook_id = uuid4()
    ordinary = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=1,
        rank=1,
    )
    titled = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=2,
        title_match=True,
        rank=2,
    )
    duplicate_path = replace(
        ordinary,
        paths=(RetrievalPathEvidenceV2(path="expanded-parent", source_rank=1, source_score=0.8),),
        expansion_reason="parent_and_adjacent",
    )
    source = FakeSource(
        EvidenceRepresentation.CANONICAL_TEXT,
        (ordinary, titled),
        expansions=(duplicate_path,),
    )
    result = asyncio.run(
        _service(source, reranker=ReverseReranker()).execute(
            _plan(notebook_id, expansion=ExpansionPolicy.PARENT_AND_ADJACENT)
        )
    )
    assert result.completeness is RetrievalCompleteness.UNKNOWN
    assert result.results[0].candidate_id == titled.candidate_id
    assert {item.candidate_id for item in result.results} == {
        ordinary.candidate_id,
        titled.candidate_id,
    }
    merged = next(item for item in result.results if item.candidate_id == ordinary.candidate_id)
    assert {path.path for path in merged.paths} == {"canonical_text", "expanded-parent"}
    assert merged.chunk is ordinary.chunk
    assert merged.source_id == ordinary.source_id
    assert result.diagnostics.expanded == 1
    assert result.diagnostics.deduplicated == 1


def test_distinct_ocr_vision_and_visual_evidence_is_not_text_deduplicated() -> None:
    notebook_id, occurrence_id = uuid4(), uuid4()
    shared = dict(
        notebook_id=notebook_id,
        index=3,
        occurrence_id=occurrence_id,
        content="same visible text",
        document_id=uuid4(),
        version_id=uuid4(),
        source_id=uuid4(),
    )
    sources = tuple(
        FakeSource(rep, (_candidate(representation=rep, derivation_id=uuid4(), **shared),))
        for rep in (
            EvidenceRepresentation.OCR_TEXT,
            EvidenceRepresentation.VISION_ANALYSIS,
            EvidenceRepresentation.VISUAL_VECTOR,
        )
    )
    result = asyncio.run(
        _service(*sources).execute(
            _plan(notebook_id, representations=tuple(source.representation for source in sources))
        )
    )
    assert len(result.results) == 3
    assert {item.representation for item in result.results} == {
        EvidenceRepresentation.OCR_TEXT,
        EvidenceRepresentation.VISION_ANALYSIS,
        EvidenceRepresentation.VISUAL_VECTOR,
    }


def test_unavailable_representation_is_partial_not_no_match_or_complete() -> None:
    notebook_id = uuid4()
    canonical = FakeSource(EvidenceRepresentation.CANONICAL_TEXT, ())
    result = asyncio.run(
        _service(canonical).execute(
            _plan(
                notebook_id,
                representations=(
                    EvidenceRepresentation.CANONICAL_TEXT,
                    EvidenceRepresentation.VISUAL_VECTOR,
                ),
            )
        )
    )
    assert result.completeness is RetrievalCompleteness.PARTIAL
    assert result.results == ()
    unavailable = result.diagnostics.representation_reports[1]
    assert unavailable.status.value == "unavailable"
    assert unavailable.reason_code == "representation_unavailable"


def test_source_failure_is_not_converted_to_no_match() -> None:
    notebook_id = uuid4()

    class FailedSource(FakeSource):
        async def retrieve(self, plan, *, offset, limit):  # type: ignore[no-untyped-def]
            del plan, offset, limit
            raise RuntimeError("backend stopped")

    result = asyncio.run(
        _service(FailedSource(EvidenceRepresentation.CANONICAL_TEXT, ())).execute(
            _plan(notebook_id)
        )
    )
    assert result.completeness is RetrievalCompleteness.UNKNOWN
    assert result.diagnostics.representation_reports[0].status.value == "failed"
    exhaustive = asyncio.run(
        _service(FailedSource(EvidenceRepresentation.CANONICAL_TEXT, ())).execute(
            _plan(notebook_id, mode=AdvancedRetrievalMode.EXHAUSTIVE)
        )
    )
    assert exhaustive.completeness is RetrievalCompleteness.PARTIAL
    assert exhaustive.diagnostics.representation_reports[0].status.value == "failed"


def test_exhaustive_signed_cursor_completion_tamper_expiry_and_snapshot_change() -> None:
    notebook_id = uuid4()
    candidates = tuple(
        _candidate(
            notebook_id=notebook_id,
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            index=index,
        )
        for index in range(1, 6)
    )
    source = FakeSource(EvidenceRepresentation.CANONICAL_TEXT, candidates)
    service = _service(source)
    plan = _plan(
        notebook_id,
        mode=AdvancedRetrievalMode.EXHAUSTIVE,
        budgets=_budgets(result_limit=2, rerank_limit=2),
    )
    first = asyncio.run(service.execute(plan))
    assert first.completeness is RetrievalCompleteness.TRUNCATED
    assert first.next_cursor and len(first.results) == 2
    with pytest.raises(IntegrityError, match="cursor is invalid"):
        asyncio.run(service.execute(plan, cursor=first.next_cursor + "x"))
    second = asyncio.run(service.execute(plan, cursor=first.next_cursor))
    assert second.completeness is RetrievalCompleteness.TRUNCATED
    third = asyncio.run(service.execute(plan, cursor=second.next_cursor))
    assert third.completeness is RetrievalCompleteness.COMPLETE
    assert len(third.results) == 1
    source.snapshot = "b" * 64
    with pytest.raises(ConflictError, match="snapshot changed"):
        asyncio.run(service.execute(plan, cursor=first.next_cursor))
    expired_codec = RetrievalCursorCodec(b"cursor-test-key" * 4, ttl=timedelta(seconds=1))
    token = expired_codec.encode(
        plan=plan,
        representation_index=0,
        offset=1,
        snapshots={EvidenceRepresentation.CANONICAL_TEXT.value: source.snapshot},
        now=NOW,
    )
    with pytest.raises(ConflictError, match="expired"):
        expired_codec.decode(token, plan=plan, now=NOW + timedelta(seconds=2))
    with pytest.raises(ConflictError, match="does not match"):
        asyncio.run(
            service.execute(
                _plan(notebook_id, mode=AdvancedRetrievalMode.EXHAUSTIVE, query="changed"),
                cursor=first.next_cursor,
            )
        )


def test_exhaustive_byte_bound_cursor_advances_without_repeating_candidates() -> None:
    notebook_id = uuid4()
    candidates = tuple(
        _candidate(
            notebook_id=notebook_id,
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            index=index,
            content="x" * 180,
        )
        for index in range(1, 4)
    )
    service = _service(FakeSource(EvidenceRepresentation.CANONICAL_TEXT, candidates))
    plan = _plan(
        notebook_id,
        mode=AdvancedRetrievalMode.EXHAUSTIVE,
        budgets=_budgets(
            result_limit=3,
            rerank_limit=3,
            max_serialized_bytes=candidates[0].serialized_size + 32,
        ),
    )
    first = asyncio.run(service.execute(plan))
    assert first.completeness is RetrievalCompleteness.TRUNCATED
    assert len(first.results) == 1
    second = asyncio.run(service.execute(plan, cursor=first.next_cursor))
    assert second.results[0].candidate_id != first.results[0].candidate_id


def test_single_oversized_candidate_fails_instead_of_issuing_non_progress_cursor() -> None:
    notebook_id = uuid4()
    candidate = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=9,
        content="x" * 2_000,
    )
    plan = _plan(
        notebook_id,
        mode=AdvancedRetrievalMode.EXHAUSTIVE,
        budgets=_budgets(max_serialized_bytes=256),
    )
    with pytest.raises(ContractValidationError, match="cannot serialize one evidence item"):
        asyncio.run(
            _service(FakeSource(EvidenceRepresentation.CANONICAL_TEXT, (candidate,))).execute(plan)
        )


def test_authorization_candidate_and_expansion_explosion_fail_closed() -> None:
    notebook_id = uuid4()
    leaked = _candidate(
        notebook_id=uuid4(), representation=EvidenceRepresentation.CANONICAL_TEXT, index=1
    )
    with pytest.raises(IntegrityError, match="another notebook"):
        asyncio.run(
            _service(FakeSource(EvidenceRepresentation.CANONICAL_TEXT, (leaked,))).execute(
                _plan(notebook_id)
            )
        )

    seed = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=2,
    )

    class ExplodingSource(FakeSource):
        async def expand(self, plan, seeds, *, limit):  # type: ignore[no-untyped-def]
            del plan, seeds
            return tuple(
                _candidate(
                    notebook_id=notebook_id,
                    representation=EvidenceRepresentation.CANONICAL_TEXT,
                    index=100 + index,
                )
                for index in range(limit + 1)
            )

    with pytest.raises(IntegrityError, match="expansion budget"):
        asyncio.run(
            _service(ExplodingSource(EvidenceRepresentation.CANONICAL_TEXT, (seed,))).execute(
                _plan(notebook_id, expansion=ExpansionPolicy.ADJACENT)
            )
        )


def test_reranker_cannot_erase_paths_or_change_runtime_provenance() -> None:
    notebook_id = uuid4()
    candidate = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=4,
    )

    class MetadataDroppingReranker:
        async def rerank(self, query, candidates):  # type: ignore[no-untyped-def]
            del query
            return (
                replace(
                    candidates[0],
                    paths=(
                        RetrievalPathEvidenceV2(
                            path="replacement", source_rank=1, source_score=1.0
                        ),
                    ),
                ),
            )

    with pytest.raises(IntegrityError, match="provenance"):
        asyncio.run(
            _service(
                FakeSource(EvidenceRepresentation.CANONICAL_TEXT, (candidate,)),
                reranker=MetadataDroppingReranker(),
            ).execute(_plan(notebook_id))
        )


@pytest.mark.parametrize(
    ("format_name", "locator"),
    (
        ("pdf", {"page": 3, "bbox": [0.1, 0.2, 0.8, 0.9]}),
        ("pptx", {"slide": 4, "shape_order": 2}),
        ("docx", {"paragraph": 7, "block_order": 9}),
        ("xlsx", {"sheet": "Data", "cell_range": "B2:D8"}),
        ("code", {"file": "module.py", "start_line": 10, "end_line": 20}),
        ("ocr", {"page": 2, "region": 5}),
        ("vision", {"occurrence": "image-1", "region": 1}),
    ),
)
def test_typed_representation_locators_survive_ranked_pipeline(
    format_name: str, locator: dict[str, object]
) -> None:
    notebook_id = uuid4()
    base = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.VISION_ANALYSIS,
        index=8,
    )
    candidate = replace(base, locator=FrozenMetadata({"format": format_name, **locator}))
    result = asyncio.run(
        _service(FakeSource(EvidenceRepresentation.VISION_ANALYSIS, (candidate,))).execute(
            _plan(
                notebook_id,
                representations=(EvidenceRepresentation.VISION_ANALYSIS,),
            )
        )
    )
    assert result.results[0].locator == candidate.locator
    assert result.results[0].occurrence_id == candidate.occurrence_id


def test_model_bounds_modes_positions_and_candidate_identity() -> None:
    notebook_id = uuid4()
    assert _plan(notebook_id).fingerprint == _plan(notebook_id).fingerprint
    assert _plan(notebook_id).fingerprint != _plan(notebook_id, query="changed").fingerprint
    with pytest.raises(ValueError, match="ranked retrieval requires"):
        _plan(notebook_id, query="")
    with pytest.raises(ValueError, match="ranking policy"):
        RetrievalPlanV2(
            **{
                **_plan(notebook_id).model_dump(),
                "ranking_policy": RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER,
            }
        )
    with pytest.raises(ValueError, match="page_start"):
        PositionalScopeV2(page_start=3, page_end=2)
    with pytest.raises(ValueError, match="fusion_limit"):
        _budgets(recall_limit=1, expansion_limit=0, fusion_limit=2)
    candidate = _candidate(
        notebook_id=notebook_id, representation=EvidenceRepresentation.CANONICAL_TEXT, index=9
    )
    with pytest.raises(ValueError, match="candidate_id"):
        replace(candidate, candidate_id=uuid4())


@pytest.mark.parametrize(
    ("factory", "message"),
    (
        (lambda: RetrievalScopeV2(notebook_id=uuid4(), source_ids=(UUID(int=1),) * 2), "unique"),
        (lambda: PositionalScopeV2(section_indexes=(-1,)), "non-negative"),
        (lambda: PositionalScopeV2(section_indexes=(1, 1)), "unique"),
        (lambda: PositionalScopeV2(heading_prefix=("",)), "empty"),
        (lambda: _budgets(rerank_limit=11, fusion_limit=10), "rerank_limit"),
        (lambda: _budgets(result_limit=11, rerank_limit=10), "result_limit"),
        (
            lambda: RetrievalPlanV2(
                **{
                    **_plan(uuid4()).model_dump(),
                    "query": "x" * 4097,
                }
            ),
            "4096",
        ),
        (
            lambda: RetrievalPlanV2(
                **{
                    **_plan(uuid4()).model_dump(),
                    "representations": (),
                }
            ),
            "empty",
        ),
        (
            lambda: RetrievalPlanV2(
                **{
                    **_plan(uuid4()).model_dump(),
                    "representations": (
                        EvidenceRepresentation.CANONICAL_TEXT,
                        EvidenceRepresentation.CANONICAL_TEXT,
                    ),
                }
            ),
            "unique",
        ),
        (
            lambda: RetrievalPathEvidenceV2(path="x", source_rank=0, source_score=None),
            "positive",
        ),
        (
            lambda: advanced_candidate_id(
                representation=EvidenceRepresentation.OCR_TEXT,
                document_id=uuid4(),
                version_id=uuid4(),
                chunk_id=None,
                occurrence_id=None,
                derivation_id=None,
            ),
            "authoritative",
        ),
    ),
)
def test_advanced_contract_rejects_unsafe_inputs(factory, message: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match=message):
        factory()


def test_candidate_report_diagnostics_and_result_invariants() -> None:
    notebook_id = uuid4()
    candidate = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=31,
    )
    with pytest.raises(ValueError, match="provenance"):
        replace(candidate, chunk=None, occurrence_id=None, derivation_id=None)
    with pytest.raises(ValueError, match="does not match"):
        replace(candidate, document_id=uuid4())
    with pytest.raises(TypeError, match="FrozenMetadata"):
        replace(candidate, locator={})
    with pytest.raises(ValueError, match="document_title"):
        replace(candidate, document_title="")
    with pytest.raises(ValueError, match="content"):
        replace(candidate, content="")
    with pytest.raises(ValueError, match="paths"):
        replace(candidate, paths=())
    with pytest.raises(ValueError, match="unique"):
        replace(candidate, paths=(candidate.paths[0], candidate.paths[0]))
    with pytest.raises(ValueError, match="fused_score"):
        replace(candidate, fused_score=float("nan"))
    with pytest.raises(ValueError, match="final_rank"):
        replace(candidate, final_rank=0)
    with pytest.raises(ValueError, match="expansion_reason"):
        replace(candidate, expansion_reason="")

    searched = RepresentationReportV2(
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        status=RepresentationSearchStatus.SEARCHED,
        examined=1,
        returned=1,
        exhausted=True,
    )
    with pytest.raises(ValueError, match="non-negative"):
        replace(searched, examined=-1)
    with pytest.raises(ValueError, match="cannot exceed"):
        replace(searched, returned=2)
    with pytest.raises(ValueError, match="failure reason"):
        replace(searched, reason_code="failure")
    with pytest.raises(ValueError, match="requires a reason"):
        replace(searched, status=RepresentationSearchStatus.UNAVAILABLE)

    diagnostics = RetrievalDiagnosticsV2(
        mode=AdvancedRetrievalMode.RANKED,
        recalled=1,
        expanded=0,
        deduplicated=0,
        fused=1,
        reranked=0,
        returned=1,
        serialized_bytes=candidate.serialized_size,
        content_characters=len(candidate.content or ""),
        truncated=False,
        truncation_reason=None,
        elapsed_milliseconds=1,
        representation_reports=(searched,),
    )
    with pytest.raises(ValueError, match="non-negative"):
        replace(diagnostics, recalled=-1)
    with pytest.raises(ValueError, match="truncation reason"):
        replace(diagnostics, truncated=True)

    ranked = replace(candidate, final_rank=1)
    result = RetrievalResultSetV1(
        query_fingerprint="a" * 64,
        snapshot_identity="b" * 64,
        ordering_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
        completeness=RetrievalCompleteness.UNKNOWN,
        results=(ranked,),
        examined_count=1,
        returned_count=1,
        next_cursor=None,
        diagnostics=diagnostics,
    )
    with pytest.raises(ValueError, match="returned_count"):
        replace(result, returned_count=0)
    with pytest.raises(ValueError, match="examined_count"):
        replace(result, examined_count=0)
    with pytest.raises(ValueError, match="contiguous"):
        replace(result, results=(replace(ranked, final_rank=2),))
    with pytest.raises(ValueError, match="continuation cursor"):
        replace(result, completeness=RetrievalCompleteness.TRUNCATED)
    with pytest.raises(ValueError, match="only valid"):
        replace(result, next_cursor="opaque")
    with pytest.raises(ValueError, match="requires no results"):
        replace(result, completeness=RetrievalCompleteness.EMPTY)
    with pytest.raises(ValueError, match="diagnostic returned"):
        replace(result, diagnostics=replace(diagnostics, returned=0))
    with pytest.raises(ValueError, match="source-rank-fusion"):
        replace(result, ordering_policy=RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER)


def test_cursor_and_service_contract_validation() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        RetrievalCursorCodec(b"short")
    with pytest.raises(ValueError, match="positive"):
        RetrievalCursorCodec(b"x" * 32, ttl=timedelta(0))
    notebook_id = uuid4()
    service = _service()
    with pytest.raises(TypeError, match="RetrievalPlanV2"):
        asyncio.run(service.execute(object()))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="only valid"):
        asyncio.run(service.execute(_plan(notebook_id), cursor="bad"))
    with pytest.raises(IntegrityError, match="cursor is invalid"):
        RetrievalCursorCodec(b"x" * 32).decode("bad", plan=_plan(notebook_id), now=NOW)
    codec = RetrievalCursorCodec(b"x" * 32)
    with pytest.raises(ValueError, match="representation index"):
        codec.encode(
            plan=_plan(notebook_id),
            representation_index=1,
            offset=0,
            snapshots={},
            now=NOW,
        )
    with pytest.raises(ValueError, match="offset"):
        codec.encode(
            plan=_plan(notebook_id),
            representation_index=0,
            offset=-1,
            snapshots={},
            now=NOW,
        )
    with pytest.raises(ValueError, match="SHA-256"):
        codec.encode(
            plan=_plan(notebook_id),
            representation_index=0,
            offset=0,
            snapshots={"canonical_text": "bad"},
            now=NOW,
        )
    with pytest.raises(TypeError, match="sources"):
        AdvancedRetrievalService(
            sources=(object(),),  # type: ignore[arg-type]
            cursor_codec=RetrievalCursorCodec(b"x" * 32),
        )
    source = FakeSource(EvidenceRepresentation.CANONICAL_TEXT, ())
    with pytest.raises(ValueError, match="one source"):
        AdvancedRetrievalService(
            sources=(source, source),
            cursor_codec=RetrievalCursorCodec(b"x" * 32),
        )
    with pytest.raises(TypeError, match="reranker"):
        AdvancedRetrievalService(
            sources=(),
            cursor_codec=RetrievalCursorCodec(b"x" * 32),
            reranker=object(),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "kind",
    ("representation", "budget", "duplicate", "continuation", "snapshot"),
)
def test_malformed_source_pages_fail_closed(kind: str) -> None:
    notebook_id = uuid4()
    candidate = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=41,
    )

    class MalformedSource(FakeSource):
        async def retrieve(self, plan, *, offset, limit):  # type: ignore[no-untyped-def]
            page = await super().retrieve(plan, offset=offset, limit=limit)
            if kind == "representation":
                return replace(page, representation=EvidenceRepresentation.OCR_TEXT)
            if kind == "budget":
                return replace(page, examined=0)
            if kind == "duplicate":
                return replace(page, candidates=(candidate, candidate), examined=2)
            if kind == "continuation":
                return replace(page, exhausted=True, next_offset=1)
            return replace(page, snapshot_identity="bad")

    with pytest.raises(IntegrityError):
        asyncio.run(
            _service(MalformedSource(EvidenceRepresentation.CANONICAL_TEXT, (candidate,))).execute(
                _plan(notebook_id)
            )
        )


class FakeSparseRetriever:
    retrieval_mode = "sparse"

    def __init__(self, chunks: tuple[Chunk, ...]) -> None:
        self.chunks = chunks

    def capabilities(self) -> RetrieverCapabilities:
        return RetrieverCapabilities(
            supports_hybrid=False,
            supports_metadata_filters=True,
            supports_parent_child=False,
            supports_reranking=False,
        )

    async def retrieve(self, query, query_embedding, filters, top_k):  # type: ignore[no-untyped-def]
        del query, query_embedding, filters
        return tuple(
            ScoredChunk(chunk=chunk, score=1.0 / index, source="sparse", rank=index)
            for index, chunk in enumerate(self.chunks[:top_k], 1)
        )


def test_canonical_reranker_preserves_advanced_provenance_and_title() -> None:
    notebook_id = uuid4()
    first = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=81,
        title_match=True,
    )
    second = _candidate(
        notebook_id=notebook_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        index=82,
    )

    class ReverseV1Reranker:
        def capabilities(self):  # type: ignore[no-untyped-def]
            from mnemo.interfaces import RerankerCapabilities

            return RerankerCapabilities(
                supports_cross_encoder=True,
                supports_batch=True,
                preserves_raw_scores=True,
            )

        async def rerank(self, query, candidates, top_k):  # type: ignore[no-untyped-def]
            del query
            return tuple(reversed(candidates))[:top_k]

    result = asyncio.run(
        CanonicalAdvancedReranker(ReverseV1Reranker()).rerank("q", (first, second))
    )
    assert tuple(item.candidate_id for item in result) == (second.candidate_id, first.candidate_id)
    assert result[1].title_match
    assert result[1].paths == first.paths


def test_canonical_adapter_rejects_incompatible_dependencies() -> None:
    with pytest.raises(TypeError, match="store"):
        CanonicalTextAdvancedSource(
            store=object(),  # type: ignore[arg-type]
            ranked_retriever=FakeSparseRetriever(()),
        )

    class DenseLike(FakeSparseRetriever):
        retrieval_mode = "dense"

    class StructuralStore:
        async def advanced_canonical_snapshot(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            return "a" * 64

        async def enumerate_advanced_canonical(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            return ()

        async def get_advanced_canonical_records(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            return ()

        async def expand_advanced_canonical(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            return ()

    with pytest.raises(TypeError, match="retriever"):
        CanonicalTextAdvancedSource(
            store=StructuralStore(),
            ranked_retriever=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="sparse"):
        CanonicalTextAdvancedSource(store=StructuralStore(), ranked_retriever=DenseLike(()))


def test_sqlite_canonical_exhaustive_position_title_and_notebook_scope(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(db_path=tmp_path / "advanced.db")
        await store.open()
        notebook_id, other_notebook = uuid4(), uuid4()
        await store.upsert_notebook(
            Notebook(
                notebook_id=notebook_id, title="N", description=None, created_at=NOW, updated_at=NOW
            )
        )
        await store.upsert_notebook(
            Notebook(
                notebook_id=other_notebook,
                title="O",
                description=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        chunks: list[Chunk] = []
        for number, notebook, title in (
            (1, notebook_id, "Project Portfolio"),
            (2, other_notebook, "Private Notes"),
            (3, notebook_id, "Project Appendix"),
        ):
            document_id, version_id = uuid4(), uuid4()
            version = DocumentVersion(
                version_id=version_id,
                document_id=document_id,
                content_hash=f"{number}" * 64,
                metadata=DocumentMetadata(content_hash=f"{number}" * 64, title=title),
                status=DocumentVersionStatus.CURRENT,
                created_at=NOW,
            )
            await store.upsert_document(
                Document(
                    document_id=document_id,
                    versions=(version,),
                    current_version_id=version_id,
                    current_hash=f"{number}" * 64,
                    status=DocumentStatus.INDEXED,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await store.upsert_source(
                Source(
                    source_id=uuid4(), notebook_id=notebook, document_id=document_id, created_at=NOW
                )
            )
            local = (
                replace(
                    _chunk(
                        number * 10 + 1,
                        document_id,
                        version_id,
                        "लक्ष्य target page one" if number == 3 else "target page one",
                    ),
                    position=ChunkPosition(
                        section_index=0, chunk_index_in_section=0, page_number=1
                    ),
                ),
                replace(
                    _chunk(number * 10 + 2, document_id, version_id, "target page two"),
                    position=ChunkPosition(
                        section_index=0, chunk_index_in_section=1, page_number=2
                    ),
                ),
            )
            await store.upsert_chunks(local)
            chunks.extend(local)
        composite = CompositeStorage(
            object(),  # type: ignore[arg-type]
            store,
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )
        source = CanonicalTextAdvancedSource(
            store=composite, ranked_retriever=FakeSparseRetriever(tuple(chunks[:2]))
        )
        service = AdvancedRetrievalService(
            sources=(source,), cursor_codec=RetrievalCursorCodec(b"sqlite-cursor-key" * 3)
        )
        positional = _plan(
            notebook_id,
            mode=AdvancedRetrievalMode.EXHAUSTIVE,
            position=PositionalScopeV2(page_start=2, page_end=2),
            query="target",
        )
        result = await service.execute(positional)
        assert result.completeness is RetrievalCompleteness.COMPLETE
        assert len(result.results) == 2
        assert all(item.locator["page_number"] == 2 for item in result.results)
        assert {item.document_title for item in result.results} == {
            "Project Portfolio",
            "Project Appendix",
        }
        assert all(item.notebook_id == notebook_id for item in result.results)
        title_result = await service.execute(
            _plan(
                notebook_id,
                mode=AdvancedRetrievalMode.EXHAUSTIVE,
                query="Project Portfolio",
            )
        )
        assert title_result.results
        assert all(item.title_match for item in title_result.results)
        marathi_result = await service.execute(
            _plan(notebook_id, mode=AdvancedRetrievalMode.EXHAUSTIVE, query="लक्ष्य")
        )
        assert len(marathi_result.results) == 1
        assert marathi_result.results[0].document_title == "Project Appendix"
        paged = await service.execute(
            _plan(
                notebook_id,
                mode=AdvancedRetrievalMode.EXHAUSTIVE,
                query="target",
                budgets=_budgets(result_limit=1, rerank_limit=1),
            )
        )
        assert paged.completeness is RetrievalCompleteness.TRUNCATED
        assert paged.next_cursor is not None
        ranked = await service.execute(_plan(notebook_id, query="Project Portfolio"))
        assert ranked.results[0].document_title == "Project Portfolio"
        assert all(item.document_title != "Private Notes" for item in ranked.results)

        # Scoped document query where ranked retriever returns candidates outside scope
        doc_appendix = chunks[4].document_id
        scoped_plan = _plan(
            notebook_id,
            query="target",
            scope=RetrievalScopeV2(
                notebook_id=notebook_id,
                document_ids=(doc_appendix,),
            ),
        )
        scoped_result = await service.execute(scoped_plan)
        assert all(item.document_id == doc_appendix for item in scoped_result.results)

        with pytest.raises(ValueError, match="offsets"):
            await source.retrieve(_plan(notebook_id), offset=1, limit=1)
        expanded = await source.expand(
            _plan(notebook_id, expansion=ExpansionPolicy.ADJACENT),
            (ranked.results[0],),
            limit=2,
        )
        assert expanded
        assert all(item.expansion_reason == "adjacent" for item in expanded)
        assert await source.expand(_plan(notebook_id), (ranked.results[0],), limit=0) == ()
        await store.close()

    asyncio.run(scenario())
