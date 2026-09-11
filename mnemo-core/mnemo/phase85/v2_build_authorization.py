"""Typed fail-closed authorization for one isolated Full Multilingual V2 build."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid5

from mnemo.interfaces.errors import ContractValidationError

_AUTHORIZATION_NAMESPACE = UUID("091f748a-e9e8-5fad-8753-e20db25c4ae2")
_SCHEMA_VERSION = "mnemo.v2-build-authorization/1"
_STATE = "authorized_for_next_controlled_build_to_ready_only"
_SCOPE = "create_isolated_database_and_build_generations_to_ready_only"


def _sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_digest(value: str, name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ContractValidationError(f"{name} must be a lowercase SHA-256 digest")


def _normalized_relative_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value.endswith("/mnemo.db"):
        raise ContractValidationError("V2 build target must be a bounded relative mnemo.db path")
    normalized = path.as_posix()
    if not normalized.startswith("scratch/phase8_5_full_multilingual_v2/"):
        raise ContractValidationError("V2 build target is outside the isolated namespace")
    return normalized


@dataclass(frozen=True, slots=True, kw_only=True)
class V2BuildAuthorizationV1:
    run_id: UUID
    target_database_path: str
    profile_fingerprint: str
    corpus_digest: str
    census_digest: str
    generation_namespace: str
    vector_space_identity: str
    storage_manifest_digest: str
    build_manifest_digest: str
    authorization_scope: str
    authorization_state: str
    authorized: bool
    authority_class: str
    decision_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "target_database_path", _normalized_relative_path(self.target_database_path)
        )
        for value, name in (
            (self.profile_fingerprint, "profile_fingerprint"),
            (self.corpus_digest, "corpus_digest"),
            (self.census_digest, "census_digest"),
            (self.vector_space_identity, "vector_space_identity"),
            (self.storage_manifest_digest, "storage_manifest_digest"),
            (self.build_manifest_digest, "build_manifest_digest"),
        ):
            _require_digest(value, name)
        if not self.generation_namespace.strip():
            raise ContractValidationError("generation_namespace must not be blank")
        if self.authorization_scope != _SCOPE:
            raise ContractValidationError("build authorization scope is not READY-only")
        if self.authorization_state != _STATE or not self.authorized:
            raise ContractValidationError("V2 database build is not authorized")
        if self.authority_class != "human_governance":
            raise ContractValidationError("V2 build requires human governance authority")
        if not self.decision_reference.strip():
            raise ContractValidationError("authorization decision reference is required")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "run_id": str(self.run_id),
            "target_database_path": self.target_database_path,
            "profile_fingerprint": self.profile_fingerprint,
            "corpus_digest": self.corpus_digest,
            "census_digest": self.census_digest,
            "generation_namespace": self.generation_namespace,
            "vector_space_identity": self.vector_space_identity,
            "storage_manifest_digest": self.storage_manifest_digest,
            "build_manifest_digest": self.build_manifest_digest,
            "authorization_scope": self.authorization_scope,
            "authorization_state": self.authorization_state,
            "authorized": self.authorized,
            "authority_class": self.authority_class,
            "decision_reference": self.decision_reference,
        }

    @property
    def authorization_id(self) -> UUID:
        return uuid5(_AUTHORIZATION_NAMESPACE, _sha256(self.identity_payload()))

    @property
    def artifact_digest(self) -> str:
        return _sha256({**self.identity_payload(), "authorization_id": str(self.authorization_id)})

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> V2BuildAuthorizationV1:
        try:
            if raw["schema_version"] != _SCHEMA_VERSION:
                raise ValueError("unsupported authorization schema")
            value = cls(
                run_id=UUID(str(raw["run_id"])),
                target_database_path=str(raw["target_database_path"]),
                profile_fingerprint=str(raw["profile_fingerprint"]),
                corpus_digest=str(raw["corpus_digest"]),
                census_digest=str(raw["census_digest"]),
                generation_namespace=str(raw["generation_namespace"]),
                vector_space_identity=str(raw["vector_space_identity"]),
                storage_manifest_digest=str(raw["storage_manifest_digest"]),
                build_manifest_digest=str(raw["build_manifest_digest"]),
                authorization_scope=str(raw["authorization_scope"]),
                authorization_state=str(raw["authorization_state"]),
                authorized=raw["authorized"] is True,
                authority_class=str(raw["authority_class"]),
                decision_reference=str(raw["decision_reference"]),
            )
            if str(raw["authorization_id"]) != str(value.authorization_id):
                raise ValueError("authorization identity mismatch")
            if str(raw["artifact_digest"]) != value.artifact_digest:
                raise ValueError("authorization digest mismatch")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise ContractValidationError("V2 build authorization is malformed") from error


def validate_v2_build_authorization(
    authorization: V2BuildAuthorizationV1 | None,
    *,
    storage_manifest: Mapping[str, object],
    build_manifest: Mapping[str, object],
    workspace_root: Path,
    protected_database_paths: tuple[Path, ...],
) -> Path:
    """Validate authorization before a caller may enumerate or create build data."""
    if authorization is None:
        raise ContractValidationError("V2 build authorization is required")
    if storage_manifest.get("database_creation_authorization_mode") != (
        "typed_build_authorization_v1_required"
    ):
        raise ContractValidationError("storage manifest does not require typed authorization")
    if build_manifest.get("authorization_state") != "TYPED_BUILD_AUTHORIZATION_REQUIRED":
        raise ContractValidationError("build manifest authorization state is incompatible")
    bindings = (
        (str(storage_manifest.get("run_id")), str(authorization.run_id), "run"),
        (
            str(storage_manifest.get("target_path")),
            authorization.target_database_path,
            "target",
        ),
        (
            str(storage_manifest.get("profile_fingerprint")),
            authorization.profile_fingerprint,
            "profile",
        ),
        (
            str(storage_manifest.get("corpus_digest")),
            authorization.corpus_digest,
            "corpus",
        ),
        (
            str(storage_manifest.get("census_digest")),
            authorization.census_digest,
            "census",
        ),
        (
            str(storage_manifest.get("generation_namespace")),
            authorization.generation_namespace,
            "generation namespace",
        ),
        (
            str(storage_manifest.get("vector_space_profile_identity")),
            authorization.vector_space_identity,
            "vector space",
        ),
        (
            str(build_manifest.get("vector_space_profile_identity")),
            authorization.vector_space_identity,
            "build vector space",
        ),
        (
            str(storage_manifest.get("artifact_digest")),
            authorization.storage_manifest_digest,
            "storage manifest",
        ),
        (
            str(build_manifest.get("artifact_digest")),
            authorization.build_manifest_digest,
            "build manifest",
        ),
    )
    mismatch = next((name for actual, expected, name in bindings if actual != expected), None)
    if mismatch is not None:
        raise ContractValidationError(f"V2 build authorization {mismatch} binding mismatch")
    target = (workspace_root / authorization.target_database_path).resolve(strict=False)
    root = workspace_root.resolve(strict=False)
    if root not in target.parents:
        raise ContractValidationError("V2 target escapes the workspace")
    protected = {path.resolve(strict=False) for path in protected_database_paths}
    if target in protected:
        raise ContractValidationError("protected database cannot be authorized as a V2 target")
    if storage_manifest.get("disposable") is not True:
        raise ContractValidationError("V2 target must be disposable")
    return target
