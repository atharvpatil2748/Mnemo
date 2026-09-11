"""Focused WP-01 tests for ADR-0074 runtime composition and activation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from mnemo import (
    EmbeddingConfig,
    LLMConfig,
    LLMRoleConfig,
    MnemoConfig,
    Phase85ProviderRegistration,
    Phase85Runtime,
    Phase85ServiceRegistration,
    PluginConfig,
    ProviderReadinessResult,
    RerankerConfig,
    StorageConfig,
)
from mnemo.phase85 import CapabilityLifecycleStage, CapabilityState
from mnemo.phase85.runtime import PHASE85_CAPABILITY_IDS


def _config(tmp_path: Path) -> MnemoConfig:
    role = LLMRoleConfig(provider="test", model="gemma4:e4b", max_context_tokens=128)
    return MnemoConfig(
        storage=StorageConfig(),
        llm=LLMConfig(planner=role, synthesizer=role, extractor=role, classifier=role),
        embedding=EmbeddingConfig(provider="test", model="embedding", dimensions=3),
        reranker=RerankerConfig(provider="test", model="reranker"),
        plugins=PluginConfig(directory=tmp_path / "plugins"),
    )


@dataclass(slots=True)
class _Probe:
    result: ProviderReadinessResult | Exception

    async def probe(self, profile: object) -> ProviderReadinessResult:
        del profile
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_capability_lifecycle_is_monotonic_and_certification_is_evidence_gated() -> None:
    state = CapabilityState().advance(CapabilityLifecycleStage.ACTIVE)
    assert state.stage is CapabilityLifecycleStage.ACTIVE
    assert not state.behaviorally_verified
    assert not state.certified
    with pytest.raises(ValueError, match="cannot move backwards"):
        state.advance(CapabilityLifecycleStage.READY)
    with pytest.raises(ValueError, match="security verification"):
        state.advance(CapabilityLifecycleStage.CERTIFIED)
    certified = (
        state.advance(CapabilityLifecycleStage.VERIFIED)
        .with_security_verification()
        .advance(CapabilityLifecycleStage.CERTIFIED)
    )
    assert certified.certified


def test_configuration_resolution_is_deterministic_and_uses_frozen_profiles(
    tmp_path: Path,
) -> None:
    first = Phase85Runtime(_config(tmp_path), engine_ready=False)
    second = Phase85Runtime(_config(tmp_path), engine_ready=False)

    assert first.configuration_fingerprint == second.configuration_fingerprint
    assert first.profile_status("vision").model == "qwen2.5vl:latest"
    assert first.profile_status("multilingual_embedding").model == "BAAI/bge-m3"
    assert first.profile_status("multilingual_embedding").dimensions == 1024
    assert first.profile_status("multilingual_reranker").model == "BAAI/bge-reranker-v2-m3"
    assert first.profile_status("visual_embedding").model == "openai/clip-vit-large-patch14"
    assert first.profile_status("ocr").reason_code == "profile_not_configured"
    assert not first.profile_status("vision").state.initialized


def test_repository_mnemo_toml_is_the_profile_authority() -> None:
    root = Path(__file__).resolve().parents[3]
    runtime = Phase85Runtime(MnemoConfig.from_file(root / "mnemo.toml"), engine_ready=False)

    assert runtime.profile_status("vision").model is None
    assert runtime.profile_status("vision").reason_code == "profile_not_configured"
    assert runtime.profile_status("multilingual_embedding").model == "BAAI/bge-m3"
    assert runtime.profile_status("multilingual_reranker").model == "BAAI/bge-reranker-v2-m3"
    assert runtime.profile_status("visual_embedding").model is None
    assert runtime.profile_status("visual_embedding").reason_code == "profile_not_configured"
    assert not runtime.profile_status("vision").state.active


def test_optional_provider_failure_isolated_from_required_core(tmp_path: Path) -> None:
    runtime = Phase85Runtime(
        _config(tmp_path),
        engine_ready=True,
        active_v1_profiles=frozenset({"v1.embedding", "v1.reranker"}),
        core_active_capabilities=frozenset({"canonical_ingestion", "v1_retrieval"}),
        provider_registrations=(
            Phase85ProviderRegistration(
                profile_id="vision",
                probe=_Probe(RuntimeError("provider unavailable")),
            ),
        ),
    )

    assert not runtime.readiness().runtime_ready
    asyncio.run(runtime.initialize())

    assert runtime.readiness().runtime_ready
    assert runtime.capability_status("v1_retrieval").state.active
    assert not runtime.capability_status("vision").state.active
    assert runtime.profile_status("vision").reason_code == "provider_probe_failed:RuntimeError"
    assert "vision" in runtime.readiness().unavailable_optional

    asyncio.run(runtime.shutdown())
    assert not runtime.readiness().runtime_ready
    assert runtime.profile_status("vision").reason_code == "provider_not_registered"


def test_generation_and_dependencies_gate_activation(tmp_path: Path) -> None:
    service = object()
    config = _config(tmp_path)
    profile_fingerprint = Phase85Runtime(config, engine_ready=False).active_profile.fingerprint
    runtime = Phase85Runtime(
        config,
        engine_ready=True,
        active_v1_profiles=frozenset({"v1.embedding", "v1.reranker"}),
        core_active_capabilities=frozenset({"canonical_ingestion", "v1_retrieval"}),
        provider_registrations=(
            Phase85ProviderRegistration(
                profile_id="vision",
                probe=_Probe(
                    ProviderReadinessResult(
                        available_locally=True,
                        loadable=True,
                        initialized=True,
                    )
                ),
            ),
        ),
        service_registrations=(
            Phase85ServiceRegistration(
                capability_id="vision",
                service=service,
                ready=True,
                activate=True,
                generation_id="vision-generation-1",
                generation_active=True,
                profile_fingerprint=profile_fingerprint,
            ),
        ),
    )

    asyncio.run(runtime.initialize())

    status = runtime.capability_status("vision")
    assert not status.state.active
    assert status.reason_code == "dependency_unavailable:processing_jobs"
    assert runtime.service("vision") is service


def test_runtime_taxonomy_matches_governance_matrix() -> None:
    root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (root / "docs/governance/contracts/phase8_5_capability_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    governance_ids = {item["id"] for item in payload["capabilities"]}
    assert governance_ids == PHASE85_CAPABILITY_IDS


def test_registration_invariants_reject_fake_activation() -> None:
    with pytest.raises(ValueError, match="activation requires"):
        Phase85ServiceRegistration(
            capability_id="vision", service=object(), ready=False, activate=True
        )
    with pytest.raises(ValueError, match="active generation"):
        Phase85ServiceRegistration(
            capability_id="vision", service=object(), ready=True, generation_active=True
        )
