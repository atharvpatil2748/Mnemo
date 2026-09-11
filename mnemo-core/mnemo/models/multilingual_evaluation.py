"""Grounded evidence-level Full Multilingual V2 evaluation contracts."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .multilingual import LanguageEvidenceReferenceV3
from .text_representations import ObservationReferenceV1, TextRepresentationReferenceV1


class QueryClassV2(StrEnum):
    SEMANTIC_QUALITY = "semantic_quality"
    ROUTING_BEHAVIORAL = "routing_behavioral"
    SECURITY_PROVENANCE = "security_provenance"
    REPRESENTATION_TRANSFORMATION = "representation_transformation"
    NO_ANSWER = "no_answer"


class QueryGroundingState(StrEnum):
    GROUNDED = "query_grounded"
    UNGROUNDED = "query_ungrounded"


class EvaluationStageV2(StrEnum):
    CORPUS = "corpus"
    LANGUAGE_DETECTION = "language_detection"
    SCRIPT_DETECTION = "script_detection"
    REPRESENTATION_DETECTION = "representation_detection"
    TRANSFORMATION = "transformation"
    EMBEDDING = "embedding"
    INDEX = "index"
    SPARSE_RETRIEVAL = "sparse_retrieval"
    DENSE_RETRIEVAL = "dense_retrieval"
    FUSION = "fusion"
    CANDIDATE_BUILD = "candidate_build"
    RERANKING = "reranking"
    AUTHORIZATION = "authorization"
    PROVENANCE = "provenance"
    TRANSPORT = "transport"
    QRELS = "qrels"
    METRICS = "metrics"


class EvaluationStageStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    FILTERED = "filtered"
    UNAVAILABLE = "unavailable"


class EvaluationFailureCodeV2(StrEnum):
    CORPUS_ABSENT = "CORPUS_ABSENT"
    CORPUS_PRESENT_UNDETECTED = "CORPUS_PRESENT_UNDETECTED"
    CORPUS_PRESENT_WRONG_LANGUAGE = "CORPUS_PRESENT_WRONG_LANGUAGE"
    SCRIPT_UNRESOLVED = "SCRIPT_UNRESOLVED"
    REPRESENTATION_UNRESOLVED = "REPRESENTATION_UNRESOLVED"
    REPRESENTATION_PRESENT_WRONG_TYPE = "REPRESENTATION_PRESENT_WRONG_TYPE"
    TRANSFORMATION_UNAVAILABLE = "TRANSFORMATION_UNAVAILABLE"
    TRANSFORMATION_FAILED = "TRANSFORMATION_FAILED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_IDENTITY_MISMATCH = "PROVIDER_IDENTITY_MISMATCH"
    EMBEDDING_UNAVAILABLE = "EMBEDDING_UNAVAILABLE"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    GENERATION_MISSING = "GENERATION_MISSING"
    GENERATION_INCOMPLETE = "GENERATION_INCOMPLETE"
    GENERATION_STALE = "GENERATION_STALE"
    INDEX_MISSING = "INDEX_MISSING"
    VECTOR_SPACE_MISMATCH = "VECTOR_SPACE_MISMATCH"
    DENSE_RETRIEVAL_FAILED = "DENSE_RETRIEVAL_FAILED"
    SPARSE_RETRIEVAL_FAILED = "SPARSE_RETRIEVAL_FAILED"
    FUSION_FAILED = "FUSION_FAILED"
    RERANKER_INPUT_INVALID = "RERANKER_INPUT_INVALID"
    RERANKER_FAILED = "RERANKER_FAILED"
    AUTHORIZATION_FILTERED = "AUTHORIZATION_FILTERED"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    TRANSPORT_FAILED = "TRANSPORT_FAILED"
    CAPABILITY_ADVERTISEMENT_INCONSISTENT = "CAPABILITY_ADVERTISEMENT_INCONSISTENT"
    QUERY_UNGROUNDED = "QUERY_UNGROUNDED"
    QREL_INVALID = "QREL_INVALID"
    EVALUATION_HARNESS_ERROR = "EVALUATION_HARNESS_ERROR"
    METRIC_COMPUTATION_ERROR = "METRIC_COMPUTATION_ERROR"


class QueryRecordV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str = Field(min_length=1, max_length=128)
    query_text: str = Field(min_length=1, max_length=4096)
    query_hash: str
    query_class: QueryClassV2
    grounding_state: QueryGroundingState
    topic_id: str | None = Field(default=None, min_length=1)
    query_language_observation_references: tuple[ObservationReferenceV1, ...] = ()
    query_script_observation_references: tuple[ObservationReferenceV1, ...] = ()
    include_in_ranking_metrics: bool
    schema_version: str = "mnemo.multilingual-evaluation-query/2"

    @model_validator(mode="after")
    def _grounded_quality_only(self) -> QueryRecordV2:
        _require_sha256(self.query_hash, "query_hash")
        if hashlib.sha256(self.query_text.encode("utf-8")).hexdigest() != self.query_hash:
            raise ValueError("query hash mismatch")
        semantic = self.query_class is QueryClassV2.SEMANTIC_QUALITY
        if semantic and (
            self.grounding_state is not QueryGroundingState.GROUNDED
            or self.topic_id is None
            or not self.include_in_ranking_metrics
        ):
            raise ValueError("semantic quality queries must be grounded and metric eligible")
        if not semantic and self.include_in_ranking_metrics:
            raise ValueError("non-semantic queries cannot contribute ranking metrics")
        if self.grounding_state is QueryGroundingState.UNGROUNDED and (
            self.include_in_ranking_metrics
        ):
            raise ValueError("ungrounded queries cannot contribute ranking metrics")
        return self


class EvidenceQrelV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    qrel_id: UUID
    query_id: str = Field(min_length=1)
    topic_id: str = Field(min_length=1)
    metric_scope: str = "evidence"
    evidence_reference: LanguageEvidenceReferenceV3
    representation_reference: TextRepresentationReferenceV1 | None
    relevance_grade: int = Field(ge=0, le=2)
    language_observation_references: tuple[ObservationReferenceV1, ...] = ()
    script_observation_references: tuple[ObservationReferenceV1, ...] = ()
    authorization_expected: str
    provenance_expected: str = "exact"
    adjudication_state: str
    qrel_digest: str
    schema_version: str = "mnemo.multilingual-evaluation-qrel/2"

    @model_validator(mode="after")
    def _validate_qrel(self) -> EvidenceQrelV2:
        if self.metric_scope not in {"evidence", "document_labeled_non_semantic"}:
            raise ValueError("unsupported qrel metric scope")
        if self.authorization_expected not in {"authorized", "denied"}:
            raise ValueError("invalid qrel authorization expectation")
        if self.provenance_expected != "exact":
            raise ValueError("V2 qrels require exact provenance")
        if self.adjudication_state not in {"pending", "agreed", "adjudicated", "rejected"}:
            raise ValueError("invalid qrel adjudication state")
        _require_sha256(self.qrel_digest, "qrel_digest")
        if self.metric_scope == "evidence" and self.representation_reference is None:
            raise ValueError("evidence-level qrels require representation identity")
        return self


class CorpusPresenceEvidenceV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_manifest_digest: str
    source_census_digest: str
    authorized_evidence_census_digest: str
    notebook_id: UUID
    query_id: str = Field(min_length=1)
    presence_state: str
    relevant_evidence_reference_digests: tuple[str, ...] = ()
    census_algorithm_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _presence_contract(self) -> CorpusPresenceEvidenceV1:
        for value in (
            self.corpus_manifest_digest,
            self.source_census_digest,
            self.authorized_evidence_census_digest,
            *self.relevant_evidence_reference_digests,
        ):
            _require_sha256(value, "corpus evidence digest")
        if self.presence_state not in {"present", "absent_proven", "unknown"}:
            raise ValueError("invalid corpus presence state")
        if self.presence_state == "present" and not self.relevant_evidence_reference_digests:
            raise ValueError("present corpus evidence requires evidence identities")
        if self.presence_state == "absent_proven" and self.relevant_evidence_reference_digests:
            raise ValueError("proven absence cannot list relevant evidence")
        return self


class EvaluationStageRecordV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: EvaluationStageV2
    status: EvaluationStageStatus
    implementation_id: str = Field(min_length=1)
    input_digest: str
    output_digest: str | None = None
    examined_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    failure_code: EvaluationFailureCodeV2 | None = None
    evidence_refs: tuple[str, ...] = ()
    started_at: datetime
    elapsed_milliseconds: float = Field(ge=0)

    @field_validator("input_digest", "output_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        if value is not None:
            _require_sha256(value, "stage digest")
        return value


class EvaluationFailureRecordV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    failure_code: EvaluationFailureCodeV2
    stage: str = Field(min_length=1)
    evidence_refs: tuple[str, ...]
    preceding_stage_status: tuple[str, ...]
    recoverable: bool
    message: str | None = Field(default=None, max_length=2048)
    schema_version: str = "2.0-proposed"


class RuntimeParityEvidenceV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    application_service_id: str = Field(min_length=1)
    authorization_service_id: str = Field(min_length=1)
    retrieval_service_id: str = Field(min_length=1)
    candidate_builder_id: str = "mnemo.v2-typed-candidate-builder/1"
    reranker_public_protocol_id: str = Field(min_length=1)
    query_preprocessing_identity: str = Field(min_length=1)
    document_preprocessing_identity: str = Field(min_length=1)
    tokenizer_policy_id: str = "bge-reranker-v2-m3-pair-256-contextual-v1"
    provenance_validator_id: str = Field(min_length=1)
    direct_provider_calls: bool = False
    private_runtime_access: bool = False
    caller_constructed_reranker_input: bool = False
    parity_digest: str

    @model_validator(mode="after")
    def _enforce_parity(self) -> RuntimeParityEvidenceV1:
        if (
            self.candidate_builder_id != "mnemo.v2-typed-candidate-builder/1"
            or self.tokenizer_policy_id != "bge-reranker-v2-m3-pair-256-contextual-v1"
            or self.direct_provider_calls
            or self.private_runtime_access
            or self.caller_constructed_reranker_input
        ):
            raise ValueError("evaluation/runtime parity invariant violated")
        _require_sha256(self.parity_digest, "parity_digest")
        return self


class EvaluationCaseRecordV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    manifest_digest: str
    query: QueryRecordV2
    qrels: tuple[EvidenceQrelV2, ...]
    corpus_presence: CorpusPresenceEvidenceV1
    runtime_parity: RuntimeParityEvidenceV1
    stage_records: tuple[EvaluationStageRecordV2, ...] = Field(min_length=1)
    failures: tuple[EvaluationFailureRecordV2, ...] = ()
    raw_ranking_digest: str | None
    final_verdict: str
    schema_version: str = "mnemo.multilingual-evaluation-case/2"

    @model_validator(mode="after")
    def _case_contract(self) -> EvaluationCaseRecordV2:
        _require_sha256(self.manifest_digest, "manifest_digest")
        if self.raw_ranking_digest is not None:
            _require_sha256(self.raw_ranking_digest, "raw_ranking_digest")
        if self.query.query_class is QueryClassV2.SEMANTIC_QUALITY:
            if not self.qrels or self.raw_ranking_digest is None:
                raise ValueError("semantic evaluation requires evidence qrels and raw ranking")
            if any(item.metric_scope != "evidence" for item in self.qrels):
                raise ValueError("semantic metrics require evidence-level qrels")
        if self.query.grounding_state is QueryGroundingState.UNGROUNDED and (
            self.final_verdict != "excluded_ungrounded"
        ):
            raise ValueError("ungrounded query must be excluded")
        if (
            any(
                item.failure_code is EvaluationFailureCodeV2.CORPUS_ABSENT for item in self.failures
            )
            and self.corpus_presence.presence_state != "absent_proven"
        ):
            raise ValueError("CORPUS_ABSENT requires census-proven absence")
        return self


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")
