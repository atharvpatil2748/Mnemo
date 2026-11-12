"""Pre-retrieval integrity tests for the separately authored MVEA language cohort."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from scripts import bind_module_894_mvea_language as binder


def test_language_cases_are_snapshot_bound_before_retrieval() -> None:
    manifest = binder.bind()
    cases = manifest["cases"]
    assert len(cases) == 90
    assert manifest["judgment_method"] == "DETERMINISTIC_ENGINEERING"
    assert manifest["human_relevance_reviewed"] is False
    assert manifest["semantic_relevance_adjudicated"] is False
    assert manifest["active_alias_digest"] == binder.EXPECTED_ALIAS
    assert manifest["snapshot_sha256"] == binder.EXPECTED_SNAPSHOT_SHA256
    assert len({case["case_id"] for case in cases}) == 90
    counts = Counter((case["query_language"], case["document_language"]) for case in cases)
    assert all(
        counts[(query, document)] == 10
        for query in binder.LANGUAGES
        for document in binder.LANGUAGES
    )
    assert all(case["targets"] and case["selected_notebooks"] for case in cases)
    assert all(
        target["notebook_id"] in case["selected_notebooks"]
        for case in cases
        for target in case["targets"]
    )


def test_language_binding_rejects_wrong_disposable_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binder, "EXPECTED_ALIAS", "0" * 64)
    with pytest.raises(ValueError, match="active alias differs"):
        binder.bind()


def test_language_binding_rejects_repeated_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blueprint = json.loads(binder.BLUEPRINT.read_text(encoding="utf-8"))
    blueprint["targets"][1]["chunk"] = blueprint["targets"][0]["chunk"]
    path = tmp_path / "duplicate-blueprint.json"
    path.write_text(json.dumps(blueprint, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(binder, "BLUEPRINT", path)
    with pytest.raises(ValueError, match="invalid or repeated target"):
        binder.bind()
