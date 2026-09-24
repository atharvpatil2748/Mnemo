"""Staged-generation admission uses only synthetic files and in-memory secrets."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from uuid import uuid4

import pytest
from mnemo.config import MnemoConfig
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.config import ServerConfig
from mnemo_server.services import production_credentials as credential_module
from mnemo_server.services import v2_certification as certification_module
from mnemo_server.services.pre_certification_observation import (
    TRANSPORTS,
    resolve_pre_certification_observation,
)
from mnemo_server.services.production_credentials import (
    CertificationStage,
    CredentialKind,
    ProductionCredentialRegistry,
)
from mnemo_server.services.production_runtime_binding import (
    resolve_certified_production_binding,
)
from mnemo_server.services.v2_reranker_lifecycle import (
    DurableRerankerActivationStoreV1,
    RerankerActivationEvidenceV1,
    V2RerankerMode,
)
from test_pre_certification_observation import _runtime
from test_production_credentials import FakeSecretStore, _provision

pytest_plugins = ("test_production_runtime_binding",)


def _staged(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, ServerConfig, MnemoConfig, ProductionCredentialRegistry, FakeSecretStore]:
    root, _, core = canonical
    manifest_path = root / "config/production/full_multilingual_v2.production.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    authority = manifest["configuration_authority"]
    for field in (
        "durable_activation_state",
        "certified_lifecycle_state",
        "final_certification_evidence",
    ):
        authority.pop(field)
    authority["credential_registry"] = "operational/credentials.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    store = FakeSecretStore()
    registry = ProductionCredentialRegistry(
        path=root / "operational/credentials.json", secret_store=store
    )
    record = _provision(registry)
    cursor = registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
    activation_id = uuid4()
    path = root / "operational" / "staged-activation.json"
    signing_key = hmac.new(
        cursor.encode(), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
    ).digest()
    DurableRerankerActivationStoreV1(
        path=path,
        signing_key=signing_key,
        prohibited_paths=(),
        credential_generation_id=record.generation_id,
        activation_generation_id=activation_id,
    ).commit(
        desired_mode=V2RerankerMode.BGE_V2_M3,
        principal=PrincipalContextV1(actor_id=uuid4(), authenticated=True),
        evidence=RerankerActivationEvidenceV1(
            v2_exposed=True,
            production_evaluation_passed=True,
            production_store_identity=manifest["corpus"]["database_identity"],
            expected_production_store_identity=manifest["corpus"]["database_identity"],
        ),
    )
    registry.stage_observation(
        generation_id=record.generation_id,
        activation_path=path,
        activation_generation_id=activation_id,
    )
    monkeypatch.setattr(credential_module, "WindowsCredentialStore", lambda: store)
    for name in (
        "MNEMO_SERVER_AUTH_MODE",
        "MNEMO_SERVER_API_KEY",
        "MNEMO_SERVER_JWT_SECRET",
        "MNEMO_SERVER_DELIVERY_CURSOR_SECRET",
        "MNEMO_SERVER_RERANKER_ACTIVATION_OPERATOR_SUBJECT",
        "MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT",
        "MNEMO_SERVER_RERANKER_ACTIVATION_STATE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE", str(root / "cache"))
    sha = hashlib.sha256((root / "governed/mnemo.db").read_bytes()).hexdigest()
    monkeypatch.setattr(certification_module, "STORE_SHA256", sha)
    config = ServerConfig.from_env(
        certified_production=True,
        certified_root=root,
        pre_certification_observation=True,
    )
    return root, config, core, registry, store


def test_staged_observer_admits_exact_server_owned_identity(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config, core, registry, store = _staged(canonical, monkeypatch)
    before = hashlib.sha256((root / "governed/mnemo.db").read_bytes()).hexdigest()
    resolved, identity, authority = resolve_pre_certification_observation(
        server_config=config, root=root, mnemo_config=core, secret_store=store
    )
    assert resolved == core
    assert identity.credential_generation_id == str(registry.load().generations[0].generation_id)
    assert identity.database_sha256 == before
    assert identity.reranker_revision
    assert authority.campaign_id == registry.load().generations[0].observation_campaign_id
    assert hashlib.sha256((root / "governed/mnemo.db").read_bytes()).hexdigest() == before
    assert not list((root / "governed").glob("mnemo.db-*"))
    assert registry.load().active_generation_id is None
    assert registry.load().generations[0].certification_stage is (
        CertificationStage.PRE_CERTIFICATION_OBSERVATION
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=config,
            root=root,
            mnemo_config=core,
            environment={},
            credential_secret_store=store,
        )
    relocated_cache = config.model_copy(
        update={"full_multilingual_v2_model_cache": root / "other-cache"}
    )
    _, relocated, _ = resolve_pre_certification_observation(
        server_config=relocated_cache,
        root=root,
        mnemo_config=core,
        secret_store=store,
    )
    assert relocated == identity


def test_signed_convergence_advances_only_staged_evidence(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config, core, registry, store = _staged(canonical, monkeypatch)
    _, identity, authority = resolve_pre_certification_observation(
        server_config=config, root=root, mnemo_config=core, secret_store=store
    )
    engine, runtime = _runtime(identity)
    observations = {
        transport: asyncio.run(
            authority.observe(
                transport=transport,
                identity=identity,
                principal_subject="synthetic-observer",
                correlation_id=uuid4(),
                engine=engine,
                runtime=runtime,
            )
        )
        for transport in TRANSPORTS
    }
    target = (
        root
        / "operational/pre_certification_observations"
        / str(authority.generation_id)
        / str(authority.campaign_id)
        / "convergence.json"
    )
    authority.converge(observations=observations, output=target)
    staged = registry.record_observation_convergence(
        generation_id=authority.generation_id, convergence_path=target
    )
    assert staged.certification_stage is CertificationStage.OBSERVATION_CONVERGED
    assert registry.load().active_generation_id is None
    assert staged.final_evidence_path is None


def test_staged_observer_rejects_auth_and_database_forks(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config, core, _, store = _staged(canonical, monkeypatch)
    for fork in (
        config.model_copy(update={"api_key": "wrong"}),
        config.model_copy(update={"auth_mode": "none"}),
        config.model_copy(update={"mutable_workspace_root": root / "workspace"}),
    ):
        with pytest.raises(RuntimeError, match="PRE_CERTIFICATION_"):
            resolve_pre_certification_observation(
                server_config=fork, root=root, mnemo_config=core, secret_store=store
            )
    with pytest.raises(RuntimeError, match="PRE_CERTIFICATION_"):
        resolve_pre_certification_observation(
            server_config=config,
            root=root,
            mnemo_config=core.model_copy(
                update={"storage": core.storage.model_copy(update={"sqlite": object()})}
            ),
            secret_store=store,
        )
    with pytest.raises(RuntimeError, match="CONFIGURATION_FORK_REJECTED"):
        resolve_pre_certification_observation(
            server_config=config,
            root=root,
            mnemo_config=core,
            secret_store=store,
            environment={"MNEMO_STORAGE_SQLITE_PATH": "historical.db"},
        )


def test_staged_observer_rejects_runtime_identity_forks(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config, core, registry, store = _staged(canonical, monkeypatch)
    for field, value in (
        ("production_mode", False),
        ("full_multilingual_v2_enabled", False),
        ("auth_mode", "none"),
        ("full_multilingual_v2_reranker_mode", "PASS_THROUGH"),
        ("full_multilingual_v2_model_cache", None),
        ("credential_registry_path", root / "other-registry.json"),
        ("credential_generation_id", uuid4()),
        ("reranker_activation_operator_subject", "wrong-operator"),
        ("mcp_stdio_principal_subject", "wrong-service"),
        ("reranker_activation_state_path", root / "wrong-activation.json"),
        ("final_qa_operational_store_path", root / "wrong-final-qa.db"),
        ("delivery_cursor_secret", "wrong-cursor"),
    ):
        with pytest.raises(RuntimeError, match="PRE_CERTIFICATION_"):
            resolve_pre_certification_observation(
                server_config=config.model_copy(update={field: value}),
                root=root,
                mnemo_config=core,
                secret_store=store,
            )
    record = registry.load().generations[0]
    assert record.activation_path is not None
    activation = Path(record.activation_path)
    activation.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="PRE_CERTIFICATION_"):
        resolve_pre_certification_observation(
            server_config=config, root=root, mnemo_config=core, secret_store=store
        )


def test_observation_admission_rejects_invalid_registry_stage(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config, core, registry, store = _staged(canonical, monkeypatch)
    original = registry.load()
    record = original.generations[0]
    for change in (
        {"observation_campaign_id": None},
        {"activation_path": None},
        {"activation_sha256": None},
        {"activation_sha256": "0" * 64},
        {"owner_subject": "different-operator"},
        {"service_subject": "different-service"},
    ):
        registry._save(
            original.model_copy(update={"generations": (record.model_copy(update=change),)})
        )
        with pytest.raises(RuntimeError, match="PRE_CERTIFICATION_"):
            resolve_pre_certification_observation(
                server_config=config, root=root, mnemo_config=core, secret_store=store
            )
    registry._save(original)
    assert resolve_pre_certification_observation(
        server_config=config, root=root, mnemo_config=core, secret_store=store
    )[1].credential_generation_id == str(record.generation_id)


def test_observation_admission_rejects_changed_corpus_and_incomplete_manifest(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config, core, _, store = _staged(canonical, monkeypatch)
    database = root / "governed/mnemo.db"
    database.write_bytes(database.read_bytes() + b"changed")
    with pytest.raises(RuntimeError, match="DATABASE_REJECTED"):
        resolve_pre_certification_observation(
            server_config=config, root=root, mnemo_config=core, secret_store=store
        )
    manifest_path = root / "config/production/full_multilingual_v2.production.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("reranker")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="BINDING_REJECTED"):
        resolve_pre_certification_observation(
            server_config=config, root=root, mnemo_config=core, secret_store=store
        )
