"""Same-store production readiness tests; no provider inference or exposure."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mnemo.config import MnemoConfig
from mnemo_server.config import ServerConfig
from mnemo_server.runtime_config import resolve_mnemo_runtime_config
from mnemo_server.services.production_store_readiness import (
    EVALUATION_DATABASE,
    ProductionV2ReadinessEvidenceBuilderV1,
    validate_production_v2_serving_readiness,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
    / "V2_DATABASE_ARTIFACT_IDENTITY.json"
)


def test_http_and_mcp_shared_config_resolves_governed_44_document_store() -> None:
    config = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    store_path = (ROOT / config.storage.sqlite.path).resolve()
    if not store_path.exists():
        pytest.skip("Governed production database not present in environment")
    result = asyncio.run(
        validate_production_v2_serving_readiness(
            workspace_root=ROOT,
            mnemo_config=config,
            server_config=ServerConfig(),
            identity_manifest=MANIFEST,
        )
    )
    assert result.ready_for_controlled_exposure is True
    assert result.currently_exposed is False
    assert result.production_store.document_count == 44
    assert result.production_store.chunk_count == 2_658
    assert result.production_store.source_blob_count == 44
    assert len(set(result.component_store_identities.values())) == 1
    assert result.candidate_pool_k == 50
    assert result.requested_k_semantics.startswith("dynamic-result-limit")
    assert result.advanced_retrieval_deadline_milliseconds == 30_000
    assert result.advanced_retrieval_deadline_owner == "server-transport"
    assert result.reranker_pair_policy == "bge-reranker-v2-m3-pair-256-contextual-v1"
    assert result.reranker_device == "cuda"
    assert result.reranker_batch_size == 2
    assert result.reranker_cpu_fallback is False
    assert result.context_compression_target_tokens == 100
    assert result.context_compression_hard_max_tokens == 120


def test_evaluation_database_cannot_be_selected_as_production() -> None:
    original = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    unsafe = original.model_copy(
        update={
            "storage": original.storage.model_copy(
                update={
                    "sqlite": original.storage.sqlite.model_copy(
                        update={"path": (ROOT / EVALUATION_DATABASE).resolve()}
                    )
                }
            )
        }
    )
    with pytest.raises(RuntimeError, match="PRODUCTION_STORE_CONFIGURATION_MISMATCH"):
        asyncio.run(
            validate_production_v2_serving_readiness(
                workspace_root=ROOT,
                mnemo_config=unsafe,
                server_config=ServerConfig(),
                identity_manifest=MANIFEST,
            )
        )


def test_explicit_config_has_precedence_for_both_transport_processes() -> None:
    config = MnemoConfig.from_file(ROOT / "mnemo.toml")
    assert resolve_mnemo_runtime_config(config) is config


def test_production_owned_builder_proves_ready_but_not_exposed() -> None:
    config = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    store_path = (ROOT / config.storage.sqlite.path).resolve()
    if not store_path.exists():
        pytest.skip("Governed production database not present in environment")
    server = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="test",
        delivery_cursor_secret="x" * 32,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_model_cache=ROOT / "scratch/models",
        final_qa_operational_store_path=ROOT / "scratch/test-final-qa-operational.db",
        mcp_stdio_principal_subject="mnemo-production-stdio",
    )
    evidence, snapshot = asyncio.run(
        ProductionV2ReadinessEvidenceBuilderV1(
            workspace_root=ROOT,
            mnemo_config=config,
            server_config=server,
            identity_manifest=MANIFEST,
        ).build()
    )
    assert evidence.reranker_mode == "PASS_THROUGH"
    assert evidence.bge_active is False
    assert evidence.authenticated_http_capability is True
    assert evidence.authenticated_mcp_stdio_capability is True
    assert evidence.authenticated_mcp_sse_capability is True
    assert evidence.final_qa_operational_store_is_distinct is True
    assert evidence.final_qa_operational_store.endswith("test-final-qa-operational.db")
    assert snapshot.v2_ready is True
    assert snapshot.v2_active is True
    assert snapshot.v2_exposed is False


def test_readiness_rejects_corpus_as_final_qa_operational_store() -> None:
    config = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    server = ServerConfig(
        final_qa_operational_store_path=config.storage.sqlite.path,
    )
    with pytest.raises(RuntimeError, match="FINAL_QA_OPERATIONAL_STORE_MUST_DIFFER"):
        asyncio.run(
            validate_production_v2_serving_readiness(
                workspace_root=ROOT,
                mnemo_config=config,
                server_config=server,
                identity_manifest=MANIFEST,
            )
        )
