"""Typed, fail-closed authorization for one Full Multilingual V2 activation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid5

from mnemo.interfaces.errors import ContractValidationError

_NAMESPACE = UUID("a1ef986b-d27a-56d5-a07f-053d57bf3dd4")
_SCHEMA = "mnemo.v2-activation-authorization/1"
_FIRST = "first_v2_activation"
_UPGRADE = "v2_upgrade"
_RECOVERY_DEACTIVATE = "deactivate_v2_alias_set"
_RECOVERY_PRIOR = "prior_v2_alias_set"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_digest(value: str, name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ContractValidationError(f"{name} must be a lowercase SHA-256 digest")


def _path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value.endswith("/mnemo.db"):
        raise ContractValidationError(
            "V2 activation target must be a bounded relative mnemo.db path"
        )
    normalized = path.as_posix()
    if not normalized.startswith("scratch/phase8_5_full_multilingual_v2/"):
        raise ContractValidationError("V2 activation target is outside the isolated namespace")
    return normalized


@dataclass(frozen=True, slots=True, kw_only=True)
class V2ActivationAuthorizationV1:
    run_id: UUID
    target_database_path: str
    profile_fingerprint: str
    corpus_digest: str
    census_digest: str
    generation_namespace: str
    vector_space_identity: str
    storage_manifest_digest: str
    build_manifest_digest: str
    generation_ids: tuple[UUID, ...]
    generation_checksums: tuple[str, ...]
    activation_mode: str
    recovery_mode: str
    authorization_scope: str
    authorization_state: str
    authorized: bool
    authority_class: str
    decision_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_database_path", _path(self.target_database_path))
        for value, name in (
            (self.profile_fingerprint, "profile_fingerprint"),
            (self.corpus_digest, "corpus_digest"),
            (self.census_digest, "census_digest"),
            (self.vector_space_identity, "vector_space_identity"),
            (self.storage_manifest_digest, "storage_manifest_digest"),
            (self.build_manifest_digest, "build_manifest_digest"),
            *tuple((value, "generation_checksum") for value in self.generation_checksums),
        ):
            _require_digest(value, name)
        if len(self.generation_ids) != 4 or len(set(self.generation_ids)) != 4:
            raise ContractValidationError("activation requires exactly four unique generations")
        if len(self.generation_checksums) != 4:
            raise ContractValidationError("activation requires exactly four generation checksums")
        if self.activation_mode not in {_FIRST, _UPGRADE}:
            raise ContractValidationError("unsupported V2 activation mode")
        required_recovery = (
            _RECOVERY_DEACTIVATE if self.activation_mode == _FIRST else _RECOVERY_PRIOR
        )
        if self.recovery_mode != required_recovery:
            raise ContractValidationError("activation mode and recovery mode are incompatible")
        if self.authorization_scope != "activate_exact_ready_v2_alias_set_only":
            raise ContractValidationError("activation authorization scope is invalid")
        if (
            self.authorization_state != "authorized_for_controlled_v2_activation_only"
            or not self.authorized
        ):
            raise ContractValidationError("V2 activation is not authorized")
        if self.authority_class != "human_governance" or not self.decision_reference.strip():
            raise ContractValidationError("V2 activation requires human governance authority")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "run_id": str(self.run_id),
            "target_database_path": self.target_database_path,
            "profile_fingerprint": self.profile_fingerprint,
            "corpus_digest": self.corpus_digest,
            "census_digest": self.census_digest,
            "generation_namespace": self.generation_namespace,
            "vector_space_identity": self.vector_space_identity,
            "storage_manifest_digest": self.storage_manifest_digest,
            "build_manifest_digest": self.build_manifest_digest,
            "generation_ids": [str(value) for value in self.generation_ids],
            "generation_checksums": list(self.generation_checksums),
            "activation_mode": self.activation_mode,
            "recovery_mode": self.recovery_mode,
            "authorization_scope": self.authorization_scope,
            "authorization_state": self.authorization_state,
            "authorized": self.authorized,
            "authority_class": self.authority_class,
            "decision_reference": self.decision_reference,
        }

    @property
    def authorization_id(self) -> UUID:
        return uuid5(_NAMESPACE, _digest(self.identity_payload()))

    @property
    def artifact_digest(self) -> str:
        return _digest({**self.identity_payload(), "authorization_id": str(self.authorization_id)})

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> V2ActivationAuthorizationV1:
        try:
            if raw["schema_version"] != _SCHEMA:
                raise ValueError("unsupported activation authorization schema")
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
                generation_ids=tuple(
                    UUID(str(item)) for item in _sequence(raw["generation_ids"], "generation_ids")
                ),
                generation_checksums=tuple(
                    str(item)
                    for item in _sequence(raw["generation_checksums"], "generation_checksums")
                ),
                activation_mode=str(raw["activation_mode"]),
                recovery_mode=str(raw["recovery_mode"]),
                authorization_scope=str(raw["authorization_scope"]),
                authorization_state=str(raw["authorization_state"]),
                authorized=raw["authorized"] is True,
                authority_class=str(raw["authority_class"]),
                decision_reference=str(raw["decision_reference"]),
            )
            if len(value.generation_ids) != 4 or len(value.generation_checksums) != 4:
                raise ValueError("activation authorization requires four generations")
            if str(raw["authorization_id"]) != str(value.authorization_id):
                raise ValueError("activation authorization identity mismatch")
            if str(raw["artifact_digest"]) != value.artifact_digest:
                raise ValueError("activation authorization digest mismatch")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise ContractValidationError("V2 activation authorization is malformed") from error


def first_v2_deactivation_recovery_digest(*, profile_fingerprint: str) -> str:
    """Bind first-activation recovery to disabling only the V2 alias namespace."""
    _require_digest(profile_fingerprint, "profile_fingerprint")
    return _digest(
        {
            "recovery_mode": _RECOVERY_DEACTIVATE,
            "profile_fingerprint": profile_fingerprint,
            "v1_aliases_mutated": False,
        }
    )


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value
