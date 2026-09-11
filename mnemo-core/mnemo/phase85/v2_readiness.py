"""Deterministic Full Multilingual V2 readiness projection over runtime evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast
from uuid import UUID

from mnemo.models._shared import require_non_empty, require_sha256

if TYPE_CHECKING:
    from mnemo.phase85.runtime import Phase85ServiceRegistration

V2_READINESS_SCHEMA = "mnemo.full-multilingual-v2-readiness/1"
V2_CAPABILITY_ID = "multilingual_retrieval_v2"


class V2GenerationCapability(StrEnum):
    REPRESENTATION_DERIVATION = "representation_derivation_v2"
    LANGUAGE_TEXT = "language_text_v2"
    MULTILINGUAL_EMBEDDING = "multilingual_embedding_v2"
    MULTILINGUAL_VECTOR = "multilingual_vector_v2"


@dataclass(frozen=True, slots=True, kw_only=True)
class V2GenerationEvidence:
    capability: V2GenerationCapability
    generation_id: UUID
    profile_id: str
    provider_identity: str | None
    model_identity: str | None
    configuration_digest: str
    vector_space_identity: str | None
    state: str
    coverage_completeness: str
    item_count: int
    coverage_count: int
    checksum: str
    coverage_checksum: str
    source_generation_ids: tuple[UUID, ...]
    language_coverage_digest: str
    script_coverage_digest: str
    representation_coverage_digest: str
    provenance_digest: str

    def __post_init__(self) -> None:
        require_non_empty(self.profile_id, "profile_id")
        for value, name in (
            (self.configuration_digest, "configuration_digest"),
            (self.checksum, "checksum"),
            (self.coverage_checksum, "coverage_checksum"),
            (self.language_coverage_digest, "language_coverage_digest"),
            (self.script_coverage_digest, "script_coverage_digest"),
            (self.representation_coverage_digest, "representation_coverage_digest"),
            (self.provenance_digest, "provenance_digest"),
        ):
            require_sha256(value, name)
        if self.state != "ready" or self.coverage_completeness != "complete":
            raise ValueError("V2 readiness accepts only ready complete generations")
        if self.item_count < 0 or self.coverage_count < 0:
            raise ValueError("generation counts must be non-negative")
        if self.coverage_count != self.item_count:
            raise ValueError("complete generation coverage must equal item count")
        if len(set(self.source_generation_ids)) != len(self.source_generation_ids):
            raise ValueError("source generation identities must be unique")
        vector_capability = self.capability in {
            V2GenerationCapability.MULTILINGUAL_EMBEDDING,
            V2GenerationCapability.MULTILINGUAL_VECTOR,
        }
        if vector_capability != (self.vector_space_identity is not None):
            raise ValueError("vector-space identity must exist only for vector generations")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2RollbackTarget:
    alias_set_digest: str
    generation_ids: tuple[UUID, ...]
    complete: bool
    compatible: bool
    retained: bool
    recovery_mode: str = "prior_v2_alias_set"

    def __post_init__(self) -> None:
        require_sha256(self.alias_set_digest, "alias_set_digest")
        if self.recovery_mode == "prior_v2_alias_set":
            if not self.generation_ids or len(set(self.generation_ids)) != len(self.generation_ids):
                raise ValueError("prior V2 rollback target requires unique generation identities")
        elif self.recovery_mode == "deactivate_v2_alias_set":
            if self.generation_ids:
                raise ValueError("first V2 deactivation recovery cannot name generations")
        else:
            raise ValueError("unsupported V2 rollback recovery mode")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2TransportEvidence:
    representation_vocabulary_digest: str
    http_schema_digest: str
    openapi_digest: str
    mcp_schema_digest: str
    structured_content_schema_digest: str
    json_fallback_schema_digest: str
    capability_schema_digest: str
    stdio_verified: bool
    sse_verified: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.representation_vocabulary_digest, "representation_vocabulary_digest"),
            (self.http_schema_digest, "http_schema_digest"),
            (self.openapi_digest, "openapi_digest"),
            (self.mcp_schema_digest, "mcp_schema_digest"),
            (self.structured_content_schema_digest, "structured_content_schema_digest"),
            (self.json_fallback_schema_digest, "json_fallback_schema_digest"),
            (self.capability_schema_digest, "capability_schema_digest"),
        ):
            require_sha256(value, name)


@dataclass(frozen=True, slots=True, kw_only=True)
class V2ReadinessInputs:
    profile_fingerprint: str
    provider_dependencies_ready: bool
    detector_dependencies_ready: bool
    representation_dependencies_ready: bool
    transformation_dependencies_ready: bool
    vector_space_compatible: bool
    checksums_valid: bool
    provenance_complete: bool
    authorization_compatible: bool
    rollback_metadata_valid: bool
    active_alias_set_atomic: bool
    active_alias_matches_ready_set: bool
    transport_contract_complete: bool
    transport_parity_verified: bool
    shared_application_path_verified: bool
    pre_exposure_security_gate_passed: bool
    generation_set: tuple[V2GenerationEvidence, ...]
    rollback_target: V2RollbackTarget
    transport_evidence: V2TransportEvidence
    runtime_activation_selected: bool
    runtime_exposure_selected: bool

    def __post_init__(self) -> None:
        require_sha256(self.profile_fingerprint, "profile_fingerprint")
        capabilities = tuple(item.capability for item in self.generation_set)
        if set(capabilities) != set(V2GenerationCapability) or len(capabilities) != 4:
            raise ValueError("V2 readiness requires exactly one generation per dependency")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2ReadinessSnapshot:
    inputs: V2ReadinessInputs
    snapshot_identity: str
    v2_ready: bool
    v2_active: bool
    v2_exposed: bool
    reason_codes: tuple[str, ...]
    schema_version: str = V2_READINESS_SCHEMA
    capability_id: str = V2_CAPABILITY_ID

    def __post_init__(self) -> None:
        require_sha256(self.snapshot_identity, "snapshot_identity")
        if self.v2_active and not self.v2_ready:
            raise ValueError("V2 ACTIVE requires READY")
        if self.v2_exposed and not self.v2_active:
            raise ValueError("V2 EXPOSED requires ACTIVE")


def project_v2_readiness(inputs: V2ReadinessInputs) -> V2ReadinessSnapshot:
    """Project states; this function stores no mutable lifecycle authority."""
    generation_by_capability = {item.capability: item for item in inputs.generation_set}
    embedding = generation_by_capability[V2GenerationCapability.MULTILINGUAL_EMBEDDING]
    vector = generation_by_capability[V2GenerationCapability.MULTILINGUAL_VECTOR]
    embedding_ready = (
        embedding.state == "ready" and embedding.coverage_count == embedding.item_count
    )
    sparse_ready = generation_by_capability[V2GenerationCapability.LANGUAGE_TEXT].state == "ready"
    vector_ready = vector.state == "ready" and vector.coverage_count == vector.item_count
    coverage_complete = all(
        item.coverage_completeness == "complete" and item.coverage_count == item.item_count
        for item in inputs.generation_set
    )
    rollback_valid = (
        inputs.rollback_metadata_valid
        and inputs.rollback_target.complete
        and inputs.rollback_target.compatible
        and inputs.rollback_target.retained
        and inputs.rollback_target.recovery_mode
        in {"prior_v2_alias_set", "deactivate_v2_alias_set"}
    )
    ready_checks = {
        "authorization_incompatible": inputs.authorization_compatible,
        "checksums_invalid": inputs.checksums_valid,
        "coverage_incomplete": coverage_complete,
        "detector_dependencies_not_ready": inputs.detector_dependencies_ready,
        "embedding_generation_incomplete": embedding_ready,
        "provider_dependencies_not_ready": inputs.provider_dependencies_ready,
        "provenance_incomplete": inputs.provenance_complete,
        "representation_dependencies_not_ready": inputs.representation_dependencies_ready,
        "rollback_metadata_invalid": rollback_valid,
        "sparse_generation_missing": sparse_ready,
        "transformation_dependencies_not_ready": inputs.transformation_dependencies_ready,
        "vector_generation_missing": vector_ready,
        "vector_space_mismatch": inputs.vector_space_compatible
        and embedding.vector_space_identity == vector.vector_space_identity,
    }
    v2_ready = all(ready_checks.values())
    v2_active = (
        v2_ready
        and inputs.runtime_activation_selected
        and inputs.active_alias_set_atomic
        and inputs.active_alias_matches_ready_set
    )
    exposure_checks = {
        "capability_application_path_unverified": inputs.shared_application_path_verified,
        "pre_exposure_security_gate_failed": inputs.pre_exposure_security_gate_passed,
        "transport_contract_incomplete": inputs.transport_contract_complete,
        "transport_parity_unverified": inputs.transport_parity_verified
        and inputs.transport_evidence.stdio_verified
        and inputs.transport_evidence.sse_verified,
    }
    v2_exposed = v2_active and inputs.runtime_exposure_selected and all(exposure_checks.values())
    reasons = tuple(
        sorted(
            reason for reason, passed in {**ready_checks, **exposure_checks}.items() if not passed
        )
    )
    payload = {
        "inputs": _jsonable(inputs),
        "v2_ready": v2_ready,
        "v2_active": v2_active,
        "v2_exposed": v2_exposed,
        "reason_codes": reasons,
    }
    return V2ReadinessSnapshot(
        inputs=inputs,
        snapshot_identity=_digest(payload),
        v2_ready=v2_ready,
        v2_active=v2_active,
        v2_exposed=v2_exposed,
        reason_codes=reasons,
    )


def v2_service_registration(
    *,
    service: object,
    snapshot: V2ReadinessSnapshot,
) -> Phase85ServiceRegistration:
    """Project V2 evidence into the existing runtime registration authority."""
    from mnemo.phase85.runtime import Phase85ServiceRegistration

    return Phase85ServiceRegistration(
        capability_id=V2_CAPABILITY_ID,
        service=service,
        ready=snapshot.v2_ready,
        activate=snapshot.v2_active,
        generation_id=snapshot.snapshot_identity,
        generation_active=snapshot.v2_active,
        profile_fingerprint=snapshot.inputs.profile_fingerprint,
        exposed=snapshot.v2_exposed,
        security_verified=snapshot.inputs.pre_exposure_security_gate_passed,
    )


def _jsonable(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        field_names = cast(dict[str, object], value.__dataclass_fields__)
        return {name: _jsonable(getattr(value, name)) for name in field_names}
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
