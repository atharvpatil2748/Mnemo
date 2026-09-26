"""CI-safe tests for ADR-0077 production storage-role composition."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mnemo import MnemoConfig
from mnemo.engine import KnowledgeEngine
from mnemo_server.config import ServerConfig
from mnemo_server.services.mutable_workspace import StorageRole, WorkspaceMode
from mnemo_server.services.production_storage_composition import (
    build_protected_storage_inventory,
    preflight_production_storage,
)


def _config(tmp_path: Path) -> MnemoConfig:
    config_path = tmp_path / "application" / "mnemo.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        """
[storage.filesystem]
enabled = true
root = "governed/blobs"

[storage.sqlite]
enabled = true
path = "governed/corpus.db"

[storage.qdrant]
enabled = false

[storage.surrealdb]
enabled = false

[plugins]
directory = "plugins"

[llm.planner]
provider = "ollama"
model = "planner"
[llm.synthesizer]
provider = "ollama"
model = "synthesizer"
[llm.extractor]
provider = "ollama"
model = "extractor"
[llm.classifier]
provider = "ollama"
model = "classifier"
[embedding]
provider = "ollama"
model = "embedder"
dimensions = 8
[reranker]
provider = "v2-owned-pass-through"
model = "none"
""",
        encoding="utf-8",
    )
    return MnemoConfig.from_file(config_path)


def test_missing_workspace_composes_certified_read_only_without_writes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    application = tmp_path / "application"

    composition = preflight_production_storage(
        application_root=application,
        mnemo_config=config,
        server_config=ServerConfig(),
    )

    assert composition.decision.mode is WorkspaceMode.READ_ONLY
    assert composition.certified_read_only is True
    assert composition.engine_config is config
    assert composition.embedding_cache_path is None
    assert not (application / "governed").exists()


def test_injected_runtime_must_match_store_and_model_profile(tmp_path: Path) -> None:
    config = _config(tmp_path)
    composition = preflight_production_storage(
        application_root=tmp_path / "application",
        mnemo_config=config,
        server_config=ServerConfig(),
    )
    engine = MagicMock(spec=KnowledgeEngine)
    engine.certified_read_only = True
    engine.config = config
    composition.validate_injected_engine(engine)

    engine.config = config.model_copy(
        update={
            "storage": config.storage.model_copy(
                update={
                    "sqlite": config.storage.sqlite.model_copy(
                        update={"path": tmp_path / "historical-v1.db"}
                    )
                }
            )
        }
    )
    with pytest.raises(RuntimeError, match="INJECTED_PRODUCTION_RUNTIME_MISMATCH"):
        composition.validate_injected_engine(engine)
    engine.config = config.model_copy(
        update={"embedding": config.embedding.model_copy(update={"model": "historical-v1"})}
    )
    with pytest.raises(RuntimeError, match="INJECTED_PRODUCTION_RUNTIME_MISMATCH"):
        composition.validate_injected_engine(engine)
    assert not (tmp_path / "historical-v1.db").exists()


def test_valid_workspace_gets_disjoint_database_blobs_and_cache(tmp_path: Path) -> None:
    config = _config(tmp_path)
    application = tmp_path / "application"
    workspace = tmp_path / "operator-workspace"

    composition = preflight_production_storage(
        application_root=application,
        mnemo_config=config,
        server_config=ServerConfig(mutable_workspace_root=workspace),
    )

    assert composition.decision.mode is WorkspaceMode.MUTABLE
    assert composition.engine_config.storage.sqlite.path == workspace / "workspace.db"
    assert composition.engine_config.storage.filesystem.root == workspace / "blobs"
    assert composition.embedding_cache_path == workspace / "caches" / "embedding-cache.db"
    assert composition.certified_config.storage.sqlite.path == application / "governed/corpus.db"
    assert not workspace.exists()

    materialized = composition.materialize()
    assert materialized.decision.mutable
    assert workspace.is_dir()
    assert not materialized.engine_config.storage.sqlite.path.exists()


def test_inventory_has_all_non_workspace_roles(tmp_path: Path) -> None:
    config = _config(tmp_path)
    application = tmp_path / "application"
    workspace = tmp_path / "operator-workspace"
    server = ServerConfig(
        mutable_workspace_root=workspace,
        final_qa_operational_store_path=application / "operations/finalqa.db",
        full_multilingual_v2_model_cache=application / "models",
    )

    composition = preflight_production_storage(
        application_root=application,
        mnemo_config=config,
        server_config=server,
    )
    roles = {location.role for location in composition.inventory.locations}

    assert roles == {
        StorageRole.CERTIFIED_CORPUS,
        StorageRole.EVALUATION_ARTIFACT,
        StorageRole.GOVERNED_OPERATIONAL,
        StorageRole.USER_CACHE,
    }
    assert StorageRole.MUTABLE_WORKSPACE not in roles


def test_workspace_cannot_contain_certified_database(tmp_path: Path) -> None:
    config = _config(tmp_path)
    application = tmp_path / "application"

    composition = preflight_production_storage(
        application_root=application,
        mnemo_config=config,
        server_config=ServerConfig(mutable_workspace_root=application),
    )

    assert composition.decision.mode is WorkspaceMode.READ_ONLY
    assert "OVERLAPS" in composition.decision.reason
    assert not (application / "governed").exists()


def test_every_server_owned_protected_location_rejects_workspace_equality(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    application = tmp_path / "application"
    server = ServerConfig(
        final_qa_operational_store_path=application / "operations/finalqa.db",
        full_multilingual_v2_model_cache=application / "models",
    )
    inventory = build_protected_storage_inventory(
        application_root=application,
        mnemo_config=config,
        server_config=server,
    )

    for location in inventory.locations:
        composition = preflight_production_storage(
            application_root=application,
            mnemo_config=config,
            server_config=server.model_copy(update={"mutable_workspace_root": location.path}),
        )
        assert composition.decision.mode is WorkspaceMode.READ_ONLY, location.label
        assert "OVERLAPS" in composition.decision.reason, location.label

    assert not (application / "governed").exists()
    assert not (application / "operations").exists()
    assert not (application / "models").exists()
