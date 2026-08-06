"""Unit tests for the Phase 1 Module 1.4 configuration system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mnemo import (
    EmbeddingConfig,
    FilesystemStorageConfig,
    LLMConfig,
    LLMRoleConfig,
    MnemoConfig,
    PluginConfig,
    QdrantStorageConfig,
    RerankerConfig,
    SQLiteStorageConfig,
    StorageConfig,
    SurrealDBStorageConfig,
)
from pydantic import ValidationError

_RECOGNIZED_ENVIRONMENT_NAMES = (
    "MNEMO_STORAGE_FILESYSTEM_ENABLED",
    "MNEMO_STORAGE_FILESYSTEM_ROOT",
    "MNEMO_STORAGE_SQLITE_ENABLED",
    "MNEMO_STORAGE_SQLITE_PATH",
    "MNEMO_STORAGE_QDRANT_ENABLED",
    "MNEMO_STORAGE_QDRANT_URL",
    "MNEMO_STORAGE_QDRANT_API_KEY",
    "MNEMO_STORAGE_SURREALDB_ENABLED",
    "MNEMO_STORAGE_SURREALDB_URL",
    "MNEMO_STORAGE_SURREALDB_USERNAME",
    "MNEMO_STORAGE_SURREALDB_PASSWORD",
    "MNEMO_STORAGE_SURREALDB_NAMESPACE",
    "MNEMO_STORAGE_SURREALDB_DATABASE",
    "MNEMO_LLM_PLANNER_PROVIDER",
    "MNEMO_LLM_PLANNER_MODEL",
    "MNEMO_LLM_PLANNER_MAX_CONTEXT_TOKENS",
    "MNEMO_LLM_SYNTHESIZER_PROVIDER",
    "MNEMO_LLM_SYNTHESIZER_MODEL",
    "MNEMO_LLM_SYNTHESIZER_MAX_CONTEXT_TOKENS",
    "MNEMO_LLM_EXTRACTOR_PROVIDER",
    "MNEMO_LLM_EXTRACTOR_MODEL",
    "MNEMO_LLM_EXTRACTOR_MAX_CONTEXT_TOKENS",
    "MNEMO_LLM_CLASSIFIER_PROVIDER",
    "MNEMO_LLM_CLASSIFIER_MODEL",
    "MNEMO_LLM_CLASSIFIER_MAX_CONTEXT_TOKENS",
    "MNEMO_EMBEDDING_PROVIDER",
    "MNEMO_EMBEDDING_MODEL",
    "MNEMO_EMBEDDING_DIMENSIONS",
    "MNEMO_RERANKER_PROVIDER",
    "MNEMO_RERANKER_MODEL",
    "MNEMO_PLUGINS_DIRECTORY",
    "MNEMO_PLUGINS",
)


@pytest.fixture(autouse=True)
def clear_mnemo_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep configuration tests independent of the developer environment."""
    for name in _RECOGNIZED_ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)


def _toml(*, extra: str = "") -> str:
    """Return the smallest valid V1 configuration file."""
    return f"""
[llm.planner]
provider = "ollama"
model = "planner-model"

[llm.synthesizer]
provider = "ollama"
model = "synthesizer-model"

[llm.extractor]
provider = "ollama"
model = "extractor-model"

[llm.classifier]
provider = "ollama"
model = "classifier-model"

[embedding]
provider = "ollama"
model = "embedding-model"
dimensions = 768

[reranker]
provider = "local"
model = "reranker-model"
{extra}
"""


def _write_config(directory: Path, content: str | None = None) -> Path:
    """Write one test TOML configuration and return its path."""
    path = directory / "mnemo.toml"
    path.write_text(_toml() if content is None else content, encoding="utf-8")
    return path


def _set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set every required provider value for environment-only loading."""
    for role in ("PLANNER", "SYNTHESIZER", "EXTRACTOR", "CLASSIFIER"):
        monkeypatch.setenv(f"MNEMO_LLM_{role}_PROVIDER", "ollama")
        monkeypatch.setenv(f"MNEMO_LLM_{role}_MODEL", role.casefold())
    monkeypatch.setenv("MNEMO_EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("MNEMO_EMBEDDING_MODEL", "nomic-embed")
    monkeypatch.setenv("MNEMO_EMBEDDING_DIMENSIONS", "768")
    monkeypatch.setenv("MNEMO_RERANKER_PROVIDER", "local")
    monkeypatch.setenv("MNEMO_RERANKER_MODEL", "cross-encoder")


def test_file_loading_applies_defaults_and_resolves_paths(tmp_path: Path) -> None:
    """Defaults are validated and relative paths use the TOML directory."""
    config = MnemoConfig.from_file(_write_config(tmp_path))

    assert config.storage.filesystem.enabled is True
    assert config.storage.filesystem.root == tmp_path / "data" / "files"
    assert config.storage.sqlite.enabled is True
    assert config.storage.sqlite.path == tmp_path / "data" / "mnemo.db"
    assert config.storage.qdrant == QdrantStorageConfig()
    assert config.storage.surrealdb == SurrealDBStorageConfig()
    assert config.plugins == PluginConfig(directory=tmp_path / "plugins")
    assert config.llm.planner.max_context_tokens == 8192
    assert config.llm.synthesizer.max_context_tokens == 16384
    assert config.llm.extractor.max_context_tokens == 8192
    assert config.llm.classifier.max_context_tokens == 4096
    assert (tmp_path / "data" / "files").is_dir()
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "plugins").is_dir()
    assert not (tmp_path / "data" / "mnemo.db").exists()


def test_all_approved_file_fields_are_loaded(tmp_path: Path) -> None:
    """All and only the frozen V1 fields can be supplied through TOML."""
    content = _toml(
        extra="""
[storage.filesystem]
enabled = false
root = "./blobs"

[storage.sqlite]
enabled = false
path = "./metadata/store.db"

[storage.qdrant]
enabled = false
url = "https://qdrant.example.test:7443"
api_key = "secret"

[storage.surrealdb]
enabled = false
url = "https://surreal.example.test:8443"
username = "mnemo-user"
password = "mnemo-password"
namespace = "local"
database = "documents"

[plugins]
directory = "./extensions"
"""
    )
    config = MnemoConfig.from_file(_write_config(tmp_path, content))

    assert config.storage.filesystem.enabled is False
    assert config.storage.filesystem.root == tmp_path / "blobs"
    assert config.storage.sqlite.path == tmp_path / "metadata" / "store.db"
    assert str(config.storage.qdrant.url) == "https://qdrant.example.test:7443/"
    assert config.storage.qdrant.api_key == "secret"
    assert config.storage.surrealdb.username == "mnemo-user"
    assert config.storage.surrealdb.password == "mnemo-password"
    assert config.storage.surrealdb.namespace == "local"
    assert config.storage.surrealdb.database == "documents"
    assert config.plugins.directory == tmp_path / "extensions"


def test_environment_only_loading_uses_cwd_for_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment-only defaults and overrides resolve against the cwd."""
    monkeypatch.chdir(tmp_path)
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("MNEMO_STORAGE_FILESYSTEM_ROOT", "blobs")
    monkeypatch.setenv("MNEMO_STORAGE_SQLITE_PATH", "state/mnemo.sqlite")
    monkeypatch.setenv("MNEMO_PLUGINS_DIRECTORY", "extensions")

    config = MnemoConfig.from_env()

    assert config.storage.filesystem.root == tmp_path / "blobs"
    assert config.storage.sqlite.path == tmp_path / "state" / "mnemo.sqlite"
    assert config.plugins.directory == tmp_path / "extensions"


def test_environment_overrides_toml_at_leaf_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recognized environment leaves win without replacing sibling fields."""
    monkeypatch.setenv("MNEMO_LLM_PLANNER_MODEL", "environment-planner")
    monkeypatch.setenv("MNEMO_LLM_PLANNER_MAX_CONTEXT_TOKENS", "12288")
    monkeypatch.setenv("MNEMO_STORAGE_QDRANT_ENABLED", "false")
    monkeypatch.setenv("MNEMO_STORAGE_QDRANT_API_KEY", "from-environment")
    monkeypatch.setenv("MNEMO_EMBEDDING_DIMENSIONS", "1024")

    config = MnemoConfig.from_file(_write_config(tmp_path))

    assert config.llm.planner.provider == "ollama"
    assert config.llm.planner.model == "environment-planner"
    assert config.llm.planner.max_context_tokens == 12288
    assert config.storage.qdrant.enabled is False
    assert config.storage.qdrant.api_key == "from-environment"
    assert config.embedding.dimensions == 1024


def test_canonical_plugin_environment_variable_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The canonical plugin variable takes precedence over its legacy alias."""
    monkeypatch.setenv("MNEMO_PLUGINS", "legacy")
    monkeypatch.setenv("MNEMO_PLUGINS_DIRECTORY", "canonical")

    config = MnemoConfig.from_file(_write_config(tmp_path))

    assert config.plugins.directory == tmp_path / "canonical"


def test_legacy_plugin_environment_variable_is_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deprecated Module 1.3 plugin variable remains a loading alias."""
    monkeypatch.setenv("MNEMO_PLUGINS", "legacy")

    config = MnemoConfig.from_file(_write_config(tmp_path))

    assert config.plugins.directory == tmp_path / "legacy"


def test_unknown_environment_variables_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown MNEMO_ variables do not expand the V1 public schema."""
    monkeypatch.setenv("MNEMO_SERVER_PORT", "8000")
    monkeypatch.setenv("MNEMO_UNKNOWN", "value")

    config = MnemoConfig.from_file(_write_config(tmp_path))

    assert set(type(config).model_fields) == {
        "storage",
        "llm",
        "embedding",
        "reranker",
        "plugins",
    }


@pytest.mark.parametrize("section", ["logging", "cache", "retrieval", "server", "graph"])
def test_reserved_or_unknown_toml_sections_are_rejected(tmp_path: Path, section: str) -> None:
    """Reserved namespaces remain unavailable in the V1 schema."""
    path = _write_config(tmp_path, _toml(extra=f"\n[{section}]\nenabled = true\n"))

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MnemoConfig.from_file(path)


def test_unknown_nested_toml_field_is_rejected(tmp_path: Path) -> None:
    """Typos inside an approved section fail validation."""
    path = _write_config(
        tmp_path,
        _toml(extra="\n[storage.qdrant]\ntimeout = 30\n"),
    )

    with pytest.raises(ValidationError, match="timeout"):
        MnemoConfig.from_file(path)


@pytest.mark.parametrize(
    "name,value,message",
    [
        ("MNEMO_STORAGE_QDRANT_ENABLED", "yes", "must be 'true' or 'false'"),
        ("MNEMO_EMBEDDING_DIMENSIONS", "7.5", "must be a base-10 integer"),
    ],
)
def test_malformed_environment_scalars_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    """Recognized malformed environment values are never ignored."""
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        MnemoConfig.from_file(_write_config(tmp_path))


def test_empty_environment_api_key_represents_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The optional API key accepts an explicit empty environment override."""
    monkeypatch.setenv("MNEMO_STORAGE_QDRANT_API_KEY", "")
    config = MnemoConfig.from_file(_write_config(tmp_path))
    assert config.storage.qdrant.api_key is None


@pytest.mark.parametrize(
    "content,field",
    [
        (_toml().replace('provider = "ollama"', 'provider = ""', 1), "provider"),
        (_toml().replace('model = "planner-model"', 'model = "   "'), "model"),
        (_toml().replace("dimensions = 768", "dimensions = 0"), "dimensions"),
        (_toml().replace("dimensions = 768", 'dimensions = "768"'), "dimensions"),
        (_toml(extra='\n[storage.qdrant]\nurl = "host.docker.internal:6333"\n'), "url"),
    ],
)
def test_invalid_model_values_fail(tmp_path: Path, content: str, field: str) -> None:
    """Strict field invariants reject empty, non-positive, and malformed values."""
    with pytest.raises(ValidationError, match=field):
        MnemoConfig.from_file(_write_config(tmp_path, content))


def test_missing_required_sections_and_role_fields_fail(tmp_path: Path) -> None:
    """Providers and models have no implicit defaults."""
    with pytest.raises(ValidationError) as missing_sections:
        MnemoConfig.from_file(_write_config(tmp_path, ""))
    assert {error["loc"][0] for error in missing_sections.value.errors()} == {
        "llm",
        "embedding",
        "reranker",
    }

    content = _toml().replace('model = "classifier-model"', "")
    with pytest.raises(ValidationError, match=r"llm\.classifier\.model"):
        MnemoConfig.from_file(_write_config(tmp_path, content))


@pytest.mark.parametrize(
    "filename,content,error_type",
    [
        ("mnemo.yaml", "", ValueError),
        ("missing.toml", "", FileNotFoundError),
        ("broken.toml", "[llm", ValueError),
    ],
)
def test_file_loading_failures_are_clear(
    tmp_path: Path,
    filename: str,
    content: str,
    error_type: type[Exception],
) -> None:
    """Wrong formats, missing files, and malformed TOML fail explicitly."""
    path = tmp_path / filename
    if filename != "missing.toml":
        path.write_text(content, encoding="utf-8")
    with pytest.raises(error_type, match=r"configuration|TOML"):
        MnemoConfig.from_file(path)


def test_directory_conflicts_fail_validation(tmp_path: Path) -> None:
    """A configured directory cannot point at an existing regular file."""
    conflict = tmp_path / "not-a-directory"
    conflict.write_text("content", encoding="utf-8")
    path = _write_config(
        tmp_path,
        _toml(extra=f'\n[plugins]\ndirectory = "{conflict.as_posix()}"\n'),
    )

    with pytest.raises(ValidationError, match="not a directory"):
        MnemoConfig.from_file(path)


def test_sqlite_path_cannot_be_a_directory(tmp_path: Path) -> None:
    """SQLite configuration requires a file path rather than a directory."""
    existing = tmp_path / "sqlite-directory"
    existing.mkdir()
    path = _write_config(
        tmp_path,
        _toml(extra=f'\n[storage.sqlite]\npath = "{existing.as_posix()}"\n'),
    )

    with pytest.raises(ValidationError, match="file path is a directory"):
        MnemoConfig.from_file(path)


def test_configuration_is_deeply_immutable_and_hashable(tmp_path: Path) -> None:
    """The complete runtime snapshot supports equality and cannot be mutated."""
    path = _write_config(tmp_path)
    first = MnemoConfig.from_file(path)
    second = MnemoConfig.from_file(path)

    assert first == second
    assert hash(first) == hash(second)
    with pytest.raises(ValidationError, match="frozen"):
        first.embedding = EmbeddingConfig(provider="other", model="other", dimensions=1)
    with pytest.raises(ValidationError, match="frozen"):
        first.llm.planner.model = "other"


def test_serialization_supports_python_and_json_modes(tmp_path: Path) -> None:
    """Resolved models serialize through Pydantic's standard dump APIs."""
    config = MnemoConfig.from_file(_write_config(tmp_path))

    python_dump = config.model_dump()
    json_dump = config.model_dump(mode="json")
    encoded = config.model_dump_json()

    assert isinstance(python_dump["storage"]["filesystem"]["root"], Path)
    assert json_dump["storage"]["filesystem"]["root"] == str(tmp_path / "data" / "files")
    assert json.loads(encoded) == json_dump


def test_public_nested_models_validate_independently(tmp_path: Path) -> None:
    """Every public supporting model has a usable, typed constructor."""
    role = LLMRoleConfig(provider="custom", model="model", max_context_tokens=1)
    llm = LLMConfig(
        planner=role,
        synthesizer=role,
        extractor=role,
        classifier=role,
    )
    embedding = EmbeddingConfig(provider="custom", model="embed", dimensions=1)
    reranker = RerankerConfig(provider="custom", model="rank")
    storage = StorageConfig(
        filesystem=FilesystemStorageConfig(root=tmp_path / "files"),
        sqlite=SQLiteStorageConfig(path=tmp_path / "db" / "mnemo.db"),
    )

    assert llm.planner is role
    assert embedding.dimensions == 1
    assert reranker.provider == "custom"
    assert storage.filesystem.enabled is True


def test_provider_names_are_free_form(tmp_path: Path) -> None:
    """Configuration does not own provider registration or allowlists."""
    content = _toml().replace('provider = "ollama"', 'provider = "plugin.acme"')
    config = MnemoConfig.from_file(_write_config(tmp_path, content))
    assert config.llm.planner.provider == "plugin.acme"
