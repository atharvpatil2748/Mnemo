"""Pre-retrieval verification for retained original-image engineering targets."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from mnemo.models.advanced_retrieval import AdvancedRetrievalCandidate, EvidenceRepresentation

from scripts import bind_module_894_mvea_visual as binder
from scripts.evaluate_module_894_multimodal import (
    _visual_candidate_key,
    _visual_candidate_record,
)


def test_visual_cases_are_hash_and_projection_bound() -> None:
    manifest = binder.bind()
    cases = manifest["cases"]
    assert len(cases) == 20
    assert manifest["semantic_relevance_adjudicated"] is False
    assert Counter(case["representation"] for case in cases) == {
        "vision_text": 10,
        "visual_vector": 10,
    }
    assert all(case["targets"] for case in cases)
    assert all(
        target["notebook_id"] in case["selected_notebooks"]
        and len(target["asset_sha256"]) == 64
        and target["generation_id"]
        for case in cases
        for target in case["targets"]
    )


def test_visual_binding_rejects_missing_original_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        binder, "_asset_blob", lambda _digest: (_ for _ in ()).throw(ValueError("missing blob"))
    )
    with pytest.raises(ValueError, match="missing blob"):
        binder.bind()


def test_visual_binding_rejects_duplicate_occurrence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blueprint = json.loads(binder.BLUEPRINT.read_text(encoding="utf-8"))
    blueprint["targets"][1]["vision_derivation_id"] = blueprint["targets"][0][
        "vision_derivation_id"
    ]
    path = tmp_path / "duplicate-visual.json"
    path.write_text(json.dumps(blueprint), encoding="utf-8")
    monkeypatch.setattr(binder, "BLUEPRINT", path)
    with pytest.raises(ValueError, match="duplicate or incompatible"):
        binder.bind()


def test_pipeline_trace_identity_preserves_ancestry_without_content() -> None:
    candidate = cast(
        AdvancedRetrievalCandidate,
        SimpleNamespace(
            candidate_id=UUID(int=10),
            notebook_id=UUID(int=1),
            source_id=UUID(int=2),
            document_id=UUID(int=3),
            version_id=UUID(int=4),
            representation=EvidenceRepresentation.VISION_ANALYSIS,
            chunk=None,
            occurrence_id=UUID(int=5),
            derivation_id=UUID(int=6),
            evidence_id=None,
            fused_score=0.25,
            locator={"page_number": 2, "evidence_kind": "vision_description"},
            paths=(SimpleNamespace(path="vision_analysis", source_rank=1),),
            content="must-not-appear-in-diagnostic",
        ),
    )

    identity = _visual_candidate_key(candidate)
    trace = _visual_candidate_record(candidate)

    assert identity == (
        str(UUID(int=1)),
        str(UUID(int=2)),
        str(UUID(int=3)),
        str(UUID(int=4)),
        str(UUID(int=6)),
    )
    assert trace["occurrence_id"] == str(UUID(int=5))
    assert trace["derivation_id"] == str(UUID(int=6))
    assert trace["locator_keys"] == ["evidence_kind", "page_number"]
    locator_digest = trace["locator_sha256"]
    assert isinstance(locator_digest, str) and len(locator_digest) == 64
    assert "content" not in trace
    assert "must-not-appear-in-diagnostic" not in repr(trace)
