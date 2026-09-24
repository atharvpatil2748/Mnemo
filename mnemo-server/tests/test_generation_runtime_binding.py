"""CI-safe certified binding with a staged credential generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
import test_production_generation_evidence as evidence_test_module
import test_v2_certification_authority as certification_test_module
from mnemo.config import MnemoConfig
from mnemo_server.config import ServerConfig
from mnemo_server.services import production_credentials as credential_module
from mnemo_server.services import production_generation_evidence as final_module
from mnemo_server.services import v2_certification as certification_module
from mnemo_server.services.production_runtime_binding import (
    resolve_certified_production_binding,
)
from test_production_credentials import _bound_chain, _provision, _registry

pytest_plugins = ("test_production_runtime_binding",)


def test_runtime_uses_only_active_signed_generation(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, core = canonical
    database = root / "governed/mnemo.db"
    database_before = database.read_bytes()
    sha = hashlib.sha256(database_before).hexdigest()
    identity = "synthetic-certified-store-identity"
    for module in (certification_module, final_module, certification_test_module):
        monkeypatch.setattr(module, "STORE_SHA256", sha)
    for module in (
        certification_module,
        final_module,
        evidence_test_module,
        certification_test_module,
    ):
        monkeypatch.setattr(module, "STORE_IDENTITY", identity)

    registry, store = _registry(root / "operational")
    record = _provision(registry)
    profile = json.loads((root / "governance/identity.json").read_text(encoding="utf-8"))[
        "profile_fingerprint"
    ]

    def stage(path: Path, activation_id: UUID) -> UUID:
        staged = registry.stage_observation(
            generation_id=record.generation_id,
            activation_path=path,
            activation_generation_id=activation_id,
        )
        assert staged.observation_campaign_id is not None
        return staged.observation_campaign_id

    authority = _bound_chain(
        root / "operational/new-generation",
        registry,
        record.generation_id,
        model_profile_fingerprint=profile,
        stage_activation=stage,
    )
    registry.record_observation_convergence(
        generation_id=record.generation_id,
        convergence_path=authority.transport_parity_path,
    )
    authority.create()
    registry.record_final_evidence(generation_id=record.generation_id, authority=authority)
    registry.validate_with_evidence(generation_id=record.generation_id, authority=authority)
    registry.promote(generation_id=record.generation_id, authority=authority)

    manifest_path = root / "config/production/full_multilingual_v2.production.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config_authority = manifest["configuration_authority"]
    for field in (
        "durable_activation_state",
        "certified_lifecycle_state",
        "final_certification_evidence",
    ):
        config_authority.pop(field)
    config_authority["credential_registry"] = "operational/credentials.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
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
    server = ServerConfig.from_env(certified_production=True, certified_root=root)
    resolved, binding = resolve_certified_production_binding(
        server_config=server,
        mnemo_config=core,
        root=root,
        environment={},
        credential_secret_store=store,
    )
    assert resolved == core
    assert binding.credential_generation_id == str(record.generation_id)
    assert binding.database_sha256 == sha
    assert database.read_bytes() == database_before
    for suffix in ("-wal", "-shm", "-journal"):
        assert not Path(str(database) + suffix).exists()

    bad_server = server.model_copy(update={"api_key": "wrong"})
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=bad_server,
            mnemo_config=core,
            root=root,
            environment={},
            credential_secret_store=store,
        )
    registry.revoke(record.generation_id)
    with pytest.raises(RuntimeError):
        resolve_certified_production_binding(
            server_config=server,
            mnemo_config=core,
            root=root,
            environment={},
            credential_secret_store=store,
        )
