"""Provider-neutral durable processing records for Phase 8.5.3."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid5

from ._shared import (
    FrozenMetadata,
    require_enum,
    require_non_empty,
    require_non_negative,
    require_optional_non_empty,
    require_positive,
    require_sha256,
    require_utc,
    require_uuid,
    thaw_metadata,
)

PROCESSING_FINGERPRINT_DOMAIN = "mnemo.processing.job.v1"
PROCESSING_FINGERPRINT_VERSION = 1
PROCESSING_MANIFEST_SCHEMA_VERSION = 1
PROCESSING_CHECKPOINT_SCHEMA_VERSION = 1
_JOB_NAMESPACE = UUID("b1386a76-6e03-5e93-bec6-5b6ee98b72dc")
_FORBIDDEN_KEYS = frozenset(
    {"api_key", "authorization", "bearer", "credential", "password", "prompt", "secret", "token"}
)


class ProcessingJobState(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"
    BLOCKED_POLICY = "blocked_policy"


class ProcessingAttemptState(StrEnum):
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ProcessingFailureClass(StrEnum):
    TRANSIENT = "transient"
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    BUDGET_POLICY = "budget_policy"
    PROVIDER_PERMANENT = "provider_permanent"
    CANCELLATION = "cancellation"
    CORRUPTED_INPUT = "corrupted_input"
    INTERNAL = "internal"


class ProcessingPolicyDecision(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_CONSENT = "requires_consent"
    EXCEEDS_BUDGET = "exceeds_budget"
    UNAVAILABLE = "unavailable"


class ProcessingTrustClass(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


class ProcessingProgressKind(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    CHECKPOINT = "checkpoint"
    RETRY = "retry"
    CANCELLATION = "cancellation"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingCostStatus(StrEnum):
    ESTIMATED = "estimated"
    ACTUAL = "actual"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingBudget:
    max_wall_seconds: int | None = None
    max_cpu_seconds: int | None = None
    max_gpu_seconds: int | None = None
    max_input_units: int | None = None
    max_output_units: int | None = None
    max_tokens: int | None = None
    max_bytes: int | None = None
    max_memory_bytes: int | None = None
    max_vram_bytes: int | None = None
    max_operations: int | None = None
    max_pages: int | None = None
    max_pixels: int | None = None
    max_images: int | None = None
    max_cloud_requests: int | None = None
    max_currency_micros: int | None = None

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if value is not None:
                require_non_negative(value, name)

    def to_payload(self) -> dict[str, int | None]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingConsent:
    decision: ProcessingPolicyDecision
    policy_version: str
    decided_at: datetime
    reason_code: str

    def __post_init__(self) -> None:
        require_enum(self.decision, ProcessingPolicyDecision, "decision")
        require_non_empty(self.policy_version, "policy_version")
        require_utc(self.decided_at, "decided_at")
        require_non_empty(self.reason_code, "reason_code")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingEstimate:
    status: ProcessingCostStatus
    units: FrozenMetadata
    uncertainty: str | None = None

    def __post_init__(self) -> None:
        require_enum(self.status, ProcessingCostStatus, "status")
        if not isinstance(self.units, FrozenMetadata):
            raise TypeError("units must be FrozenMetadata")
        require_optional_non_empty(self.uncertainty, "uncertainty")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingManifest:
    actor_id: str
    notebook_id: UUID
    operation: str
    occurrence_id: UUID
    document_id: UUID
    version_id: UUID
    provider_profile: str
    provider_identity: str
    provider_trust: ProcessingTrustClass
    model_identity: str
    configuration: FrozenMetadata
    generation_id: UUID | None
    language: str | None
    output_schema: str
    policy_version: str
    consent: ProcessingConsent
    estimate: ProcessingEstimate
    budget: ProcessingBudget
    max_retries: int
    schema_version: int = PROCESSING_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_non_empty(self.actor_id, "actor_id")
        require_uuid(self.notebook_id, "notebook_id")
        require_non_empty(self.operation, "operation")
        require_uuid(self.occurrence_id, "occurrence_id")
        require_uuid(self.document_id, "document_id")
        require_uuid(self.version_id, "version_id")
        require_non_empty(self.provider_profile, "provider_profile")
        require_non_empty(self.provider_identity, "provider_identity")
        require_enum(self.provider_trust, ProcessingTrustClass, "provider_trust")
        require_non_empty(self.model_identity, "model_identity")
        if not isinstance(self.configuration, FrozenMetadata):
            raise TypeError("configuration must be FrozenMetadata")
        if self.generation_id is not None:
            require_uuid(self.generation_id, "generation_id")
        require_optional_non_empty(self.language, "language")
        require_non_empty(self.output_schema, "output_schema")
        require_non_empty(self.policy_version, "policy_version")
        if not isinstance(self.consent, ProcessingConsent):
            raise TypeError("consent must be ProcessingConsent")
        if not isinstance(self.estimate, ProcessingEstimate):
            raise TypeError("estimate must be ProcessingEstimate")
        if not isinstance(self.budget, ProcessingBudget):
            raise TypeError("budget must be ProcessingBudget")
        require_non_negative(self.max_retries, "max_retries")
        require_positive(self.schema_version, "schema_version")
        _reject_sensitive_configuration(thaw_metadata(self.configuration))

    def canonical_payload(self) -> dict[str, object]:
        """Return deterministic, secret-free semantic execution inputs."""
        return {
            "schema_version": self.schema_version,
            "actor_id": self.actor_id,
            "notebook_id": str(self.notebook_id),
            "operation": self.operation,
            "occurrence_id": str(self.occurrence_id),
            "document_id": str(self.document_id),
            "version_id": str(self.version_id),
            "provider_profile": self.provider_profile,
            "provider_identity": self.provider_identity,
            "provider_trust": self.provider_trust.value,
            "model_identity": self.model_identity,
            "configuration": thaw_metadata(self.configuration),
            "generation_id": None if self.generation_id is None else str(self.generation_id),
            "language": self.language,
            "output_schema": self.output_schema,
            "policy_version": self.policy_version,
            "consent": {
                "decision": self.consent.decision.value,
                "policy_version": self.consent.policy_version,
                "decided_at": self.consent.decided_at.isoformat(),
                "reason_code": self.consent.reason_code,
            },
            "estimate": {
                "status": self.estimate.status.value,
                "units": thaw_metadata(self.estimate.units),
                "uncertainty": self.estimate.uncertainty,
            },
            "budget": self.budget.to_payload(),
            "max_retries": self.max_retries,
        }


def processing_job_fingerprint(manifest: ProcessingManifest) -> str:
    manifest_payload = manifest.canonical_payload()
    consent_payload = cast(dict[str, object], manifest_payload["consent"]).copy()
    consent_payload.pop("decided_at")
    manifest_payload["consent"] = consent_payload
    material = {
        "domain": PROCESSING_FINGERPRINT_DOMAIN,
        "serialization_version": PROCESSING_FINGERPRINT_VERSION,
        "manifest": manifest_payload,
    }
    encoded = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def processing_job_id(fingerprint: str) -> UUID:
    require_sha256(fingerprint, "fingerprint")
    return uuid5(_JOB_NAMESPACE, fingerprint)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingJob:
    job_id: UUID
    fingerprint: str
    manifest: ProcessingManifest
    state: ProcessingJobState
    attempt_count: int
    lease_owner: str | None
    lease_token: UUID | None
    lease_expires_at: datetime | None
    failure_classification: ProcessingFailureClass | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        require_uuid(self.job_id, "job_id")
        require_sha256(self.fingerprint, "fingerprint")
        if self.fingerprint != processing_job_fingerprint(self.manifest):
            raise ValueError("fingerprint does not match manifest")
        if self.job_id != processing_job_id(self.fingerprint):
            raise ValueError("job_id does not match fingerprint")
        require_enum(self.state, ProcessingJobState, "state")
        require_non_negative(self.attempt_count, "attempt_count")
        require_optional_non_empty(self.lease_owner, "lease_owner")
        if self.lease_token is not None:
            require_uuid(self.lease_token, "lease_token")
        if self.lease_expires_at is not None:
            require_utc(self.lease_expires_at, "lease_expires_at")
        if self.failure_classification is not None:
            require_enum(
                self.failure_classification, ProcessingFailureClass, "failure_classification"
            )
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        if self.completed_at is not None:
            require_utc(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingAttempt:
    attempt_id: UUID
    job_id: UUID
    attempt_number: int
    worker_id: str
    lease_token: UUID
    state: ProcessingAttemptState
    provider_profile: str
    started_at: datetime
    ended_at: datetime | None
    failure_classification: ProcessingFailureClass | None = None

    def __post_init__(self) -> None:
        require_uuid(self.attempt_id, "attempt_id")
        require_uuid(self.job_id, "job_id")
        require_positive(self.attempt_number, "attempt_number")
        require_non_empty(self.worker_id, "worker_id")
        require_uuid(self.lease_token, "lease_token")
        require_enum(self.state, ProcessingAttemptState, "state")
        require_non_empty(self.provider_profile, "provider_profile")
        require_utc(self.started_at, "started_at")
        if self.ended_at is not None:
            require_utc(self.ended_at, "ended_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingCheckpoint:
    checkpoint_id: UUID
    job_id: UUID
    attempt_id: UUID
    sequence: int
    fingerprint: str
    provider_profile: str
    generation_id: UUID | None
    payload: FrozenMetadata
    created_at: datetime
    schema_version: int = PROCESSING_CHECKPOINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_uuid(self.checkpoint_id, "checkpoint_id")
        require_uuid(self.job_id, "job_id")
        require_uuid(self.attempt_id, "attempt_id")
        require_non_negative(self.sequence, "sequence")
        require_sha256(self.fingerprint, "fingerprint")
        require_non_empty(self.provider_profile, "provider_profile")
        if self.generation_id is not None:
            require_uuid(self.generation_id, "generation_id")
        if not isinstance(self.payload, FrozenMetadata):
            raise TypeError("payload must be FrozenMetadata")
        _reject_sensitive_configuration(thaw_metadata(self.payload))
        require_utc(self.created_at, "created_at")
        require_positive(self.schema_version, "schema_version")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingResult:
    result_id: UUID
    job_id: UUID
    attempt_id: UUID
    fingerprint: str
    output_reference: str | None
    payload: FrozenMetadata
    created_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_uuid(self.result_id, "result_id")
        require_uuid(self.job_id, "job_id")
        require_uuid(self.attempt_id, "attempt_id")
        require_sha256(self.fingerprint, "fingerprint")
        require_optional_non_empty(self.output_reference, "output_reference")
        if not isinstance(self.payload, FrozenMetadata):
            raise TypeError("payload must be FrozenMetadata")
        _reject_sensitive_configuration(thaw_metadata(self.payload))
        require_utc(self.created_at, "created_at")
        require_positive(self.schema_version, "schema_version")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingLedgerEntry:
    entry_id: UUID
    job_id: UUID
    attempt_id: UUID
    status: ProcessingCostStatus
    provider_identity: str
    model_identity: str
    usage: FrozenMetadata
    created_at: datetime

    def __post_init__(self) -> None:
        require_uuid(self.entry_id, "entry_id")
        require_uuid(self.job_id, "job_id")
        require_uuid(self.attempt_id, "attempt_id")
        require_enum(self.status, ProcessingCostStatus, "status")
        require_non_empty(self.provider_identity, "provider_identity")
        require_non_empty(self.model_identity, "model_identity")
        if not isinstance(self.usage, FrozenMetadata):
            raise TypeError("usage must be FrozenMetadata")
        _reject_sensitive_configuration(thaw_metadata(self.usage))
        require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingProgressEvent:
    event_id: UUID
    job_id: UUID
    sequence: int
    kind: ProcessingProgressKind
    detail_code: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_uuid(self.event_id, "event_id")
        require_uuid(self.job_id, "job_id")
        require_positive(self.sequence, "sequence")
        require_enum(self.kind, ProcessingProgressKind, "kind")
        require_non_empty(self.detail_code, "detail_code")
        require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingClaim:
    job: ProcessingJob
    attempt: ProcessingAttempt


def is_legal_processing_transition(source: ProcessingJobState, target: ProcessingJobState) -> bool:
    legal = {
        ProcessingJobState.QUEUED: {
            ProcessingJobState.CLAIMED,
            ProcessingJobState.CANCELLED,
            ProcessingJobState.BLOCKED_POLICY,
        },
        ProcessingJobState.CLAIMED: {
            ProcessingJobState.RUNNING,
            ProcessingJobState.CANCEL_REQUESTED,
            ProcessingJobState.FAILED_RETRYABLE,
            ProcessingJobState.BLOCKED_POLICY,
        },
        ProcessingJobState.RUNNING: {
            ProcessingJobState.CANCEL_REQUESTED,
            ProcessingJobState.SUCCEEDED,
            ProcessingJobState.FAILED_RETRYABLE,
            ProcessingJobState.FAILED_FINAL,
            ProcessingJobState.BLOCKED_POLICY,
        },
        ProcessingJobState.CANCEL_REQUESTED: {ProcessingJobState.CANCELLED},
        ProcessingJobState.FAILED_RETRYABLE: {
            ProcessingJobState.QUEUED,
            ProcessingJobState.FAILED_FINAL,
        },
        ProcessingJobState.CANCELLED: set(),
        ProcessingJobState.SUCCEEDED: set(),
        ProcessingJobState.FAILED_FINAL: set(),
        ProcessingJobState.BLOCKED_POLICY: set(),
    }
    return target in legal[source]


def _reject_sensitive_configuration(value: object, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = key.casefold().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS or any(
                token in normalized for token in ("api_key", "password", "secret")
            ):
                raise ValueError(f"{path} contains forbidden sensitive key")
            _reject_sensitive_configuration(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_sensitive_configuration(nested, f"{path}[{index}]")
