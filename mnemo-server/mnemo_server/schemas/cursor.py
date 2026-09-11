"""Lossless transport mapping for Phase 8.5 completeness and coverage."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TransportCompletenessV2(StrEnum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    PARTIAL = "partial"
    BOUNDED = "bounded"
    RANKED = "ranked"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CoverageResponseV2(BaseModel):
    """Machine-readable proof surface for what a page did and did not cover."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    completeness: TransportCompletenessV2
    searched: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    omissions: tuple[str, ...] = ()
    next_cursor: str | None = Field(
        default=None,
        description="Opaque continuation state; pass unchanged to the same operation.",
    )

    @model_validator(mode="after")
    def _cursor_matches_completeness(self) -> CoverageResponseV2:
        if (
            self.next_cursor is not None
            and self.completeness is not TransportCompletenessV2.TRUNCATED
        ):
            raise ValueError("a continuation cursor requires truncated completeness")
        if self.completeness is TransportCompletenessV2.TRUNCATED and self.next_cursor is None:
            raise ValueError("truncated completeness requires a continuation cursor")
        if self.completeness is TransportCompletenessV2.COMPLETE and (
            self.unavailable or self.omissions
        ):
            raise ValueError("complete coverage cannot contain unavailable paths or omissions")
        return self


def map_transport_coverage(
    completeness: object,
    *,
    next_cursor: str | None,
    searched: tuple[str, ...] = (),
    unavailable: tuple[str, ...] = (),
    omissions: tuple[str, ...] = (),
) -> CoverageResponseV2:
    """Map domain enums by value without upgrading partial evidence to complete."""

    raw = getattr(completeness, "value", completeness)
    try:
        state = TransportCompletenessV2(str(raw))
    except ValueError:
        state = TransportCompletenessV2.UNKNOWN
    if next_cursor is not None:
        state = TransportCompletenessV2.TRUNCATED
    elif state is TransportCompletenessV2.COMPLETE and (unavailable or omissions):
        state = TransportCompletenessV2.PARTIAL
    return CoverageResponseV2(
        completeness=state,
        searched=searched,
        unavailable=unavailable,
        omissions=omissions,
        next_cursor=next_cursor,
    )
