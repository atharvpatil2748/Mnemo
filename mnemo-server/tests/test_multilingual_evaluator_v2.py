from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mnemo.interfaces import PrincipalContextV1
from mnemo.models.multilingual_evaluation import (
    CorpusPresenceEvidenceV1,
    QueryClassV2,
    QueryGroundingState,
    QueryRecordV2,
)
from mnemo_server.evaluation.multilingual_v2 import (
    MultilingualEvaluatorV2,
    SharedRetrievalEvaluationApplicationV2,
    _digest,
    _require_sha256,
)


def _query(*, grounded: bool) -> QueryRecordV2:
    text = "मराठी retrieval contract"
    return QueryRecordV2(
        query_id="case-1",
        query_text=text,
        query_hash=hashlib.sha256(text.encode()).hexdigest(),
        query_class=QueryClassV2.ROUTING_BEHAVIORAL,
        grounding_state=(
            QueryGroundingState.GROUNDED if grounded else QueryGroundingState.UNGROUNDED
        ),
        include_in_ranking_metrics=False,
    )


class Catalog:
    notebook_id = uuid4()

    async def qrels_for_query(self, query_id: str):  # type: ignore[no-untyped-def]
        assert query_id == "case-1"
        return ()

    async def corpus_presence_for_query(self, query_id: str) -> CorpusPresenceEvidenceV1:
        return CorpusPresenceEvidenceV1(
            corpus_manifest_digest="a" * 64,
            source_census_digest="b" * 64,
            authorized_evidence_census_digest="c" * 64,
            notebook_id=self.notebook_id,
            query_id=query_id,
            presence_state="unknown",
            census_algorithm_id="identity-census-v1",
        )


class Parity:
    authorization_service_id = "central-authorization-v3"
    retrieval_service_id = "retrieval-v2"
    reranker_public_protocol_id = "mnemo.multilingual-reranker-v3"
    query_preprocessing_identity = "query-v1"
    document_preprocessing_identity = "document-v1"
    provenance_validator_id = "provenance-v1"


class Retrieval:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def execute(self, request: object, principal: object) -> object:
        self.requests.append((request, principal))
        return SimpleNamespace(
            coverage={"examined": 3},
            items=(
                {
                    "candidate_id": "candidate-1",
                    "locator": {"evidence_reference_digest": "d" * 64},
                    "rank": 1,
                    "representation": "multilingual_text",
                },
                {
                    "candidate_id": "candidate-2",
                    "locator": "malformed-but-contained",
                    "rank": 2,
                    "representation": "multilingual_text",
                },
            ),
        )


def _application(retrieval: Retrieval | None = None) -> SharedRetrievalEvaluationApplicationV2:
    return SharedRetrievalEvaluationApplicationV2(
        retrieval=retrieval or Retrieval(),  # type: ignore[arg-type]
        catalog=Catalog(),
        parity=Parity(),
    )


def test_shared_evaluation_records_grounded_runtime_parity_and_ranking() -> None:
    retrieval = Retrieval()
    application = _application(retrieval)
    principal = PrincipalContextV1(uuid4(), True)
    result = asyncio.run(
        MultilingualEvaluatorV2(application).execute(
            principal=principal,
            query=_query(grounded=True),
            manifest_digest="e" * 64,
        )
    )

    assert result.final_verdict == "measured_thresholds_open"
    assert result.stage_records[0].examined_count == 3
    assert result.stage_records[0].returned_count == 2
    assert result.stage_records[0].evidence_refs == ("d" * 64,)
    assert result.runtime_parity.parity_digest == _digest(
        {
            "application_service_id": application.application_service_id,
            "authorization_service_id": Parity.authorization_service_id,
            "retrieval_service_id": Parity.retrieval_service_id,
            "reranker_public_protocol_id": Parity.reranker_public_protocol_id,
            "query_preprocessing_identity": Parity.query_preprocessing_identity,
            "document_preprocessing_identity": Parity.document_preprocessing_identity,
            "provenance_validator_id": Parity.provenance_validator_id,
        }
    )
    assert len(retrieval.requests) == 1


def test_shared_evaluation_excludes_ungrounded_without_retrieval() -> None:
    retrieval = Retrieval()
    result = asyncio.run(
        _application(retrieval).evaluate_multilingual_case(
            principal=PrincipalContextV1(uuid4(), True),
            query=_query(grounded=False),
            manifest_digest="f" * 64,
        )
    )
    assert result.final_verdict == "excluded_ungrounded"
    assert result.raw_ranking_digest is None
    assert result.stage_records[0].returned_count == 0
    assert retrieval.requests == []


def test_evaluator_rejects_authentication_binding_and_parity_violations() -> None:
    application = _application()
    query = _query(grounded=False)
    evaluator = MultilingualEvaluatorV2(application)
    with pytest.raises(PermissionError, match="authenticated"):
        asyncio.run(
            evaluator.execute(
                principal=PrincipalContextV1(uuid4(), False),
                query=query,
                manifest_digest="a" * 64,
            )
        )

    valid = asyncio.run(
        application.evaluate_multilingual_case(
            principal=PrincipalContextV1(uuid4(), True),
            query=query,
            manifest_digest="a" * 64,
        )
    )

    class ResultApplication:
        application_service_id = application.application_service_id

        def __init__(self, result: object) -> None:
            self.result = result

        async def evaluate_multilingual_case(self, **_: object) -> object:
            return self.result

    wrong_service = valid.model_copy(
        update={
            "runtime_parity": valid.runtime_parity.model_copy(
                update={"application_service_id": "other-service"}
            )
        }
    )
    with pytest.raises(RuntimeError, match="different application"):
        asyncio.run(
            MultilingualEvaluatorV2(ResultApplication(wrong_service)).execute(  # type: ignore[arg-type]
                principal=PrincipalContextV1(uuid4(), True),
                query=query,
                manifest_digest="a" * 64,
            )
        )

    invalid_parity = valid.model_copy(
        update={
            "runtime_parity": valid.runtime_parity.model_copy(
                update={"private_runtime_access": True}
            )
        }
    )
    with pytest.raises(RuntimeError, match="parity invariant"):
        asyncio.run(
            MultilingualEvaluatorV2(ResultApplication(invalid_parity)).execute(  # type: ignore[arg-type]
                principal=PrincipalContextV1(uuid4(), True),
                query=query,
                manifest_digest="a" * 64,
            )
        )

    wrong_binding = valid.model_copy(update={"manifest_digest": "b" * 64})
    with pytest.raises(RuntimeError, match="not bound"):
        asyncio.run(
            MultilingualEvaluatorV2(ResultApplication(wrong_binding)).execute(  # type: ignore[arg-type]
                principal=PrincipalContextV1(uuid4(), True),
                query=query,
                manifest_digest="a" * 64,
            )
        )


def test_evaluation_constructors_and_digest_validation_fail_closed() -> None:
    with pytest.raises(TypeError, match="shared multilingual"):
        MultilingualEvaluatorV2(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="governed evidence"):
        SharedRetrievalEvaluationApplicationV2(
            retrieval=Retrieval(),  # type: ignore[arg-type]
            catalog=object(),  # type: ignore[arg-type]
            parity=Parity(),
        )
    with pytest.raises(TypeError, match="runtime parity"):
        SharedRetrievalEvaluationApplicationV2(
            retrieval=Retrieval(),  # type: ignore[arg-type]
            catalog=Catalog(),
            parity=object(),  # type: ignore[arg-type]
        )
    for value in ("A" * 64, "a" * 63, "g" * 64):
        with pytest.raises(ValueError, match="lowercase SHA-256"):
            _require_sha256(value, "digest")
