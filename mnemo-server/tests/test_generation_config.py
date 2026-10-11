"""Certified config reads an active OS-backed credential generation only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mnemo_server.config import ServerConfig
from mnemo_server.services import production_credentials as credential_module
from mnemo_server.services.production_credentials import CredentialKind
from test_production_credentials import FakeSecretStore, _bound_chain, _provision, _registry


def _manifest(root: Path) -> None:
    target = root / "config/production/full_multilingual_v2.production.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "configuration_authority": {"credential_registry": "credentials.json"},
                "reranker_activation": {"active_mode": "BGE_V2_M3"},
                "final_qa_operational_store": {"path": "operational/final_qa_v2.db"},
            }
        ),
        encoding="utf-8",
    )


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: FakeSecretStore) -> None:
    _manifest(tmp_path)
    selection = tmp_path / "config/production/runtime-selection.json"
    selection.write_text(
        json.dumps(
            {
                "schema": "mnemo.production-runtime-selection/1",
                "deployment_key": "fixture",
                "state": "UNINDEXED",
            }
        ),
        encoding="utf-8",
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
    monkeypatch.setenv("MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE", str(tmp_path / "cache"))


def test_unindexed_config_rejects_even_valid_historical_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, store = _registry(tmp_path)
    record = _provision(registry)
    authority = _bound_chain(tmp_path / "chain", registry, record.generation_id)
    authority.create()
    registry.validate_with_evidence(generation_id=record.generation_id, authority=authority)
    registry.promote(generation_id=record.generation_id, authority=authority)
    _env(monkeypatch, tmp_path, store)
    assert registry.retrieve(record.generation_id, CredentialKind.API_KEY)
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        ServerConfig.from_env(certified_production=True, certified_root=tmp_path)


def test_unindexed_config_rejects_before_secret_env_fork(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, store = _registry(tmp_path)
    record = _provision(registry)
    authority = _bound_chain(tmp_path / "chain", registry, record.generation_id)
    authority.create()
    registry.validate_with_evidence(generation_id=record.generation_id, authority=authority)
    registry.promote(generation_id=record.generation_id, authority=authority)
    _env(monkeypatch, tmp_path, store)
    monkeypatch.setenv("MNEMO_SERVER_API_KEY", "conflicting-value-not-printed")
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        ServerConfig.from_env(certified_production=True, certified_root=tmp_path)


def test_unindexed_config_rejects_before_missing_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, store = _registry(tmp_path)
    _env(monkeypatch, tmp_path, store)
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        ServerConfig.from_env(certified_production=True, certified_root=tmp_path)
