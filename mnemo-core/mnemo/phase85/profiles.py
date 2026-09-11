"""Versioned Phase 8.5 model-profile documents and immutable registry snapshots."""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

_NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, strict=True)]
_Positive = Annotated[int, Field(strict=True, gt=0)]
_COMPONENT_IDS = frozenset(
    {"vision", "multilingual_embedding", "multilingual_reranker", "visual_embedding"}
)


class ModelProfileMode(StrEnum):
    """Operational effect of one selected profile document entry."""

    PHASE85 = "phase8_5"
    V1_ONLY = "v1_only"
    DISABLED = "disabled"


class ModelProfileTrustClass(StrEnum):
    """Provider trust boundary declared without credentials or machine paths."""

    LOCAL_TRUSTED = "local_trusted"
    LOCAL_SANDBOXED = "local_sandboxed"
    CLOUD = "cloud"


class ModelProfileCertification(StrEnum):
    """Governance label; selection never promotes this value implicitly."""

    NON_CERTIFIED_DEFAULT = "non_certified_default"
    CANDIDATE = "candidate"
    CERTIFIED = "certified"


class ModelProviderLanguageClaim(BaseModel):
    """Governed provider metadata; this record never grants runtime readiness."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    language: _NonEmpty
    script: _NonEmpty | None = None
    operations: tuple[_NonEmpty, ...]
    claim_source_digest: _NonEmpty

    @model_validator(mode="after")
    def _validate_claim(self) -> ModelProviderLanguageClaim:
        if not self.operations or tuple(sorted(set(self.operations))) != self.operations:
            raise ValueError("provider claim operations must be sorted, unique, and non-empty")
        if len(self.claim_source_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.claim_source_digest
        ):
            raise ValueError("provider claim source must be a lowercase SHA-256 digest")
        return self


class ModelProfileComponent(BaseModel):
    """One exact provider/model identity inside a versioned profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: _NonEmpty
    model: _NonEmpty
    revision: _NonEmpty
    license: _NonEmpty
    dimensions: _Positive | None = None
    metric: Literal["cosine", "dot", "euclidean"] | None = None
    normalization: Literal["none", "l2"] | None = None
    preprocessing: _NonEmpty
    languages: tuple[_NonEmpty, ...] = ()
    scripts: tuple[_NonEmpty, ...] = ()
    language_claims: tuple[ModelProviderLanguageClaim, ...] = ()
    modalities: tuple[_NonEmpty, ...] = ()
    max_batch: _Positive | None = None
    max_context_tokens: _Positive | None = None
    max_input_bytes: _Positive | None = None
    max_pixels: _Positive | None = None

    @model_validator(mode="after")
    def _vector_contract_is_complete(self) -> ModelProfileComponent:
        if self.dimensions is not None and (self.metric is None or self.normalization is None):
            raise ValueError("vector profile requires metric and normalization")
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("profile languages must be unique")
        if len(set(self.scripts)) != len(self.scripts):
            raise ValueError("profile scripts must be unique")
        if len(set(self.modalities)) != len(self.modalities):
            raise ValueError("profile modalities must be unique")
        claim_keys = tuple(
            (claim.language, claim.script, operation)
            for claim in self.language_claims
            for operation in claim.operations
        )
        if len(set(claim_keys)) != len(claim_keys):
            raise ValueError("provider language claims must not overlap")
        return self


class ModelProfileDefinition(BaseModel):
    """One selectable Phase 8.5 profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: _NonEmpty
    version: _NonEmpty
    mode: ModelProfileMode
    trust_class: ModelProfileTrustClass
    certification: ModelProfileCertification
    certification_evidence: tuple[_NonEmpty, ...] = ()
    capabilities: tuple[_NonEmpty, ...] = ()
    models: dict[str, ModelProfileComponent] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_definition(self) -> ModelProfileDefinition:
        unknown = set(self.models) - _COMPONENT_IDS
        if unknown:
            raise ValueError(f"unknown model profile components: {', '.join(sorted(unknown))}")
        if self.mode is ModelProfileMode.PHASE85 and not self.models:
            raise ValueError("phase8_5 profile requires at least one model component")
        if self.mode is not ModelProfileMode.PHASE85 and self.models:
            raise ValueError("V1-only/disabled profiles cannot declare Phase 8.5 models")
        if (
            self.certification is ModelProfileCertification.CERTIFIED
            and not self.certification_evidence
        ):
            raise ValueError("certified profile requires certification evidence")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("profile capabilities must be unique")
        return self


class ModelProfileDocument(BaseModel):
    """Strict tracked document containing selectable profiles."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["mnemo.model-profiles/1"]
    profiles: dict[str, ModelProfileDefinition]

    @model_validator(mode="after")
    def _keys_match_profile_ids(self) -> ModelProfileDocument:
        if not self.profiles:
            raise ValueError("model profile document must contain profiles")
        mismatches = tuple(
            key for key, profile in self.profiles.items() if key != profile.profile_id
        )
        if mismatches:
            raise ValueError("profile table keys must equal profile_id")
        return self

    @classmethod
    def from_file(cls, path: str | Path) -> ModelProfileDocument:
        """Load one strict TOML profile document."""
        profile_path = Path(path).expanduser().resolve(strict=False)
        if profile_path.suffix.casefold() != ".toml":
            raise ValueError("model profile document must use TOML")
        if not profile_path.is_file():
            raise FileNotFoundError("selected model profile document does not exist")
        try:
            with profile_path.open("rb") as stream:
                raw = tomllib.load(stream)
        except tomllib.TOMLDecodeError as error:
            raise ValueError("selected model profile document is invalid TOML") from error
        return cls.model_validate(raw)

    def select(self, profile_name: str) -> ModelProfileDefinition:
        """Resolve exactly one named profile without fallback."""
        try:
            return self.profiles[profile_name]
        except KeyError as error:
            raise ValueError("selected model profile name does not exist") from error


@dataclass(frozen=True, slots=True, kw_only=True)
class ActiveModelProfileSnapshot:
    """Redactable immutable identity consumed by the production runtime."""

    schema_version: str
    profile_id: str
    version: str
    mode: ModelProfileMode
    enabled: bool
    trust_class: ModelProfileTrustClass
    certification: ModelProfileCertification
    certification_evidence: tuple[str, ...]
    capabilities: tuple[str, ...]
    components: Mapping[str, ModelProfileComponent]
    fingerprint: str
    http_enabled: bool = True
    mcp_enabled: bool = True

    def public_metadata(self) -> dict[str, object]:
        """Return provider identity and governance state without paths or secrets."""
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "version": self.version,
            "mode": self.mode.value,
            "enabled": self.enabled,
            "trust_class": self.trust_class.value,
            "certification": self.certification.value,
            "fingerprint": self.fingerprint,
            "http_enabled": self.http_enabled,
            "mcp_enabled": self.mcp_enabled,
        }


def profile_snapshot(
    definition: ModelProfileDefinition,
    *,
    schema_version: str = "mnemo.model-profiles/1",
    http_enabled: bool = True,
    mcp_enabled: bool = True,
) -> ActiveModelProfileSnapshot:
    """Create a deterministic immutable snapshot from a validated definition."""
    canonical = definition.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ActiveModelProfileSnapshot(
        schema_version=schema_version,
        profile_id=definition.profile_id,
        version=definition.version,
        mode=definition.mode,
        enabled=definition.mode is ModelProfileMode.PHASE85,
        trust_class=definition.trust_class,
        certification=definition.certification,
        certification_evidence=definition.certification_evidence,
        capabilities=definition.capabilities,
        components=MappingProxyType(dict(sorted(definition.models.items()))),
        fingerprint=digest,
        http_enabled=http_enabled,
        mcp_enabled=mcp_enabled,
    )


class ModelProfileRegistry:
    """Resolve the one immutable production profile selected by ``MnemoConfig``."""

    def __init__(self, config: object) -> None:
        from mnemo.config import MnemoConfig

        if not isinstance(config, MnemoConfig):
            raise TypeError("config must be MnemoConfig")
        selected: ModelProfileDefinition | None = None
        schema_version = "mnemo.model-profiles/1"
        if config.phase85.profile_file is not None and config.phase85.profile_name is not None:
            document = ModelProfileDocument.from_file(config.phase85.profile_file)
            selected = document.select(config.phase85.profile_name)
            schema_version = document.schema_version
        components: dict[str, ModelProfileComponent] = {}
        selected_components = {} if selected is None else selected.models
        for name in sorted(_COMPONENT_IDS):
            value = getattr(config.models, name)
            if not value.enabled:
                continue
            if value.provider is None or value.model is None:
                raise ValueError("enabled model profile requires provider and model")
            original = selected_components.get(name)
            revision = value.revision or (None if original is None else original.revision)
            if revision is None:
                raise ValueError("enabled model profile requires an immutable revision")
            components[name] = ModelProfileComponent(
                provider=value.provider,
                model=value.model,
                revision=revision,
                license="operator-supplied" if original is None else original.license,
                dimensions=value.dimensions,
                metric=(
                    ("cosine" if value.dimensions is not None else None)
                    if original is None
                    else original.metric
                ),
                normalization=(
                    ("l2" if value.dimensions is not None else None)
                    if original is None
                    else original.normalization
                ),
                preprocessing="inline-legacy" if original is None else original.preprocessing,
                languages=() if original is None else original.languages,
                scripts=() if original is None else original.scripts,
                language_claims=() if original is None else original.language_claims,
                modalities=() if original is None else original.modalities,
                max_batch=None if original is None else original.max_batch,
                max_context_tokens=None if original is None else original.max_context_tokens,
                max_input_bytes=None if original is None else original.max_input_bytes,
                max_pixels=None if original is None else original.max_pixels,
            )
        configured_mode = ModelProfileMode(config.phase85.mode)
        effective_mode = (
            configured_mode
            if config.phase85.enabled
            else (
                ModelProfileMode.V1_ONLY
                if configured_mode is ModelProfileMode.V1_ONLY
                else ModelProfileMode.DISABLED
            )
        )
        if effective_mode is not ModelProfileMode.PHASE85:
            components = {}
        definition = ModelProfileDefinition(
            profile_id=config.phase85.profile_name or "inline_legacy",
            version=config.phase85.profile_version,
            mode=effective_mode,
            trust_class=ModelProfileTrustClass(config.phase85.trust_class),
            certification=ModelProfileCertification(config.phase85.certification),
            certification_evidence=config.phase85.certification_evidence,
            capabilities=() if selected is None else selected.capabilities,
            models=components,
        )
        self._active = profile_snapshot(
            definition,
            schema_version=schema_version,
            http_enabled=config.phase85.features.http and config.phase85.enabled,
            mcp_enabled=config.phase85.features.mcp and config.phase85.enabled,
        )
        self._selected_document_fingerprint: str | None
        if config.phase85.profile_fingerprint is not None and selected is not None:
            # The resolved model leaves may have explicit inline/environment overrides.
            # A changed fingerprint is intentional and becomes the generation identity.
            self._selected_document_fingerprint = config.phase85.profile_fingerprint
        else:
            self._selected_document_fingerprint = None

    @property
    def active(self) -> ActiveModelProfileSnapshot:
        return self._active

    def component(self, component_id: str) -> ModelProfileComponent | None:
        return self._active.components.get(component_id)

    @property
    def selected_document_fingerprint(self) -> str | None:
        return self._selected_document_fingerprint
