"""Immutable Module 6.8 grounded-answer records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ._shared import require_non_empty, require_positive
from .context import ContextBuildResult


class GroundedAnswerStatus(StrEnum):
    """Typed outcomes of grounded answer generation."""

    GENERATED = "generated"
    NO_CONTEXT = "no_context"


@dataclass(frozen=True, slots=True, kw_only=True)
class GenerationEvidence:
    """Provider and token evidence for one generated answer."""

    provider: str
    model: str
    tokenizer_id: str
    prompt_token_count: int
    max_output_tokens: int
    answer_token_count: int

    def __post_init__(self) -> None:
        require_non_empty(self.provider, "provider")
        require_non_empty(self.model, "model")
        require_non_empty(self.tokenizer_id, "tokenizer_id")
        if isinstance(self.prompt_token_count, bool) or not isinstance(
            self.prompt_token_count, int
        ):
            raise TypeError("prompt_token_count must be an integer")
        if self.prompt_token_count < 0:
            raise ValueError("prompt_token_count must be non-negative")
        _validate_output_bound(self.max_output_tokens)
        require_positive(self.answer_token_count, "answer_token_count")
        if self.answer_token_count > self.max_output_tokens:
            raise ValueError("answer_token_count exceeds max_output_tokens")


@dataclass(frozen=True, slots=True, kw_only=True)
class GroundedAnswerResult:
    """Canonical provenance-preserving Module 6.8 output."""

    context_result: ContextBuildResult
    query: str
    status: GroundedAnswerStatus
    answer: str | None
    generation_evidence: GenerationEvidence | None

    def __post_init__(self) -> None:
        if not isinstance(self.context_result, ContextBuildResult):
            raise TypeError("context_result must be ContextBuildResult")
        require_non_empty(self.query, "query")
        if self.query != self.context_result.rerank_result.query:
            raise ValueError("query must equal the retained context query")
        if not isinstance(self.status, GroundedAnswerStatus):
            raise TypeError("status must be GroundedAnswerStatus")
        if self.status is GroundedAnswerStatus.GENERATED:
            if not self.context_result.items:
                raise ValueError("generated answer requires non-empty context")
            if self.answer is None:
                raise ValueError("generated answer requires answer text")
            require_non_empty(self.answer, "answer")
            if not isinstance(self.generation_evidence, GenerationEvidence):
                raise ValueError("generated answer requires generation evidence")
            if self.generation_evidence.tokenizer_id != self.context_result.tokenizer_id:
                raise ValueError("generation tokenizer must match the context tokenizer")
        else:
            if self.context_result.items or self.context_result.empty_reason is None:
                raise ValueError("no-context answer requires a typed empty context")
            if self.answer is not None or self.generation_evidence is not None:
                raise ValueError("no-context answer cannot contain answer or evidence")


def _validate_output_bound(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("max_output_tokens must be an integer")
    if not 1 <= value <= 4096:
        raise ValueError("max_output_tokens must be from 1 through 4096")
