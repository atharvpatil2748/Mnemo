"""V2 evaluator constrained to the shared authorized application path."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from mnemo.models.advanced_retrieval import AdvancedRetrievalMode, EvidenceRepresentation
from mnemo.models.multilingual_evaluation import (
    CorpusPresenceEvidenceV1,
    EvaluationCaseRecordV2,
    EvaluationStageRecordV2,
    EvaluationStageStatus,
    EvaluationStageV2,
    EvidenceQrelV2,
    QueryGroundingState,
    QueryRecordV2,
    RuntimeParityEvidenceV1,
)

from mnemo_server.schemas.retrieval_v2 import EvidenceScopeRequest, EvidenceSearchRequest
from mnemo_server.services.authorization import ServerPrincipalV1
from mnemo_server.services.retrieval_v2 import EvidenceRetrievalApplicationService


@runtime_checkable
class EvaluationEvidenceCatalogV2(Protocol):  # pragma: no cover
    async def qrels_for_query(self, query_id: str) -> tuple[EvidenceQrelV2, ...]: ...

    async def corpus_presence_for_query(self, query_id: str) -> CorpusPresenceEvidenceV1: ...


@runtime_checkable
class RuntimeParityDescriptorV1(Protocol):  # pragma: no cover
    @property
    def authorization_service_id(self) -> str: ...

    @property
    def retrieval_service_id(self) -> str: ...

    @property
    def reranker_public_protocol_id(self) -> str: ...

    @property
    def query_preprocessing_identity(self) -> str: ...

    @property
    def document_preprocessing_identity(self) -> str: ...

    @property
    def provenance_validator_id(self) -> str: ...


@runtime_checkable
class MultilingualEvaluationApplicationV2(Protocol):  # pragma: no cover
    """Public application boundary also used by HTTP/MCP production retrieval."""

    @property
    def application_service_id(self) -> str: ...

    async def evaluate_multilingual_case(
        self,
        *,
        principal: ServerPrincipalV1,
        query: QueryRecordV2,
        manifest_digest: str,
    ) -> EvaluationCaseRecordV2: ...


class MultilingualEvaluatorV2:
    """Observe a shared application result; never call providers or build candidates."""

    def __init__(self, application: MultilingualEvaluationApplicationV2) -> None:
        if not isinstance(application, MultilingualEvaluationApplicationV2):
            raise TypeError("V2 evaluator requires the shared multilingual application service")
        self._application = application

    async def execute(
        self,
        *,
        principal: ServerPrincipalV1,
        query: QueryRecordV2,
        manifest_digest: str,
    ) -> EvaluationCaseRecordV2:
        if not principal.authenticated:
            raise PermissionError("V2 evaluation requires a real authenticated principal")
        result = await self._application.evaluate_multilingual_case(
            principal=principal,
            query=query,
            manifest_digest=manifest_digest,
        )
        parity = result.runtime_parity
        if parity.application_service_id != self._application.application_service_id:
            raise RuntimeError("evaluation result came from a different application service")
        if (
            parity.direct_provider_calls
            or parity.private_runtime_access
            or parity.caller_constructed_reranker_input
        ):
            raise RuntimeError("V2 evaluation/runtime parity invariant failed")
        if result.query != query or result.manifest_digest != manifest_digest:
            raise RuntimeError("V2 evaluator result is not bound to its request")
        return result


class SharedRetrievalEvaluationApplicationV2:
    """Record measurements by calling the exact HTTP/MCP application service."""

    application_service_id = "mnemo.evidence-retrieval-application/2"

    def __init__(
        self,
        *,
        retrieval: EvidenceRetrievalApplicationService,
        catalog: EvaluationEvidenceCatalogV2,
        parity: RuntimeParityDescriptorV1,
    ) -> None:
        if not isinstance(catalog, EvaluationEvidenceCatalogV2):
            raise TypeError("V2 evaluation requires a governed evidence catalog")
        if not isinstance(parity, RuntimeParityDescriptorV1):
            raise TypeError("V2 evaluation requires an explicit runtime parity descriptor")
        self._retrieval = retrieval
        self._catalog = catalog
        self._parity = parity

    async def evaluate_multilingual_case(
        self,
        *,
        principal: ServerPrincipalV1,
        query: QueryRecordV2,
        manifest_digest: str,
    ) -> EvaluationCaseRecordV2:
        _require_sha256(manifest_digest, "manifest_digest")
        qrels = await self._catalog.qrels_for_query(query.query_id)
        corpus = await self._catalog.corpus_presence_for_query(query.query_id)
        if query.grounding_state is QueryGroundingState.UNGROUNDED:
            return EvaluationCaseRecordV2(
                case_id=query.query_id,
                manifest_digest=manifest_digest,
                query=query,
                qrels=qrels,
                corpus_presence=corpus,
                runtime_parity=self._runtime_parity(),
                stage_records=(
                    EvaluationStageRecordV2(
                        stage=EvaluationStageV2.QRELS,
                        status=EvaluationStageStatus.FILTERED,
                        implementation_id="query-grounding-gate-v2",
                        input_digest=query.query_hash,
                        examined_count=0,
                        returned_count=0,
                        started_at=datetime.now(UTC),
                        elapsed_milliseconds=0.0,
                    ),
                ),
                failures=(),
                raw_ranking_digest=None,
                final_verdict="excluded_ungrounded",
            )
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        response = await self._retrieval.execute(
            EvidenceSearchRequest(
                query=query.query_text,
                mode=AdvancedRetrievalMode.RANKED,
                scope=EvidenceScopeRequest(notebook_id=corpus.notebook_id),
                representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
                candidate_budget=1000,
                evidence_budget=200,
            ),
            principal,
        )
        ranking = [
            {
                "candidate_id": item.get("candidate_id"),
                "evidence_reference_digest": (
                    item.get("locator", {}).get("evidence_reference_digest")
                    if isinstance(item.get("locator"), dict)
                    else None
                ),
                "rank": item.get("rank"),
                "representation": item.get("representation"),
            }
            for item in response.items
        ]
        raw_ranking_digest = _digest(ranking)
        return EvaluationCaseRecordV2(
            case_id=query.query_id,
            manifest_digest=manifest_digest,
            query=query,
            qrels=qrels,
            corpus_presence=corpus,
            runtime_parity=self._runtime_parity(),
            stage_records=(
                EvaluationStageRecordV2(
                    stage=EvaluationStageV2.FUSION,
                    status=EvaluationStageStatus.PASSED,
                    implementation_id=self.application_service_id,
                    input_digest=query.query_hash,
                    output_digest=raw_ranking_digest,
                    examined_count=int(response.coverage.get("examined", 0)),
                    returned_count=len(response.items),
                    evidence_refs=tuple(
                        str(item["evidence_reference_digest"])
                        for item in ranking
                        if item["evidence_reference_digest"] is not None
                    ),
                    started_at=started_at,
                    elapsed_milliseconds=(time.perf_counter() - started) * 1000,
                ),
            ),
            failures=(),
            raw_ranking_digest=raw_ranking_digest,
            final_verdict="measured_thresholds_open",
        )

    def _runtime_parity(self) -> RuntimeParityEvidenceV1:
        values = {
            "application_service_id": self.application_service_id,
            "authorization_service_id": self._parity.authorization_service_id,
            "retrieval_service_id": self._parity.retrieval_service_id,
            "reranker_public_protocol_id": self._parity.reranker_public_protocol_id,
            "query_preprocessing_identity": self._parity.query_preprocessing_identity,
            "document_preprocessing_identity": self._parity.document_preprocessing_identity,
            "provenance_validator_id": self._parity.provenance_validator_id,
        }
        return RuntimeParityEvidenceV1(
            application_service_id=values["application_service_id"],
            authorization_service_id=values["authorization_service_id"],
            retrieval_service_id=values["retrieval_service_id"],
            reranker_public_protocol_id=values["reranker_public_protocol_id"],
            query_preprocessing_identity=values["query_preprocessing_identity"],
            document_preprocessing_identity=values["document_preprocessing_identity"],
            provenance_validator_id=values["provenance_validator_id"],
            parity_digest=_digest(values),
        )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")
