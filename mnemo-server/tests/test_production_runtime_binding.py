"""CI-safe identity/admission tests for Phase 8.8.1 (no governed DB access)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from mnemo.config import MnemoConfig
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot
from mnemo_server.config import ServerConfig
from mnemo_server.services.durable_reranker_activation import _signing_key
from mnemo_server.services.production_runtime_binding import (
    PROFILE_NAME,
    collect_certified_convergence,
    record_certified_transport_startup,
    reject_uncertified_corpus_startup,
    resolve_certified_production_binding,
    write_certified_convergence,
)


def _write(root: Path, relative: str, value: object) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return target


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def canonical(tmp_path: Path) -> tuple[Path, ServerConfig, MnemoConfig]:
    root = tmp_path / "application"
    root.mkdir()
    core = root / "mnemo.toml"
    core.write_text(
        """
[storage.filesystem]
enabled = true
root = "governed/blobs"
[storage.sqlite]
enabled = true
path = "governed/mnemo.db"
[storage.qdrant]
enabled = false
[storage.surrealdb]
enabled = false
[plugins]
directory = "plugins"
[llm.planner]
provider = "ollama"
model = "gemma4:e4b"
[llm.synthesizer]
provider = "ollama"
model = "gemma4:e4b"
[llm.extractor]
provider = "ollama"
model = "gemma4:e4b"
[llm.classifier]
provider = "ollama"
model = "gemma4:e4b"
[embedding]
provider = "sentence-transformers"
model = "BAAI/bge-m3"
dimensions = 1024
[reranker]
provider = "v2-owned-pass-through"
model = "no-outer-reranker"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = MnemoConfig.from_file(core)
    db = root / "governed/mnemo.db"
    db.parent.mkdir()
    db.write_bytes(b"synthetic immutable certified database; never opened as SQLite")
    source_profile = (
        Path(__file__).resolve().parents[2]
        / "config/model_profiles/full_multilingual_v2_profiles.toml"
    )
    profile_path = root / "config/model_profiles/full_multilingual_v2_profiles.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_bytes(source_profile.read_bytes())
    profile = profile_snapshot(ModelProfileDocument.from_file(profile_path).select(PROFILE_NAME))
    embedding = profile.components["multilingual_embedding"]
    reranker = profile.components["multilingual_reranker"]
    identity = "synthetic-certified-store-identity"
    certificate = {
        "status": "PRODUCTION_CERTIFICATION_PASS",
        "production_store_identity": identity,
        "production_store_sha256": _sha(db.read_bytes()),
        "bge_revision": reranker.revision,
        "pair_policy": "bge-reranker-v2-m3-pair-256-contextual-v1",
        "signature": "synthetic-test-certificate-signature",
    }
    _write(root, "operational/certification.json", certificate)
    _write(
        root,
        "operational/final-certification.json",
        {
            "production_store": {
                "governed_identity": identity,
                "sha256_after": _sha(db.read_bytes()),
            },
            "governance": {"wp17_signature": certificate["signature"]},
        },
    )
    _write(
        root,
        "governance/identity.json",
        {
            "profile_fingerprint": profile.fingerprint,
            "database_identity": identity,
            "target_path": "governed/mnemo.db",
        },
    )
    _write(
        root,
        "config/production/full_multilingual_v2.production.json",
        {
            "configuration_authority": {
                "core_runtime": "mnemo.toml",
                "model_profile": "config/model_profiles/full_multilingual_v2_profiles.toml",
                "durable_activation_state": "operational/activation.json",
                "certified_lifecycle_state": "operational/certification.json",
                "final_certification_evidence": "operational/final-certification.json",
            },
            "corpus": {
                "database_path": "governed/mnemo.db",
                "database_identity": identity,
                "identity_manifest": "governance/identity.json",
            },
            "final_qa_operational_store": {"path": "operational/final_qa_v2.db"},
            "retrieval": {
                "semantic_model": embedding.model,
                "semantic_revision": embedding.revision,
            },
            "reranker": {
                "model": reranker.model,
                "revision": reranker.revision,
                "pair_policy": certificate["pair_policy"],
            },
            "reranker_activation": {"active_mode": "BGE_V2_M3"},
        },
    )
    server = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_reranker_mode="BGE_V2_M3",
        full_multilingual_v2_model_cache=tmp_path / "models",
        reranker_activation_state_path=Path("operational/activation.json"),
        reranker_activation_operator_subject="operator",
        final_qa_operational_store_path=Path("operational/final_qa_v2.db"),
        mcp_stdio_principal_subject="stdio-subject",
        auth_mode="api-key",
        api_key="synthetic-api-key",
        delivery_cursor_secret="s" * 32,
    )
    unsigned = {
        "schema_version": "mnemo.v2-reranker-activation-state/1",
        "sequence": 1,
        "desired_mode": "BGE_V2_M3",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "updated_by_actor_id": None,
        "activation_evidence": {
            "v2_exposed": True,
            "production_evaluation_passed": True,
            "production_store_identity": identity,
            "expected_production_store_identity": identity,
            "candidate_builder_id": "mnemo.v2-typed-candidate-builder/1",
            "model": reranker.model,
            "revision": reranker.revision,
            "pair_policy": certificate["pair_policy"],
            "device": "cuda",
            "batch_size": 2,
            "cpu_fallback": False,
        },
    }
    signature = hmac.new(
        _signing_key(server),
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    _write(root, "operational/activation.json", {**unsigned, "signature": signature})
    return root, server, config


def test_canonical_binding_is_deterministic_and_side_effect_free(
    canonical: tuple[Path, ServerConfig, MnemoConfig], tmp_path: Path
) -> None:
    root, server, config = canonical
    before = _sha((root / "governed/mnemo.db").read_bytes())
    observations = {}
    for transport in ("http", "mcp_stdio", "mcp_sse", "external_tunnel"):
        resolved, binding = resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )
        assert resolved == config
        observations[transport] = binding
    assert len({item.binding_id for item in observations.values()}) == 1
    assert observations["http"].database_identity == "synthetic-certified-store-identity"
    assert _sha((root / "governed/mnemo.db").read_bytes()) == before
    assert not (root / "governed/mnemo.db-wal").exists()
    for transport, binding in observations.items():
        record_certified_transport_startup(
            binding=binding, transport=transport, server_config=server, root=root
        )
    result = collect_certified_convergence(
        server_config=server, expected_binding_id=observations["http"].binding_id, root=root
    )
    assert result["result"] == "PASS"


def test_certified_process_derives_non_secret_values_from_manifest(
    canonical: tuple[Path, ServerConfig, MnemoConfig], tmp_path: Path
) -> None:
    root, server, core = canonical
    env = {
        "MNEMO_SERVER_AUTH_MODE": "api-key",
        "MNEMO_SERVER_API_KEY": server.api_key or "",
        "MNEMO_SERVER_DELIVERY_CURSOR_SECRET": server.delivery_cursor_secret,
        "MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE": str(tmp_path / "models"),
        "MNEMO_SERVER_RERANKER_ACTIVATION_OPERATOR_SUBJECT": "operator",
        "MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT": "stdio-subject",
    }
    with patch.dict(os.environ, env, clear=True):
        resolved = ServerConfig.from_env(certified_production=True, certified_root=root)
    assert resolved.production_mode and resolved.full_multilingual_v2_enabled
    assert resolved.full_multilingual_v2_reranker_mode == "BGE_V2_M3"
    assert resolved.reranker_activation_state_path == Path("operational/activation.json")
    assert resolved.final_qa_operational_store_path == Path("operational/final_qa_v2.db")
    _, binding = resolve_certified_production_binding(
        server_config=resolved, mnemo_config=core, root=root, environment={}
    )
    assert binding.database_identity == "synthetic-certified-store-identity"


@pytest.mark.parametrize(
    "name,value",
    [
        ("MNEMO_SERVER_RERANKER_ACTIVATION_STATE_PATH", "operational/other.json"),
        ("MNEMO_SERVER_FINAL_QA_OPERATIONAL_STORE_PATH", "operational/other.db"),
        ("MNEMO_SERVER_FULL_MULTILINGUAL_V2_RERANKER_MODE", "PASS_THROUGH"),
    ],
)
def test_explicit_environment_cannot_fork_manifest_owned_identity(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    root, server, core = canonical
    env = {
        "MNEMO_SERVER_AUTH_MODE": "api-key",
        "MNEMO_SERVER_API_KEY": server.api_key or "",
        "MNEMO_SERVER_DELIVERY_CURSOR_SECRET": server.delivery_cursor_secret,
        "MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE": str(tmp_path / "models"),
        "MNEMO_SERVER_RERANKER_ACTIVATION_OPERATOR_SUBJECT": "operator",
        "MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT": "stdio-subject",
        name: value,
    }
    with patch.dict(os.environ, env, clear=True):
        resolved = ServerConfig.from_env(certified_production=True, certified_root=root)
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=resolved, mnemo_config=core, root=root, environment={}
        )


def test_certified_process_rejects_false_lifecycle_flag(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, _, _ = canonical
    with (
        patch.dict(os.environ, {"MNEMO_SERVER_PRODUCTION_MODE": "false"}, clear=True),
        pytest.raises(ValueError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"),
    ):
        ServerConfig.from_env(certified_production=True, certified_root=root)


@pytest.mark.parametrize(
    "missing",
    [
        "MNEMO_SERVER_API_KEY",
        "MNEMO_SERVER_DELIVERY_CURSOR_SECRET",
        "MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT",
        "MNEMO_SERVER_RERANKER_ACTIVATION_OPERATOR_SUBJECT",
    ],
)
def test_certified_process_missing_operator_configuration_fails_closed(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
    tmp_path: Path,
    missing: str,
) -> None:
    root, server, core = canonical
    env = {
        "MNEMO_SERVER_AUTH_MODE": "api-key",
        "MNEMO_SERVER_API_KEY": server.api_key or "",
        "MNEMO_SERVER_DELIVERY_CURSOR_SECRET": server.delivery_cursor_secret,
        "MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE": str(tmp_path / "models"),
        "MNEMO_SERVER_RERANKER_ACTIVATION_OPERATOR_SUBJECT": "operator",
        "MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT": "stdio-subject",
    }
    env.pop(missing)
    with patch.dict(os.environ, env, clear=True):
        try:
            resolved = ServerConfig.from_env(certified_production=True, certified_root=root)
        except ValueError:
            return
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=resolved, mnemo_config=core, root=root, environment={}
        )


def test_certified_process_cannot_use_anonymous_authentication(
    canonical: tuple[Path, ServerConfig, MnemoConfig], tmp_path: Path
) -> None:
    root, server, _ = canonical
    env = {
        "MNEMO_SERVER_AUTH_MODE": "none",
        "MNEMO_SERVER_DELIVERY_CURSOR_SECRET": server.delivery_cursor_secret,
        "MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE": str(tmp_path / "models"),
        "MNEMO_SERVER_RERANKER_ACTIVATION_OPERATOR_SUBJECT": "operator",
        "MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT": "stdio-subject",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        pytest.raises(ValueError),
    ):
        ServerConfig.from_env(certified_production=True, certified_root=root)


def test_model_cache_location_is_not_certified_runtime_identity(
    canonical: tuple[Path, ServerConfig, MnemoConfig], tmp_path: Path
) -> None:
    root, server, core = canonical
    _, first = resolve_certified_production_binding(
        server_config=server, mnemo_config=core, root=root, environment={}
    )
    _, second = resolve_certified_production_binding(
        server_config=server.model_copy(
            update={"full_multilingual_v2_model_cache": tmp_path / "other-model-cache"}
        ),
        mnemo_config=core,
        root=root,
        environment={},
    )
    assert first.binding_id == second.binding_id
    assert first.configuration_digest == second.configuration_digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("auth_mode", "none"),
        ("auth_mode", "jwt"),
        ("api_key", None),
        ("production_mode", False),
        ("full_multilingual_v2_reranker_mode", "PASS_THROUGH"),
        ("full_multilingual_v2_model_cache", Path("relative-model-cache")),
        ("reranker_activation_state_path", None),
        ("final_qa_operational_store_path", Path("operational/other.db")),
        ("reranker_activation_state_path", Path("operational/other.json")),
    ],
)
def test_server_identity_forks_fail_closed(
    canonical: tuple[Path, ServerConfig, MnemoConfig], field: str, value: object
) -> None:
    root, server, config = canonical
    fork = server.model_copy(update={field: value})
    with pytest.raises(RuntimeError):
        resolve_certified_production_binding(
            server_config=fork, mnemo_config=config, root=root, environment={}
        )


def test_historical_environment_fork_rejected(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server,
            mnemo_config=config,
            root=root,
            environment={"MNEMO_STORAGE_SQLITE_PATH": "historical.db"},
        )


def test_database_and_certificate_forks_rejected(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    (root / "governed/mnemo.db").write_bytes(b"altered synthetic database")
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


def test_refuses_false_four_transport_evidence(
    canonical: tuple[Path, ServerConfig, MnemoConfig], tmp_path: Path
) -> None:
    root, server, config = canonical
    _, binding = resolve_certified_production_binding(
        server_config=server, mnemo_config=config, root=root, environment={}
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        collect_certified_convergence(
            server_config=server, expected_binding_id=binding.binding_id, root=root
        )


def test_attested_four_transport_artifact_is_durable_and_diffable(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    _, binding = resolve_certified_production_binding(
        server_config=server, mnemo_config=config, root=root, environment={}
    )
    for transport in ("http", "mcp_stdio", "mcp_sse", "external_tunnel"):
        observation = record_certified_transport_startup(
            binding=binding, transport=transport, server_config=server, root=root
        )
        assert observation.is_file()
    artifact = write_certified_convergence(server_config=server, root=root)
    document = json.loads(artifact.read_text(encoding="utf-8"))
    assert document["result"] == "PASS"
    assert document["binding_id"] == binding.binding_id
    assert set(document["observations"]) == {"http", "mcp_stdio", "mcp_sse", "external_tunnel"}
    assert "synthetic-api-key" not in artifact.read_text(encoding="utf-8")


def test_tampered_transport_observation_fails_closed(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    _, binding = resolve_certified_production_binding(
        server_config=server, mnemo_config=config, root=root, environment={}
    )
    for transport in ("http", "mcp_stdio", "mcp_sse", "external_tunnel"):
        record_certified_transport_startup(
            binding=binding, transport=transport, server_config=server, root=root
        )
    tampered = root / "scratch/phase8_8_1_runtime_convergence/external_tunnel.json"
    document = json.loads(tampered.read_text(encoding="utf-8"))
    document["binding"]["database_identity"] = "historical-fork"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        collect_certified_convergence(
            server_config=server, expected_binding_id=binding.binding_id, root=root
        )
    assert not (tampered.parent / "convergence.json").exists()


@pytest.mark.parametrize(
    "relative,field,value",
    [
        ("operational/certification.json", "bge_revision", "wrong-revision"),
        ("operational/certification.json", "signature", "wrong-signature"),
        ("operational/final-certification.json", "governance", {}),
        ("config/production/full_multilingual_v2.production.json", "corpus", {}),
        ("config/production/full_multilingual_v2.production.json", "retrieval", {}),
        ("config/production/full_multilingual_v2.production.json", "reranker", {}),
        ("governance/identity.json", "database_identity", "wrong-identity"),
        ("operational/activation.json", "desired_mode", "PASS_THROUGH"),
    ],
)
def test_certified_identity_forks_never_admit(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
    relative: str,
    field: str,
    value: object,
) -> None:
    root, server, config = canonical
    target = root / relative
    document = json.loads(target.read_text(encoding="utf-8"))
    document[field] = value
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises((RuntimeError, KeyError, ValueError)):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


@pytest.mark.parametrize(
    "relative,field,value",
    [
        ("config/production/full_multilingual_v2.production.json", "configuration_authority", {}),
        ("config/production/full_multilingual_v2.production.json", "corpus", None),
        ("config/production/full_multilingual_v2.production.json", "retrieval", None),
        (
            "config/production/full_multilingual_v2.production.json",
            "final_qa_operational_store",
            {},
        ),
        ("operational/final-certification.json", "production_store", None),
        ("operational/final-certification.json", "governance", None),
        ("operational/certification.json", "status", "NOT_CERTIFIED"),
        ("governance/identity.json", "profile_fingerprint", "wrong-fingerprint"),
    ],
)
def test_missing_or_conflicting_authority_fails_closed(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
    relative: str,
    field: str,
    value: object,
) -> None:
    root, server, config = canonical
    target = root / relative
    document = json.loads(target.read_text(encoding="utf-8"))
    document[field] = value
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises((RuntimeError, KeyError, ValueError)):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


@pytest.mark.parametrize("unsafe_path", ["../outside.db", "C:/outside.db", ""])
def test_manifest_cannot_escape_governed_root(
    canonical: tuple[Path, ServerConfig, MnemoConfig], unsafe_path: str
) -> None:
    root, server, config = canonical
    target = root / "config/production/full_multilingual_v2.production.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["corpus"]["database_path"] = unsafe_path
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


def test_credential_change_changes_binding_identity(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    _, first = resolve_certified_production_binding(
        server_config=server, mnemo_config=config, root=root, environment={}
    )
    _, second = resolve_certified_production_binding(
        server_config=server.model_copy(update={"api_key": "rotated-synthetic-key"}),
        mnemo_config=config,
        root=root,
        environment={},
    )
    assert first.configuration_digest == second.configuration_digest
    assert first.binding_id != second.binding_id


def test_mismatched_signed_observations_do_not_converge(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    _, first = resolve_certified_production_binding(
        server_config=server, mnemo_config=config, root=root, environment={}
    )
    _, second = resolve_certified_production_binding(
        server_config=server.model_copy(update={"api_key": "rotated-synthetic-key"}),
        mnemo_config=config,
        root=root,
        environment={},
    )
    for transport in ("http", "mcp_stdio", "mcp_sse"):
        record_certified_transport_startup(
            binding=first, transport=transport, server_config=server, root=root
        )
    record_certified_transport_startup(
        binding=second, transport="external_tunnel", server_config=server, root=root
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        collect_certified_convergence(
            server_config=server, expected_binding_id=first.binding_id, root=root
        )


def test_missing_manifest_does_not_block_unrelated_synthetic_development(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, config = canonical
    (root / "config/production/full_multilingual_v2.production.json").unlink()
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.repository_root", lambda: root
    )
    reject_uncertified_corpus_startup(mnemo_config=config, server_config=ServerConfig())


def test_malformed_authority_has_safe_diagnostic(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    (root / "config/production/full_multilingual_v2.production.json").write_text(
        "[malformed", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


def test_missing_certified_database_fails_before_any_sqlite_connection(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    (root / "governed/mnemo.db").unlink()
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )
    assert not (root / "governed/mnemo.db-wal").exists()


def test_manifest_wrong_db_binding_is_rejected(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    target = root / "config/production/full_multilingual_v2.production.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["corpus"]["database_path"] = "governed/historical.db"
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


def test_disabled_vector_backend_cannot_be_activated_by_core_config(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, _ = canonical
    core = root / "mnemo.toml"
    core.write_text(
        core.read_text(encoding="utf-8").replace(
            "[storage.qdrant]\nenabled = false", "[storage.qdrant]\nenabled = true"
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(server_config=server, root=root, environment={})


def test_invalid_transport_cannot_write_observation(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    _, binding = resolve_certified_production_binding(
        server_config=server, mnemo_config=config, root=root, environment={}
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        record_certified_transport_startup(
            binding=binding, transport="historical", server_config=server, root=root
        )
    assert not (root / "scratch/phase8_8_1_runtime_convergence").exists()


def test_signed_activation_cannot_bind_wrong_corpus(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    target = root / "operational/activation.json"
    state = json.loads(target.read_text(encoding="utf-8"))
    state["activation_evidence"]["production_store_identity"] = "historical"
    state.pop("signature")
    state["signature"] = hmac.new(
        _signing_key(server),
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    target.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


def test_signed_rollback_state_cannot_serve_active_bge_profile(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    target = root / "operational/activation.json"
    state = json.loads(target.read_text(encoding="utf-8"))
    state["desired_mode"] = "PASS_THROUGH"
    state["activation_evidence"] = None
    state.pop("signature")
    state["signature"] = hmac.new(
        _signing_key(server),
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    target.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


def test_authority_must_be_json_object(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    (root / "config/production/full_multilingual_v2.production.json").write_text(
        "[]", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=server, mnemo_config=config, root=root, environment={}
        )


def test_generic_engine_may_not_open_certified_database(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, config = canonical
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.repository_root", lambda: root
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        reject_uncertified_corpus_startup(mnemo_config=config, server_config=ServerConfig())


def test_invalid_corpus_manifest_rejected_before_generic_engine(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, config = canonical
    manifest = root / "config/production/full_multilingual_v2.production.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["corpus"] = None
    manifest.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.repository_root", lambda: root
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        reject_uncertified_corpus_startup(mnemo_config=config, server_config=ServerConfig())


def test_signed_observation_with_wrong_schema_is_rejected(
    canonical: tuple[Path, ServerConfig, MnemoConfig],
) -> None:
    root, server, config = canonical
    _, binding = resolve_certified_production_binding(
        server_config=server, mnemo_config=config, root=root, environment={}
    )
    for transport in ("http", "mcp_stdio", "mcp_sse", "external_tunnel"):
        record_certified_transport_startup(
            binding=binding, transport=transport, server_config=server, root=root
        )
    target = root / "scratch/phase8_8_1_runtime_convergence/mcp_sse.json"
    record = json.loads(target.read_text(encoding="utf-8"))
    record["schema_version"] = "invalid-observation"
    record.pop("signature")
    record["signature"] = hmac.new(
        server.delivery_cursor_secret.encode("utf-8"),
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    target.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        collect_certified_convergence(
            server_config=server, expected_binding_id=binding.binding_id, root=root
        )


def test_observation_directory_cannot_alias_certified_storage(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, server, config = canonical
    _, binding = resolve_certified_production_binding(
        server_config=server, mnemo_config=config, root=root, environment={}
    )
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.OBSERVATION_DIR",
        Path("governed"),
    )
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        record_certified_transport_startup(
            binding=binding, transport="http", server_config=server, root=root
        )
    assert not (root / "governed/http.json").exists()
