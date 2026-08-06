"""Immutable, validated configuration for Mnemo core."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, ClassVar, Final, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, strict=True),
]
PositiveInteger = Annotated[int, Field(strict=True, gt=0)]

_INTEGER_PATTERN: Final = re.compile(r"[+-]?[0-9]+")
_PATH_CONTEXT_KEY: Final = "base_directory"


class _FrozenConfigModel(BaseModel):
    """Shared strictness and immutability rules for nested configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)


def _base_directory(info: ValidationInfo) -> Path:
    """Return the loader-provided path base or the current working directory."""
    context = info.context
    if isinstance(context, Mapping):
        candidate = context.get(_PATH_CONTEXT_KEY)
        if isinstance(candidate, Path):
            return candidate
    return Path.cwd()


def _resolve_path(value: Path | str, info: ValidationInfo) -> Path:
    """Expand and resolve one configured path against its configuration base."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = _base_directory(info) / path
    return path.resolve(strict=False)


def _prepare_directory(value: Path | str, info: ValidationInfo) -> Path:
    """Normalize, create, and verify a configured writable directory."""
    path = _resolve_path(value, info)
    if path.exists() and not path.is_dir():
        raise ValueError(f"configured directory is not a directory: {path}")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"could not create directory {path}: {error}") from error
    if not path.is_dir():
        raise ValueError(f"configured directory is not a directory: {path}")
    if not os.access(path, os.W_OK):
        raise ValueError(f"configured directory is not writable: {path}")
    return path


def _prepare_file_path(value: Path | str, info: ValidationInfo) -> Path:
    """Normalize a file path and prepare its writable parent directory."""
    path = _resolve_path(value, info)
    if path.exists() and path.is_dir():
        raise ValueError(f"configured file path is a directory: {path}")
    _prepare_directory(path.parent, info)
    if path.exists() and not os.access(path, os.W_OK):
        raise ValueError(f"configured file is not writable: {path}")
    return path


class FilesystemStorageConfig(_FrozenConfigModel):
    """Configuration for the content-addressable filesystem blob store."""

    enabled: StrictBool = True
    root: Path = Path("./data/files")

    @field_validator("root", mode="before")
    @classmethod
    def _validate_root(cls, value: Path | str, info: ValidationInfo) -> Path:
        return _prepare_directory(value, info)


class SQLiteStorageConfig(_FrozenConfigModel):
    """Configuration for the local SQLite metadata and keyword store."""

    enabled: StrictBool = True
    path: Path = Path("./data/mnemo.db")

    @field_validator("path", mode="before")
    @classmethod
    def _validate_path(cls, value: Path | str, info: ValidationInfo) -> Path:
        return _prepare_file_path(value, info)


class QdrantStorageConfig(_FrozenConfigModel):
    """Configuration for the Qdrant vector backend."""

    enabled: StrictBool = True
    url: HttpUrl = HttpUrl("http://localhost:6333")
    api_key: NonEmptyString | None = None


class SurrealDBStorageConfig(_FrozenConfigModel):
    """Configuration for the SurrealDB metadata and graph backend."""

    enabled: StrictBool = True
    url: HttpUrl = HttpUrl("http://localhost:8000")
    username: NonEmptyString = "root"
    password: NonEmptyString = "root"
    namespace: NonEmptyString = "mnemo"
    database: NonEmptyString = "knowledge"


class StorageConfig(_FrozenConfigModel):
    """Configuration for every backend behind composite storage."""

    filesystem: FilesystemStorageConfig = Field(default_factory=FilesystemStorageConfig)
    sqlite: SQLiteStorageConfig = Field(default_factory=SQLiteStorageConfig)
    qdrant: QdrantStorageConfig = Field(default_factory=QdrantStorageConfig)
    surrealdb: SurrealDBStorageConfig = Field(default_factory=SurrealDBStorageConfig)


class LLMRoleConfig(_FrozenConfigModel):
    """Provider, model, and context limit for one language-model role."""

    provider: NonEmptyString
    model: NonEmptyString
    max_context_tokens: PositiveInteger


class LLMConfig(_FrozenConfigModel):
    """Mandatory language-model roles used by Mnemo core."""

    planner: LLMRoleConfig
    synthesizer: LLMRoleConfig
    extractor: LLMRoleConfig
    classifier: LLMRoleConfig

    _CONTEXT_DEFAULTS: ClassVar[dict[str, int]] = {
        "planner": 8192,
        "synthesizer": 16384,
        "extractor": 8192,
        "classifier": 4096,
    }

    @model_validator(mode="before")
    @classmethod
    def _apply_context_defaults(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        resolved: dict[object, object] = dict(value)
        for role, default in cls._CONTEXT_DEFAULTS.items():
            role_value = resolved.get(role)
            if isinstance(role_value, Mapping):
                role_fields: dict[object, object] = dict(role_value)
                role_fields.setdefault("max_context_tokens", default)
                resolved[role] = role_fields
        return resolved


class EmbeddingConfig(_FrozenConfigModel):
    """Configuration for the embedding provider family."""

    provider: NonEmptyString
    model: NonEmptyString
    dimensions: PositiveInteger


class RerankerConfig(_FrozenConfigModel):
    """Configuration for the reranking provider family."""

    provider: NonEmptyString
    model: NonEmptyString


class PluginConfig(_FrozenConfigModel):
    """Configuration for local plugin discovery."""

    directory: Path = Path("./plugins")

    @field_validator("directory", mode="before")
    @classmethod
    def _validate_directory(cls, value: Path | str, info: ValidationInfo) -> Path:
        return _prepare_directory(value, info)


_EnvironmentPath = tuple[str, ...]
_ENVIRONMENT_FIELDS: Final[dict[str, tuple[_EnvironmentPath, str]]] = {
    "MNEMO_STORAGE_FILESYSTEM_ENABLED": (("storage", "filesystem", "enabled"), "bool"),
    "MNEMO_STORAGE_FILESYSTEM_ROOT": (("storage", "filesystem", "root"), "string"),
    "MNEMO_STORAGE_SQLITE_ENABLED": (("storage", "sqlite", "enabled"), "bool"),
    "MNEMO_STORAGE_SQLITE_PATH": (("storage", "sqlite", "path"), "string"),
    "MNEMO_STORAGE_QDRANT_ENABLED": (("storage", "qdrant", "enabled"), "bool"),
    "MNEMO_STORAGE_QDRANT_URL": (("storage", "qdrant", "url"), "string"),
    "MNEMO_STORAGE_QDRANT_API_KEY": (("storage", "qdrant", "api_key"), "optional"),
    "MNEMO_STORAGE_SURREALDB_ENABLED": (("storage", "surrealdb", "enabled"), "bool"),
    "MNEMO_STORAGE_SURREALDB_URL": (("storage", "surrealdb", "url"), "string"),
    "MNEMO_STORAGE_SURREALDB_USERNAME": (("storage", "surrealdb", "username"), "string"),
    "MNEMO_STORAGE_SURREALDB_PASSWORD": (("storage", "surrealdb", "password"), "string"),
    "MNEMO_STORAGE_SURREALDB_NAMESPACE": (("storage", "surrealdb", "namespace"), "string"),
    "MNEMO_STORAGE_SURREALDB_DATABASE": (("storage", "surrealdb", "database"), "string"),
    "MNEMO_LLM_PLANNER_PROVIDER": (("llm", "planner", "provider"), "string"),
    "MNEMO_LLM_PLANNER_MODEL": (("llm", "planner", "model"), "string"),
    "MNEMO_LLM_PLANNER_MAX_CONTEXT_TOKENS": (("llm", "planner", "max_context_tokens"), "int"),
    "MNEMO_LLM_SYNTHESIZER_PROVIDER": (("llm", "synthesizer", "provider"), "string"),
    "MNEMO_LLM_SYNTHESIZER_MODEL": (("llm", "synthesizer", "model"), "string"),
    "MNEMO_LLM_SYNTHESIZER_MAX_CONTEXT_TOKENS": (
        ("llm", "synthesizer", "max_context_tokens"),
        "int",
    ),
    "MNEMO_LLM_EXTRACTOR_PROVIDER": (("llm", "extractor", "provider"), "string"),
    "MNEMO_LLM_EXTRACTOR_MODEL": (("llm", "extractor", "model"), "string"),
    "MNEMO_LLM_EXTRACTOR_MAX_CONTEXT_TOKENS": (("llm", "extractor", "max_context_tokens"), "int"),
    "MNEMO_LLM_CLASSIFIER_PROVIDER": (("llm", "classifier", "provider"), "string"),
    "MNEMO_LLM_CLASSIFIER_MODEL": (("llm", "classifier", "model"), "string"),
    "MNEMO_LLM_CLASSIFIER_MAX_CONTEXT_TOKENS": (("llm", "classifier", "max_context_tokens"), "int"),
    "MNEMO_EMBEDDING_PROVIDER": (("embedding", "provider"), "string"),
    "MNEMO_EMBEDDING_MODEL": (("embedding", "model"), "string"),
    "MNEMO_EMBEDDING_DIMENSIONS": (("embedding", "dimensions"), "int"),
    "MNEMO_RERANKER_PROVIDER": (("reranker", "provider"), "string"),
    "MNEMO_RERANKER_MODEL": (("reranker", "model"), "string"),
    "MNEMO_PLUGINS_DIRECTORY": (("plugins", "directory"), "string"),
}


def _parse_environment_value(name: str, value: str, kind: str) -> object:
    """Parse a recognized environment scalar without permissive coercion."""
    if kind == "bool":
        normalized = value.casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise ValueError(f"{name} must be 'true' or 'false'")
    if kind == "int":
        if _INTEGER_PATTERN.fullmatch(value) is None:
            raise ValueError(f"{name} must be a base-10 integer")
        return int(value, 10)
    if kind == "optional" and value == "":
        return None
    return value


def _set_nested(target: dict[str, object], path: _EnvironmentPath, value: object) -> None:
    """Set a leaf in a nested string-keyed configuration mapping."""
    current = target
    for segment in path[:-1]:
        existing = current.get(segment)
        if existing is None:
            child: dict[str, object] = {}
            current[segment] = child
            current = child
            continue
        if not isinstance(existing, dict):
            raise ValueError(f"cannot override non-table configuration field {segment}")
        current = cast(dict[str, object], existing)
    current[path[-1]] = value


def _set_nested_default(target: dict[str, object], path: _EnvironmentPath, value: object) -> None:
    """Set a nested loader default without replacing configured values."""
    current = target
    for segment in path[:-1]:
        existing = current.get(segment)
        if existing is None:
            child: dict[str, object] = {}
            current[segment] = child
            current = child
            continue
        if not isinstance(existing, dict):
            return
        current = cast(dict[str, object], existing)
    current.setdefault(path[-1], value)


def _apply_path_defaults(values: dict[str, object]) -> None:
    """Materialize relative path defaults so they receive loader context."""
    _set_nested_default(values, ("storage", "filesystem", "root"), "./data/files")
    _set_nested_default(values, ("storage", "sqlite", "path"), "./data/mnemo.db")
    _set_nested_default(values, ("plugins", "directory"), "./plugins")


def _environment_overrides(environment: Mapping[str, str]) -> dict[str, object]:
    """Build nested values from the recognized V1 environment variables."""
    result: dict[str, object] = {}
    for name, (path, kind) in _ENVIRONMENT_FIELDS.items():
        if name in environment:
            _set_nested(
                result,
                path,
                _parse_environment_value(name, environment[name], kind),
            )
    if "MNEMO_PLUGINS_DIRECTORY" not in environment and "MNEMO_PLUGINS" in environment:
        _set_nested(result, ("plugins", "directory"), environment["MNEMO_PLUGINS"])
    return result


def _merge_nested(base: dict[str, object], overrides: Mapping[str, object]) -> None:
    """Merge environment leaves into a TOML-derived mapping in place."""
    for key, value in overrides.items():
        existing = base.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            _merge_nested(existing, cast(Mapping[str, object], value))
        else:
            base[key] = value


class MnemoConfig(BaseModel):
    """The complete immutable V1 runtime configuration snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: LLMConfig
    embedding: EmbeddingConfig
    reranker: RerankerConfig
    plugins: PluginConfig = Field(default_factory=PluginConfig)

    @classmethod
    def from_file(cls, path: str | Path) -> MnemoConfig:
        """Load TOML, overlay recognized environment values, and validate."""
        config_path = Path(path).expanduser().resolve(strict=False)
        if config_path.suffix.lower() != ".toml":
            raise ValueError(f"configuration file must use the .toml extension: {config_path}")
        if not config_path.is_file():
            raise FileNotFoundError(f"configuration file does not exist: {config_path}")
        try:
            with config_path.open("rb") as stream:
                parsed = tomllib.load(stream)
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"invalid TOML configuration {config_path}: {error}") from error
        values = cast(dict[str, object], parsed)
        _apply_path_defaults(values)
        _merge_nested(values, _environment_overrides(os.environ))
        return cls.model_validate(
            values,
            context={_PATH_CONTEXT_KEY: config_path.parent},
        )

    @classmethod
    def from_env(cls) -> MnemoConfig:
        """Load recognized environment values over V1 defaults and validate."""
        values: dict[str, object] = {}
        _apply_path_defaults(values)
        _merge_nested(values, _environment_overrides(os.environ))
        return cls.model_validate(
            values,
            context={_PATH_CONTEXT_KEY: Path.cwd()},
        )
