"""ADR-0046 deterministic final-QA orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from mnemo.interfaces import (
    ConflictError,
    ContractValidationError,
    Message,
    MessageRole,
    NotFoundError,
    StorageInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    CitationResolutionStatus,
    FinalQARequest,
    FinalQAResult,
    FinalQAStatus,
    GroundedAnswerStatus,
    MetadataFilter,
    RetrievalPlan,
    Session,
    SubQuery,
    Turn,
    TurnRole,
)


class FinalQAOrchestrator:
    """Compose the exact completed Phase 6 stages without provider lifecycle work."""

    __slots__ = (
        "_answer",
        "_citation",
        "_clock",
        "_context",
        "_fusion",
        "_locks",
        "_planner",
        "_reranker",
        "_storage",
    )

    def __init__(
        self,
        planner: Any,
        fusion: Any,
        reranker: Any,
        context_builder: Any,
        answer_generator: Any,
        citation_engine: Any,
        storage: StorageInterfaceV1,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(storage, StorageInterfaceV1):
            raise TypeError("storage must implement StorageInterfaceV1")
        if not callable(clock):
            raise TypeError("clock must be callable")
        for name, component, method in (
            ("planner", planner, "plan"),
            ("fusion", fusion, "execute"),
            ("reranker", reranker, "execute"),
            ("context_builder", context_builder, "build"),
            ("answer_generator", answer_generator, "generate"),
            ("citation_engine", citation_engine, "resolve_and_persist"),
        ):
            if not callable(getattr(component, method, None)):
                raise TypeError(f"{name} must expose {method}()")
        self._planner = planner
        self._fusion = fusion
        self._reranker = reranker
        self._context = context_builder
        self._answer = answer_generator
        self._citation = citation_engine
        self._storage = storage
        self._clock = clock
        self._locks: dict[object, asyncio.Lock] = {}

    async def execute(self, request: FinalQARequest) -> FinalQAResult:
        if not isinstance(request, FinalQARequest):
            raise ContractValidationError("request must be FinalQARequest")
        session = await self._session(request.session_id)
        user_turn = _initial_user_turn(session, request)
        history = session.turns[: user_turn.sequence + 1]
        messages = tuple(
            Message(role=MessageRole(turn.role.value), content=turn.content) for turn in history
        )
        planned = await self._planner.plan(
            request.query,
            table_of_contents=request.table_of_contents,
            source_titles=request.source_titles,
            recent_turns=history,
        )
        effective = _effective_plan(planned, request.metadata_filter)
        if effective.requires_multi_hop:
            raise UnsupportedError("multi-hop final QA is unavailable in V1")
        fusion = await self._fusion.execute(effective, global_limit=request.global_limit)
        reranked = await self._reranker.execute(request.query, fusion)
        context = await self._context.build(
            reranked,
            context_budget=request.context_budget,
            system_prompt=request.system_prompt,
            session_history=messages,
            document_labels=request.document_labels,
        )
        answer = await self._answer.generate(
            context,
            max_output_tokens=request.max_output_tokens,
        )
        if answer.status is GroundedAnswerStatus.NO_CONTEXT:
            citation = await self._citation.resolve_and_persist(
                answer,
                assistant_turn=None,
                document_labels=(),
            )
            return _result(citation)

        lock = self._locks.setdefault(request.session_id, asyncio.Lock())
        async with lock:
            current = await self._session(request.session_id)
            assistant = await self._assistant_turn(current, user_turn, request, answer.answer)
            selected_keys = {
                (
                    item.reranked_result.fused_result.chunk.document_id,
                    item.reranked_result.fused_result.chunk.version_id,
                )
                for item in context.items
            }
            labels = tuple(
                label
                for label in request.document_labels
                if (label.document_id, label.version_id) in selected_keys
            )
            citation = await self._citation.resolve_and_persist(
                answer,
                assistant_turn=assistant,
                document_labels=labels,
            )
            return _result(citation)

    async def _session(self, session_id: UUID) -> Session:
        session = await self._storage.get_session(session_id)
        if session is None:
            raise NotFoundError("final-QA session does not exist")
        return session

    async def _assistant_turn(
        self,
        session: Session,
        original_user: Turn,
        request: FinalQARequest,
        answer: str | None,
    ) -> Turn:
        if answer is None:
            raise ContractValidationError("generated answer text is unavailable")
        existing = next(
            (turn for turn in session.turns if turn.turn_id == request.assistant_turn_id), None
        )
        expected_sequence = original_user.sequence + 1
        if existing is not None:
            if (
                existing.session_id != request.session_id
                or existing.role is not TurnRole.ASSISTANT
                or existing.sequence != expected_sequence
                or existing.content != answer
            ):
                raise ConflictError("assistant turn identity conflicts with persisted history")
            return existing
        current_user = _required_user_turn(session, request)
        created_at = self._clock()
        _validate_clock(created_at, current_user)
        assistant = Turn(
            turn_id=request.assistant_turn_id,
            session_id=request.session_id,
            sequence=expected_sequence,
            role=TurnRole.ASSISTANT,
            content=answer,
            created_at=created_at,
        )
        await self._storage.append_turn(request.session_id, assistant)
        return assistant


def _required_user_turn(session: Session, request: FinalQARequest) -> Turn:
    user = next((turn for turn in session.turns if turn.turn_id == request.user_turn_id), None)
    if (
        user is None
        or user.role is not TurnRole.USER
        or user.content != request.query
        or not session.turns
        or session.turns[-1] is not user
    ):
        raise ContractValidationError("user turn must be the final persisted query turn")
    return user


def _initial_user_turn(session: Session, request: FinalQARequest) -> Turn:
    user = next((turn for turn in session.turns if turn.turn_id == request.user_turn_id), None)
    if user is None or user.role is not TurnRole.USER or user.content != request.query:
        raise ContractValidationError("user turn must be the persisted query turn")
    tail = session.turns[user.sequence + 1 :]
    if not tail:
        if session.turns[-1] is not user:
            raise ContractValidationError("user turn must be the final persisted query turn")
        return user
    if len(tail) == 1 and tail[0].turn_id == request.assistant_turn_id:
        return user
    raise ContractValidationError("session contains turns after the requested query")


def _effective_plan(plan: RetrievalPlan, hard: MetadataFilter) -> RetrievalPlan:
    if not isinstance(plan, RetrievalPlan):
        raise ContractValidationError("planner returned an invalid RetrievalPlan")
    return RetrievalPlan(
        intent=plan.intent,
        requires_multi_hop=plan.requires_multi_hop,
        requires_multi_doc=plan.requires_multi_doc,
        sub_queries=tuple(
            SubQuery(
                query_text=item.query_text,
                retrieval_mode=item.retrieval_mode,
                filters=_merge_filter(item.filters, hard),
                max_results=item.max_results,
            )
            for item in plan.sub_queries
        ),
    )


def _merge_filter(planned: MetadataFilter, hard: MetadataFilter) -> MetadataFilter:
    if (
        planned.notebook_id is not None
        and hard.notebook_id is not None
        and planned.notebook_id != hard.notebook_id
    ):
        raise ContractValidationError("planner notebook filter conflicts with hard filter")
    date_after = (
        max(item for item in (planned.date_after, hard.date_after) if item is not None)
        if (planned.date_after is not None or hard.date_after is not None)
        else None
    )
    date_before = (
        min(item for item in (planned.date_before, hard.date_before) if item is not None)
        if (planned.date_before is not None or hard.date_before is not None)
        else None
    )
    if date_after is not None and date_before is not None and date_after > date_before:
        raise ContractValidationError("projected date filter is inverted")
    return MetadataFilter(
        notebook_id=hard.notebook_id or planned.notebook_id,
        doc_types=_intersection(planned.doc_types, hard.doc_types, "doc_types"),
        date_after=date_after,
        date_before=date_before,
        source_ids=_intersection(planned.source_ids, hard.source_ids, "source_ids"),
    )


def _intersection(left: tuple[Any, ...], right: tuple[Any, ...], name: str) -> tuple[Any, ...]:
    if not left:
        return right
    if not right:
        return left
    common = tuple(item for item in left if item in frozenset(right))
    if not common:
        raise ContractValidationError(f"{name} hard-filter intersection is empty")
    return common


def _validate_clock(value: object, user: Turn) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ContractValidationError("assistant clock must return timezone-aware UTC")
    if value < user.created_at:
        raise ContractValidationError("assistant timestamp precedes user turn")


def _result(citation: Any) -> FinalQAResult:
    mapping = {
        CitationResolutionStatus.RESOLVED: FinalQAStatus.CITATION_RESOLVED,
        CitationResolutionStatus.UNMARKED: FinalQAStatus.UNMARKED,
        CitationResolutionStatus.NO_CONTEXT: FinalQAStatus.NO_CONTEXT,
    }
    return FinalQAResult(citation_result=citation, status=mapping[citation.status])
