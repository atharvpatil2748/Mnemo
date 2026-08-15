"""Focused ADR-0043 context-construction tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, replace
from uuid import UUID

import pytest
from mnemo import PluginRegistry
from mnemo.interfaces import (
    CompletionResult,
    ContractValidationError,
    HealthStatus,
    IntegrityError,
    LLMCapabilities,
    Message,
    MessageRole,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    CompressionEvidence,
    ContextBuildResult,
    ContextEmptyReason,
    ContextItem,
    ContextItemKind,
    DocumentContextLabel,
    FrozenMetadata,
    FusedChunkResult,
    FusionEvidence,
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
from mnemo.retrieval.context import (
    COMPRESSION_HARD_MAX_TOKENS,
    EXTRACTOR_SYSTEM_PROMPT,
    SUMMARY_SCHEMA,
    ContextBuilder,
    _render,
    _serialize_fixed_input,
)

pytestmark = pytest.mark.anyio

_DOCUMENT = UUID("10000000-0000-4000-8000-000000000001")
_VERSION = UUID("10000000-0000-4000-8000-000000000002")


class _Counter:
    tokenizer_id = "test/count-characters"

    def count(self, text: str) -> int:
        return len(text)


class _Extractor:
    provider = "test-provider"
    model = "test-extractor"
    max_context_tokens = 100_000

    def __init__(self, outputs: tuple[object, ...] = ("short",)) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[str, tuple[Message, ...], object, int]] = []
        self.active = 0
        self.max_active = 0
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
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0)
            if self.failure is not None:
                raise self.failure
            output = self.outputs.pop(0)
            if isinstance(output, CompletionResult):
                return output
            return CompletionResult(
                model=self.model,
                structured=FrozenMetadata({"summary": output}),
            )
        finally:
            self.active -= 1

    def stream(
        self, system: str, messages: tuple[Message, ...], max_tokens: int = 1000
    ) -> AsyncIterator[str]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[str]:
        yield "unused"

    async def health_check(self) -> HealthStatus:
        raise NotImplementedError


class _ExtractorPlugin:
    name = "test-context-extractor"
    version = "1.0.0"
    core_version_range = ">=0.20.1"

    def __init__(self, extractor: _Extractor) -> None:
        self.extractor = extractor

    def capabilities(self) -> tuple[str, ...]:
        return ("llm",)

    def register(self, registry: PluginRegistry) -> None:
        registry.register_llm("extractor", self.extractor, priority=0, plugin_name=self.name)


def _chunk(
    index: int,
    *,
    text: str | None = None,
    document_id: UUID = _DOCUMENT,
    version_id: UUID = _VERSION,
    heading: tuple[str, ...] = (),
    page: int | None = None,
) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        text=text or f"candidate {index}",
        document_id=document_id,
        version_id=version_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(
            section_index=0,
            chunk_index_in_section=index,
            page_number=page,
        ),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=heading,
    )


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
    chunks = tuple(_chunk(index, text=text) for index, text in enumerate(texts, 1))
    scored = tuple(
        ScoredChunk(chunk=chunk, score=1.0 / rank, source="dense", rank=rank)
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
        if texts
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
                    identity_introduced_by_parent_promotion=item.rank == 1,
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


def _builder(extractor: _Extractor | None = None) -> ContextBuilder:
    registry = PluginRegistry(core_version="0.20.1")
    if extractor is not None:
        registry.load_plugin(_ExtractorPlugin(extractor))
    registry.freeze()
    return ContextBuilder(registry, _Counter())


def _fixed(result: RetrievalRerankResult, history: tuple[Message, ...] = ()) -> int:
    return len(_serialize_fixed_input("system", result, history))


def _mandatory_size(result: RetrievalRerankResult, count: int | None = None) -> int:
    candidates = result.results[: count or min(3, len(result.results))]
    return len(
        "\n\n".join(
            _render(index, item, item.fused_result.chunk.text, {})
            for index, item in enumerate(candidates, 1)
        )
    )


async def test_empty_result_resolves_extractor_without_calling_it() -> None:
    rerank = _rerank(())
    extractor = _Extractor()
    result = await _builder(extractor).build(rerank, context_budget=1000, system_prompt="system")

    assert result.empty_reason is ContextEmptyReason.NO_CANDIDATES
    assert result.compression_available
    assert result.rerank_result is rerank
    assert result.omitted_results == ()
    assert extractor.calls == []


@pytest.mark.parametrize("count", (1, 2, 3))
async def test_mandatory_candidates_are_verbatim_and_preserve_identity(count: int) -> None:
    rerank = _rerank(tuple(f"text {index}" for index in range(count)))
    result = await _builder().build(rerank, context_budget=10_000, system_prompt="system")

    assert tuple(item.kind for item in result.items) == (ContextItemKind.VERBATIM,) * count
    assert all(
        item.reranked_result is rerank.results[index] for index, item in enumerate(result.items)
    )
    assert tuple(item.source_number for item in result.items) == tuple(range(1, count + 1))
    with pytest.raises(FrozenInstanceError):
        result.context_budget = 2  # type: ignore[misc]


async def test_fixed_serialization_and_budget_boundaries() -> None:
    rerank = _rerank(("text",))
    history = (Message(role=MessageRole.USER, content="prior"),)
    expected = "SYSTEM\nsystem\nQUESTION\nWhat is duty?\nHISTORY\nuser\nprior\n"
    assert _serialize_fixed_input("system", rerank, history) == expected
    for budget in (0, 1_000_001):
        with pytest.raises(ContractValidationError):
            await _builder().build(rerank, context_budget=budget, system_prompt="system")
    empty = await _builder().build(
        rerank,
        context_budget=len(expected),
        system_prompt="system",
        session_history=history,
    )
    assert empty.empty_reason is ContextEmptyReason.FIXED_OVERHEAD_EXHAUSTED


async def test_mandatory_prefix_is_all_or_empty_and_never_compressed() -> None:
    rerank = _rerank(("one", "two", "three", "four"))
    extractor = _Extractor()
    result = await _builder(extractor).build(
        rerank,
        context_budget=_fixed(rerank) + _mandatory_size(rerank) - 1,
        system_prompt="system",
    )

    assert result.empty_reason is ContextEmptyReason.VERBATIM_PREFIX_DOES_NOT_FIT
    assert result.items == ()
    assert result.omitted_results == rerank.results
    assert extractor.calls == []


async def test_exact_fit_includes_separator_and_marker_overhead() -> None:
    rerank = _rerank(("one", "two", "three"))
    exact = _fixed(rerank) + _mandatory_size(rerank)
    result = await _builder().build(rerank, context_budget=exact, system_prompt="system")

    assert len(result.items) == 3
    assert result.context_tokens == result.available_context_tokens
    assert "\n\n=== Source [2]" in result.rendered_context


async def test_skip_over_selects_later_smaller_candidate() -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500, "z"))
    first_three = _mandatory_size(rerank)
    fifth_rendered = _render(4, rerank.results[4], "z", {})
    budget = _fixed(rerank) + first_three + 2 + len(fifth_rendered)
    result = await _builder().build(rerank, context_budget=budget, system_prompt="system")

    assert tuple(item.reranked_result for item in result.items) == (
        *rerank.results[:3],
        rerank.results[4],
    )
    assert result.omitted_results == (rerank.results[3],)


async def test_compression_uses_exact_prompt_schema_and_canonical_json() -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500))
    extractor = _Extractor((" compressed   summary ",))
    compressed_render = _render(4, rerank.results[3], "compressed summary", {})
    budget = _fixed(rerank) + _mandatory_size(rerank) + 2 + len(compressed_render)
    result = await _builder(extractor).build(rerank, context_budget=budget, system_prompt="system")

    compressed = result.items[-1]
    assert compressed.kind is ContextItemKind.COMPRESSED
    assert compressed.content == "compressed summary"
    assert compressed.compression_evidence is not None
    assert compressed.compression_evidence.target_tokens == 100
    system, messages, schema, max_tokens = extractor.calls[0]
    assert system == EXTRACTOR_SYSTEM_PROMPT
    assert schema == SUMMARY_SCHEMA
    assert max_tokens == COMPRESSION_HARD_MAX_TOKENS
    assert json.loads(messages[0].content) == {
        "chunk_id": rerank.results[3].fused_result.chunk.id,
        "document_id": str(_DOCUMENT),
        "query": rerank.query,
        "text": "X" * 500,
        "version_id": str(_VERSION),
    }
    assert messages[0].content == json.dumps(
        json.loads(messages[0].content), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


async def test_compressed_item_that_does_not_fit_is_omitted() -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500))
    extractor = _Extractor(("Y",))
    result = await _builder(extractor).build(
        rerank,
        context_budget=_fixed(rerank) + _mandatory_size(rerank),
        system_prompt="system",
    )
    assert len(result.items) == 3
    assert result.omitted_results == (rerank.results[3],)


async def test_compression_over_hard_maximum_is_rejected_without_truncation() -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500))
    with pytest.raises(IntegrityError):
        await _builder(_Extractor(("Y" * 121,))).build(
            rerank,
            context_budget=_fixed(rerank) + _mandatory_size(rerank) + 500,
            system_prompt="system",
        )


async def test_attribution_marker_uses_exact_version_label_and_optional_fields() -> None:
    rerank = _rerank(("text",))
    chunk = replace(
        rerank.results[0].fused_result.chunk,
        heading_path=("Chapter 1", "Duty"),
        position=replace(rerank.results[0].fused_result.chunk.position, page_number=7),
    )
    fused = replace(rerank.results[0].fused_result, chunk=chunk)
    item = replace(rerank.results[0], fused_result=fused)
    fusion = replace(rerank.fusion_result, results=(fused,))
    rerank = replace(rerank, fusion_result=fusion, results=(item,))
    label = DocumentContextLabel(document_id=_DOCUMENT, version_id=_VERSION, title='Gita "Book"')
    result = await _builder().build(
        rerank,
        context_budget=10_000,
        system_prompt="system",
        document_labels=(label,),
    )

    assert result.items[0].rendered_text.startswith(
        "=== Source [1] | document_id=10000000-0000-4000-8000-000000000001 | "
        'version_id=10000000-0000-4000-8000-000000000002 | title="Gita \\"Book\\"" | '
        'heading="Chapter 1 > Duty" | page=7 ===\n'
    )
    missing = await _builder().build(rerank, context_budget=10_000, system_prompt="system")
    assert "title=" not in missing.rendered_context


async def test_duplicate_labels_fail_but_partial_labels_are_allowed() -> None:
    rerank = _rerank(("text",))
    label = DocumentContextLabel(document_id=_DOCUMENT, version_id=_VERSION, title="Gita")
    with pytest.raises(ContractValidationError):
        await _builder().build(
            rerank,
            context_budget=10_000,
            system_prompt="system",
            document_labels=(label, label),
        )
    assert (await _builder().build(rerank, context_budget=10_000, system_prompt="system")).items


@pytest.mark.parametrize("summary", ("", 42, "\ud800"))
async def test_malformed_compression_output_fails(summary: object) -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500))
    with pytest.raises(IntegrityError):
        await _builder(_Extractor((summary,))).build(
            rerank,
            context_budget=_fixed(rerank) + _mandatory_size(rerank) + 500,
            system_prompt="system",
        )


async def test_extra_or_missing_structured_fields_fail() -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500))
    malformed = CompletionResult(
        model="test-extractor",
        structured=FrozenMetadata({"summary": "ok", "extra": True}),
    )
    with pytest.raises(IntegrityError):
        await _builder(_Extractor((malformed,))).build(
            rerank,
            context_budget=_fixed(rerank) + _mandatory_size(rerank) + 500,
            system_prompt="system",
        )


async def test_context_window_rejection_occurs_before_provider_call() -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500))
    extractor = _Extractor()
    extractor.max_context_tokens = 120
    with pytest.raises(ContractValidationError):
        await _builder(extractor).build(
            rerank,
            context_budget=_fixed(rerank) + _mandatory_size(rerank) + 500,
            system_prompt="system",
        )
    assert extractor.calls == []


async def test_registered_provider_failure_and_cancellation_propagate() -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500))
    budget = _fixed(rerank) + _mandatory_size(rerank) + 500
    extractor = _Extractor()
    failure = RuntimeError("extractor failed")
    extractor.failure = failure
    with pytest.raises(RuntimeError) as raised:
        await _builder(extractor).build(rerank, context_budget=budget, system_prompt="system")
    assert raised.value is failure
    extractor.failure = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await _builder(extractor).build(rerank, context_budget=budget, system_prompt="system")


async def test_sequential_compression_and_deterministic_repeat() -> None:
    rerank = _rerank(("a", "b", "c", "X" * 500, "Y" * 500))
    budget = _fixed(rerank) + _mandatory_size(rerank) + 1000
    first_extractor = _Extractor(("four", "five"))
    second_extractor = _Extractor(("four", "five"))
    first = await _builder(first_extractor).build(
        rerank, context_budget=budget, system_prompt="system"
    )
    second = await _builder(second_extractor).build(
        rerank, context_budget=budget, system_prompt="system"
    )
    assert first == second
    assert first_extractor.max_active == 1
    assert tuple(item.reranked_result for item in first.items) + first.omitted_results
    assert {id(item.reranked_result) for item in first.items} | {
        id(item) for item in first.omitted_results
    } == {id(item) for item in rerank.results}


async def test_low_relevance_metadata_is_selection_neutral() -> None:
    rerank = _rerank(("a", "b", "c"))
    result = await _builder().build(rerank, context_budget=10_000, system_prompt="system")
    assert tuple(item.reranked_result for item in result.items) == rerank.results


async def test_context_builder_requires_frozen_registry() -> None:
    with pytest.raises(ContractValidationError):
        ContextBuilder(PluginRegistry(core_version="0.20.1"), _Counter())


async def test_document_versions_receive_distinct_source_numbers() -> None:
    rerank = _rerank(("one", "two"))
    second_version = UUID("10000000-0000-4000-8000-000000000003")
    second_chunk = replace(rerank.results[1].fused_result.chunk, version_id=second_version)
    second_fused = replace(rerank.results[1].fused_result, chunk=second_chunk)
    second = replace(rerank.results[1], fused_result=second_fused)
    fusion = replace(rerank.fusion_result, results=(rerank.fusion_result.results[0], second_fused))
    rerank = replace(rerank, fusion_result=fusion, results=(rerank.results[0], second))
    result = await _builder().build(rerank, context_budget=10_000, system_prompt="system")
    assert tuple(item.source_number for item in result.items) == (1, 2)
    assert str(second_version) in result.items[1].rendered_text


@pytest.mark.parametrize(
    "factory",
    (
        lambda: DocumentContextLabel(document_id="bad", version_id=_VERSION, title="x"),
        lambda: DocumentContextLabel(document_id=_DOCUMENT, version_id="bad", title="x"),
        lambda: DocumentContextLabel(document_id=_DOCUMENT, version_id=_VERSION, title=" "),
        lambda: CompressionEvidence(
            extractor_provider=" ", extractor_model="model", compressed_token_count=1
        ),
        lambda: CompressionEvidence(
            extractor_provider="provider", extractor_model=" ", compressed_token_count=1
        ),
        lambda: CompressionEvidence(
            extractor_provider="provider",
            extractor_model="model",
            target_tokens=99,
            compressed_token_count=1,
        ),
        lambda: CompressionEvidence(
            extractor_provider="provider",
            extractor_model="model",
            hard_max_tokens=119,
            compressed_token_count=1,
        ),
        lambda: CompressionEvidence(
            extractor_provider="provider", extractor_model="model", compressed_token_count=0
        ),
        lambda: CompressionEvidence(
            extractor_provider="provider", extractor_model="model", compressed_token_count=121
        ),
    ),
)
def test_context_metadata_models_reject_invalid_values(factory: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


async def test_context_item_validation_rejects_inconsistent_representation() -> None:
    reranked = _rerank(("text",)).results[0]
    valid = ContextItem(
        source_number=1,
        reranked_result=reranked,
        kind=ContextItemKind.VERBATIM,
        content="text",
        content_token_count=4,
        rendered_text="marker\ntext",
        rendered_token_count=11,
    )
    evidence = CompressionEvidence(
        extractor_provider="provider", extractor_model="model", compressed_token_count=1
    )
    invalid = (
        {"source_number": 0},
        {"reranked_result": object()},
        {"kind": "verbatim"},
        {"content": " "},
        {"content_token_count": 0},
        {"rendered_text": " "},
        {"rendered_token_count": 0},
        {"content": "changed"},
        {"compression_evidence": evidence},
        {"kind": ContextItemKind.COMPRESSED, "content": "summary"},
    )
    for changes in invalid:
        with pytest.raises((TypeError, ValueError)):
            replace(valid, **changes)


async def test_context_build_result_validation_rejects_broken_partition_and_counts() -> None:
    rerank = _rerank(("text",))
    valid = await _builder().build(rerank, context_budget=10_000, system_prompt="system")
    invalid = (
        {"rerank_result": object()},
        {"tokenizer_id": " "},
        {"context_budget": True},
        {"context_budget": 0},
        {"fixed_overhead_tokens": True},
        {"fixed_overhead_tokens": -1},
        {"available_context_tokens": 1},
        {"context_tokens": valid.available_context_tokens + 1},
        {"items": []},
        {"omitted_results": []},
        {"compression_available": 1},
        {"items": (replace(valid.items[0], source_number=2),)},
        {"rendered_context": "changed"},
        {"items": (), "rendered_context": "", "context_tokens": 0},
        {"empty_reason": ContextEmptyReason.NO_ITEM_FITS},
    )
    for changes in invalid:
        with pytest.raises((TypeError, ValueError)):
            replace(valid, **changes)

    empty = ContextBuildResult(
        rerank_result=rerank,
        tokenizer_id="test",
        context_budget=1,
        fixed_overhead_tokens=1,
        available_context_tokens=0,
        context_tokens=0,
        rendered_context="",
        items=(),
        omitted_results=rerank.results,
        compression_available=False,
        empty_reason=ContextEmptyReason.FIXED_OVERHEAD_EXHAUSTED,
    )
    with pytest.raises(ValueError):
        replace(empty, rendered_context="unexpected")
