"""Structured query planning and HyDE expansion for Module 6.1."""

from __future__ import annotations

import math

from pydantic import ValidationError

from mnemo.interfaces import (
    CompletionResult,
    EmbeddingProviderV1,
    EmbeddingVector,
    IntegrityError,
    LLMInterfaceV1,
    Message,
    MessageRole,
    UnsupportedError,
)
from mnemo.models import (
    FrozenMetadata,
    RetrievalMode,
    RetrievalPlan,
    Turn,
    TurnRole,
)

_MAX_WORKING_MEMORY_TURNS = 3
_PLANNER_MAX_TOKENS = 2000
_PLANNER_SYSTEM_PROMPT = """You are Mnemo's retrieval planner.
Transform the user's question and supplied notebook context into only the JSON
object required by the supplied RetrievalPlan schema. Plan document retrieval;
do not answer the user, call tools, execute retrieval, or invent filters.

Choose exactly one intent: factual, comparative, exploratory, or synthesis.
Preserve the question's meaning and avoid unnecessary decomposition. Use only
these modes: dense, sparse, or hybrid. Every max_results value
must be from 1 through 100. Use empty MetadataFilter collections when no hard
filter was supplied; never fabricate identifiers or dates.

At least one dense or hybrid sub-query is required. Its query_text must be a
single hypothetical answer paragraph (HyDE) resembling relevant source prose.
It is retrieval expansion, not a factual answer: include no citations, quotes,
page numbers, document IDs, source IDs, or claims of evidentiary certainty.
Other sub-queries may preserve concise keyword or alternate phrasing queries.
"""


class QueryPlanner:
    """Create validated retrieval plans through configured core providers."""

    def __init__(
        self,
        llm: LLMInterfaceV1,
        embedding_provider: EmbeddingProviderV1,
    ) -> None:
        """Bind the configured planner role and primary embedding provider."""
        if not isinstance(llm, LLMInterfaceV1):
            raise TypeError("llm must implement LLMInterfaceV1")
        if not isinstance(embedding_provider, EmbeddingProviderV1):
            raise TypeError("embedding_provider must implement EmbeddingProviderV1")
        if not llm.capabilities().supports_json:
            raise UnsupportedError("planner LLM must support structured JSON output")
        self._llm = llm
        self._embedding_provider = embedding_provider

    async def plan(
        self,
        question: str,
        *,
        table_of_contents: tuple[str, ...] = (),
        source_titles: tuple[str, ...] = (),
        recent_turns: tuple[Turn, ...] = (),
    ) -> RetrievalPlan:
        """Return a validated plan without executing any retrieval operation."""
        question = _normalize_required_text(question, "question")
        table_of_contents = _validate_text_tuple(table_of_contents, "table_of_contents")
        source_titles = _validate_text_tuple(source_titles, "source_titles")
        recent_turns = _validate_recent_turns(recent_turns)

        messages = (
            *_context_messages(recent_turns),
            Message(
                role=MessageRole.USER,
                content=_planning_request(question, table_of_contents, source_titles),
            ),
        )
        result = await self._llm.complete(
            system=_PLANNER_SYSTEM_PROMPT,
            messages=messages,
            structured_output=FrozenMetadata(RetrievalPlan.model_json_schema()),
            max_tokens=_PLANNER_MAX_TOKENS,
        )
        plan = _validated_plan(result)
        if not any(
            subquery.retrieval_mode in (RetrievalMode.DENSE, RetrievalMode.HYBRID)
            for subquery in plan.sub_queries
        ):
            raise IntegrityError("planner output does not contain a HyDE dense query")
        return plan

    async def embed_hyde(self, plan: RetrievalPlan) -> EmbeddingVector:
        """Embed the plan's HyDE paragraph through the configured provider."""
        if not isinstance(plan, RetrievalPlan):
            raise TypeError("plan must be RetrievalPlan")
        hyde_query = next(
            (
                subquery
                for subquery in plan.sub_queries
                if subquery.retrieval_mode in (RetrievalMode.DENSE, RetrievalMode.HYBRID)
            ),
            None,
        )
        if hyde_query is None:
            raise IntegrityError("retrieval plan does not contain a HyDE dense query")
        vector = await self._embedding_provider.embed(hyde_query.query_text)
        if len(vector) != self._embedding_provider.dimensions:
            raise IntegrityError("HyDE embedding dimensions do not match the provider")
        if not vector or any(
            isinstance(component, bool)
            or not isinstance(component, (int, float))
            or not math.isfinite(component)
            for component in vector
        ):
            raise IntegrityError("HyDE embedding contains invalid components")
        return vector

    async def plan_with_hyde_embedding(
        self,
        question: str,
        *,
        table_of_contents: tuple[str, ...] = (),
        source_titles: tuple[str, ...] = (),
        recent_turns: tuple[Turn, ...] = (),
    ) -> tuple[RetrievalPlan, EmbeddingVector]:
        """Create a plan and embed its hypothetical paragraph in one operation."""
        plan = await self.plan(
            question,
            table_of_contents=table_of_contents,
            source_titles=source_titles,
            recent_turns=recent_turns,
        )
        return plan, await self.embed_hyde(plan)


def _validated_plan(result: CompletionResult) -> RetrievalPlan:
    if not isinstance(result, CompletionResult):
        raise IntegrityError("planner returned an invalid completion result")
    if result.text is not None:
        raise IntegrityError("planner returned text instead of structured output")
    try:
        return RetrievalPlan.model_validate(result.structured)
    except (TypeError, ValueError, ValidationError) as error:
        raise IntegrityError("planner returned an invalid RetrievalPlan") from error


def _context_messages(turns: tuple[Turn, ...]) -> tuple[Message, ...]:
    messages: list[Message] = []
    for turn in turns[-_MAX_WORKING_MEMORY_TURNS:]:
        role = MessageRole.USER if turn.role is TurnRole.USER else MessageRole.ASSISTANT
        messages.append(Message(role=role, content=turn.content))
    return tuple(messages)


def _planning_request(
    question: str,
    table_of_contents: tuple[str, ...],
    source_titles: tuple[str, ...],
) -> str:
    toc = "\n".join(f"- {heading}" for heading in table_of_contents) or "(not supplied)"
    sources = "\n".join(f"- {title}" for title in source_titles) or "(not supplied)"
    return (
        f"Original question:\n{question}\n\n"
        f"Active notebook table of contents:\n{toc}\n\n"
        f"Active notebook sources:\n{sources}"
    )


def _normalize_required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _validate_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    return tuple(_normalize_required_text(value, field_name) for value in values)


def _validate_recent_turns(turns: tuple[Turn, ...]) -> tuple[Turn, ...]:
    if not isinstance(turns, tuple):
        raise TypeError("recent_turns must be a tuple")
    if any(not isinstance(turn, Turn) for turn in turns):
        raise TypeError("recent_turns must contain Turn instances")
    return turns
