"""Operation-scoped language capability views over authoritative runtime evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from enum import StrEnum

from mnemo.models.multilingual import LanguageCode, ScriptCode
from mnemo.models.text_representations import TextRepresentationType
from mnemo.phase85.models import CapabilityState
from mnemo.phase85.profiles import ActiveModelProfileSnapshot
from mnemo.phase85.v2_readiness import V2ReadinessSnapshot


class LanguageCapabilityOperation(StrEnum):
    LANGUAGE_DETECTION = "language_detection"
    SCRIPT_DETECTION = "script_detection"
    REPRESENTATION_DETECTION = "representation_detection"
    NORMALIZATION = "normalization"
    REPRESENTATION_TRANSFORMATION = "representation_transformation"
    TRANSLITERATION = "transliteration"
    TRANSLATION = "translation"
    EMBEDDING = "embedding"
    VECTOR_INDEXING = "vector_indexing"
    DENSE_RETRIEVAL = "dense_retrieval"
    SPARSE_RETRIEVAL = "sparse_retrieval"
    RERANKING = "reranking"
    OCR_LANGUAGE = "ocr_language"
    VISION_LANGUAGE = "vision_language"
    ANSWER_LANGUAGE = "answer_language"


class ProviderSupportState(StrEnum):
    MODEL_SUPPORTED = "model_supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class AssuranceState(StrEnum):
    UNVALIDATED = "unvalidated"
    EVALUATED = "evaluated"
    VERIFIED = "verified"
    CERTIFIED = "certified"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderLanguageClaimV1:
    """Governed provider metadata; it is evidence, never runtime admission."""

    provider_id: str
    profile_id: str
    model_id: str
    model_revision: str
    operation: LanguageCapabilityOperation
    language: LanguageCode
    script: ScriptCode | None
    claim_source_digest: str
    claim_digest: str

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.provider_id,
                self.profile_id,
                self.model_id,
                self.model_revision,
            )
        ):
            raise ValueError("provider language claim identity must not be blank")
        for value in (self.claim_source_digest, self.claim_digest):
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("provider language claim requires SHA-256 digests")
        payload = {
            "provider_id": self.provider_id,
            "profile_id": self.profile_id,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "operation": self.operation.value,
            "language": self.language.value,
            "script": None if self.script is None else self.script.value,
            "claim_source_digest": self.claim_source_digest,
        }
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if self.claim_digest != expected:
            raise ValueError("provider language claim digest mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageCapabilityEvidenceV3:
    provider_claims: tuple[str, ...] = ()
    runtime_refs: tuple[str, ...] = ()
    generation_refs: tuple[str, ...] = ()
    transport_refs: tuple[str, ...] = ()
    evaluation_refs: tuple[str, ...] = ()
    security_refs: tuple[str, ...] = ()
    behavioral_refs: tuple[str, ...] = ()
    governance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for item in fields(self):
            digests = getattr(self, item.name)
            if len(set(digests)) != len(digests):
                raise ValueError("capability evidence digests must be unique")
            if any(len(item) != 64 for item in digests):
                raise ValueError("capability evidence references must be SHA-256 digests")


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageCapabilityProjectionInputV3:
    language: LanguageCode
    script: ScriptCode | None
    operation: LanguageCapabilityOperation
    representation: TextRepresentationType
    provider_support_state: ProviderSupportState
    provider_claim: ProviderLanguageClaimV1 | None
    implementation_available: bool
    configured: bool
    buildable: bool
    runtime_state: CapabilityState
    readiness: V2ReadinessSnapshot
    evaluated: bool
    verified: bool
    certified: bool
    disabled: bool
    policy_denied: bool
    evidence: LanguageCapabilityEvidenceV3

    def __post_init__(self) -> None:
        if self.provider_support_state is ProviderSupportState.MODEL_SUPPORTED:
            if self.provider_claim is None:
                raise ValueError("MODEL_SUPPORTED requires a governed provider claim")
            if (
                self.provider_claim.language != self.language
                or self.provider_claim.operation is not self.operation
                or self.provider_claim.script != self.script
            ):
                raise ValueError("provider claim does not match capability scope")
        elif self.provider_claim is not None:
            raise ValueError("provider claim conflicts with provider support state")


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageCapabilityRecordV3:
    input: LanguageCapabilityProjectionInputV3
    effective_state: str
    availability_state: str
    snapshot_digest: str
    reason_code: str | None


class LanguageCapabilityAdmissionV2:
    """Operation-scoped admission view; provider claims alone never admit work."""

    def __init__(self, records: tuple[LanguageCapabilityRecordV3, ...]) -> None:
        self._records = records

    def permits(self, *, language: LanguageCode, operation: str) -> bool:
        try:
            requested = LanguageCapabilityOperation(operation)
        except ValueError:
            return False
        return any(
            item.input.language == language
            and item.input.operation is requested
            and item.availability_state == "available"
            and item.effective_state in {"active", "exposed", "evaluated", "verified", "certified"}
            for item in self._records
        )


def provider_language_claims_from_profile(
    snapshot: ActiveModelProfileSnapshot,
) -> tuple[ProviderLanguageClaimV1, ...]:
    """Project only explicitly governed claims; legacy arrays are not capability proof."""
    projected: list[ProviderLanguageClaimV1] = []
    for _component_id, component in sorted(snapshot.components.items()):
        for configured in component.language_claims:
            for operation_name in configured.operations:
                try:
                    operation = LanguageCapabilityOperation(operation_name)
                except ValueError as error:
                    raise ValueError(
                        f"unknown provider language claim operation: {operation_name}"
                    ) from error
                payload = {
                    "provider_id": component.provider,
                    "profile_id": snapshot.profile_id,
                    "model_id": component.model,
                    "model_revision": component.revision,
                    "operation": operation.value,
                    "language": configured.language,
                    "script": configured.script,
                    "claim_source_digest": configured.claim_source_digest,
                }
                projected.append(
                    ProviderLanguageClaimV1(
                        provider_id=component.provider,
                        profile_id=snapshot.profile_id,
                        model_id=component.model,
                        model_revision=component.revision,
                        operation=operation,
                        language=LanguageCode(configured.language),
                        script=(
                            None if configured.script is None else ScriptCode(configured.script)
                        ),
                        claim_source_digest=configured.claim_source_digest,
                        claim_digest=hashlib.sha256(
                            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                                "utf-8"
                            )
                        ).hexdigest(),
                    )
                )
    return tuple(
        sorted(
            projected,
            key=lambda item: (
                item.language.value,
                "" if item.script is None else item.script.value,
                item.operation.value,
                item.model_id,
            ),
        )
    )


def project_language_capability(
    value: LanguageCapabilityProjectionInputV3,
) -> LanguageCapabilityRecordV3:
    """Derive one record; no provider claim can advance runtime state."""
    if value.policy_denied:
        effective = availability = "policy_denied"
        reason = "policy_denied"
    elif value.disabled:
        effective = availability = "disabled"
        reason = "disabled"
    elif value.provider_support_state is ProviderSupportState.UNSUPPORTED:
        effective = "unsupported"
        availability = "unavailable"
        reason = "provider_reports_unsupported"
    elif not value.implementation_available:
        effective = (
            "model_supported"
            if (value.provider_support_state is ProviderSupportState.MODEL_SUPPORTED)
            else "unvalidated"
        )
        availability = "unavailable"
        reason = "operation_not_implemented"
    elif not value.configured:
        effective, availability, reason = "implemented", "unavailable", "not_configured"
    elif not value.buildable:
        effective, availability, reason = "implemented", "unavailable", "not_buildable"
    elif value.certified and value.runtime_state.certified:
        effective, availability, reason = "certified", "available", None
    elif value.verified and value.runtime_state.behaviorally_verified:
        effective, availability, reason = "verified", "available", None
    elif value.evaluated:
        effective, availability, reason = "evaluated", "available", None
    elif value.readiness.v2_exposed and value.runtime_state.exposed:
        effective, availability, reason = "exposed", "available", None
    elif value.readiness.v2_active and value.runtime_state.active:
        effective, availability, reason = "active", "available", None
    elif value.readiness.v2_ready and value.runtime_state.ready:
        effective, availability, reason = "ready", "available", None
    else:
        effective, availability, reason = (
            "buildable",
            "unavailable",
            (
                value.readiness.reason_codes[0]
                if value.readiness.reason_codes
                else "runtime_evidence_incomplete"
            ),
        )
    payload = {
        "language": value.language.value,
        "script": None if value.script is None else value.script.value,
        "operation": value.operation.value,
        "representation": value.representation.value,
        "effective_state": effective,
        "availability_state": availability,
        "readiness": value.readiness.snapshot_identity,
        "reason_code": reason,
    }
    return LanguageCapabilityRecordV3(
        input=value,
        effective_state=effective,
        availability_state=availability,
        snapshot_digest=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        reason_code=reason,
    )
