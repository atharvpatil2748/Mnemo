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
    collection_name: NonEmptyString = "mnemo_chunks"
    on_disk: StrictBool = False


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
    api_base: str | None = None


class RerankerConfig(_FrozenConfigModel):
    """Configuration for the reranking provider family."""

    provider: NonEmptyString
    model: NonEmptyString


class DerivedModelProfileConfig(_FrozenConfigModel):
    """One additive provider/model profile selected by evaluation."""

    enabled: StrictBool = True
    provider: NonEmptyString | None = None
    model: NonEmptyString | None = None
    revision: NonEmptyString | None = None
    dimensions: PositiveInteger | None = None

    @model_validator(mode="after")
    def _enabled_profile_has_identity(self) -> DerivedModelProfileConfig:
        if self.enabled and (self.provider is None or self.model is None or self.revision is None):
            raise ValueError("enabled model profile requires provider, model, and revision")
        return self


class ModelsConfig(_FrozenConfigModel):
    """Production model profiles for vision, multilingual, and visual vector capabilities."""

    vision: DerivedModelProfileConfig = Field(
        default_factory=lambda: DerivedModelProfileConfig(
            provider="ollama",
            model="qwen2.5vl:latest",
            revision="5ced39dfa4ba",
        )
    )
    multilingual_embedding: DerivedModelProfileConfig = Field(
        default_factory=lambda: DerivedModelProfileConfig(
            provider="sentence-transformers",
            model="BAAI/bge-m3",
            revision="5617a9f61b028005a4858fdac845db406aefb181",
            dimensions=1024,
        )
    )
    multilingual_reranker: DerivedModelProfileConfig = Field(
        default_factory=lambda: DerivedModelProfileConfig(
            provider="sentence-transformers",
            model="BAAI/bge-reranker-v2-m3",
            revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        )
    )
    visual_embedding: DerivedModelProfileConfig = Field(
        default_factory=lambda: DerivedModelProfileConfig(
            provider="transformers",
            model="openai/clip-vit-large-patch14",
            revision="32bd64288804d66eefd0ccbe215aa642df71cc41",
            dimensions=768,
        )
    )

    @classmethod
    def from_file(cls, path: str | Path) -> ModelsConfig:
        """Load the model-profile document directly."""
        config_path = Path(path).expanduser().resolve(strict=False)
        if config_path.suffix.lower() != ".toml":
            raise ValueError("Model configuration must use TOML")
        if not config_path.is_file():
            raise FileNotFoundError(f"model configuration does not exist: {config_path}")
        with config_path.open("rb") as stream:
            values = tomllib.load(stream)
        return cls.model_validate(values)


class Phase85FeatureConfig(_FrozenConfigModel):
    """Independent Phase 8.5 feature and transport selections."""

    advanced_retrieval: StrictBool = True
    structured_retrieval: StrictBool = True
    ocr: StrictBool = True
    vision: StrictBool = True
    visual_vector: StrictBool = True
    multilingual: StrictBool = True
    multimodal: StrictBool = True
    final_qa_v2: StrictBool = True
    http: StrictBool = True
    mcp: StrictBool = True


class Phase85ProfileConfig(_FrozenConfigModel):
    """Selection and resolved metadata for the additive Phase 8.5 profile."""

    enabled: StrictBool = True
    profile_file: Path | None = None
    profile_name: NonEmptyString | None = None
    model_root: Path | None = None
    profile_version: NonEmptyString = "inline-v1"
    mode: NonEmptyString = "phase8_5"
    trust_class: NonEmptyString = "local_trusted"
    certification: NonEmptyString = "non_certified_default"
    certification_evidence: tuple[NonEmptyString, ...] = ()
    profile_fingerprint: NonEmptyString | None = None
    features: Phase85FeatureConfig = Field(default_factory=Phase85FeatureConfig)

    @field_validator("profile_file", "model_root", mode="before")
    @classmethod
    def _resolve_optional_path(cls, value: Path | str | None, info: ValidationInfo) -> Path | None:
        return None if value is None else _resolve_path(value, info)

    @model_validator(mode="after")
    def _selection_is_complete(self) -> Phase85ProfileConfig:
        if (self.profile_file is None) != (self.profile_name is None):
            raise ValueError("profile_file and profile_name must be configured together")
        if self.mode in {"v1_only", "disabled"} and self.enabled:
            raise ValueError("V1-only/disabled profile must disable Phase 8.5")
        return self


# Backwards-compatibility alias
Phase85ModelConfig = ModelsConfig


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
    "MNEMO_STORAGE_QDRANT_COLLECTION": (("storage", "qdrant", "collection_name"), "string"),
    "MNEMO_STORAGE_QDRANT_ON_DISK": (("storage", "qdrant", "on_disk"), "bool"),
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
    "MNEMO_MODELS_VISION_PROVIDER": (("models", "vision", "provider"), "string"),
    "MNEMO_MODELS_VISION_ENABLED": (("models", "vision", "enabled"), "bool"),
    "MNEMO_MODELS_VISION_MODEL": (("models", "vision", "model"), "string"),
    "MNEMO_MODELS_VISION_REVISION": (("models", "vision", "revision"), "optional"),
    "MNEMO_MODELS_MULTILINGUAL_EMBEDDING_PROVIDER": (
        ("models", "multilingual_embedding", "provider"),
        "string",
    ),
    "MNEMO_MODELS_MULTILINGUAL_EMBEDDING_ENABLED": (
        ("models", "multilingual_embedding", "enabled"),
        "bool",
    ),
    "MNEMO_MODELS_MULTILINGUAL_EMBEDDING_MODEL": (
        ("models", "multilingual_embedding", "model"),
        "string",
    ),
    "MNEMO_MODELS_MULTILINGUAL_EMBEDDING_REVISION": (
        ("models", "multilingual_embedding", "revision"),
        "optional",
    ),
    "MNEMO_MODELS_MULTILINGUAL_EMBEDDING_DIMENSIONS": (
        ("models", "multilingual_embedding", "dimensions"),
        "int",
    ),
    "MNEMO_MODELS_MULTILINGUAL_RERANKER_PROVIDER": (
        ("models", "multilingual_reranker", "provider"),
        "string",
    ),
    "MNEMO_MODELS_MULTILINGUAL_RERANKER_ENABLED": (
        ("models", "multilingual_reranker", "enabled"),
        "bool",
    ),
    "MNEMO_MODELS_MULTILINGUAL_RERANKER_MODEL": (
        ("models", "multilingual_reranker", "model"),
        "string",
    ),
    "MNEMO_MODELS_MULTILINGUAL_RERANKER_REVISION": (
        ("models", "multilingual_reranker", "revision"),
        "optional",
    ),
    "MNEMO_MODELS_VISUAL_EMBEDDING_PROVIDER": (
        ("models", "visual_embedding", "provider"),
        "string",
    ),
    "MNEMO_MODELS_VISUAL_EMBEDDING_ENABLED": (
        ("models", "visual_embedding", "enabled"),
        "bool",
    ),
    "MNEMO_MODELS_VISUAL_EMBEDDING_MODEL": (
        ("models", "visual_embedding", "model"),
        "string",
    ),
    "MNEMO_MODELS_VISUAL_EMBEDDING_REVISION": (
        ("models", "visual_embedding", "revision"),
        "optional",
    ),
    "MNEMO_MODELS_VISUAL_EMBEDDING_DIMENSIONS": (
        ("models", "visual_embedding", "dimensions"),
        "int",
    ),
    "MNEMO_PHASE85_ENABLED": (("phase85", "enabled"), "bool"),
    "MNEMO_PHASE85_PROFILE_FILE": (("phase85", "profile_file"), "string"),
    "MNEMO_PHASE85_PROFILE_NAME": (("phase85", "profile_name"), "string"),
    "MNEMO_PHASE85_MODEL_ROOT": (("phase85", "model_root"), "optional"),
    "MNEMO_PHASE85_ADVANCED_RETRIEVAL_ENABLED": (
        ("phase85", "features", "advanced_retrieval"),
        "bool",
    ),
    "MNEMO_PHASE85_STRUCTURED_RETRIEVAL_ENABLED": (
        ("phase85", "features", "structured_retrieval"),
        "bool",
    ),
    "MNEMO_PHASE85_OCR_ENABLED": (("phase85", "features", "ocr"), "bool"),
    "MNEMO_PHASE85_VISION_ENABLED": (("phase85", "features", "vision"), "bool"),
    "MNEMO_PHASE85_VISUAL_VECTOR_ENABLED": (
        ("phase85", "features", "visual_vector"),
        "bool",
    ),
    "MNEMO_PHASE85_MULTILINGUAL_ENABLED": (
        ("phase85", "features", "multilingual"),
        "bool",
    ),
    "MNEMO_PHASE85_MULTIMODAL_ENABLED": (
        ("phase85", "features", "multimodal"),
        "bool",
    ),
    "MNEMO_PHASE85_FINAL_QA_V2_ENABLED": (
        ("phase85", "features", "final_qa_v2"),
        "bool",
    ),
    "MNEMO_PHASE85_HTTP_ENABLED": (("phase85", "features", "http"), "bool"),
    "MNEMO_PHASE85_MCP_ENABLED": (("phase85", "features", "mcp"), "bool"),
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


def _profile_document_values(
    values: Mapping[str, object],
    environment: Mapping[str, object],
    *,
    base_directory: Path,
) -> dict[str, object]:
    """Resolve the selected profile below inline/env precedence."""
    phase_selection: dict[str, object] = {}
    inline_phase = values.get("phase85")
    if isinstance(inline_phase, Mapping):
        _merge_nested(phase_selection, cast(Mapping[str, object], inline_phase))
    environment_phase = environment.get("phase85")
    if isinstance(environment_phase, Mapping):
        _merge_nested(phase_selection, cast(Mapping[str, object], environment_phase))
    profile_file = phase_selection.get("profile_file")
    profile_name = phase_selection.get("profile_name")
    if profile_file is None and profile_name is None:
        return {}
    if not isinstance(profile_file, (str, Path)) or not isinstance(profile_name, str):
        raise ValueError("profile_file and profile_name must be configured together")
    path = Path(profile_file).expanduser()
    if not path.is_absolute():
        path = base_directory / path
    from mnemo.phase85.profiles import ModelProfileDocument, ModelProfileMode, profile_snapshot

    document = ModelProfileDocument.from_file(path)
    definition = document.select(profile_name)
    snapshot = profile_snapshot(definition, schema_version=document.schema_version)
    disabled = {"enabled": False, "provider": None, "model": None}
    models: dict[str, object] = {
        name: dict(disabled)
        for name in (
            "vision",
            "multilingual_embedding",
            "multilingual_reranker",
            "visual_embedding",
        )
    }
    for name, component in snapshot.components.items():
        models[name] = {
            "enabled": True,
            "provider": component.provider,
            "model": component.model,
            "revision": component.revision,
            "dimensions": component.dimensions,
        }
    return {
        "models": models,
        "phase85": {
            "enabled": snapshot.enabled,
            "profile_file": str(path),
            "profile_name": snapshot.profile_id,
            "profile_version": snapshot.version,
            "mode": snapshot.mode.value,
            "trust_class": snapshot.trust_class.value,
            "certification": snapshot.certification.value,
            "certification_evidence": snapshot.certification_evidence,
            "profile_fingerprint": snapshot.fingerprint,
            "features": {
                "advanced_retrieval": snapshot.mode is ModelProfileMode.PHASE85,
                "structured_retrieval": snapshot.mode is ModelProfileMode.PHASE85,
                "ocr": snapshot.mode is ModelProfileMode.PHASE85,
                "vision": snapshot.mode is ModelProfileMode.PHASE85,
                "visual_vector": snapshot.mode is ModelProfileMode.PHASE85,
                "multilingual": snapshot.mode is ModelProfileMode.PHASE85,
                "multimodal": snapshot.mode is ModelProfileMode.PHASE85,
                "final_qa_v2": snapshot.mode is ModelProfileMode.PHASE85,
                "http": snapshot.mode is ModelProfileMode.PHASE85,
                "mcp": snapshot.mode is ModelProfileMode.PHASE85,
            },
        },
    }


class MnemoConfig(BaseModel):
    """The complete immutable runtime configuration snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: LLMConfig
    embedding: EmbeddingConfig
    reranker: RerankerConfig
    plugins: PluginConfig = Field(default_factory=PluginConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    phase85: Phase85ProfileConfig = Field(default_factory=Phase85ProfileConfig)

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
        inline_values = cast(dict[str, object], parsed)
        environment = _environment_overrides(os.environ)
        values = _profile_document_values(
            inline_values,
            environment,
            base_directory=config_path.parent,
        )
        _merge_nested(values, inline_values)
        _apply_path_defaults(values)
        _merge_nested(values, environment)
        return cls.model_validate(
            values,
            context={_PATH_CONTEXT_KEY: config_path.parent},
        )

    @classmethod
    def from_env(cls) -> MnemoConfig:
        """Load recognized environment values over V1 defaults and validate."""
        environment = _environment_overrides(os.environ)
        values = _profile_document_values(
            {},
            environment,
            base_directory=Path.cwd(),
        )
        _apply_path_defaults(values)
        _merge_nested(values, environment)
        return cls.model_validate(
            values,
            context={_PATH_CONTEXT_KEY: Path.cwd()},
        )
