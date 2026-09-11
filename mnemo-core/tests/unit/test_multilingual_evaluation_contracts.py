from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from mnemo.models.multilingual_evaluation import (
    CorpusPresenceEvidenceV1,
    EvaluationStageRecordV2,
    EvaluationStageStatus,
    EvaluationStageV2,
    QueryClassV2,
    QueryGroundingState,
    QueryRecordV2,
    RuntimeParityEvidenceV1,
)
from pydantic import ValidationError

ZERO = "0" * 64


def _query(**changes: object) -> QueryRecordV2:
    text = str(changes.pop("query_text", "grounded query"))
    values = {
        "query_id": "q-1",
        "query_text": text,
        "query_hash": hashlib.sha256(text.encode()).hexdigest(),
        "query_class": QueryClassV2.SEMANTIC_QUALITY,
        "grounding_state": QueryGroundingState.GROUNDED,
        "topic_id": "topic",
        "include_in_ranking_metrics": True,
    }
    return QueryRecordV2.model_validate({**values, **changes})


def test_evaluation_query_contract_separates_semantic_and_behavioral_metrics() -> None:
    assert _query().include_in_ranking_metrics
    with pytest.raises(ValidationError, match="query hash mismatch"):
        _query(query_hash="1" * 64)
    for changes in (
        {"grounding_state": QueryGroundingState.UNGROUNDED},
        {"topic_id": None},
        {"include_in_ranking_metrics": False},
    ):
        with pytest.raises(ValidationError, match="semantic quality"):
            _query(**changes)
    behavioral = _query(
        query_class=QueryClassV2.ROUTING_BEHAVIORAL,
        include_in_ranking_metrics=False,
    )
    assert not behavioral.include_in_ranking_metrics
    with pytest.raises(ValidationError, match="non-semantic"):
        _query(query_class=QueryClassV2.NO_ANSWER)
    with pytest.raises(ValidationError, match="lowercase SHA-256"):
        _query(query_hash="bad")


def _presence(**changes: object) -> CorpusPresenceEvidenceV1:
    values = {
        "corpus_manifest_digest": ZERO,
        "source_census_digest": ZERO,
        "authorized_evidence_census_digest": ZERO,
        "notebook_id": uuid4(),
        "query_id": "q-1",
        "presence_state": "present",
        "relevant_evidence_reference_digests": ("1" * 64,),
        "census_algorithm_id": "census-v1",
    }
    return CorpusPresenceEvidenceV1.model_validate({**values, **changes})


def test_corpus_presence_contract_proves_presence_absence_or_unknown() -> None:
    assert _presence().presence_state == "present"
    assert (
        _presence(
            presence_state="absent_proven", relevant_evidence_reference_digests=()
        ).presence_state
        == "absent_proven"
    )
    assert (
        _presence(presence_state="unknown", relevant_evidence_reference_digests=()).presence_state
        == "unknown"
    )
    for changes, message in (
        ({"presence_state": "invalid"}, "presence state"),
        ({"relevant_evidence_reference_digests": ()}, "requires evidence"),
        ({"presence_state": "absent_proven"}, "cannot list"),
        ({"corpus_manifest_digest": "bad"}, "lowercase SHA-256"),
    ):
        with pytest.raises(ValidationError, match=message):
            _presence(**changes)


def _parity(**changes: object) -> RuntimeParityEvidenceV1:
    values = {
        "application_service_id": "app",
        "authorization_service_id": "auth",
        "retrieval_service_id": "retrieval",
        "reranker_public_protocol_id": "reranker",
        "query_preprocessing_identity": "query-v1",
        "document_preprocessing_identity": "doc-v1",
        "provenance_validator_id": "provenance",
        "parity_digest": ZERO,
    }
    return RuntimeParityEvidenceV1.model_validate({**values, **changes})


def test_runtime_parity_contract_rejects_private_or_caller_owned_paths() -> None:
    assert not _parity().direct_provider_calls
    for changes in (
        {"candidate_builder_id": "other"},
        {"tokenizer_policy_id": "other"},
        {"direct_provider_calls": True},
        {"private_runtime_access": True},
        {"caller_constructed_reranker_input": True},
    ):
        with pytest.raises(ValidationError, match="parity invariant"):
            _parity(**changes)
    with pytest.raises(ValidationError, match="lowercase SHA-256"):
        _parity(parity_digest="bad")


def test_evaluation_stage_digest_validation_accepts_optional_output() -> None:
    record = EvaluationStageRecordV2(
        stage=EvaluationStageV2.CORPUS,
        status=EvaluationStageStatus.PASSED,
        implementation_id="corpus-v1",
        input_digest=ZERO,
        output_digest=None,
        examined_count=1,
        returned_count=1,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        elapsed_milliseconds=0,
    )
    assert record.output_digest is None
    with pytest.raises(ValidationError, match="lowercase SHA-256"):
        record.model_copy(update={"output_digest": "bad"}).model_validate(
            {**record.model_dump(), "output_digest": "bad"}
        )
