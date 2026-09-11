"""Deterministic comparison primitives layered over structured evidence (WP-11)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from mnemo.interfaces.errors import ContractValidationError
from mnemo.models.structured_retrieval import StructuredValue, StructuredValueStatus

from .structured import compare_structured_values


class ComparisonRelation(StrEnum):
    LESS = "less"
    EQUAL = "equal"
    GREATER = "greater"


@dataclass(frozen=True, slots=True, kw_only=True)
class DeterministicComparisonResultV1:
    relation: ComparisonRelation
    difference: Decimal | None
    left: StructuredValue
    right: StructuredValue


class DeterministicComparisonServiceV1:
    """Compare already-authorized typed values without LLM or lexical coercion."""

    def compare(
        self, *, left: StructuredValue, right: StructuredValue
    ) -> DeterministicComparisonResultV1:
        if (
            left.status is not StructuredValueStatus.VALUE_PRESENT
            or right.status is not StructuredValueStatus.VALUE_PRESENT
        ):
            raise ContractValidationError("comparison requires two present structured values")
        ordering = compare_structured_values(left, right)
        relation = (
            ComparisonRelation.LESS
            if ordering < 0
            else ComparisonRelation.GREATER
            if ordering > 0
            else ComparisonRelation.EQUAL
        )
        difference: Decimal | None = None
        if left.field_type.value in {"integer", "decimal", "float"}:
            difference = Decimal(str(left.value)) - Decimal(str(right.value))
        return DeterministicComparisonResultV1(
            relation=relation, difference=difference, left=left, right=right
        )
