"""Focused ADR-0044 grounded-answer tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, replace
from uuid import UUID

import pytest
from mnemo import PluginRegistry
from mnemo.interfaces import (
    CompletionResult,
    ContractValidationError,
    DependencyUnavailableError,
    HealthStatus,
    IntegrityError,
    LLMCapabilities,
    LLMInterfaceV1,
    Message,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    ContextBuildResult,
    ContextEmptyReason,
    ContextItem,
    ContextItemKind,
    FrozenMetadata,
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
)
from mnemo.retrieval.answer import (
    GROUNDED_ANSWER_SYSTEM_PROMPT,
    GroundedAnswerGenerator,
    _user_message,
)

pytestmark = pytest.mark.anyio

_DOCUMENT = UUID("20000000-0000-4000-8000-000000000001")
_VERSION = UUID("20000000-0000-4000-8000-000000000002")


class _Counter:
    def __init__(self, tokenizer_id: str = "test/count-characters") -> None:
        self.tokenizer_id = tokenizer_id

    def count(self, text: str) -> int:
        return len(text)


class _Synthesizer:
    provider = "test-provider"
    model = "test-synthesizer"
    max_context_tokens = 100_000

    def __init__(self, result: CompletionResult | None = None) -> None:
        self.result = result or CompletionResult(model=self.model, text="Grounded [source:1]")
        self.calls: list[tuple[str, tuple[Message, ...], object, int]] = []
        self.failure: BaseException | None = None

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_streaming=False,
            supports_json=True,
            supports_vision=False,
            supports_reasoning=False,
        )

    async def complete(
        self,
        system: str,
        messages: tuple[Message, ...],
        structured_output: object = None,
        max_tokens: int = 1000,
    ) -> CompletionResult:
        self.calls.append((system, messages, structured_output, max_tokens))
        await asyncio.sleep(0)
        if self.failure is not None:
            raise self.failure
        return self.result

    def stream(
        self, system: str, messages: tuple[Message, ...], max_tokens: int = 1000
    ) -> AsyncIterator[str]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[str]:
        yield "unused"

    async def health_check(self) -> HealthStatus:
        raise NotImplementedError


class _Plugin:
    name = "test-grounded-synthesizer"
    version = "1.0.0"
    core_version_range = ">=0.20.1"

    def __init__(self, synthesizer: _Synthesizer) -> None:
        self.synthesizer = synthesizer

    def capabilities(self) -> tuple[str, ...]:
        return ("llm",)

    def register(self, registry: PluginRegistry) -> None:
        registry.register_llm("synthesizer", self.synthesizer, priority=0, plugin_name=self.name)


class _TrackingRegistry(PluginRegistry):
    def __init__(self) -> None:
        super().__init__(core_version="0.20.1")
        self.resolve_calls = 0

    def resolve_llm(self, slot: str) -> LLMInterfaceV1 | None:
        self.resolve_calls += 1
        return super().resolve_llm(slot)


def _rerank(texts: tuple[str, ...]) -> RetrievalRerankResult:
    subquery = SubQuery(
        query_text="What is duty?",
        retrieval_mode=RetrievalMode.DENSE,
        filters=MetadataFilter(),
        max_results=max(1, len(texts)),
    )
    plan = RetrievalPlan(
        intent=RetrievalIntent.FACTUAL,
        sub_queries=(subquery,),
        requires_multi_hop=False,
        requires_multi_doc=False,
    )
    chunks = tuple(
        Chunk(
            id=f"{index:064x}",
            text=text,
            document_id=_DOCUMENT,
            version_id=_VERSION,
            chunk_type=ChunkType.PASSAGE,
            position=ChunkPosition(section_index=0, chunk_index_in_section=index),
            source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
            heading_path=(),
        )
        for index, text in enumerate(texts, 1)
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
                    identity_introduced_by_parent_promotion=False,
                ),
            ),
        )
        for item in scored
    )
    fusion = RetrievalFusionResult(plan=plan, invocations=invocations, results=fused)
    reranked = tuple(
        RerankedChunkResult(fused_result=item, rerank_evidence=None, reranked_rank=item.global_rank)
        for item in fused
    )
    return RetrievalRerankResult(
        query="What is duty?",
        fusion_result=fusion,
        policy=RerankPolicy.RRF_FALLBACK if reranked else RerankPolicy.UNCHANGED_EMPTY,
        results=reranked,
        fallback_reason=RerankFallbackReason.PROVIDER_UNAVAILABLE if reranked else None,
    )


def _context(*, empty_reason: ContextEmptyReason | None = None) -> ContextBuildResult:
    rerank = _rerank(()) if empty_reason is ContextEmptyReason.NO_CANDIDATES else _rerank(("Duty",))
    if empty_reason is not None:
        return ContextBuildResult(
            rerank_result=rerank,
            tokenizer_id="test/count-characters",
            context_budget=1000,
            fixed_overhead_tokens=10,
            available_context_tokens=990,
            context_tokens=0,
            rendered_context="",
            items=(),
            omitted_results=rerank.results,
            compression_available=False,
            empty_reason=empty_reason,
        )
    candidate = rerank.results[0]
    rendered = f"=== Source [1] | document_id={_DOCUMENT} | version_id={_VERSION} ===\nDuty"
    item = ContextItem(
        source_number=1,
        reranked_result=candidate,
        kind=ContextItemKind.VERBATIM,
        content="Duty",
        content_token_count=4,
        rendered_text=rendered,
        rendered_token_count=len(rendered),
    )
    return ContextBuildResult(
        rerank_result=rerank,
        tokenizer_id="test/count-characters",
        context_budget=1000,
        fixed_overhead_tokens=10,
        available_context_tokens=990,
        context_tokens=len(rendered),
        rendered_context=rendered,
        items=(item,),
        omitted_results=(),
        compression_available=False,
    )


def _generator(
    synthesizer: _Synthesizer | None = None,
    *,
    counter: _Counter | None = None,
) -> GroundedAnswerGenerator:
    registry = PluginRegistry(core_version="0.20.1")
    if synthesizer is not None:
        registry.load_plugin(_Plugin(synthesizer))
    registry.freeze()
    return GroundedAnswerGenerator(registry, counter or _Counter())


def _evidence(**changes: object) -> GenerationEvidence:
    values = {
        "provider": "provider",
        "model": "model",
        "tokenizer_id": "test/count-characters",
        "prompt_token_count": 10,
        "max_output_tokens": 100,
        "answer_token_count": 4,
    }
    values.update(changes)
    return GenerationEvidence(**values)  # type: ignore[arg-type]


def _empty_completion() -> CompletionResult:
    result = object.__new__(CompletionResult)
    object.__setattr__(result, "model", "test-synthesizer")
    object.__setattr__(result, "text", "   ")
    object.__setattr__(result, "structured", None)
    object.__setattr__(result, "metadata", FrozenMetadata())
    return result


def test_models_are_immutable_and_validate_status_combinations() -> None:
    context = _context()
    result = GroundedAnswerResult(
        context_result=context,
        query="What is duty?",
        status=GroundedAnswerStatus.GENERATED,
        answer="text",
        generation_evidence=_evidence(),
    )
    assert result.context_result is context
    with pytest.raises(FrozenInstanceError):
        result.answer = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="requires generation evidence"):
        replace(result, generation_evidence=None)
    with pytest.raises(ValueError, match="cannot contain"):
        GroundedAnswerResult(
            context_result=_context(empty_reason=ContextEmptyReason.NO_ITEM_FITS),
            query="What is duty?",
            status=GroundedAnswerStatus.NO_CONTEXT,
            answer="text",
            generation_evidence=None,
        )


@pytest.mark.parametrize("value", (0, 4097, True, 1.5))
def test_generation_evidence_rejects_invalid_output_bounds(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _evidence(max_output_tokens=value)


@pytest.mark.parametrize(
    "changes",
    (
        {"provider": ""},
        {"model": ""},
        {"tokenizer_id": ""},
        {"prompt_token_count": -1},
        {"answer_token_count": 0},
        {"answer_token_count": 101},
    ),
)
def test_generation_evidence_validates_identifiers_and_counts(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        _evidence(**changes)


@pytest.mark.parametrize("reason", tuple(ContextEmptyReason))
async def test_typed_empty_context_does_not_resolve_or_invoke_provider(
    reason: ContextEmptyReason,
) -> None:
    registry = _TrackingRegistry()
    registry.freeze()
    result = await GroundedAnswerGenerator(registry, _Counter()).generate(
        _context(empty_reason=reason), max_output_tokens=20
    )
    assert result.status is GroundedAnswerStatus.NO_CONTEXT
    assert result.answer is None
    assert result.generation_evidence is None
    assert registry.resolve_calls == 0


async def test_exact_prompt_call_token_accounting_and_provenance() -> None:
    synthesizer = _Synthesizer(
        CompletionResult(
            model="test-synthesizer", text="  Answer [source:1]\n\nSecond paragraph.  "
        )
    )
    context = _context()
    result = await _generator(synthesizer).generate(context, max_output_tokens=200)
    expected_user = _user_message("What is duty?", context.rendered_context)

    assert len(synthesizer.calls) == 1
    system, messages, schema, bound = synthesizer.calls[0]
    assert system == GROUNDED_ANSWER_SYSTEM_PROMPT
    assert len(messages) == 1 and messages[0].content == expected_user
    assert schema is None and bound == 200
    assert result.answer == "Answer [source:1]\n\nSecond paragraph."
    assert result.context_result is context
    assert result.query == context.rerank_result.query
    assert result.generation_evidence == GenerationEvidence(
        provider="test-provider",
        model="test-synthesizer",
        tokenizer_id="test/count-characters",
        prompt_token_count=len(GROUNDED_ANSWER_SYSTEM_PROMPT) + len(expected_user),
        max_output_tokens=200,
        answer_token_count=len(result.answer),
    )


async def test_missing_provider_and_tokenizer_mismatch_are_typed() -> None:
    with pytest.raises(DependencyUnavailableError):
        await _generator().generate(_context(), max_output_tokens=10)
    synthesizer = _Synthesizer()
    with pytest.raises(ContractValidationError, match="identity"):
        await _generator(synthesizer, counter=_Counter("wrong")).generate(
            _context(), max_output_tokens=10
        )
    assert synthesizer.calls == []


async def test_context_window_exact_fit_and_overflow_preflight() -> None:
    context = _context()
    synthesizer = _Synthesizer()
    prompt = len(GROUNDED_ANSWER_SYSTEM_PROMPT) + len(
        _user_message(context.rerank_result.query, context.rendered_context)
    )
    synthesizer.max_context_tokens = prompt + 20
    await _generator(synthesizer).generate(context, max_output_tokens=20)
    synthesizer.calls.clear()
    synthesizer.max_context_tokens = prompt + 19
    with pytest.raises(ContractValidationError, match="exceed"):
        await _generator(synthesizer).generate(context, max_output_tokens=20)
    assert synthesizer.calls == []


@pytest.mark.parametrize("value", (0, 4097, True))
async def test_generate_rejects_invalid_output_bound(value: object) -> None:
    with pytest.raises(ContractValidationError):
        await _generator().generate(_context(), max_output_tokens=value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("completion", "match"),
    (
        (CompletionResult(model="other", text="answer"), "model identity"),
        (CompletionResult(model="test-synthesizer", structured=FrozenMetadata()), "structured"),
        (_empty_completion(), "empty answer"),
        (object(), "CompletionResult"),
        (CompletionResult(model="test-synthesizer", text="bad\ud800"), "surrogate"),
        (CompletionResult(model="test-synthesizer", text="x" * 21), "exceeds"),
    ),
)
async def test_malformed_provider_outputs_raise_integrity(completion: object, match: str) -> None:
    synthesizer = _Synthesizer()
    synthesizer.result = completion  # type: ignore[assignment]
    with pytest.raises(IntegrityError, match=match):
        await _generator(synthesizer).generate(_context(), max_output_tokens=20)


async def test_provider_failure_and_cancellation_propagate() -> None:
    failure = RuntimeError("provider failed")
    synthesizer = _Synthesizer()
    synthesizer.failure = failure
    with pytest.raises(RuntimeError, match="provider failed"):
        await _generator(synthesizer).generate(_context(), max_output_tokens=20)

    synthesizer.failure = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await _generator(synthesizer).generate(_context(), max_output_tokens=20)


async def test_identical_validated_output_constructs_equivalent_results() -> None:
    context = _context()
    first = await _generator(_Synthesizer()).generate(context, max_output_tokens=30)
    second = await _generator(_Synthesizer()).generate(context, max_output_tokens=30)
    assert first == second
    assert first.context_result is context and second.context_result is context
