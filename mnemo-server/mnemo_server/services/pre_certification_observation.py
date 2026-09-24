"""Signed, observation-only evidence for a staged production generation.

This authority cannot certify or activate a generation. Its outputs are
deliberately a different schema from WP-17 final certification evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from mnemo.config import MnemoConfig
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot

from ..config import ServerConfig
from .full_multilingual_v2_startup import InstalledFullMultilingualV2RuntimeV1
from .production_credentials import (
    CredentialKind,
    CredentialState,
    ProductionCredentialRegistry,
    SecretStore,
    WindowsCredentialStore,
    _write_new,
)
from .production_runtime_binding import (
    _IDENTITY_ENV_PREFIXES,
    MANIFEST,
    PROFILE_NAME,
    _digest,
    _document,
    _governed_path,
    repository_root,
)
from .v2_reranker_lifecycle import DurableRerankerActivationStoreV1, V2RerankerMode

Transport = Literal["http", "stdio", "sse", "external_tunnel"]
TRANSPORTS: tuple[Transport, ...] = ("http", "stdio", "sse", "external_tunnel")
OBSERVATION_TYPE = "PRE_CERTIFICATION_TRANSPORT_OBSERVATION"
CONVERGENCE_TYPE = "PRE_CERTIFICATION_TRANSPORT_CONVERGENCE"
_OBSERVATION_SCHEMA = "mnemo.pre-certification-transport-observation/1"
_CONVERGENCE_SCHEMA = "mnemo.pre-certification-transport-convergence/1"
_DOMAIN = b"mnemo.pre-certification-observation/1\0"


def observation_root_for_convergence(path: Path, *, generation_id: UUID, campaign_id: UUID) -> Path:
    """Recover the canonical observation root from a governed evidence path."""
    resolved = path.resolve()
    if resolved.parent.name == str(campaign_id) and resolved.parent.parent.name == str(
        generation_id
    ):
        return resolved.parents[2]
    return resolved.parent


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ObservationIdentity:
    """Exact semantic identity; no certificate/final-evidence claim or secret."""

    credential_generation_id: str
    configuration_digest: str
    database_identity: str
    database_sha256: str
    model_profile_fingerprint: str
    embedding_model: str
    embedding_revision: str
    reranker_model: str
    reranker_revision: str
    reranker_mode: str
    activation_sha256: str
    operational_store_identity: str
    runtime_binding_digest: str
    composition_identity: str


def resolve_pre_certification_observation(
    *,
    server_config: ServerConfig,
    root: Path | None = None,
    mnemo_config: MnemoConfig | None = None,
    secret_store: SecretStore | None = None,
    environment: dict[str, str] | None = None,
) -> tuple[MnemoConfig, ObservationIdentity, PreCertificationObservationAuthority]:
    """Admit only one registry-staged, signed V2 composition; never certify it."""
    try:
        env = os.environ if environment is None else environment
        if any(name.startswith(_IDENTITY_ENV_PREFIXES) for name in env):
            raise RuntimeError("PRE_CERTIFICATION_CONFIGURATION_FORK_REJECTED")
        base = (root or repository_root()).resolve(strict=True)
        manifest = _document(base / MANIFEST)
        configuration = manifest["configuration_authority"]
        corpus = manifest["corpus"]
        operational = manifest["final_qa_operational_store"]
        retrieval = manifest["retrieval"]
        reranker = manifest["reranker"]
        registry_path = _governed_path(base, configuration["credential_registry"])
        core_path = _governed_path(base, configuration["core_runtime"])
        profile_path = _governed_path(base, configuration["model_profile"])
        database = _governed_path(base, corpus["database_path"])
        operational_path = _governed_path(base, operational["path"])
        identity_artifact = _document(_governed_path(base, corpus["identity_manifest"]))
        core = MnemoConfig.from_file(core_path)
        profile = profile_snapshot(
            ModelProfileDocument.from_file(profile_path).select(PROFILE_NAME)
        )
        embedding = profile.components["multilingual_embedding"]
        model_reranker = profile.components["multilingual_reranker"]
        registry = ProductionCredentialRegistry(
            path=registry_path, secret_store=secret_store or WindowsCredentialStore()
        )
        staged = [
            item
            for item in registry.load().generations
            if item.state is CredentialState.PROVISIONED
            and item.observation_campaign_id is not None
        ]
        if len(staged) != 1:
            raise RuntimeError("PRE_CERTIFICATION_GENERATION_UNAVAILABLE")
        record = staged[0]
        if (
            not server_config.production_mode
            or not server_config.full_multilingual_v2_enabled
            or server_config.auth_mode not in {"api-key", "jwt"}
            or server_config.full_multilingual_v2_reranker_mode != "BGE_V2_M3"
            or server_config.mutable_workspace_root is not None
            or server_config.full_multilingual_v2_model_cache is None
            or not server_config.full_multilingual_v2_model_cache.is_absolute()
            or server_config.credential_registry_path != registry_path
            or server_config.credential_generation_id != record.generation_id
            or server_config.reranker_activation_operator_subject != record.owner_subject
            or server_config.mcp_stdio_principal_subject != record.service_subject
            or record.activation_path is None
            or record.activation_sha256 is None
            or record.observation_campaign_id is None
            or (mnemo_config is not None and mnemo_config != core)
            or core.storage.sqlite.path.resolve() != database
            or core.storage.qdrant.enabled
            or core.storage.surrealdb.enabled
            or database == operational_path
            or server_config.final_qa_operational_store_path is None
            or (base / server_config.final_qa_operational_store_path).resolve() != operational_path
            or core.embedding.model != embedding.model
            or core.embedding.dimensions != embedding.dimensions
            or retrieval["semantic_model"] != embedding.model
            or retrieval["semantic_revision"] != embedding.revision
            or reranker["model"] != model_reranker.model
            or reranker["revision"] != model_reranker.revision
            or identity_artifact["profile_fingerprint"] != profile.fingerprint
            or identity_artifact["database_identity"] != corpus["database_identity"]
            or _governed_path(base, identity_artifact["target_path"]) != database
        ):
            raise RuntimeError("PRE_CERTIFICATION_BINDING_REJECTED")
        activation_path = Path(record.activation_path).resolve(strict=True)
        if (
            not activation_path.is_relative_to(registry_path.parent)
            or server_config.reranker_activation_state_path is None
            or (base / server_config.reranker_activation_state_path).resolve() != activation_path
            or _digest(activation_path) != record.activation_sha256
        ):
            raise RuntimeError("PRE_CERTIFICATION_ACTIVATION_REJECTED")
        activation_doc = _document(activation_path)
        activation_id = UUID(str(activation_doc["activation_generation_id"]))
        cursor = registry.retrieve(record.generation_id, CredentialKind.DELIVERY_CURSOR)
        certification_secret = registry.retrieve(
            record.generation_id, CredentialKind.CERTIFICATION_SIGNING
        )
        auth_kind = (
            CredentialKind.API_KEY
            if server_config.auth_mode == "api-key"
            else CredentialKind.JWT_SECRET
        )
        auth_secret = registry.retrieve(record.generation_id, auth_kind)
        if not hmac.compare_digest(
            cursor, server_config.delivery_cursor_secret
        ) or not hmac.compare_digest(
            auth_secret,
            server_config.api_key or ""
            if auth_kind is CredentialKind.API_KEY
            else server_config.jwt_secret or "",
        ):
            raise RuntimeError("PRE_CERTIFICATION_CREDENTIAL_REJECTED")
        activation_key = hmac.new(
            cursor.encode("utf-8"), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
        ).digest()
        activation = DurableRerankerActivationStoreV1(
            path=activation_path,
            signing_key=activation_key,
            prohibited_paths=(database, operational_path),
            credential_generation_id=record.generation_id,
            activation_generation_id=activation_id,
        ).load()
        if (
            activation.desired_mode is not V2RerankerMode.BGE_V2_M3
            or activation.activation_evidence is None
            or activation.activation_evidence.production_store_identity
            != corpus["database_identity"]
        ):
            raise RuntimeError("PRE_CERTIFICATION_ACTIVATION_REJECTED")
        database_sha = _digest(database)
        if database_sha != identity_artifact.get(
            "sha256"
        ) and database_sha != identity_artifact.get("physical_sha256"):
            # The identity artifact uses different field names across old builds;
            # the immutable WP-17 DB digest remains the final check.
            from .v2_certification import STORE_SHA256

            if database_sha != STORE_SHA256:
                raise RuntimeError("PRE_CERTIFICATION_DATABASE_REJECTED")
        server_identity = {
            "auth_mode": server_config.auth_mode,
            "stdio_subject": server_config.mcp_stdio_principal_subject,
            "operational_path": str(operational_path),
            "activation_path": str(activation_path),
            "workspace_identity": "read-only",
            "reranker_mode": server_config.full_multilingual_v2_reranker_mode,
            "advanced_deadline": server_config.max_advanced_elapsed_milliseconds,
            "final_qa_deadline": server_config.max_final_qa_elapsed_milliseconds,
        }
        configuration_digest = hashlib.sha256(
            core_path.read_bytes()
            + b"\0"
            + (base / MANIFEST).read_bytes()
            + b"\0"
            + json.dumps(server_identity, sort_keys=True).encode("utf-8")
        ).hexdigest()
        semantic: dict[str, str] = {
            "credential_generation_id": str(record.generation_id),
            "configuration_digest": configuration_digest,
            "database_identity": str(corpus["database_identity"]),
            "database_sha256": database_sha,
            "model_profile_fingerprint": profile.fingerprint,
            "embedding_model": embedding.model,
            "embedding_revision": embedding.revision,
            "reranker_model": model_reranker.model,
            "reranker_revision": model_reranker.revision,
            "reranker_mode": activation.desired_mode.value,
            "activation_sha256": record.activation_sha256,
            "operational_store_identity": hashlib.sha256(
                str(operational_path).encode("utf-8")
            ).hexdigest(),
        }
        composition = hashlib.sha256(_canonical(semantic)).hexdigest()
        binding_digest = hmac.new(
            cursor.encode("utf-8"), _canonical(semantic), hashlib.sha256
        ).hexdigest()
        identity = ObservationIdentity(
            **semantic,
            runtime_binding_digest=binding_digest,
            composition_identity=composition,
        )
        authority = PreCertificationObservationAuthority(
            generation_id=record.generation_id,
            signing_key=certification_secret.encode("utf-8"),
            observation_root=registry_path.parent / "pre_certification_observations",
            campaign_id=record.observation_campaign_id,
        )
        return core, identity, authority
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise RuntimeError("PRE_CERTIFICATION_BINDING_REJECTED") from exc


class PreCertificationObservationAuthority:
    """Sign real transport observations and compare four independent calls."""

    def __init__(
        self,
        *,
        generation_id: UUID,
        signing_key: bytes,
        observation_root: Path,
        campaign_id: UUID,
    ) -> None:
        if len(signing_key) < 32 or not observation_root.is_absolute():
            raise ValueError("PRE_CERTIFICATION_AUTHORITY_INVALID")
        self.generation_id = generation_id
        self.campaign_id = campaign_id
        self._key = hmac.new(signing_key, _DOMAIN, hashlib.sha256).digest()
        self._root = observation_root.resolve()

    def _sign(self, payload: dict[str, Any]) -> str:
        return hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()

    def _load_signed(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("PRE_CERTIFICATION_EVIDENCE_UNAVAILABLE") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("PRE_CERTIFICATION_EVIDENCE_INVALID")
        signature = payload.pop("signature", None)
        if not isinstance(signature, str) or not hmac.compare_digest(
            signature, self._sign(payload)
        ):
            raise RuntimeError("PRE_CERTIFICATION_SIGNATURE_INVALID")
        return payload

    async def observe(
        self,
        *,
        transport: Transport,
        identity: ObservationIdentity,
        principal_subject: str,
        correlation_id: UUID,
        engine: KnowledgeEngine,
        runtime: InstalledFullMultilingualV2RuntimeV1,
        action: str = "observe_runtime",
    ) -> Path:
        """Create-only after a real, authenticated, ready runtime call."""
        from .v2_reranker_lifecycle import V2RerankerMode

        if (
            transport not in TRANSPORTS
            or identity.credential_generation_id != str(self.generation_id)
            or not principal_subject.strip()
            or action != "observe_runtime"
            or engine.state is not EngineState.READY
            or engine.certified_read_only is not True
            or runtime.reranker.mode is not V2RerankerMode.BGE_V2_M3
            or runtime.reranker.activation_record is None
            or runtime.reranker.activation_record.revision != identity.reranker_revision
            or runtime.assembler.identity.database_identity != identity.database_identity
            or runtime.assembler.identity.profile_fingerprint != identity.model_profile_fingerprint
            or runtime.exposure_snapshot.v2_exposed is not True
        ):
            raise RuntimeError("PRE_CERTIFICATION_OBSERVATION_REJECTED")
        readiness = await runtime.embedding.readiness()
        if readiness.initialized is not True or readiness.exact_identity is not True:
            raise RuntimeError("PRE_CERTIFICATION_MODEL_UNAVAILABLE")
        payload: dict[str, Any] = {
            "schema_version": _OBSERVATION_SCHEMA,
            "evidence_type": OBSERVATION_TYPE,
            "observation_state": "PRE_CERTIFICATION_OBSERVATION",
            "credential_generation_id": str(self.generation_id),
            "campaign_id": str(self.campaign_id),
            "transport": transport,
            "identity": asdict(identity),
            "correlation_id": str(correlation_id),
            "observed_at": datetime.now(UTC).isoformat(),
            "action": action,
            "success": True,
            "principal_identity": hashlib.sha256(principal_subject.encode("utf-8")).hexdigest(),
            "observation_producer": "PreCertificationObservationAuthority/1",
        }
        payload["signature"] = self._sign(payload)
        path = (
            self._root
            / str(self.generation_id)
            / str(self.campaign_id)
            / (f"{transport}-{correlation_id}.json")
        )
        _write_new(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")
        return path

    def verify_observation(self, *, path: Path, transport: Transport) -> dict[str, Any]:
        if not path.resolve().is_relative_to(
            self._root / str(self.generation_id) / str(self.campaign_id)
        ):
            raise RuntimeError("PRE_CERTIFICATION_PATH_REJECTED")
        payload = self._load_signed(path)
        identity = payload.get("identity")
        if (
            payload.get("schema_version") != _OBSERVATION_SCHEMA
            or payload.get("evidence_type") != OBSERVATION_TYPE
            or payload.get("observation_state") != "PRE_CERTIFICATION_OBSERVATION"
            or payload.get("credential_generation_id") != str(self.generation_id)
            or payload.get("campaign_id") != str(self.campaign_id)
            or payload.get("transport") != transport
            or payload.get("action") != "observe_runtime"
            or payload.get("success") is not True
            or not isinstance(identity, dict)
            or set(identity) != set(ObservationIdentity.__dataclass_fields__)
            or identity.get("credential_generation_id") != str(self.generation_id)
        ):
            raise RuntimeError("PRE_CERTIFICATION_OBSERVATION_INVALID")
        return payload

    def converge(self, *, observations: dict[Transport, Path], output: Path) -> Path:
        """Publish a signed PASS only for four exact, separate observations."""
        if set(observations) != set(TRANSPORTS):
            raise RuntimeError("PRE_CERTIFICATION_TRANSPORT_SET_INVALID")
        loaded = {
            transport: self.verify_observation(path=observations[transport], transport=transport)
            for transport in TRANSPORTS
        }
        identities = [item["identity"] for item in loaded.values()]
        correlations = [item["correlation_id"] for item in loaded.values()]
        if any(item != identities[0] for item in identities[1:]) or len(set(correlations)) != 4:
            raise RuntimeError("PRE_CERTIFICATION_CONVERGENCE_FAILED")
        resolved = output.resolve()
        if not resolved.is_relative_to(self._root) or resolved.exists():
            raise RuntimeError("PRE_CERTIFICATION_CONVERGENCE_PATH_REJECTED")
        payload: dict[str, Any] = {
            "schema_version": _CONVERGENCE_SCHEMA,
            "evidence_type": CONVERGENCE_TYPE,
            "observation_state": "OBSERVATION_CONVERGED",
            "status": "PASS",
            "credential_generation_id": str(self.generation_id),
            "campaign_id": str(self.campaign_id),
            "identity": identities[0],
            "observations": {
                transport: {
                    "sha256": _sha256(observations[transport]),
                    "path": str(observations[transport].resolve()),
                    "correlation_id": loaded[transport]["correlation_id"],
                }
                for transport in TRANSPORTS
            },
            "converged_at": datetime.now(UTC).isoformat(),
        }
        payload["signature"] = self._sign(payload)
        _write_new(resolved, json.dumps(payload, sort_keys=True, indent=2) + "\n")
        self.verify_convergence(resolved)
        return resolved

    def verify_convergence(self, path: Path) -> dict[str, Any]:
        if not path.resolve().is_relative_to(self._root):
            raise RuntimeError("PRE_CERTIFICATION_PATH_REJECTED")
        payload = self._load_signed(path)
        references = payload.get("observations")
        if (
            payload.get("schema_version") != _CONVERGENCE_SCHEMA
            or payload.get("evidence_type") != CONVERGENCE_TYPE
            or payload.get("observation_state") != "OBSERVATION_CONVERGED"
            or payload.get("status") != "PASS"
            or payload.get("credential_generation_id") != str(self.generation_id)
            or payload.get("campaign_id") != str(self.campaign_id)
            or not isinstance(references, dict)
            or set(references) != set(TRANSPORTS)
        ):
            raise RuntimeError("PRE_CERTIFICATION_CONVERGENCE_INVALID")
        identities = []
        correlations = []
        for transport in TRANSPORTS:
            reference = references[transport]
            if not isinstance(reference, dict):
                raise RuntimeError("PRE_CERTIFICATION_CONVERGENCE_INVALID")
            observation_path = Path(str(reference.get("path", "")))
            observed = self.verify_observation(path=observation_path, transport=transport)
            if _sha256(observation_path) != reference.get("sha256") or observed[
                "correlation_id"
            ] != reference.get("correlation_id"):
                raise RuntimeError("PRE_CERTIFICATION_OBSERVATION_CHANGED")
            identities.append(observed["identity"])
            correlations.append(observed["correlation_id"])
        if (
            any(identity != identities[0] for identity in identities[1:])
            or len(set(correlations)) != 4
            or payload.get("identity") != identities[0]
        ):
            raise RuntimeError("PRE_CERTIFICATION_CONVERGENCE_FAILED")
        return payload
