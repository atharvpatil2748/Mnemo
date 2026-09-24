"""Atomic, operator-owned migration from historical to staged credential authority.

Preparing a transition is read-only. Committing is deliberately separate and
requires an already staged, signed generation; this module never provisions one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo.config import MnemoConfig
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot

from .production_credentials import (
    CredentialKind,
    CredentialState,
    ProductionCredentialRegistry,
    SecretStore,
)
from .production_runtime_binding import MANIFEST, PROFILE_NAME, _governed_path
from .v2_reranker_lifecycle import DurableRerankerActivationStoreV1, V2RerankerMode


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class AuthorityTransitionPlan:
    """Non-secret compare-and-swap plan; not itself a certified state."""

    manifest_path: Path
    previous_manifest_sha256: str
    proposed_manifest: bytes
    registry_path: Path
    registry_sha256: str
    generation_id: UUID
    activation_sha256: str
    historical_artifact_sha256: dict[str, str]


def prepare_authority_transition(
    *, root: Path, secret_store: SecretStore
) -> AuthorityTransitionPlan:
    """Validate an existing staged generation before changing any manifest byte."""
    try:
        base = root.resolve(strict=True)
        manifest_path = base / MANIFEST
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise ValueError("manifest is not an object")
        authority = manifest["configuration_authority"]
        lifecycle = manifest["lifecycle"]
        activation_config = manifest["reranker_activation"]
        if (
            not isinstance(authority, dict)
            or not isinstance(lifecycle, dict)
            or not isinstance(activation_config, dict)
            or "credential_registry" in authority
        ):
            raise ValueError("ambiguous authority")
        historical_names = (
            "durable_activation_state",
            "certified_lifecycle_state",
            "final_certification_evidence",
        )
        historical = {name: _governed_path(base, authority[name]) for name in historical_names}
        if len(set(historical.values())) != len(historical):
            raise ValueError("historical artifacts overlap")
        if (
            _governed_path(base, activation_config["state_path"])
            != historical["durable_activation_state"]
        ):
            raise ValueError("activation authorities conflict")
        historical_hashes = {name: _digest(path) for name, path in historical.items()}

        operational = _governed_path(base, manifest["final_qa_operational_store"]["path"])
        registry_path = (operational.parent / "credentials.json").resolve()
        if (
            not registry_path.is_relative_to(base)
            or registry_path in historical.values()
            or registry_path == operational
            or not registry_path.is_file()
        ):
            raise ValueError("registry unavailable")
        registry = ProductionCredentialRegistry(path=registry_path, secret_store=secret_store)
        document = registry.load()
        staged = [
            item for item in document.generations if item.state is CredentialState.PROVISIONED
        ]
        if document.active_generation_id is not None or len(staged) != 1:
            raise ValueError("staged generation is ambiguous")
        record = staged[0]
        if (
            record.observation_campaign_id is None
            or record.activation_path is None
            or record.activation_sha256 is None
            or record.certificate_path is not None
            or record.final_evidence_path is not None
            or not record.owner_subject
            or not record.service_subject
        ):
            raise ValueError("staged generation is incomplete")
        activation_path = Path(record.activation_path).resolve(strict=True)
        if (
            not activation_path.is_relative_to(registry_path.parent)
            or activation_path in historical.values()
            or activation_path in {registry_path, operational}
            or _digest(activation_path) != record.activation_sha256
        ):
            raise ValueError("activation is not governed")
        cursor = registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
        registry.retrieve(record.generation_id, CredentialKind.CERTIFICATION_SIGNING)
        kinds = {item.kind for item in record.secrets}
        if (CredentialKind.API_KEY in kinds) == (CredentialKind.JWT_SECRET in kinds):
            raise ValueError("authentication kind is ambiguous")
        registry.retrieve(
            record.generation_id,
            CredentialKind.API_KEY
            if CredentialKind.API_KEY in kinds
            else CredentialKind.JWT_SECRET,
        )
        activation_doc = json.loads(activation_path.read_text(encoding="utf-8"))
        activation_id = UUID(str(activation_doc["activation_generation_id"]))
        signing_key = hmac.new(
            cursor.encode("utf-8"), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
        ).digest()
        state = DurableRerankerActivationStoreV1(
            path=activation_path,
            signing_key=signing_key,
            prohibited_paths=(*historical.values(), operational, registry_path),
            credential_generation_id=record.generation_id,
            activation_generation_id=activation_id,
        ).load()
        corpus = manifest["corpus"]
        reranker = manifest["reranker"]
        profile_path = _governed_path(base, authority["model_profile"])
        profile = profile_snapshot(
            ModelProfileDocument.from_file(profile_path).select(PROFILE_NAME)
        )
        model = profile.components["multilingual_reranker"]
        core_path = _governed_path(base, authority["core_runtime"])
        core = MnemoConfig.from_file(core_path)
        database = _governed_path(base, corpus["database_path"])
        evidence = state.activation_evidence
        if (
            state.desired_mode is not V2RerankerMode.BGE_V2_M3
            or evidence is None
            or not evidence.v2_exposed
            or not evidence.production_evaluation_passed
            or evidence.production_store_identity != corpus["database_identity"]
            or evidence.expected_production_store_identity != corpus["database_identity"]
            or evidence.model != reranker["model"]
            or evidence.revision != reranker["revision"]
            or model.model != reranker["model"]
            or model.revision != reranker["revision"]
            or core.storage.sqlite.path.resolve() != database
            or operational == database
            or operational.parent == database.parent
            or core.storage.qdrant.enabled
            or core.storage.surrealdb.enabled
        ):
            raise ValueError("staged identity does not match production")

        candidate = json.loads(raw)
        candidate_authority = candidate["configuration_authority"]
        for name in historical_names:
            del candidate_authority[name]
        candidate_authority["credential_registry"] = str(registry_path.relative_to(base)).replace(
            "\\", "/"
        )
        candidate["reranker_activation"]["state_path"] = str(
            activation_path.relative_to(base)
        ).replace("\\", "/")
        candidate["reranker_activation"]["currently_activated"] = False
        for name in (
            "active_generation_alias",
            "v2_transport_exposed",
            "bge_reranker_activated",
            "verified",
            "certified",
        ):
            candidate["lifecycle"][name] = False
        return AuthorityTransitionPlan(
            manifest_path=manifest_path,
            previous_manifest_sha256=hashlib.sha256(raw).hexdigest(),
            proposed_manifest=_json_bytes(candidate),
            registry_path=registry_path,
            registry_sha256=_digest(registry_path),
            generation_id=record.generation_id,
            activation_sha256=record.activation_sha256,
            historical_artifact_sha256=historical_hashes,
        )
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise RuntimeError("MNEMO_AUTHORITY_TRANSITION_REJECTED") from exc


def commit_authority_transition(
    *, plan: AuthorityTransitionPlan, root: Path, secret_store: SecretStore
) -> str:
    """Compare-and-swap one manifest; a failed write leaves old bytes intact."""
    manifest = (root.resolve(strict=True) / MANIFEST).resolve()
    if manifest != plan.manifest_path:
        raise RuntimeError("MNEMO_AUTHORITY_TRANSITION_REJECTED")
    lock_path = manifest.with_suffix(manifest.suffix + ".transition.lock")
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise RuntimeError("MNEMO_AUTHORITY_TRANSITION_LOCKED") from exc
    os.close(descriptor)
    temporary: Path | None = None
    try:
        current = prepare_authority_transition(root=root, secret_store=secret_store)
        if current != plan or _digest(manifest) != plan.previous_manifest_sha256:
            raise RuntimeError("MNEMO_AUTHORITY_TRANSITION_CHANGED")
        descriptor, name = tempfile.mkstemp(
            prefix=f".{manifest.name}.", suffix=".tmp", dir=manifest.parent
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(plan.proposed_manifest)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, manifest)
        return hashlib.sha256(plan.proposed_manifest).hexdigest()
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)
