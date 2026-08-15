"""Immutable Module 6.9 citation-resolution records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .answer import GroundedAnswerResult, GroundedAnswerStatus
from .notebook import Citation, Turn, TurnRole


class CitationResolutionStatus(StrEnum):
    """Typed outcomes of citation resolution and persistence."""

    RESOLVED = "resolved"
    UNMARKED = "unmarked"
    NO_CONTEXT = "no_context"


@dataclass(frozen=True, slots=True, kw_only=True)
class CitationResolutionResult:
    """Canonical provenance-preserving Module 6.9 output."""

    answer_result: GroundedAnswerResult
    assistant_turn: Turn | None
    status: CitationResolutionStatus
    citations: tuple[Citation, ...]
    persisted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.answer_result, GroundedAnswerResult):
            raise TypeError("answer_result must be GroundedAnswerResult")
        if self.assistant_turn is not None and not isinstance(self.assistant_turn, Turn):
            raise TypeError("assistant_turn must be Turn or None")
        if not isinstance(self.status, CitationResolutionStatus):
            raise TypeError("status must be CitationResolutionStatus")
        if not isinstance(self.citations, tuple) or any(
            not isinstance(item, Citation) for item in self.citations
        ):
            raise TypeError("citations must be a tuple of Citation values")
        if not isinstance(self.persisted, bool):
            raise TypeError("persisted must be boolean")
        if self.status is CitationResolutionStatus.RESOLVED:
            self._validate_resolved()
        elif self.status is CitationResolutionStatus.UNMARKED:
            self._validate_unmarked()
        else:
            self._validate_no_context()

    def _validate_resolved(self) -> None:
        if self.answer_result.status is not GroundedAnswerStatus.GENERATED:
            raise ValueError("resolved citations require a generated answer")
        if self.assistant_turn is None or self.assistant_turn.role is not TurnRole.ASSISTANT:
            raise ValueError("resolved citations require an assistant turn")
        if self.assistant_turn.content != self.answer_result.answer:
            raise ValueError("assistant turn content must equal the generated answer")
        if not self.citations or not self.persisted:
            raise ValueError("resolved status requires persisted citations")
        if any(item.turn_id != self.assistant_turn.turn_id for item in self.citations):
            raise ValueError("all citations must reference the retained assistant turn")
        source_numbers = tuple(item.source_number for item in self.citations)
        if len(source_numbers) != len(set(source_numbers)):
            raise ValueError("resolved citation source numbers must be unique")

    def _validate_unmarked(self) -> None:
        if self.answer_result.status is not GroundedAnswerStatus.GENERATED:
            raise ValueError("unmarked status requires a generated answer")
        if self.assistant_turn is None or self.assistant_turn.role is not TurnRole.ASSISTANT:
            raise ValueError("unmarked status requires an assistant turn")
        if self.assistant_turn.content != self.answer_result.answer:
            raise ValueError("assistant turn content must equal the generated answer")
        if self.citations or self.persisted:
            raise ValueError("unmarked status cannot contain persisted citations")

    def _validate_no_context(self) -> None:
        if self.answer_result.status is not GroundedAnswerStatus.NO_CONTEXT:
            raise ValueError("no-context status requires a no-context answer result")
        if self.assistant_turn is not None or self.citations or self.persisted:
            raise ValueError("no-context status cannot contain turn or citation state")
