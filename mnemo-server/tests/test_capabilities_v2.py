"""Focused WP-13 runtime capability discovery and transport tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import jsonschema
import pytest
from fastapi import FastAPI
from mnemo import (
    EmbeddingConfig,
    EngineState,
    LLMConfig,
    LLMRoleConfig,
    MnemoConfig,
    Phase85FeatureConfig,
    Phase85ProfileConfig,
    Phase85ProviderRegistration,
    Phase85Runtime,
    Phase85ServiceRegistration,
    PluginConfig,
    ProviderReadinessResult,
    RerankerConfig,
    StorageConfig,
)
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo_server.auth import AuthMiddleware
from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_server_config
from mnemo_server.errors import register_error_handlers
from mnemo_server.mcp.tools import execute_mcp_tool, get_mcp_tools, structured_content_for
from mnemo_server.routers.capabilities_v2 import router
from mnemo_server.schemas.capabilities_v2 import CapabilityDiscoveryRequest, CapabilityDocument
from mnemo_server.services.capabilities_v2 import CapabilityDiscoveryService
from mnemo_server.services.mutable_workspace import (
    MutableWorkspaceDecision,
    MutableWorkspaceLayout,
    WorkspaceMode,
)
from mnemo_server.services.production_runtime_binding import CertifiedProductionBinding


@dataclass(slots=True)
class _Probe:
    result: ProviderReadinessResult

    async def probe(self, profile: object) -> ProviderReadinessResult:
        del profile
        return self.result


def _config(tmp_path: Path) -> MnemoConfig:
    role = LLMRoleConfig(provider="test", model="local", max_context_tokens=128)
    return MnemoConfig(
        storage=StorageConfig(),
        llm=LLMConfig(planner=role, synthesizer=role, extractor=role, classifier=role),
        embedding=EmbeddingConfig(provider="test", model="embedding", dimensions=3),
        reranker=RerankerConfig(provider="test", model="reranker"),
        plugins=PluginConfig(directory=tmp_path / "plugins"),
    )


async def _engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    service = object()
    runtime = Phase85Runtime(
        _config(tmp_path),
        engine_ready=True,
        active_v1_profiles=frozenset({"v1.embedding", "v1.reranker"}),
        core_active_capabilities=frozenset(
            {
                "canonical_ingestion",
                "v1_retrieval",
                "authorization",
                "completeness",
                "cursor_continuation",
                "provenance",
                "capability_discovery",
                "runtime_profile_activation",
            }
        ),
        provider_registrations=(
            Phase85ProviderRegistration(
                profile_id="vision",
                probe=_Probe(
                    ProviderReadinessResult(
                        available_locally=False,
                        loadable=False,
                        initialized=False,
                        reason_code="provider_unavailable",
                    )
                ),
            ),
        ),
        service_registrations=(
            Phase85ServiceRegistration(
                capability_id="capability_discovery",
                service=service,
                ready=True,
                activate=True,
                exposed=True,
            ),
            Phase85ServiceRegistration(
                capability_id="exhaustive_retrieval",
                service=service,
                ready=True,
                activate=True,
                exposed=True,
            ),
            Phase85ServiceRegistration(
                capability_id="structured_retrieval",
                service=service,
                ready=True,
                activate=True,
                generation_id="structured-generation",
                generation_active=True,
                exposed=True,
            ),
            Phase85ServiceRegistration(
                capability_id="asset_discovery",
                service=service,
                ready=True,
                activate=True,
                exposed=True,
            ),
            Phase85ServiceRegistration(
                capability_id="asset_delivery",
                service=service,
                ready=True,
                activate=True,
                exposed=True,
                behaviorally_verified=True,
            ),
            Phase85ServiceRegistration(
                capability_id="multimodal_retrieval",
                service=service,
                ready=True,
                activate=True,
                generation_id="multimodal-generation",
                generation_active=True,
                exposed=True,
            ),
            Phase85ServiceRegistration(
                capability_id="final_qa_v2",
                service=service,
                ready=True,
                activate=True,
                exposed=True,
            ),
            Phase85ServiceRegistration(
                capability_id="exact_retrieval",
                service=service,
                ready=True,
                activate=True,
                exposed=True,
            ),
            Phase85ServiceRegistration(
                capability_id="positional_retrieval",
                service=service,
                ready=True,
                activate=True,
                exposed=True,
            ),
            Phase85ServiceRegistration(
                capability_id="document_delivery",
                service=service,
                ready=True,
                activate=False,
            ),
        ),
    )
    await runtime.initialize()
    return SimpleNamespace(state=EngineState.READY, phase85=runtime)


@pytest.mark.anyio
async def test_capability_document_is_strict_deterministic_and_runtime_derived(
    tmp_path: Path,
) -> None:
    engine = await _engine(tmp_path)
    service = CapabilityDiscoveryService(engine, ServerConfig())
    first = service.document()
    second = service.document()
    assert first == second
    assert first.snapshot_identity == second.snapshot_identity
    jsonschema.validate(first.model_dump(mode="json"), CapabilityDocument.model_json_schema())
    assert first.runtime.active_profile.profile_id == "inline_legacy"
    assert first.runtime.active_profile.certification == "non_certified_default"
    assert len(first.runtime.active_profile.fingerprint) == 64
    with pytest.raises(Exception, match="extra"):
        CapabilityDiscoveryRequest.model_validate({"internal_path": "C:/secret"})

    capabilities = {item.capability_id: item for item in first.capabilities}
    assert capabilities["vision"].lifecycle.configured
    assert not capabilities["vision"].lifecycle.ready
    assert capabilities["vision"].profiles[0].reason == "provider_unavailable"
    assert capabilities["vision"].profiles[0].provider == "ollama"
    assert capabilities["vision"].profiles[0].revision == "5ced39dfa4ba"
    assert capabilities["document_delivery"].lifecycle.stage == "ready"
    assert not capabilities["document_delivery"].lifecycle.active
    assert capabilities["exhaustive_retrieval"].lifecycle.stage == "exposed"
    assert not capabilities["exhaustive_retrieval"].lifecycle.behaviorally_verified
    assert capabilities["asset_delivery"].lifecycle.stage == "verified"
    assert not capabilities["asset_delivery"].lifecycle.certified
    assert capabilities["structured_retrieval"].generation.active
    assert capabilities["structured_retrieval"].transports.callable
    assert not capabilities["multilingual_retrieval"].generation.present
    assert not capabilities["multilingual_retrieval"].transports.callable
    assert capabilities["multilingual_retrieval"].supported_languages == ()


@pytest.mark.anyio
async def test_final_qa_capability_reports_http_v2_contract_not_legacy_streaming(
    tmp_path: Path,
) -> None:
    engine = await _engine(tmp_path)
    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="test-key",
        delivery_cursor_secret="independent-chat-cursor-secret-32-bytes",
    )
    document = CapabilityDiscoveryService(engine, config).document()
    capability = next(item for item in document.capabilities if item.capability_id == "final_qa_v2")
    assert capability.limits["production_chat_transport"] == "authenticated_http_final_qa_v2"
    assert capability.limits["authentication_required"] is True
    assert capability.limits["v1_streaming_production"] is False
    assert capability.limits["v2_streaming_required"] is False
    assert capability.limits["governed_operational_store_required"] is True


@pytest.mark.anyio
async def test_blind_agent_guidance_limits_and_no_secret_leakage(tmp_path: Path) -> None:
    engine = await _engine(tmp_path)
    config = ServerConfig(
        max_advanced_evidence_budget=17,
        max_structured_rows_returned=23,
        delivery_cursor_secret="private-cursor-secret",
        api_key="private-api-key",
    )
    document = CapabilityDiscoveryService(engine, config).document()
    guidance = {item.task: item for item in document.task_guidance}
    assert guidance["ranked_semantic_search"].tool == "search_evidence"
    assert guidance["exhaustive_lookup"].tool == "search_evidence"
    assert guidance["exact_document_traversal"].tool == "get_document"
    assert guidance["structured_query"].tool == "query_structured"
    assert guidance["original_asset"].tool == "get_asset"
    assert guidance["image_analysis"].tool == "get_image_analysis"
    assert guidance["final_qa"].tool == "run_final_qa_v2"
    assert guidance["ranked_semantic_search"].available
    assert guidance["exhaustive_lookup"].available
    assert guidance["exact_document_traversal"].available
    assert guidance["structured_query"].available
    assert guidance["final_qa"].available
    assert not guidance["multilingual_search"].available

    capabilities = {item.capability_id: item for item in document.capabilities}
    assert capabilities["exhaustive_retrieval"].retrieval_modes == ("ranked", "exhaustive")
    assert capabilities["exhaustive_retrieval"].limits["max_evidence"] == 17
    assert capabilities["structured_retrieval"].limits["max_rows_returned"] == 23
    assert capabilities["exact_retrieval"].continuation
    assert not capabilities["processing_jobs"].transports.callable
    serialized = document.model_dump_json()
    assert "private-cursor-secret" not in serialized
    assert "private-api-key" not in serialized
    assert "C:\\" not in serialized and "file://" not in serialized


@pytest.mark.anyio
async def test_http_and_mcp_share_exact_capability_document_and_structured_content(
    tmp_path: Path,
) -> None:
    engine = await _engine(tmp_path)
    config = ServerConfig()
    app = FastAPI()
    app.include_router(router, prefix="/v2")
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_server_config] = lambda: config
    register_error_handlers(app)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        http_result = await client.get("/v2/capabilities")
        invalid = await client.get("/v2/capabilities?capability_ids=not-known")
    assert http_result.status_code == 200
    assert invalid.status_code == 422

    content = await execute_mcp_tool(engine, "get_capabilities", {}, config)
    mcp_document = json.loads(content[0].text)  # type: ignore[union-attr]
    assert mcp_document == http_result.json()
    assert structured_content_for("get_capabilities", {}, content) == mcp_document
    assert len(get_mcp_tools()) == 14
    assert get_mcp_tools()[-1].name == "get_capabilities"
    assert get_mcp_tools()[-1].outputSchema == CapabilityDocument.model_json_schema()


@pytest.mark.anyio
async def test_runtime_and_advertisement_consistency(tmp_path: Path) -> None:
    engine = await _engine(tmp_path)
    document = CapabilityDiscoveryService(engine, ServerConfig()).document()
    tools = {tool.name for tool in get_mcp_tools()}
    for capability in document.capabilities:
        if capability.transports.callable:
            assert set(capability.transports.mcp) <= tools
        if not capability.lifecycle.exposed:
            assert not capability.transports.callable
    discovery = next(
        item for item in document.capabilities if item.capability_id == "capability_discovery"
    )
    assert discovery.lifecycle.exposed
    assert discovery.transports.mcp == ("get_capabilities",)
    assert not discovery.lifecycle.behaviorally_verified
    assert not discovery.lifecycle.certified


@pytest.mark.anyio
async def test_http_capability_metadata_obeys_server_authentication(tmp_path: Path) -> None:
    engine = await _engine(tmp_path)
    config = ServerConfig(
        auth_mode="api-key",
        api_key="server-owned-key",
        delivery_cursor_secret="s" * 32,
    )
    app = FastAPI()
    app.add_middleware(AuthMiddleware, config=config)
    app.include_router(router, prefix="/v2")
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_server_config] = lambda: config
    register_error_handlers(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.get("/v2/capabilities")
        allowed = await client.get("/v2/capabilities", headers={"X-API-Key": "server-owned-key"})
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert "server-owned-key" not in allowed.text


@pytest.mark.anyio
async def test_profile_transport_flags_are_runtime_derived(tmp_path: Path) -> None:
    config = _config(tmp_path).model_copy(
        update={
            "phase85": Phase85ProfileConfig(features=Phase85FeatureConfig(http=False, mcp=True))
        }
    )
    service = object()
    runtime = Phase85Runtime(
        config,
        engine_ready=True,
        active_v1_profiles=frozenset({"v1.embedding", "v1.reranker"}),
        core_active_capabilities=frozenset(
            {"canonical_ingestion", "v1_retrieval", "completeness", "cursor_continuation"}
        ),
        service_registrations=(
            Phase85ServiceRegistration(
                capability_id="exhaustive_retrieval",
                service=service,
                ready=True,
                activate=True,
                exposed=True,
            ),
        ),
    )
    await runtime.initialize()
    engine = SimpleNamespace(state=EngineState.READY, phase85=runtime)
    document = CapabilityDiscoveryService(engine, ServerConfig()).document()
    advanced = next(
        item for item in document.capabilities if item.capability_id == "exhaustive_retrieval"
    )
    assert advanced.transports.http == ()
    assert advanced.transports.mcp == ("search_evidence",)
    assert advanced.transports.callable
    assert document.runtime.active_profile.http_enabled is False
    assert document.runtime.active_profile.mcp_enabled is True


@pytest.mark.anyio
async def test_production_capabilities_report_read_only_fallback(tmp_path: Path) -> None:
    engine = await _engine(tmp_path)
    engine.certified_read_only = True
    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="test-key",
        delivery_cursor_secret="production-capability-test-secret",
    )
    decision = MutableWorkspaceDecision(
        mode=WorkspaceMode.READ_ONLY,
        reason="MUTABLE_WORKSPACE_CONFIGURATION_MISSING",
    )

    storage = CapabilityDiscoveryService(engine, config, decision).document().runtime.storage

    assert storage.certified_read_available
    assert storage.certified_storage_mode == "immutable_query_only"
    assert storage.workspace_mode == "read_only"
    assert storage.workspace_available is False
    assert storage.mutation_available is False
    assert storage.read_only_fallback is True
    assert storage.reason == "MUTABLE_WORKSPACE_CONFIGURATION_MISSING"


@pytest.mark.anyio
async def test_production_capabilities_report_accepted_workspace_without_paths(
    tmp_path: Path,
) -> None:
    engine = await _engine(tmp_path)
    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="test-key",
        delivery_cursor_secret="production-capability-test-secret",
    )
    workspace = tmp_path / "operator-workspace"
    decision = MutableWorkspaceDecision(
        mode=WorkspaceMode.MUTABLE,
        reason="MUTABLE_WORKSPACE_ACCEPTED",
        layout=MutableWorkspaceLayout.from_root(workspace),
    )

    document = CapabilityDiscoveryService(engine, config, decision).document()
    storage = document.runtime.storage

    assert storage.workspace_mode == "mutable"
    assert storage.workspace_available is True
    assert storage.mutation_available is True
    assert storage.read_only_fallback is False
    assert str(workspace) not in document.model_dump_json()


@pytest.mark.anyio
async def test_capability_lifecycle_distinguishes_routes_from_services_and_image_families(
    tmp_path: Path,
) -> None:
    engine = await _engine(tmp_path)
    document = CapabilityDiscoveryService(engine, ServerConfig()).document()
    items = {item.capability_id: item for item in document.capabilities}
    delivery = items["document_delivery"]
    assert delivery.lifecycle.registered and delivery.lifecycle.implemented
    assert delivery.lifecycle.service_registered
    assert not delivery.lifecycle.active
    assert delivery.registered_mcp_tools == ("get_document", "get_document_chunk")
    assert not delivery.transports.callable
    assert not items["exhaustive_retrieval"].lifecycle.behaviorally_verified
    assert not items["exhaustive_retrieval"].lifecycle.certified
    assert items["asset_delivery"].lifecycle.active
    for capability_id in ("ocr", "vision", "caption_derivation", "clip_embedding"):
        assert capability_id in items
        assert not items[capability_id].lifecycle.active
        assert not items[capability_id].transports.callable
    for capability_id in ("caption_derivation", "clip_embedding"):
        assert not items[capability_id].lifecycle.registered
        assert not items[capability_id].lifecycle.implemented
    image_search = items["semantic_image_search"]
    assert not image_search.lifecycle.registered
    assert not image_search.lifecycle.implemented
    assert not image_search.transports.callable
    assert image_search.registered_mcp_tools == ()


@pytest.mark.anyio
async def test_registered_exact_chunk_route_does_not_activate_document_family(
    tmp_path: Path,
) -> None:
    runtime = Phase85Runtime(
        _config(tmp_path),
        engine_ready=True,
        active_v1_profiles=frozenset({"v1.embedding", "v1.reranker"}),
        core_active_capabilities=frozenset(
            {"v1_retrieval", "authorization", "provenance", "completeness", "cursor_continuation"}
        ),
        service_registrations=(
            Phase85ServiceRegistration(
                capability_id="exhaustive_retrieval",
                service=object(),
                ready=True,
                activate=True,
                exposed=True,
            ),
        ),
    )
    await runtime.initialize()
    engine = SimpleNamespace(state=EngineState.READY, phase85=runtime)
    items = {
        item.capability_id: item
        for item in CapabilityDiscoveryService(engine, ServerConfig()).document().capabilities
    }
    document = items["document_delivery"]
    assert document.unavailable_reason == "service_not_registered"
    assert document.lifecycle.service_registered is False
    assert document.registered_mcp_tools == ("get_document", "get_document_chunk")
    assert document.transports.callable is False
    exhaustive = items["exhaustive_retrieval"]
    assert exhaustive.transports.callable is True
    assert exhaustive.lifecycle.behaviorally_verified is False
    assert exhaustive.lifecycle.certified is False


@pytest.mark.anyio
async def test_notebook_capabilities_require_canonical_authorization(tmp_path: Path) -> None:
    engine = await _engine(tmp_path)
    notebook_id = uuid4()
    engine.storage = SimpleNamespace(get_notebook=AsyncMock(return_value=object()))
    service = CapabilityDiscoveryService(engine, ServerConfig())
    request = CapabilityDiscoveryRequest(notebook_id=notebook_id)
    with pytest.raises(PermissionError):
        service.document(request)
    with pytest.raises(PermissionError):
        await service.document_for_principal(request, PrincipalContextV1(uuid4(), False))
    scoped = await service.document_for_principal(request, PrincipalContextV1(uuid4(), True))
    assert scoped.scope_qualified
    assert scoped.scope_notebook_id == notebook_id
    states = {
        item.capability_id: item.lifecycle.available_for_scope for item in scoped.capabilities
    }
    assert states["exhaustive_retrieval"] is True
    assert states["document_delivery"] is False
    assert states["asset_delivery"] is None
    assert service.document().scope_qualified is False
    engine.storage.get_notebook.return_value = None
    with pytest.raises(NotFoundError, match="authorized resource was not found"):
        await service.document_for_principal(request, PrincipalContextV1(uuid4(), True))


@pytest.mark.anyio
async def test_effective_identity_uses_only_verified_server_binding(tmp_path: Path) -> None:
    engine = await _engine(tmp_path)
    binding = CertifiedProductionBinding(
        schema_version="mnemo.certified-production-binding/1",
        binding_id="a" * 64,
        configuration_digest="b" * 64,
        database_identity="c" * 64,
        database_sha256="d" * 64,
        model_profile_fingerprint="e" * 64,
        embedding_model="embedding",
        embedding_revision="f" * 40,
        reranker_model="reranker",
        reranker_revision="1" * 40,
        activation_digest="2" * 64,
        activation_mode="BGE_V2_M3",
        certification_digest="3" * 64,
        certification_signature="private-signature-not-for-output",
        final_qa_operational_identity="4" * 64,
        mutable_workspace_identity="5" * 64,
        authorization_mode="api-key",
        stdio_principal_identity="6" * 64,
        runtime_profile="test",
        credential_generation_id=str(uuid4()),
        final_evidence_digest="7" * 64,
    )
    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="private-key",
        delivery_cursor_secret="distinct-test-cursor-signing-secret-32-bytes",
    )
    document = CapabilityDiscoveryService(
        engine, config, certified_binding=binding, transport="external_tunnel"
    ).document()
    identity = document.runtime.effective_identity
    assert identity is not None
    assert identity.binding_id == binding.binding_id
    assert identity.database_identity == binding.database_identity
    assert identity.transport == "external_tunnel"
    assert "private-signature" not in document.model_dump_json()
    assert "private-key" not in document.model_dump_json()
    assert CapabilityDiscoveryService(engine, config).document().runtime.effective_identity is None


@pytest.mark.anyio
async def test_http_and_mcp_scope_use_trusted_principal_and_same_binding(tmp_path: Path) -> None:
    engine = await _engine(tmp_path)
    notebook_id = uuid4()
    engine.storage = SimpleNamespace(get_notebook=AsyncMock(return_value=object()))
    binding = CertifiedProductionBinding(
        schema_version="mnemo.certified-production-binding/1",
        binding_id="a" * 64,
        configuration_digest="b" * 64,
        database_identity="c" * 64,
        database_sha256="d" * 64,
        model_profile_fingerprint="e" * 64,
        embedding_model="embedding",
        embedding_revision="f" * 40,
        reranker_model="reranker",
        reranker_revision="1" * 40,
        activation_digest="2" * 64,
        activation_mode="BGE_V2_M3",
        certification_digest="3" * 64,
        certification_signature="private-signature-not-for-output",
        final_qa_operational_identity="4" * 64,
        mutable_workspace_identity="5" * 64,
        authorization_mode="api-key",
        stdio_principal_identity="6" * 64,
        runtime_profile="test",
        credential_generation_id=str(uuid4()),
        final_evidence_digest="7" * 64,
    )
    config = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        auth_mode="api-key",
        api_key="private-key",
        full_multilingual_v2_model_cache=tmp_path,
        final_qa_operational_store_path=tmp_path / "operational.db",
        mcp_stdio_principal_subject="test-operator",
        delivery_cursor_secret="distinct-test-cursor-signing-secret-32-bytes",
    )
    app = FastAPI()
    app.add_middleware(AuthMiddleware, config=config)
    app.include_router(router, prefix="/v2")
    app.state.certified_production_binding = binding
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_server_config] = lambda: config
    register_error_handlers(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.get("/v2/capabilities", params={"notebook_id": str(notebook_id)})
        allowed = await client.get(
            "/v2/capabilities",
            params={"notebook_id": str(notebook_id)},
            headers={"X-API-Key": "private-key"},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200
    http_doc = allowed.json()
    assert http_doc["scope_qualified"] is True
    assert http_doc["runtime"]["effective_identity"]["transport"] == "http"
    principal = PrincipalContextV1(uuid4(), True)
    content = await execute_mcp_tool(
        engine,
        "get_capabilities",
        {"notebook_id": str(notebook_id)},
        config,
        principal,
        certified_binding=binding,
        transport="external_tunnel",
    )
    mcp_doc = json.loads(content[0].text)
    assert mcp_doc["scope_qualified"] is True
    assert mcp_doc["runtime"]["effective_identity"]["transport"] == "external_tunnel"
    assert (
        mcp_doc["runtime"]["effective_identity"]["binding_id"]
        == http_doc["runtime"]["effective_identity"]["binding_id"]
    )
    assert "private-key" not in json.dumps(mcp_doc) + json.dumps(http_doc)
