"""Focused acceptance tests for Phase 6 Module 6.1 query planning."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import mnemo.retrieval.planner as planner_module
import pytest
from mnemo.interfaces import (
    CompletionResult,
    EmbeddingBatch,
    EmbeddingCapabilities,
    HealthStatus,
    IntegrityError,
    LLMCapabilities,
    Message,
    UnsupportedError,
)
from mnemo.models import (
    MAX_SUBQUERIES,
    MAX_SUBQUERY_RESULTS,
    FrozenMetadata,
    MetadataFilter,
    RetrievalIntent,
    RetrievalMode,
    RetrievalPlan,
    SubQuery,
    Turn,
    TurnRole,
)
from mnemo.retrieval import QueryPlanner
from pydantic import ValidationError


class PlannerLLMStub:
    """Deterministic structured planner provider with observable calls."""

    def __init__(
        self,
        result: CompletionResult | Exception,
        *,
        supports_json: bool = True,
    ) -> None:
        self.result = result
        self.supports_json = supports_json
        self.calls: list[tuple[str, tuple[Message, ...], object, int]] = []

    @property
    def provider(self) -> str:
        return "test"

    @property
    def model(self) -> str:
        return "planner-test"

    @property
    def max_context_tokens(self) -> int:
        return 8192

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_streaming=False,
            supports_json=self.supports_json,
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
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def stream(
        self,
        system: str,
        messages: tuple[Message, ...],
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        return self._empty_stream()

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            healthy=True,
            component="planner-test",
            checked_at=datetime.now(UTC),
        )

    async def _empty_stream(self) -> AsyncIterator[str]:
        if False:  # pragma: no cover
            yield ""


class EmbeddingStub:
    """Deterministic embedding provider recording its exact input text."""

    def __init__(self, vector: tuple[float, ...] = (0.1, 0.2, 0.3)) -> None:
        self.vector = vector
        self.texts: list[str] = []

    @property
    def model_name(self) -> str:
        return "test/embedding"

    @property
    def dimensions(self) -> int:
        return 3

    @property
    def max_tokens(self) -> int:
        return 512

    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            dimensions=self.dimensions,
            supports_batch=True,
            max_batch=8,
            multilingual=False,
            supports_normalization=False,
        )

    async def embed(self, text: str) -> tuple[float, ...]:
        self.texts.append(text)
        return self.vector

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        return EmbeddingBatch(
            vectors=tuple(self.vector for _ in texts),
            model_name=self.model_name,
            dimensions=self.dimensions,
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            healthy=True,
            component="embedding-test",
            checked_at=datetime.now(UTC),
        )


def _subquery(
    text: str = "A hypothetical source paragraph about the requested subject.",
    mode: str = "dense",
    max_results: int = 10,
    filters: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "query_text": text,
        "retrieval_mode": mode,
        "filters": {} if filters is None else filters,
        "max_results": max_results,
    }


def _payload(
    intent: str = "factual",
    sub_queries: tuple[dict[str, object], ...] | None = None,
    *,
    requires_multi_hop: bool = False,
    requires_multi_doc: bool = False,
) -> dict[str, object]:
    return {
        "intent": intent,
        "sub_queries": (_subquery(),) if sub_queries is None else sub_queries,
        "requires_multi_hop": requires_multi_hop,
        "requires_multi_doc": requires_multi_doc,
    }


def _completion(payload: dict[str, object]) -> CompletionResult:
    return CompletionResult(model="planner-test", structured=FrozenMetadata(payload))


def _planner(payload: dict[str, object]) -> tuple[QueryPlanner, PlannerLLMStub, EmbeddingStub]:
    llm = PlannerLLMStub(_completion(payload))
    embedding = EmbeddingStub()
    return QueryPlanner(llm, embedding), llm, embedding


@pytest.mark.parametrize(
    "intent",
    ("factual", "comparative", "exploratory", "synthesis"),
)
def test_retrieval_plan_accepts_all_module_intents(intent: str) -> None:
    plan = RetrievalPlan.model_validate(_payload(intent))

    assert plan.intent is RetrievalIntent(intent)
    assert plan.model_dump(mode="json")["intent"] == intent
    assert hash(plan) == hash(plan.model_copy())


@pytest.mark.parametrize(
    "payload",
    (
        _payload("unsupported"),
        _payload(sub_queries=()),
        _payload(sub_queries=(_subquery(mode="unknown"),)),
        _payload(sub_queries=(_subquery(max_results=0),)),
        _payload(sub_queries=(_subquery(max_results=MAX_SUBQUERY_RESULTS + 1),)),
        _payload(sub_queries=(_subquery(filters={"unknown": True}),)),
        {**_payload(), "requires_multi_hop": "false"},
        {**_payload(), "requires_multi_doc": 1},
    ),
)
def test_retrieval_plan_rejects_invalid_schema(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate(payload)


def test_retrieval_plan_rejects_duplicates_and_unbounded_decomposition() -> None:
    duplicate = _subquery(text="  Repeated   query ")
    with pytest.raises(ValidationError, match="semantic duplicates"):
        RetrievalPlan.model_validate(
            _payload(sub_queries=(duplicate, _subquery(text="repeated query")))
        )
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate(
            _payload(
                sub_queries=tuple(
                    _subquery(text=f"Hypothetical paragraph {index}")
                    for index in range(MAX_SUBQUERIES + 1)
                )
            )
        )


def test_subquery_normalizes_text_and_preserves_typed_filters() -> None:
    subquery = SubQuery(
        query_text="  comparative   source language ",
        retrieval_mode=RetrievalMode.SPARSE,
        filters=MetadataFilter(),
        max_results=5,
    )

    assert subquery.query_text == "comparative source language"
    assert isinstance(subquery.filters, MetadataFilter)
    with pytest.raises(ValidationError):
        SubQuery(
            query_text=" ",
            retrieval_mode=RetrievalMode.DENSE,
            filters=MetadataFilter(),
            max_results=1,
        )


@pytest.mark.anyio
async def test_factual_query_returns_structured_plan_and_passes_question() -> None:
    planner, llm, _ = _planner(_payload())

    plan = await planner.plan("What is X?")

    assert plan.intent is RetrievalIntent.FACTUAL
    assert len(plan.sub_queries) == 1
    assert "What is X?" in llm.calls[0][1][-1].content
    assert isinstance(llm.calls[0][2], FrozenMetadata)
    assert "properties" in llm.calls[0][2]


@pytest.mark.anyio
@pytest.mark.parametrize("intent", ("comparative", "synthesis"))
async def test_complex_intents_preserve_multiple_subqueries(intent: str) -> None:
    sub_queries = (
        _subquery(text="A hypothetical paragraph comparing the source positions."),
        _subquery(text="X source position", mode="sparse"),
        _subquery(text="Y source position", mode="sparse"),
    )
    planner, _, _ = _planner(_payload(intent, sub_queries, requires_multi_doc=True))

    plan = await planner.plan("How do the sources compare X and Y?")

    assert plan.intent is RetrievalIntent(intent)
    assert len(plan.sub_queries) == 3
    assert plan.requires_multi_doc


@pytest.mark.anyio
async def test_notebook_context_and_only_last_three_turns_reach_llm() -> None:
    planner, llm, _ = _planner(_payload("exploratory"))
    session_id = UUID("00000000-0000-4000-8000-000000000001")
    start = datetime(2026, 8, 13, tzinfo=UTC)
    turns = tuple(
        Turn(
            turn_id=UUID(int=index + 1),
            session_id=session_id,
            sequence=index,
            role=TurnRole.USER if index % 2 == 0 else TurnRole.ASSISTANT,
            content=f"turn-{index}",
            created_at=start + timedelta(minutes=index),
        )
        for index in range(5)
    )

    await planner.plan(
        "What are the main themes related to X?",
        table_of_contents=("Chapter One", "Section A"),
        source_titles=("Source Alpha", "Source Beta"),
        recent_turns=turns,
    )

    messages = llm.calls[0][1]
    assert tuple(message.content for message in messages[:-1]) == (
        "turn-2",
        "turn-3",
        "turn-4",
    )
    assert "Chapter One" in messages[-1].content
    assert "Source Beta" in messages[-1].content


@pytest.mark.anyio
@pytest.mark.parametrize(
    "result",
    (
        CompletionResult(model="planner-test", text="not structured"),
        _completion({**_payload(), "intent": "invalid"}),
        _completion(_payload(sub_queries=(_subquery(text=""),))),
        _completion({**_payload(), "citation": "invented"}),
    ),
)
async def test_malformed_planner_output_fails_closed(result: CompletionResult) -> None:
    planner = QueryPlanner(PlannerLLMStub(result), EmbeddingStub())

    with pytest.raises(IntegrityError):
        await planner.plan("What is X?")


@pytest.mark.anyio
async def test_llm_failure_propagates_without_repair() -> None:
    failure = RuntimeError("provider unavailable")
    planner = QueryPlanner(PlannerLLMStub(failure), EmbeddingStub())

    with pytest.raises(RuntimeError, match="provider unavailable") as raised:
        await planner.plan("What is X?")

    assert raised.value is failure


@pytest.mark.anyio
async def test_hyde_embeds_hypothetical_paragraph_not_original_question() -> None:
    hypothetical = "Relevant sources would explain X through this hypothetical prose."
    planner, _, embedding = _planner(_payload(sub_queries=(_subquery(text=hypothetical),)))

    plan, vector = await planner.plan_with_hyde_embedding("What is X?")

    assert plan.sub_queries[0].query_text == hypothetical
    assert embedding.texts == [hypothetical]
    assert vector == (0.1, 0.2, 0.3)


@pytest.mark.anyio
async def test_missing_hyde_and_invalid_embedding_fail_closed() -> None:
    planner, _, _ = _planner(
        _payload(sub_queries=(_subquery(text="exact keywords", mode="sparse"),))
    )
    with pytest.raises(IntegrityError, match="HyDE"):
        await planner.plan("What is X?")

    valid_plan = RetrievalPlan.model_validate(_payload())
    invalid_embedding_planner = QueryPlanner(
        PlannerLLMStub(_completion(_payload())),
        EmbeddingStub((float("nan"), 0.2, 0.3)),
    )
    with pytest.raises(IntegrityError, match="invalid components"):
        await invalid_embedding_planner.embed_hyde(valid_plan)


@pytest.mark.anyio
async def test_embed_hyde_rejects_invalid_plan_and_vector_dimensions() -> None:
    planner, _, _ = _planner(_payload())
    with pytest.raises(TypeError, match="RetrievalPlan"):
        await planner.embed_hyde(object())  # type: ignore[arg-type]

    sparse_plan = RetrievalPlan.model_validate(
        _payload(sub_queries=(_subquery(text="keywords", mode="sparse"),))
    )
    with pytest.raises(IntegrityError, match="HyDE"):
        await planner.embed_hyde(sparse_plan)

    dimensions_planner = QueryPlanner(
        PlannerLLMStub(_completion(_payload())),
        EmbeddingStub((0.1, 0.2)),
    )
    with pytest.raises(IntegrityError, match="dimensions"):
        await dimensions_planner.embed_hyde(RetrievalPlan.model_validate(_payload()))


@pytest.mark.anyio
async def test_invalid_completion_object_fails_closed() -> None:
    llm = PlannerLLMStub(cast(Any, object()))
    planner = QueryPlanner(llm, EmbeddingStub())

    with pytest.raises(IntegrityError, match="completion result"):
        await planner.plan("What is X?")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("question", "table_of_contents", "source_titles", "recent_turns"),
    (
        (cast(Any, 1), (), (), ()),
        (" ", (), (), ()),
        ("What is X?", cast(Any, []), (), ()),
        ("What is X?", (" ",), (), ()),
        ("What is X?", (), cast(Any, []), ()),
        ("What is X?", (), (), cast(Any, [])),
        ("What is X?", (), (), cast(Any, (object(),))),
    ),
)
async def test_invalid_planning_inputs_fail_before_llm_call(
    question: str,
    table_of_contents: tuple[str, ...],
    source_titles: tuple[str, ...],
    recent_turns: tuple[Turn, ...],
) -> None:
    planner, llm, _ = _planner(_payload())

    with pytest.raises((TypeError, ValueError)):
        await planner.plan(
            question,
            table_of_contents=table_of_contents,
            source_titles=source_titles,
            recent_turns=recent_turns,
        )

    assert not llm.calls


def test_query_planner_has_no_concrete_provider_or_storage_dependency() -> None:
    source = inspect.getsource(planner_module)
    forbidden = ("ollama", "qdrant", "sqlite", "surrealdb", "StorageInterface")

    assert not any(name.casefold() in source.casefold() for name in forbidden)


def test_constructor_requires_existing_provider_contracts() -> None:
    with pytest.raises(TypeError, match="LLMInterfaceV1"):
        QueryPlanner(object(), EmbeddingStub())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="EmbeddingProviderV1"):
        QueryPlanner(PlannerLLMStub(_completion(_payload())), object())  # type: ignore[arg-type]
    with pytest.raises(UnsupportedError, match="structured JSON output"):
        QueryPlanner(
            PlannerLLMStub(_completion(_payload()), supports_json=False),
            EmbeddingStub(),
        )


def test_schema_forbids_fake_hyde_citation_metadata() -> None:
    payload: dict[str, Any] = _subquery()
    payload["citation"] = {"page_number": 10, "source_id": "invented"}

    with pytest.raises(ValidationError):
        SubQuery.model_validate(payload)
