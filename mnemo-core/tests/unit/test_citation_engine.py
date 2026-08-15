"""Focused ADR-0045 citation resolution and persistence tests."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from mnemo.interfaces import ContractValidationError, IntegrityError, StorageInterfaceV1
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    CitationResolutionResult,
    CitationResolutionStatus,
    CompressionEvidence,
    ContextBuildResult,
    ContextEmptyReason,
    ContextItem,
    ContextItemKind,
    DocumentContextLabel,
    FusedChunkResult,
    FusionEvidence,
    GenerationEvidence,
    GroundedAnswerResult,
    GroundedAnswerStatus,
    MetadataFilter,
    RerankedChunkResult,
    RerankFallbackReason,
    RerankPolicy,
    RetrievalFusionResult,
    RetrievalIntent,
    RetrievalInvocationTrace,
    RetrievalMode,
    RetrievalPlan,
    RetrievalRerankResult,
    ScoredChunk,
    SubQuery,
    Turn,
    TurnRole,
)
from mnemo.retrieval import CitationEngine

pytestmark = pytest.mark.anyio

_DOCUMENT = UUID("30000000-0000-4000-8000-000000000001")
_VERSION = UUID("30000000-0000-4000-8000-000000000002")
_NOW = datetime(2026, 8, 13, 16, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, value: object = _NOW) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        return self.value


def _storage() -> Mock:
    return Mock(spec=StorageInterfaceV1)


def _chunks(
    count: int,
    *,
    documents: tuple[tuple[UUID, UUID], ...] | None = None,
) -> tuple[Chunk, ...]:
    identities = documents or ((_DOCUMENT, _VERSION),) * count
    return tuple(
        Chunk(
            id=f"{index:064x}",
            text=f"canonical passage {index}",
            document_id=document_id,
            version_id=version_id,
            chunk_type=ChunkType.PASSAGE,
            position=ChunkPosition(
                section_index=0,
                chunk_index_in_section=index,
                page_number=index,
            ),
            source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
            heading_path=(f"Chapter {index}",),
        )
        for index, (document_id, version_id) in enumerate(identities, 1)
    )


def _rerank(chunks: tuple[Chunk, ...], *, promoted: bool = False) -> RetrievalRerankResult:
    subquery = SubQuery(
        query_text="What is duty?",
        retrieval_mode=RetrievalMode.DENSE,
        filters=MetadataFilter(),
        max_results=max(1, len(chunks)),
    )
    plan = RetrievalPlan(
        intent=RetrievalIntent.FACTUAL,
        sub_queries=(subquery,),
        requires_multi_hop=False,
        requires_multi_doc=len({item.document_id for item in chunks}) > 1,
    )
    scored = tuple(
        ScoredChunk(chunk=chunk, score=1 / rank, source="dense", rank=rank)
        for rank, chunk in enumerate(chunks, 1)
    )
    invocations = (
        (
            RetrievalInvocationTrace(
                invocation_id="sq-1:dense",
                subquery_index=1,
                declared_mode=RetrievalMode.DENSE,
                effective_mode=RetrievalMode.DENSE,
                query_text=subquery.query_text,
                filters=subquery.filters,
                requested_top_k=subquery.max_results,
                raw_results=scored,
                promoted_results=scored,
            ),
        )
        if scored
        else ()
    )
    fused = tuple(
        FusedChunkResult(
            chunk=item.chunk,
            rrf_score=1 / (60 + item.rank),
            global_rank=item.rank,
            evidence=(
                FusionEvidence(
                    invocation_id="sq-1:dense",
                    subquery_index=1,
                    declared_mode=RetrievalMode.DENSE,
                    effective_mode=RetrievalMode.DENSE,
                    result=item,
                    identity_introduced_by_parent_promotion=promoted,
                ),
            ),
        )
        for item in scored
    )
    fusion = RetrievalFusionResult(plan=plan, invocations=invocations, results=fused)
    results = tuple(
        RerankedChunkResult(fused_result=item, rerank_evidence=None, reranked_rank=item.global_rank)
        for item in fused
    )
    return RetrievalRerankResult(
        query="What is duty?",
        fusion_result=fusion,
        policy=RerankPolicy.RRF_FALLBACK if results else RerankPolicy.UNCHANGED_EMPTY,
        results=results,
        fallback_reason=RerankFallbackReason.PROVIDER_UNAVAILABLE if results else None,
    )


def _context(
    chunks: tuple[Chunk, ...],
    *,
    selected_count: int | None = None,
    compressed_sources: frozenset[int] = frozenset(),
    promoted: bool = False,
) -> ContextBuildResult:
    rerank = _rerank(chunks, promoted=promoted)
    selected = rerank.results[: selected_count if selected_count is not None else len(chunks)]
    items: list[ContextItem] = []
    for source_number, result in enumerate(selected, 1):
        compressed = source_number in compressed_sources
        content = f"compressed {source_number}" if compressed else result.fused_result.chunk.text
        rendered = f"=== Source [{source_number}] ===\n{content}"
        items.append(
            ContextItem(
                source_number=source_number,
                reranked_result=result,
                kind=ContextItemKind.COMPRESSED if compressed else ContextItemKind.VERBATIM,
                content=content,
                content_token_count=len(content),
                rendered_text=rendered,
                rendered_token_count=len(rendered),
                compression_evidence=(
                    CompressionEvidence(
                        extractor_provider="test",
                        extractor_model="test",
                        compressed_token_count=len(content),
                    )
                    if compressed
                    else None
                ),
            )
        )
    rendered_context = "\n\n".join(item.rendered_text for item in items)
    return ContextBuildResult(
        rerank_result=rerank,
        tokenizer_id="test/tokenizer",
        context_budget=100_000,
        fixed_overhead_tokens=10,
        available_context_tokens=99_990,
        context_tokens=len(rendered_context),
        rendered_context=rendered_context,
        items=tuple(items),
        omitted_results=rerank.results[len(selected) :],
        compression_available=True,
    )


def _empty_context(reason: ContextEmptyReason) -> ContextBuildResult:
    chunks = () if reason is ContextEmptyReason.NO_CANDIDATES else _chunks(1)
    rerank = _rerank(chunks)
    return ContextBuildResult(
        rerank_result=rerank,
        tokenizer_id="test/tokenizer",
        context_budget=1000,
        fixed_overhead_tokens=10,
        available_context_tokens=990,
        context_tokens=0,
        rendered_context="",
        items=(),
        omitted_results=rerank.results,
        compression_available=False,
        empty_reason=reason,
    )


def _answer(
    text: str,
    *,
    context: ContextBuildResult | None = None,
) -> GroundedAnswerResult:
    active_context = context or _context(_chunks(2))
    return GroundedAnswerResult(
        context_result=active_context,
        query=active_context.rerank_result.query,
        status=GroundedAnswerStatus.GENERATED,
        answer=text,
        generation_evidence=GenerationEvidence(
            provider="test",
            model="test",
            tokenizer_id=active_context.tokenizer_id,
            prompt_token_count=10,
            max_output_tokens=100,
            answer_token_count=10,
        ),
    )


def _no_context(reason: ContextEmptyReason) -> GroundedAnswerResult:
    context = _empty_context(reason)
    return GroundedAnswerResult(
        context_result=context,
        query=context.rerank_result.query,
        status=GroundedAnswerStatus.NO_CONTEXT,
        answer=None,
        generation_evidence=None,
    )


def _turn(answer: GroundedAnswerResult, *, role: TurnRole = TurnRole.ASSISTANT) -> Turn:
    return Turn(
        turn_id=UUID("30000000-0000-4000-8000-000000000010"),
        session_id=UUID("30000000-0000-4000-8000-000000000011"),
        sequence=1,
        role=role,
        content=answer.answer or "no answer",
        created_at=_NOW - timedelta(seconds=1),
    )


def _labels(context: ContextBuildResult) -> tuple[DocumentContextLabel, ...]:
    keys: dict[tuple[UUID, UUID], DocumentContextLabel] = {}
    for item in context.items:
        chunk = item.reranked_result.fused_result.chunk
        key = (chunk.document_id, chunk.version_id)
        keys[key] = DocumentContextLabel(
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            title=f"Title {chunk.document_id} {chunk.version_id}",
        )
    return tuple(keys.values())


async def _resolve(
    answer: GroundedAnswerResult,
    *,
    storage: Mock | None = None,
    clock: _Clock | None = None,
    turn: Turn | None = None,
    labels: tuple[DocumentContextLabel, ...] | None = None,
) -> tuple[CitationResolutionResult, Mock, _Clock]:
    active_storage = storage or _storage()
    active_clock = clock or _Clock()
    active_turn = turn if turn is not None else _turn(answer)
    result = await CitationEngine(active_storage, active_clock).resolve_and_persist(
        answer,
        assistant_turn=active_turn,
        document_labels=labels if labels is not None else _labels(answer.context_result),
    )
    return result, active_storage, active_clock


def test_result_models_are_immutable_and_validate_statuses() -> None:
    answer = _answer("Answer without markers")
    turn = _turn(answer)
    result = CitationResolutionResult(
        answer_result=answer,
        assistant_turn=turn,
        status=CitationResolutionStatus.UNMARKED,
        citations=(),
        persisted=False,
    )
    assert result.answer_result is answer and result.assistant_turn is turn
    with pytest.raises(FrozenInstanceError):
        result.persisted = True  # type: ignore[misc]
    with pytest.raises(ValueError):
        replace(result, persisted=True)


def test_result_models_reject_malformed_fields_and_cross_status_state() -> None:
    answer = _answer("Answer without markers")
    turn = _turn(answer)
    valid = CitationResolutionResult(
        answer_result=answer,
        assistant_turn=turn,
        status=CitationResolutionStatus.UNMARKED,
        citations=(),
        persisted=False,
    )
    with pytest.raises(TypeError, match="answer_result"):
        replace(valid, answer_result=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="assistant_turn"):
        replace(valid, assistant_turn=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="status"):
        replace(valid, status="unmarked")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="citations"):
        replace(valid, citations=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="persisted"):
        replace(valid, persisted=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="content"):
        replace(valid, assistant_turn=replace(turn, content="different"))
    with pytest.raises(ValueError, match="generated answer"):
        CitationResolutionResult(
            answer_result=_no_context(ContextEmptyReason.NO_CANDIDATES),
            assistant_turn=turn,
            status=CitationResolutionStatus.UNMARKED,
            citations=(),
            persisted=False,
        )


async def test_engine_rejects_invalid_dependencies_and_operation_inputs() -> None:
    with pytest.raises(TypeError, match="storage"):
        CitationEngine(object(), _Clock())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="clock"):
        CitationEngine(_storage(), None)  # type: ignore[arg-type]
    engine = CitationEngine(_storage(), _Clock())
    with pytest.raises(ContractValidationError, match="answer_result"):
        await engine.resolve_and_persist(object(), assistant_turn=None)  # type: ignore[arg-type]
    answer = _answer("Answer without markers")
    with pytest.raises(ContractValidationError, match="document_labels"):
        await engine.resolve_and_persist(
            answer,
            assistant_turn=_turn(answer),
            document_labels=[],  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("reason", tuple(ContextEmptyReason))
async def test_no_context_never_calls_clock_or_storage(reason: ContextEmptyReason) -> None:
    storage = _storage()
    clock = _Clock()
    result = await CitationEngine(storage, clock).resolve_and_persist(
        _no_context(reason), assistant_turn=None
    )
    assert result.status is CitationResolutionStatus.NO_CONTEXT
    assert result.citations == () and not result.persisted
    assert clock.calls == 0
    storage.upsert_citation.assert_not_awaited()


async def test_no_context_rejects_turn_and_labels() -> None:
    answer = _no_context(ContextEmptyReason.NO_CANDIDATES)
    with pytest.raises(ContractValidationError, match="assistant turn"):
        await CitationEngine(_storage(), _Clock()).resolve_and_persist(
            answer, assistant_turn=_turn(_answer("answer"))
        )
    with pytest.raises(ContractValidationError, match="document labels"):
        await CitationEngine(_storage(), _Clock()).resolve_and_persist(
            answer,
            assistant_turn=None,
            document_labels=(
                DocumentContextLabel(document_id=_DOCUMENT, version_id=_VERSION, title="Title"),
            ),
        )


@pytest.mark.parametrize(
    "marker",
    (
        "[source:0]",
        "[source:01]",
        "[source:-1]",
        "[source:+1]",
        "[source: 1]",
        "[source:]",
        "[source:1",
        "[source:1x]",
    ),
)
async def test_malformed_reserved_markers_raise(marker: str) -> None:
    answer = _answer(marker)
    with pytest.raises(IntegrityError, match="malformed"):
        await _resolve(answer)


async def test_case_variant_is_unmarked_and_writes_nothing() -> None:
    answer = _answer("Ordinary [SOURCE:1] text")
    result, storage, clock = await _resolve(answer)
    assert result.status is CitationResolutionStatus.UNMARKED
    assert result.citations == () and not result.persisted
    assert clock.calls == 0
    storage.upsert_citation.assert_not_awaited()


@pytest.mark.parametrize("marker", ("[source:3]", "[source:2]"))
async def test_unknown_and_omitted_sources_raise(marker: str) -> None:
    context = _context(_chunks(2), selected_count=1)
    answer = _answer(marker, context=context)
    with pytest.raises(IntegrityError, match="unknown source"):
        await _resolve(answer)


async def test_repeats_deduplicate_and_first_occurrence_controls_order() -> None:
    answer = _answer("[source:2] then [source:1], and [source:2] again")
    result, storage, clock = await _resolve(answer)
    assert result.status is CitationResolutionStatus.RESOLVED
    assert tuple(item.source_number for item in result.citations) == (2, 1)
    assert [call.args[0] for call in storage.upsert_citation.await_args_list] == list(
        result.citations
    )
    assert clock.calls == 1


async def test_multi_digit_marker_resolves_typed_source() -> None:
    context = _context(_chunks(12))
    answer = _answer("See [source:12].", context=context)
    result, _, _ = await _resolve(answer)
    assert result.citations[0].source_number == 12
    assert result.citations[0].chunk_id == context.items[11].reranked_result.fused_result.chunk.id


async def test_turn_preconditions() -> None:
    answer = _answer("Supported [source:1]")
    engine = CitationEngine(_storage(), _Clock())
    with pytest.raises(ContractValidationError, match="requires an assistant"):
        await engine.resolve_and_persist(answer, assistant_turn=None)
    with pytest.raises(ContractValidationError, match="assistant role"):
        await engine.resolve_and_persist(answer, assistant_turn=_turn(answer, role=TurnRole.USER))
    with pytest.raises(ContractValidationError, match="content"):
        await engine.resolve_and_persist(
            answer,
            assistant_turn=replace(_turn(answer), content="different"),
        )


async def test_label_validation_precedes_clock_and_storage() -> None:
    answer = _answer("Supported [source:1]")
    storage = _storage()
    clock = _Clock()
    engine = CitationEngine(storage, clock)
    with pytest.raises(ContractValidationError, match="title is unavailable"):
        await engine.resolve_and_persist(answer, assistant_turn=_turn(answer))
    label = _labels(answer.context_result)[0]
    with pytest.raises(ContractValidationError, match="must be unique"):
        await engine.resolve_and_persist(
            answer,
            assistant_turn=_turn(answer),
            document_labels=(label, label),
        )
    with pytest.raises(ContractValidationError, match="does not match"):
        await engine.resolve_and_persist(
            answer,
            assistant_turn=_turn(answer),
            document_labels=(
                DocumentContextLabel(document_id=uuid4(), version_id=uuid4(), title="Extra"),
            ),
        )
    assert clock.calls == 0
    storage.upsert_citation.assert_not_awaited()


async def test_exact_mapping_compression_parent_and_deterministic_identity() -> None:
    context = _context(_chunks(2), compressed_sources=frozenset({1}), promoted=True)
    answer = _answer("Supported [source:1] and [source:2]", context=context)
    turn = _turn(answer)
    result, _, clock = await _resolve(answer, turn=turn)
    first, second = result.citations
    first_chunk = context.items[0].reranked_result.fused_result.chunk
    assert first.citation_id == uuid5(
        NAMESPACE_URL,
        f"mnemo:citation:v1:{turn.turn_id}:1:{first_chunk.id}",
    )
    assert first.turn_id == turn.turn_id
    assert first.document_id == first_chunk.document_id
    assert first.version_id == first_chunk.version_id
    assert first.page_number == first_chunk.position.page_number
    assert first.heading_path == first_chunk.heading_path
    assert first.verbatim_quote == first_chunk.text != context.items[0].content
    assert first.created_at == second.created_at == _NOW
    assert (
        context.items[0]
        .reranked_result.fused_result.evidence[0]
        .identity_introduced_by_parent_promotion
    )
    assert clock.calls == 1


async def test_multi_document_and_version_titles_remain_distinct() -> None:
    document_two = UUID("30000000-0000-4000-8000-000000000020")
    version_two = UUID("30000000-0000-4000-8000-000000000021")
    context = _context(
        _chunks(
            3, documents=((_DOCUMENT, _VERSION), (_DOCUMENT, version_two), (document_two, _VERSION))
        )
    )
    answer = _answer("[source:3] [source:1] [source:2]", context=context)
    result, _, _ = await _resolve(answer)
    assert tuple((item.document_id, item.version_id) for item in result.citations) == (
        (document_two, _VERSION),
        (_DOCUMENT, _VERSION),
        (_DOCUMENT, version_two),
    )
    assert len({item.document_title for item in result.citations}) == 3


@pytest.mark.parametrize(
    "value",
    (
        "not a datetime",
        datetime(2026, 8, 13, 16, 0),
        datetime(2026, 8, 13, 16, 0, tzinfo=timezone(timedelta(hours=1))),
        _NOW - timedelta(days=1),
    ),
)
async def test_invalid_clock_values_raise_before_storage(value: object) -> None:
    answer = _answer("Supported [source:1]")
    storage = _storage()
    with pytest.raises(IntegrityError, match=r"clock|precedes"):
        await _resolve(answer, storage=storage, clock=_Clock(value))
    storage.upsert_citation.assert_not_awaited()


async def test_repeated_execution_converges_to_same_citation() -> None:
    answer = _answer("Supported [source:1]")
    storage = _storage()
    first, _, _ = await _resolve(answer, storage=storage)
    second, _, _ = await _resolve(answer, storage=storage)
    assert first == second
    assert storage.upsert_citation.await_count == 2
    assert storage.upsert_citation.await_args_list[0] == storage.upsert_citation.await_args_list[1]


async def test_storage_failure_leaves_prefix_and_returns_no_result() -> None:
    answer = _answer("[source:1] [source:2]")
    storage = _storage()
    storage.upsert_citation = AsyncMock(side_effect=(None, RuntimeError("write failed")))
    with pytest.raises(RuntimeError, match="write failed"):
        await _resolve(answer, storage=storage)
    assert storage.upsert_citation.await_count == 2


async def test_cancellation_propagates_without_compensation() -> None:
    answer = _answer("[source:1] [source:2]")
    storage = _storage()
    storage.upsert_citation = AsyncMock(side_effect=(None, asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await _resolve(answer, storage=storage)
    assert storage.upsert_citation.await_count == 2


async def test_exact_provenance_and_chunks_are_not_mutated() -> None:
    context = _context(_chunks(2))
    answer = _answer("Supported [source:2]", context=context)
    original_chunks = tuple(item.reranked_result.fused_result.chunk for item in context.items)
    result, _, _ = await _resolve(answer)
    assert result.answer_result is answer
    assert result.answer_result.context_result is context
    assert result.answer_result.context_result.items[1] is context.items[1]
    assert (
        tuple(item.reranked_result.fused_result.chunk for item in context.items) == original_chunks
    )
