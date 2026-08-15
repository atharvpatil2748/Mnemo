"""ADR-0045 deterministic citation resolution and persistence."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from mnemo.interfaces import ContractValidationError, IntegrityError, StorageInterfaceV1
from mnemo.models.answer import GroundedAnswerResult, GroundedAnswerStatus
from mnemo.models.citation import CitationResolutionResult, CitationResolutionStatus
from mnemo.models.context import ContextItem, DocumentContextLabel
from mnemo.models.notebook import Citation, Turn, TurnRole

_MARKER_PREFIX = "[source:"
_MARKER = re.compile(r"\[source:([1-9][0-9]*)\]", flags=re.ASCII)


class CitationEngine:
    """Resolve typed source markers and persist deterministic citations."""

    __slots__ = ("_clock", "_storage")

    def __init__(
        self,
        storage: StorageInterfaceV1,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(storage, StorageInterfaceV1):
            raise TypeError("storage must implement StorageInterfaceV1")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._storage = storage
        self._clock = clock

    async def resolve_and_persist(
        self,
        answer_result: GroundedAnswerResult,
        *,
        assistant_turn: Turn | None,
        document_labels: tuple[DocumentContextLabel, ...] = (),
    ) -> CitationResolutionResult:
        """Resolve and persist citations using the exact ADR-0045 semantics."""
        if not isinstance(answer_result, GroundedAnswerResult):
            raise ContractValidationError("answer_result must be GroundedAnswerResult")
        _validate_labels_type(document_labels)
        if answer_result.status is GroundedAnswerStatus.NO_CONTEXT:
            if assistant_turn is not None:
                raise ContractValidationError("no-context result cannot have an assistant turn")
            if document_labels:
                raise ContractValidationError("no-context result cannot have document labels")
            return CitationResolutionResult(
                answer_result=answer_result,
                assistant_turn=None,
                status=CitationResolutionStatus.NO_CONTEXT,
                citations=(),
                persisted=False,
            )

        turn = _validate_assistant_turn(answer_result, assistant_turn)
        context_items = answer_result.context_result.items
        _validate_provenance(answer_result, context_items)
        labels = _validate_labels(document_labels, context_items)
        marker_numbers = _parse_marker_numbers(_generated_answer(answer_result))
        if not marker_numbers:
            return CitationResolutionResult(
                answer_result=answer_result,
                assistant_turn=turn,
                status=CitationResolutionStatus.UNMARKED,
                citations=(),
                persisted=False,
            )

        items_by_source = {item.source_number: item for item in context_items}
        try:
            cited_items = tuple(items_by_source[number] for number in marker_numbers)
        except KeyError as error:
            raise IntegrityError(f"unknown source marker: {error.args[0]}") from error
        for item in cited_items:
            chunk = item.reranked_result.fused_result.chunk
            if (chunk.document_id, chunk.version_id) not in labels:
                raise ContractValidationError(
                    f"document title is unavailable for source {item.source_number}"
                )

        resolved_at = self._clock()
        _validate_resolution_time(resolved_at, turn)
        citations = tuple(_citation(turn, item, labels, resolved_at) for item in cited_items)
        for citation in citations:
            await self._storage.upsert_citation(citation)
        return CitationResolutionResult(
            answer_result=answer_result,
            assistant_turn=turn,
            status=CitationResolutionStatus.RESOLVED,
            citations=citations,
            persisted=True,
        )


def _validate_labels_type(labels: object) -> None:
    if not isinstance(labels, tuple) or any(
        not isinstance(item, DocumentContextLabel) for item in labels
    ):
        raise ContractValidationError(
            "document_labels must be a tuple of DocumentContextLabel values"
        )


def _validate_assistant_turn(
    answer_result: GroundedAnswerResult,
    assistant_turn: Turn | None,
) -> Turn:
    if not isinstance(assistant_turn, Turn):
        raise ContractValidationError("generated answer requires an assistant Turn")
    if assistant_turn.role is not TurnRole.ASSISTANT:
        raise ContractValidationError("citation target turn must have assistant role")
    if assistant_turn.content != answer_result.answer:
        raise ContractValidationError("assistant turn content must equal generated answer")
    return assistant_turn


def _validate_labels(
    document_labels: tuple[DocumentContextLabel, ...],
    context_items: tuple[ContextItem, ...],
) -> dict[tuple[UUID, UUID], DocumentContextLabel]:
    keys = tuple((item.document_id, item.version_id) for item in document_labels)
    if len(keys) != len(set(keys)):
        raise ContractValidationError("document label exact-version keys must be unique")
    selected_keys = {
        (
            item.reranked_result.fused_result.chunk.document_id,
            item.reranked_result.fused_result.chunk.version_id,
        )
        for item in context_items
    }
    if any(key not in selected_keys for key in keys):
        raise ContractValidationError("document label does not match selected context")
    return {key: label for key, label in zip(keys, document_labels, strict=True)}


def _parse_marker_numbers(answer: str) -> tuple[int, ...]:
    ordered: list[int] = []
    seen: set[int] = set()
    position = 0
    while True:
        marker_start = answer.find(_MARKER_PREFIX, position)
        if marker_start < 0:
            break
        match = _MARKER.match(answer, marker_start)
        if match is None:
            raise IntegrityError("answer contains a malformed source marker")
        try:
            source_number = int(match.group(1))
        except ValueError as error:
            raise IntegrityError("source marker number cannot be resolved") from error
        if source_number not in seen:
            seen.add(source_number)
            ordered.append(source_number)
        position = match.end()
    return tuple(ordered)


def _generated_answer(answer_result: GroundedAnswerResult) -> str:
    answer = answer_result.answer
    if answer is None:  # pragma: no cover - guarded by GroundedAnswerResult
        raise IntegrityError("generated answer text is unavailable")
    return answer


def _validate_provenance(
    answer_result: GroundedAnswerResult,
    context_items: tuple[ContextItem, ...],
) -> None:
    rerank_results = {id(item): item for item in answer_result.context_result.rerank_result.results}
    fusion_results = {
        item.chunk.id: item
        for item in answer_result.context_result.rerank_result.fusion_result.results
    }
    for item in context_items:
        reranked = item.reranked_result
        fused = reranked.fused_result
        if rerank_results.get(id(reranked)) is not reranked:
            raise IntegrityError("context item does not retain canonical reranking provenance")
        if fusion_results.get(fused.chunk.id) is not fused:
            raise IntegrityError("context item does not retain canonical fusion provenance")


def _validate_resolution_time(resolved_at: object, turn: Turn) -> None:
    if not isinstance(resolved_at, datetime):
        raise IntegrityError("citation clock must return datetime")
    if resolved_at.tzinfo is None or resolved_at.utcoffset() != timedelta(0):
        raise IntegrityError("citation clock must return timezone-aware UTC")
    if resolved_at < turn.created_at:
        raise IntegrityError("citation resolution time precedes assistant turn")


def _citation(
    turn: Turn,
    item: ContextItem,
    labels: dict[tuple[UUID, UUID], DocumentContextLabel],
    resolved_at: datetime,
) -> Citation:
    chunk = item.reranked_result.fused_result.chunk
    source_number = item.source_number
    identity = uuid5(
        NAMESPACE_URL,
        f"mnemo:citation:v1:{str(turn.turn_id).lower()}:{source_number}:{chunk.id}",
    )
    try:
        return Citation(
            citation_id=identity,
            turn_id=turn.turn_id,
            source_number=source_number,
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            document_title=labels[(chunk.document_id, chunk.version_id)].title,
            page_number=chunk.position.page_number,
            heading_path=chunk.heading_path,
            verbatim_quote=chunk.text,
            created_at=resolved_at,
        )
    except (TypeError, ValueError) as error:
        raise IntegrityError(f"constructed citation is invalid: {error}") from error
