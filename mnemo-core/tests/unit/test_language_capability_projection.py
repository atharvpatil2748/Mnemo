"""Behavioral coverage for operation-scoped multilingual capability projection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from mnemo.models.multilingual import LanguageCode, ScriptCode
from mnemo.models.text_representations import TextRepresentationType
from mnemo.phase85.language_capabilities import (
    LanguageCapabilityAdmissionV2,
    LanguageCapabilityEvidenceV3,
    LanguageCapabilityOperation,
    LanguageCapabilityProjectionInputV3,
    ProviderLanguageClaimV1,
    ProviderSupportState,
    project_language_capability,
)
from mnemo.phase85.models import CapabilityLifecycleStage, CapabilityState


def _claim() -> ProviderLanguageClaimV1:
    payload = {
        "provider_id": "provider",
        "profile_id": "profile",
        "model_id": "model",
        "model_revision": "revision",
        "operation": "embedding",
        "language": "en",
        "script": "Latn",
        "claim_source_digest": "a" * 64,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ProviderLanguageClaimV1(
        provider_id="provider",
        profile_id="profile",
        model_id="model",
        model_revision="revision",
        operation=LanguageCapabilityOperation.EMBEDDING,
        language=LanguageCode("en"),
        script=ScriptCode("Latn"),
        claim_source_digest="a" * 64,
        claim_digest=digest,
    )


def _input(**changes: object) -> LanguageCapabilityProjectionInputV3:
    state = CapabilityState().advance(CapabilityLifecycleStage.READY)
    values: dict[str, object] = {
        "language": LanguageCode("en"),
        "script": ScriptCode("Latn"),
        "operation": LanguageCapabilityOperation.EMBEDDING,
        "representation": TextRepresentationType.UNICODE_SEMANTIC_TEXT,
        "provider_support_state": ProviderSupportState.MODEL_SUPPORTED,
        "provider_claim": _claim(),
        "implementation_available": True,
        "configured": True,
        "buildable": True,
        "runtime_state": state,
        "readiness": SimpleNamespace(
            v2_ready=True,
            v2_active=False,
            v2_exposed=False,
            snapshot_identity="b" * 64,
            reason_codes=(),
        ),
        "evaluated": False,
        "verified": False,
        "certified": False,
        "disabled": False,
        "policy_denied": False,
        "evidence": LanguageCapabilityEvidenceV3(provider_claims=("c" * 64,)),
    }
    values.update(changes)
    return LanguageCapabilityProjectionInputV3(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "effective", "availability", "reason"),
    [
        ({"policy_denied": True}, "policy_denied", "policy_denied", "policy_denied"),
        ({"disabled": True}, "disabled", "disabled", "disabled"),
        (
            {"provider_support_state": ProviderSupportState.UNSUPPORTED, "provider_claim": None},
            "unsupported",
            "unavailable",
            "provider_reports_unsupported",
        ),
        (
            {"implementation_available": False},
            "model_supported",
            "unavailable",
            "operation_not_implemented",
        ),
        (
            {
                "implementation_available": False,
                "provider_support_state": ProviderSupportState.UNKNOWN,
                "provider_claim": None,
            },
            "unvalidated",
            "unavailable",
            "operation_not_implemented",
        ),
        ({"configured": False}, "implemented", "unavailable", "not_configured"),
        ({"buildable": False}, "implemented", "unavailable", "not_buildable"),
        ({}, "ready", "available", None),
        (
            {
                "readiness": SimpleNamespace(
                    v2_ready=True,
                    v2_active=True,
                    v2_exposed=False,
                    snapshot_identity="d" * 64,
                    reason_codes=(),
                ),
                "runtime_state": CapabilityState().advance(CapabilityLifecycleStage.ACTIVE),
            },
            "active",
            "available",
            None,
        ),
        (
            {
                "readiness": SimpleNamespace(
                    v2_ready=True,
                    v2_active=True,
                    v2_exposed=True,
                    snapshot_identity="e" * 64,
                    reason_codes=(),
                ),
                "runtime_state": CapabilityState().advance(CapabilityLifecycleStage.EXPOSED),
            },
            "exposed",
            "available",
            None,
        ),
        ({"evaluated": True}, "evaluated", "available", None),
        (
            {
                "verified": True,
                "runtime_state": CapabilityState().advance(CapabilityLifecycleStage.VERIFIED),
            },
            "verified",
            "available",
            None,
        ),
        (
            {
                "certified": True,
                "runtime_state": CapabilityState()
                .with_security_verification()
                .advance(CapabilityLifecycleStage.CERTIFIED),
            },
            "certified",
            "available",
            None,
        ),
        (
            {
                "readiness": SimpleNamespace(
                    v2_ready=False,
                    v2_active=False,
                    v2_exposed=False,
                    snapshot_identity="f" * 64,
                    reason_codes=("generation_missing",),
                )
            },
            "buildable",
            "unavailable",
            "generation_missing",
        ),
    ],
)
def test_projection_precedence_and_availability(
    changes: dict[str, object], effective: str, availability: str, reason: str | None
) -> None:
    record = project_language_capability(_input(**changes))
    assert (record.effective_state, record.availability_state, record.reason_code) == (
        effective,
        availability,
        reason,
    )
    assert len(record.snapshot_digest) == 64


def test_projection_input_and_evidence_reject_inconsistent_claims() -> None:
    with pytest.raises(ValueError, match="requires a governed"):
        _input(provider_claim=None)
    with pytest.raises(ValueError, match="does not match"):
        _input(language=LanguageCode("hi"))
    with pytest.raises(ValueError, match="conflicts"):
        _input(provider_support_state=ProviderSupportState.UNKNOWN)
    with pytest.raises(ValueError, match="unique"):
        LanguageCapabilityEvidenceV3(runtime_refs=("a" * 64, "a" * 64))
    with pytest.raises(ValueError, match="SHA-256"):
        LanguageCapabilityEvidenceV3(runtime_refs=("short",))
    with pytest.raises(ValueError, match="identity"):
        replace(_claim(), provider_id=" ")
    with pytest.raises(ValueError, match="digest mismatch"):
        replace(_claim(), claim_digest="0" * 64)


def test_capability_admission_requires_known_available_operation() -> None:
    available = project_language_capability(_input(evaluated=True))
    unavailable = project_language_capability(_input(configured=False))
    admission = LanguageCapabilityAdmissionV2((unavailable, available))
    assert admission.permits(language=LanguageCode("en"), operation="embedding")
    assert not admission.permits(language=LanguageCode("hi"), operation="embedding")
    assert not admission.permits(language=LanguageCode("en"), operation="not-an-operation")
