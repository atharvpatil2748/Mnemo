"""Additive Phase 8.5.8 multimodal evidence and Final-QA V2 contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from ._shared import (
    FrozenMetadata,
    require_finite,
    require_non_empty,
    require_non_negative,
    require_positive,
    require_sha256,
    require_utc,
    thaw_metadata,
)
from .advanced_retrieval import RetrievalCompleteness
from .final_qa_execution import FinalQAExecutionSnapshotPhase, FinalQAExecutionState

MULTIMODAL_EVIDENCE_VERSION = "evidence-candidate-v2/1"
MULTIMODAL_CONTEXT_VERSION = "multimodal-context-v1/1"
FINAL_QA_V2_CONTRACT_VERSION = "final-qa-v2/1"
FINAL_QA_V2_SNAPSHOT_SCHEMA_VERSION = 1
_CANDIDATE_NAMESPACE = UUID("844897e3-781b-5ab2-bbd3-4d231228cf7a")
_CITATION_NAMESPACE = UUID("66b250c3-8737-5a73-9c76-6cf8881eac2d")
_EXECUTION_NAMESPACE = UUID("db900a9d-28cb-57cd-90fd-19781c16fefd")


class EvidenceKindV2(StrEnum):
    CANONICAL_CHUNK = "canonical_chunk"
    DOCUMENT_RANGE = "document_range"
    STRUCTURED_ROW = "structured_row"
    STRUCTURED_CELL = "structured_cell"
    STRUCTURED_RESULT = "structured_result"
    ASSET_OCCURRENCE = "asset_occurrence"
    OCR_REGION = "ocr_region"
    VISION_OBSERVATION = "vision_observation"
    VISUAL_VECTOR_MATCH = "visual_vector_match"
    POSITIONAL = "positional"


class EvidenceAuthorityV2(StrEnum):
    ORIGINAL = "original"
    DERIVED = "derived"


class ProviderModalityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    POLICY_DENIED = "policy_denied"
    BUDGET_DENIED = "budget_denied"


class ContextOmissionReasonV2(StrEnum):
    UNAUTHORIZED = "unauthorized"
    UNSUPPORTED_MODALITY = "unsupported_modality"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    POLICY_DENIED = "policy_denied"
    BUDGET_DENIED = "budget_denied"
    ITEM_LIMIT = "item_limit"
    TOKEN_LIMIT = "token_limit"
    BYTE_LIMIT = "byte_limit"
    ASSET_LIMIT = "asset_limit"
    PIXEL_LIMIT = "pixel_limit"
    MALFORMED = "malformed"
    STALE_GENERATION = "stale_generation"


class FinalQAV2Status(StrEnum):
    CITATION_RESOLVED = "citation_resolved"
    NO_CONTEXT = "no_context"


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceScoreComponentV2:
    method: str
    rank: int
    score: float | None = None
    vector_space: str | None = None
    title_match: bool = False

    def __post_init__(self) -> None:
        require_non_empty(self.method, "method")
        require_positive(self.rank, "rank")
        if self.score is not None:
            require_finite(self.score, "score")
        if self.vector_space is not None:
            require_non_empty(self.vector_space, "vector_space")


def evidence_candidate_v2_id(
    *,
    kind: EvidenceKindV2,
    document_id: UUID,
    version_id: UUID,
    authoritative_id: str,
) -> UUID:
    require_non_empty(authoritative_id, "authoritative_id")
    return uuid5(
        _CANDIDATE_NAMESPACE,
        f"{MULTIMODAL_EVIDENCE_VERSION}:{kind.value}:{document_id}:{version_id}:{authoritative_id}",
    )


def evidence_candidate_v2_digest(candidate: EvidenceCandidateV2) -> str:
    """Bind all immutable evidence and runtime provenance used by V2 publication."""
    material = {
        "contract": MULTIMODAL_EVIDENCE_VERSION,
        "candidate_id": str(candidate.candidate_id),
        "notebook_id": str(candidate.notebook_id),
        "source_id": str(candidate.source_id),
        "document_id": str(candidate.document_id),
        "version_id": str(candidate.version_id),
        "kind": candidate.kind.value,
        "authority": candidate.authority.value,
        "authoritative_id": candidate.authoritative_id,
        "chunk_id": candidate.chunk_id,
        "asset_id": None if candidate.asset_id is None else str(candidate.asset_id),
        "occurrence_id": None if candidate.occurrence_id is None else str(candidate.occurrence_id),
        "derivation_id": None if candidate.derivation_id is None else str(candidate.derivation_id),
        "generation_id": None if candidate.generation_id is None else str(candidate.generation_id),
        "document_title": candidate.document_title,
        "content_hash": (
            None
            if candidate.content is None
            else hashlib.sha256(candidate.content.encode("utf-8")).hexdigest()
        ),
        "resource_handle": candidate.resource_handle,
        "media_type": candidate.media_type,
        "locator": thaw_metadata(candidate.locator),
        "provider": candidate.provider,
        "model": candidate.model,
        "scores": [
            {
                "method": item.method,
                "rank": item.rank,
                "score": item.score,
                "vector_space": item.vector_space,
                "title_match": item.title_match,
            }
            for item in candidate.score_components
        ],
        "fused_score": candidate.fused_score,
        "final_rank": candidate.final_rank,
        "completeness": candidate.completeness.value,
        "parent_promoted": candidate.parent_promoted,
    }
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceCandidateV2:
    candidate_id: UUID
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    kind: EvidenceKindV2
    authority: EvidenceAuthorityV2
    authoritative_id: str
    chunk_id: str | None = None
    asset_id: UUID | None = None
    occurrence_id: UUID | None = None
    derivation_id: UUID | None = None
    generation_id: UUID | None = None
    document_title: str | None = None
    content: str | None = None
    resource_handle: str | None = None
    media_type: str | None = None
    locator: FrozenMetadata = field(default_factory=FrozenMetadata)
    provider: str | None = None
    model: str | None = None
    score_components: tuple[EvidenceScoreComponentV2, ...] = ()
    fused_score: float | None = None
    final_rank: int | None = None
    completeness: RetrievalCompleteness = RetrievalCompleteness.UNKNOWN
    parent_promoted: bool = False

    def __post_init__(self) -> None:
        expected = evidence_candidate_v2_id(
            kind=self.kind,
            document_id=self.document_id,
            version_id=self.version_id,
            authoritative_id=self.authoritative_id,
        )
        if self.candidate_id != expected:
            raise ValueError("candidate_id does not match authoritative evidence")
        if self.authority is EvidenceAuthorityV2.DERIVED and self.derivation_id is None:
            raise ValueError("derived evidence requires derivation_id")
        if (
            self.kind
            in {
                EvidenceKindV2.ASSET_OCCURRENCE,
                EvidenceKindV2.OCR_REGION,
                EvidenceKindV2.VISION_OBSERVATION,
                EvidenceKindV2.VISUAL_VECTOR_MATCH,
            }
            and self.occurrence_id is None
        ):
            raise ValueError("asset-backed evidence requires occurrence_id")
        if self.kind is EvidenceKindV2.CANONICAL_CHUNK and self.chunk_id is None:
            raise ValueError("canonical chunk evidence requires chunk_id")
        if self.content is None and self.resource_handle is None:
            raise ValueError("evidence requires bounded content or an opaque resource handle")
        if self.content is not None:
            require_non_empty(self.content, "content")
        if self.resource_handle is not None:
            require_non_empty(self.resource_handle, "resource_handle")
            if "://" not in self.resource_handle:
                raise ValueError("resource_handle must be an opaque resource URI")
        for value, name in (
            (self.document_title, "document_title"),
            (self.media_type, "media_type"),
            (self.provider, "provider"),
            (self.model, "model"),
        ):
            if value is not None:
                require_non_empty(value, name)
        if len({component.method for component in self.score_components}) != len(
            self.score_components
        ):
            raise ValueError("score component methods must be unique")
        if self.fused_score is not None:
            require_finite(self.fused_score, "fused_score")
        if self.final_rank is not None:
            require_positive(self.final_rank, "final_rank")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalRetrievalDiagnosticsV2:
    recalled: int
    deduplicated: int
    fused: int
    reranked: int
    returned: int
    modality_counts: FrozenMetadata
    omitted_reasons: FrozenMetadata
    elapsed_milliseconds: int

    def __post_init__(self) -> None:
        for name in ("recalled", "deduplicated", "fused", "reranked", "returned"):
            require_non_negative(getattr(self, name), name)
        require_non_negative(self.elapsed_milliseconds, "elapsed_milliseconds")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalRetrievalResultV2:
    query: str
    query_fingerprint: str
    snapshot_identity: str
    completeness: RetrievalCompleteness
    candidates: tuple[EvidenceCandidateV2, ...]
    diagnostics: MultimodalRetrievalDiagnosticsV2

    def __post_init__(self) -> None:
        require_non_empty(self.query, "query")
        require_sha256(self.query_fingerprint, "query_fingerprint")
        require_sha256(self.snapshot_identity, "snapshot_identity")
        if tuple(candidate.final_rank for candidate in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("candidate final ranks must be contiguous")
        if self.diagnostics.returned != len(self.candidates):
            raise ValueError("diagnostic returned count must match candidates")


class MultimodalContextBudgetsV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_items: int = Field(default=20, strict=True, ge=1, le=200)
    max_tokens: int = Field(default=16_000, strict=True, ge=1, le=1_000_000)
    max_bytes: int = Field(default=2_000_000, strict=True, ge=256, le=10_000_000)
    max_assets: int = Field(default=10, strict=True, ge=0, le=100)
    max_asset_bytes: int = Field(default=25_000_000, strict=True, ge=0, le=100_000_000)
    max_decoded_pixels: int = Field(default=100_000_000, strict=True, ge=0, le=1_000_000_000)


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalProviderCapabilitiesV1:
    provider: str
    model: str
    profile: str
    configuration_digest: str
    modality_states: FrozenMetadata
    max_context_tokens: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.provider, "provider"),
            (self.model, "model"),
            (self.profile, "profile"),
        ):
            require_non_empty(value, name)
        require_sha256(self.configuration_digest, "configuration_digest")
        require_positive(self.max_context_tokens, "max_context_tokens")
        require_positive(self.max_output_tokens, "max_output_tokens")
        for raw_state in self.modality_states.values():
            ProviderModalityState(str(raw_state))

    def state_for(self, kind: EvidenceKindV2) -> ProviderModalityState:
        raw = self.modality_states.get(kind.value, ProviderModalityState.UNSUPPORTED.value)
        return ProviderModalityState(str(raw))


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalContextItemV1:
    source_number: int
    candidate: EvidenceCandidateV2
    rendered_text: str
    token_count: int
    byte_count: int

    def __post_init__(self) -> None:
        require_positive(self.source_number, "source_number")
        require_non_empty(self.rendered_text, "rendered_text")
        require_positive(self.token_count, "token_count")
        require_positive(self.byte_count, "byte_count")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalContextOmissionV1:
    candidate_id: UUID
    reason: ContextOmissionReasonV2


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalContextBuildResultV1:
    retrieval_result: MultimodalRetrievalResultV2
    tokenizer_id: str
    provider_capabilities: MultimodalProviderCapabilitiesV1
    budgets: MultimodalContextBudgetsV1
    items: tuple[MultimodalContextItemV1, ...]
    omissions: tuple[MultimodalContextOmissionV1, ...]
    rendered_context: str
    token_count: int
    byte_count: int
    asset_count: int
    asset_bytes: int
    decoded_pixels: int
    completeness: RetrievalCompleteness

    def __post_init__(self) -> None:
        require_non_empty(self.tokenizer_id, "tokenizer_id")
        if tuple(item.source_number for item in self.items) != tuple(range(1, len(self.items) + 1)):
            raise ValueError("context source numbers must be contiguous")
        if self.rendered_context != "\n\n".join(item.rendered_text for item in self.items):
            raise ValueError("rendered context does not match context items")
        for name in ("token_count", "byte_count", "asset_count", "asset_bytes", "decoded_pixels"):
            require_non_negative(getattr(self, name), name)
        if self.token_count > self.budgets.max_tokens or self.byte_count > self.budgets.max_bytes:
            raise ValueError("context exceeds text budget")
        if self.asset_count > self.budgets.max_assets:
            raise ValueError("context exceeds asset count budget")
        if self.asset_bytes > self.budgets.max_asset_bytes:
            raise ValueError("context exceeds asset byte budget")
        if self.decoded_pixels > self.budgets.max_decoded_pixels:
            raise ValueError("context exceeds pixel budget")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalGenerationRequestV1:
    system_prompt: str
    query: str
    rendered_context: str
    resource_handles: tuple[str, ...]
    context_snapshot_identity: str
    max_output_tokens: int
    corrective_instruction: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.system_prompt, "system_prompt")
        require_non_empty(self.query, "query")
        require_non_empty(self.rendered_context, "rendered_context")
        require_sha256(self.context_snapshot_identity, "context_snapshot_identity")
        require_positive(self.max_output_tokens, "max_output_tokens")
        if self.corrective_instruction is not None:
            require_non_empty(self.corrective_instruction, "corrective_instruction")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalGenerationResultV1:
    answer: str
    provider: str
    model: str
    prompt_tokens: int
    answer_tokens: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.answer, "answer"),
            (self.provider, "provider"),
            (self.model, "model"),
        ):
            require_non_empty(value, name)
        require_non_negative(self.prompt_tokens, "prompt_tokens")
        require_positive(self.answer_tokens, "answer_tokens")


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceCitationV2:
    citation_id: UUID
    execution_id: UUID
    source_number: int
    candidate: EvidenceCandidateV2
    document_title: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        expected = uuid5(
            _CITATION_NAMESPACE,
            f"{self.execution_id}:{self.source_number}:{self.candidate.candidate_id}",
        )
        if self.citation_id != expected:
            raise ValueError("citation_id does not match evidence identity")
        require_positive(self.source_number, "source_number")
        require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalQARequestV2:
    actor_id: UUID
    notebook_id: UUID
    session_id: UUID
    user_turn_id: UUID
    assistant_turn_id: UUID
    query: str
    retrieval_result: MultimodalRetrievalResultV2
    context_budgets: MultimodalContextBudgetsV1
    system_prompt: str
    max_output_tokens: int

    def __post_init__(self) -> None:
        normalized = " ".join(self.query.split())
        require_non_empty(normalized, "query")
        object.__setattr__(self, "query", normalized)
        if normalized != self.retrieval_result.query:
            raise ValueError("query must match retrieval result")
        require_non_empty(self.system_prompt, "system_prompt")
        if not 1 <= self.max_output_tokens <= 4096:
            raise ValueError("max_output_tokens must be from 1 through 4096")


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalQAResultV2:
    execution_id: UUID
    query: str
    status: FinalQAV2Status
    answer: str | None
    context_result: MultimodalContextBuildResultV1
    citations: tuple[EvidenceCitationV2, ...]
    retry_count: int

    def __post_init__(self) -> None:
        require_non_empty(self.query, "query")
        require_non_negative(self.retry_count, "retry_count")
        if self.retry_count > 1:
            raise ValueError("Final-QA V2 permits at most one corrective retry")
        if self.status is FinalQAV2Status.NO_CONTEXT:
            if self.answer is not None or self.citations or self.context_result.items:
                raise ValueError("no-context result cannot contain answer or citations")
        else:
            if self.answer is None or not self.citations:
                raise ValueError("resolved result requires answer and citations")
            require_non_empty(self.answer, "answer")


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalQAExecutionV2:
    execution_id: UUID
    assistant_turn_id: UUID
    request_fingerprint: str
    actor_id: UUID
    notebook_id: UUID
    session_id: UUID
    user_turn_id: UUID
    provider: str
    model: str
    provider_profile: str
    state: FinalQAExecutionState
    retry_count: int
    failure_classification: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        require_sha256(self.request_fingerprint, "request_fingerprint")
        for value, name in (
            (self.provider, "provider"),
            (self.model, "model"),
            (self.provider_profile, "provider_profile"),
        ):
            require_non_empty(value, name)
        require_non_negative(self.retry_count, "retry_count")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalQAExecutionSnapshotV2:
    execution_id: UUID
    phase: FinalQAExecutionSnapshotPhase
    payload_schema_version: int
    payload: str
    payload_hash: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_positive(self.payload_schema_version, "payload_schema_version")
        require_non_empty(self.payload, "payload")
        require_sha256(self.payload_hash, "payload_hash")
        if hashlib.sha256(self.payload.encode("utf-8")).hexdigest() != self.payload_hash:
            raise ValueError("snapshot payload hash mismatch")
        require_utc(self.created_at, "created_at")


def final_qa_v2_execution_id(assistant_turn_id: UUID) -> UUID:
    return uuid5(_EXECUTION_NAMESPACE, str(assistant_turn_id))


def final_qa_v2_request_fingerprint(
    request: FinalQARequestV2,
    capabilities: MultimodalProviderCapabilitiesV1,
    tokenizer_id: str,
) -> str:
    material = {
        "domain": "mnemo.final_qa.request.v2",
        "contract": FINAL_QA_V2_CONTRACT_VERSION,
        "actor_id": str(request.actor_id),
        "notebook_id": str(request.notebook_id),
        "session_id": str(request.session_id),
        "user_turn_id": str(request.user_turn_id),
        "query": request.query,
        "retrieval_query_fingerprint": request.retrieval_result.query_fingerprint,
        "retrieval_snapshot_identity": request.retrieval_result.snapshot_identity,
        "retrieval_completeness": request.retrieval_result.completeness.value,
        "resource_manifest": [
            {
                "candidate_id": str(item.candidate_id),
                "candidate_digest": evidence_candidate_v2_digest(item),
                "kind": item.kind.value,
                "authority": item.authority.value,
                "occurrence_id": None if item.occurrence_id is None else str(item.occurrence_id),
                "derivation_id": None if item.derivation_id is None else str(item.derivation_id),
                "generation_id": None if item.generation_id is None else str(item.generation_id),
                "resource_handle": item.resource_handle,
            }
            for item in request.retrieval_result.candidates
        ],
        "context_budgets": request.context_budgets.model_dump(mode="json"),
        "system_prompt": request.system_prompt,
        "max_output_tokens": request.max_output_tokens,
        "provider": capabilities.provider,
        "model": capabilities.model,
        "profile": capabilities.profile,
        "provider_configuration": capabilities.configuration_digest,
        "modality_states": dict(capabilities.modality_states),
        "tokenizer_id": tokenizer_id,
        "citation_contract": "adr-0054/v1",
        "retry_contract": "one-corrective-retry/v1",
        "replay_contract": "adr-0056/v1",
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def multimodal_snapshot_identity(items: tuple[MultimodalContextItemV1, ...]) -> str:
    material = [
        (item.source_number, str(item.candidate.candidate_id), item.rendered_text) for item in items
    ]
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
