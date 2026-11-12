"""The expanded cohort is hash-bound and discloses its OCR evidence shortage."""

from __future__ import annotations

import pytest

from scripts import assemble_module_894_mvea as assembler


def test_cohort_binds_all_independently_grounded_sections() -> None:
    cohort = assembler.assemble()
    assert cohort["grounded_case_count"] == 130
    assert cohort["planned_case_count"] == 140
    assert cohort["status"] == "PARTIAL_GROUNDED_COHORT"
    assert cohort["unfilled_slices"]["ocr_only"]["grounded"] == 0
    assert {key: value["count"] for key, value in cohort["sections"].items()} == {
        "language": 90,
        "visual": 20,
        "security": 20,
    }
    assert cohort["human_relevance_reviewed"] is False


def test_cohort_rejects_changed_frozen_qrel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(assembler.INPUTS, "language", ("visual-identity.v1.json", 90))
    with pytest.raises(ValueError, match="invalid language cohort"):
        assembler.assemble()
