from decimal import Decimal
from uuid import UUID

import pytest
from mnemo.interfaces import ContractValidationError
from mnemo.models import (
    FrozenMetadata,
    StructuredEvidence,
    StructuredFieldType,
    StructuredValue,
    StructuredValueStatus,
)
from mnemo.retrieval import ComparisonRelation, DeterministicComparisonServiceV1


def _value(
    number: str, *, status: StructuredValueStatus = StructuredValueStatus.VALUE_PRESENT
) -> StructuredValue:
    evidence = StructuredEvidence(
        candidate_id=UUID(int=1),
        notebook_id=UUID(int=2),
        source_id=UUID(int=3),
        document_id=UUID(int=4),
        version_id=UUID(int=5),
        chunk_id="a" * 64,
        occurrence_id=None,
        derivation_id=None,
        locator=FrozenMetadata(),
        retrieval_paths=("structured",),
        extraction_method="test",
    )
    return StructuredValue(
        field="cpi",
        field_type=StructuredFieldType.DECIMAL,
        status=status,
        value=Decimal(number) if status is StructuredValueStatus.VALUE_PRESENT else None,
        unit="CPI",
        evidence=(evidence,) if status is StructuredValueStatus.VALUE_PRESENT else (),
    )


def test_numeric_comparison_is_typed_and_provenance_preserving() -> None:
    result = DeterministicComparisonServiceV1().compare(left=_value("10.0"), right=_value("9.9"))
    assert result.relation is ComparisonRelation.GREATER
    assert result.difference == Decimal("0.1")
    assert result.left.evidence[0].document_id == UUID(int=4)


def test_missing_values_are_not_compared() -> None:
    with pytest.raises(ContractValidationError, match="present"):
        DeterministicComparisonServiceV1().compare(
            left=_value("8.9"),
            right=_value("0", status=StructuredValueStatus.VALUE_MISSING),
        )
