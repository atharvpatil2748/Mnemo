"""Immutable Module 6.10 final-QA contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from ._shared import require_non_empty, require_tuple, require_uuid
from .citation import CitationResolutionResult, CitationResolutionStatus
from .context import DocumentContextLabel
from .notebook import Citation
from .retrieval import MetadataFilter


class FinalQAStatus(StrEnum):
    CITATION_RESOLVED = "citation_resolved"
    UNMARKED = "unmarked"
    NO_CONTEXT = "no_context"


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalQARequest:
    query: str
    metadata_filter: MetadataFilter
    global_limit: int
    context_budget: int
    system_prompt: str
    max_output_tokens: int
    session_id: UUID
    user_turn_id: UUID
    assistant_turn_id: UUID
    table_of_contents: tuple[str, ...] = ()
    source_titles: tuple[str, ...] = ()
    document_labels: tuple[DocumentContextLabel, ...] = ()

    def __post_init__(self) -> None:
        normalized = " ".join(self.query.split())
        require_non_empty(normalized, "query")
        object.__setattr__(self, "query", normalized)
        if not isinstance(self.metadata_filter, MetadataFilter):
            raise TypeError("metadata_filter must be MetadataFilter")
        _bounded(self.global_limit, "global_limit", 100)
        _bounded(self.context_budget, "context_budget", 1_000_000)
        require_non_empty(self.system_prompt, "system_prompt")
        _bounded(self.max_output_tokens, "max_output_tokens", 4096)
        require_uuid(self.session_id, "session_id")
        require_uuid(self.user_turn_id, "user_turn_id")
        require_uuid(self.assistant_turn_id, "assistant_turn_id")
        _text_tuple(self.table_of_contents, "table_of_contents")
        _text_tuple(self.source_titles, "source_titles")
        require_tuple(self.document_labels, "document_labels")
        if any(not isinstance(item, DocumentContextLabel) for item in self.document_labels):
            raise TypeError("document_labels must contain DocumentContextLabel values")
        keys = tuple((item.document_id, item.version_id) for item in self.document_labels)
        if len(keys) != len(set(keys)):
            raise ValueError("document label exact-version keys must be unique")


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalQAResult:
    citation_result: CitationResolutionResult
    status: FinalQAStatus

    def __post_init__(self) -> None:
        if not isinstance(self.citation_result, CitationResolutionResult):
            raise TypeError("citation_result must be CitationResolutionResult")
        if not isinstance(self.status, FinalQAStatus):
            raise TypeError("status must be FinalQAStatus")
        expected = {
            CitationResolutionStatus.RESOLVED: FinalQAStatus.CITATION_RESOLVED,
            CitationResolutionStatus.UNMARKED: FinalQAStatus.UNMARKED,
            CitationResolutionStatus.NO_CONTEXT: FinalQAStatus.NO_CONTEXT,
        }[self.citation_result.status]
        if self.status is not expected:
            raise ValueError("final QA status does not match citation resolution status")

    @property
    def query(self) -> str:
        return self.citation_result.answer_result.query

    @property
    def answer(self) -> str | None:
        return self.citation_result.answer_result.answer

    @property
    def citations(self) -> tuple[Citation, ...]:
        return self.citation_result.citations


def _bounded(value: object, name: str, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be from 1 through {maximum}")


def _text_tuple(value: object, name: str) -> None:
    require_tuple(value, name)
    for item in value if isinstance(value, tuple) else ():
        require_non_empty(item, f"{name} entry")
