"""Offline ranking replay never merges distinct notebook memberships."""

from __future__ import annotations

from scripts.compare_module_894_selection_offline import round_robin, score, unique


def _row(notebook: str, evidence: str, representation: str) -> dict[str, str]:
    return {
        "notebook_id": notebook,
        "source_id": "source",
        "document_id": "document",
        "version_id": "version",
        "evidence_id": evidence,
        "representation": representation,
    }


def test_unique_evidence_preserves_notebook_and_first_rank() -> None:
    rows = [
        _row("a", "same", "canonical_text"),
        _row("a", "same", "multilingual_text"),
        _row("b", "same", "canonical_text"),
        _row("a", "other", "multilingual_text"),
    ]
    assert unique(rows) == [rows[0], rows[2], rows[3]]
    metrics = score(rows, {("a", "source", "document", "version", "same")})
    assert metrics["recall_at_10"] == 1.0
    assert metrics["distinct_evidence_at_10"] == 3.0


def test_representation_round_robin_is_offline_only_and_stable() -> None:
    rows = [
        _row("a", "one", "canonical_text"),
        _row("a", "two", "canonical_text"),
        _row("a", "three", "visual_vector"),
    ]
    assert round_robin(rows) == [rows[0], rows[2], rows[1]]
