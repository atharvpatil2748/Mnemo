"""Side-effect-free admission of the one certified V2 production composition.

This is an identity gate, not a replacement for V2 readiness or activation.
It runs before any production storage or model is opened by a transport.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast
from uuid import UUID, uuid4

from mnemo.config import MnemoConfig
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot

from ..config import ServerConfig
from .durable_reranker_activation import _signing_key
from .production_credentials import (
    CredentialGeneration,
    CredentialKind,
    ProductionCredentialRegistry,
    SecretStore,
    WindowsCredentialStore,
)
from .production_generation_evidence import ProductionGenerationEvidenceAuthority
from .production_storage_composition import build_protected_storage_inventory
from .v2_certification import WP17GenerationBindingV2
from .v2_reranker_lifecycle import (
    DurableRerankerActivationStoreV1,
    RerankerActivationEvidenceV1,
    V2RerankerMode,
)

MANIFEST = Path("config/production/full_multilingual_v2.production.json")
OBSERVATION_DIR = Path("scratch/phase8_8_1_runtime_convergence")
PROFILE_NAME = "full_multilingual_v2_local_prebuild"
_IDENTITY_ENV_PREFIXES = (
    "MNEMO_STORAGE_",
    "MNEMO_EMBEDDING_",
    "MNEMO_RERANKER_",
    "MNEMO_LLM_",
    "MNEMO_PHASE85_",
)


def repository_root() -> Path:
    """Locate the checkout that owns the canonical production manifest, not CWD."""
    return Path(__file__).resolve().parents[3]


def _fail() -> NoReturn:
    raise RuntimeError("CERTIFIED_PRODUCTION_BINDING_REJECTED")


def _document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("CERTIFIED_PRODUCTION_BINDING_REJECTED") from exc
    if not isinstance(value, dict):
        _fail()
    return cast(dict[str, Any], value)


def _digest(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise RuntimeError("CERTIFIED_PRODUCTION_BINDING_REJECTED") from exc


def _governed_path(root: Path, raw: object) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
        _fail()
    candidate = (root / raw).resolve(strict=False)
    if not candidate.is_relative_to(root):
        _fail()
    return candidate


def reject_uncertified_corpus_startup(
    *, mnemo_config: MnemoConfig, server_config: ServerConfig
) -> None:
    """Never permit the generic writable engine to address the certified DB."""
    root = repository_root()
    if not (root / MANIFEST).is_file():
        return
    manifest = _document(root / MANIFEST)
    corpus = manifest.get("corpus")
    if not isinstance(corpus, dict):
        _fail()
    configured = mnemo_config.storage.sqlite.path
    if not isinstance(configured, Path):
        return
    if configured.resolve() == _governed_path(root, corpus.get("database_path")):
        _fail()


@dataclass(frozen=True, slots=True)
class CertifiedProductionBinding:
    """Safe, diffable identity shared by HTTP, stdio, SSE and the tunnel."""

    schema_version: str
    binding_id: str
    configuration_digest: str
    database_identity: str
    database_sha256: str
    model_profile_fingerprint: str
    embedding_model: str
    embedding_revision: str
    reranker_model: str
    reranker_revision: str
    activation_digest: str
    activation_mode: str
    certification_digest: str
    certification_signature: str
    final_qa_operational_identity: str
    mutable_workspace_identity: str
    authorization_mode: str
    stdio_principal_identity: str
    runtime_profile: str
    credential_generation_id: str
    final_evidence_digest: str

    def payload(self) -> dict[str, str]:
        return asdict(self)


def resolve_certified_production_binding(
    *,
    server_config: ServerConfig,
    mnemo_config: MnemoConfig | None = None,
    root: Path | None = None,
    environment: dict[str, str] | None = None,
    credential_secret_store: SecretStore | None = None,
) -> tuple[MnemoConfig, CertifiedProductionBinding]:
    """Reject a production fork before directory creation or SQLite connection.

    The signed activation is verified with the existing server-owned key. The
    WP-17 certificate is checked against the accepted final evidence; this
    gate does not reissue or mutate either governed artifact.
    """
    base = (root or repository_root()).resolve(strict=True)
    env = os.environ if environment is None else environment
    if any(name.startswith(_IDENTITY_ENV_PREFIXES) for name in env):
        _fail()
    if not server_config.production_mode or not server_config.full_multilingual_v2_enabled:
        _fail()
    if server_config.auth_mode == "none" or not server_config.mcp_stdio_principal_subject:
        _fail()
    if server_config.auth_mode == "api-key" and not server_config.api_key:
        _fail()
    if server_config.auth_mode == "jwt" and not server_config.jwt_secret:
        _fail()
    if server_config.full_multilingual_v2_reranker_mode != "BGE_V2_M3":
        _fail()

    manifest = _document(base / MANIFEST)
    authority = manifest.get("configuration_authority")
    corpus = manifest.get("corpus")
    if not isinstance(authority, dict) or not isinstance(corpus, dict):
        _fail()
    core_path = _governed_path(base, authority.get("core_runtime"))
    canonical_config = MnemoConfig.from_file(core_path)
    if mnemo_config is not None and mnemo_config != canonical_config:
        _fail()
    config = canonical_config
    database = _governed_path(base, corpus.get("database_path"))
    if config.storage.sqlite.path.resolve() != database:
        _fail()
    if config.storage.qdrant.enabled or config.storage.surrealdb.enabled:
        _fail()
    if (
        server_config.full_multilingual_v2_model_cache is None
        or not server_config.full_multilingual_v2_model_cache.is_absolute()
    ):
        _fail()

    generation_record: CredentialGeneration | None = None
    generation_registry: ProductionCredentialRegistry | None = None
    registry_raw = authority.get("credential_registry")
    if registry_raw is not None:
        registry_path = _governed_path(base, registry_raw)
        if server_config.credential_registry_path != registry_path:
            _fail()
        generation_registry = ProductionCredentialRegistry(
            path=registry_path,
            secret_store=credential_secret_store or WindowsCredentialStore(),
        )
        document = generation_registry.load()
        generation_record = next(
            (
                item
                for item in document.generations
                if item.generation_id == document.active_generation_id
            ),
            None,
        )
        if (
            generation_record is None
            or server_config.credential_generation_id != generation_record.generation_id
            or generation_record.activation_path is None
            or generation_record.certificate_path is None
            or generation_record.final_evidence_path is None
        ):
            _fail()
        generated_paths = tuple(
            Path(path).resolve(strict=False)
            for path in (
                generation_record.activation_path,
                generation_record.certificate_path,
                generation_record.final_evidence_path,
            )
        )
        if any(not path.is_relative_to(registry_path.parent) for path in generated_paths):
            _fail()
        final_evidence_path = generated_paths[2]
        certificate_path = generated_paths[1]
    else:
        if server_config.credential_registry_path is not None:
            _fail()
        final_evidence_path = _governed_path(base, authority.get("final_certification_evidence"))
        certificate_path = _governed_path(base, authority.get("certified_lifecycle_state"))
    final_evidence = _document(final_evidence_path)
    certificate = _document(certificate_path)
    evidence_store = final_evidence.get("production_store")
    evidence_governance = final_evidence.get("governance")
    if not isinstance(evidence_store, dict) or not isinstance(evidence_governance, dict):
        _fail()
    database_sha = _digest(database)
    identity = str(corpus.get("database_identity", ""))
    if (
        not identity
        or certificate.get("status") != "PRODUCTION_CERTIFICATION_PASS"
        or certificate.get("production_store_identity") != identity
        or certificate.get("production_store_sha256") != database_sha
        or evidence_store.get("governed_identity") != identity
        or evidence_store.get("sha256_after") != database_sha
        or evidence_governance.get("wp17_signature") != certificate.get("signature")
    ):
        _fail()

    profile = profile_snapshot(
        ModelProfileDocument.from_file(_governed_path(base, authority.get("model_profile"))).select(
            PROFILE_NAME
        )
    )
    embedding = profile.components["multilingual_embedding"]
    reranker = profile.components["multilingual_reranker"]
    identity_artifact = _document(_governed_path(base, corpus.get("identity_manifest")))
    retrieval = manifest.get("retrieval")
    governed_reranker = manifest.get("reranker")
    if not isinstance(retrieval, dict) or not isinstance(governed_reranker, dict):
        _fail()
    if (
        config.embedding.model != embedding.model
        or config.embedding.dimensions != embedding.dimensions
        or retrieval.get("semantic_model") != embedding.model
        or retrieval.get("semantic_revision") != embedding.revision
        or governed_reranker.get("model") != reranker.model
        or governed_reranker.get("revision") != reranker.revision
        or identity_artifact.get("profile_fingerprint") != profile.fingerprint
        or identity_artifact.get("database_identity") != identity
        or _governed_path(base, identity_artifact.get("target_path")) != database
        or certificate.get("bge_revision") != reranker.revision
        or certificate.get("pair_policy") != governed_reranker.get("pair_policy")
    ):
        _fail()

    activation_path = (
        Path(generation_record.activation_path).resolve()
        if generation_record is not None and generation_record.activation_path is not None
        else _governed_path(base, authority.get("durable_activation_state"))
    )
    configured_activation = server_config.reranker_activation_state_path
    configured_operational = server_config.final_qa_operational_store_path
    operational = manifest.get("final_qa_operational_store")
    if (
        configured_activation is None
        or configured_operational is None
        or not isinstance(operational, dict)
    ):
        _fail()
    if (base / configured_activation).resolve() != activation_path or (
        base / configured_operational
    ).resolve() != _governed_path(base, operational.get("path")):
        _fail()
    activation = DurableRerankerActivationStoreV1(
        path=activation_path,
        signing_key=_signing_key(server_config),
        prohibited_paths=(database, (base / configured_operational).resolve()),
        credential_generation_id=(
            generation_record.generation_id if generation_record is not None else None
        ),
        activation_generation_id=(
            UUID(str(final_evidence["activation_generation_id"]))
            if generation_record is not None
            else None
        ),
    ).load()
    if activation.desired_mode is not V2RerankerMode.BGE_V2_M3:
        _fail()
    activation_evidence = cast(RerankerActivationEvidenceV1, activation.activation_evidence)
    if activation_evidence.production_store_identity != identity:
        _fail()
    if generation_record is not None:
        if generation_registry is None:
            _fail()
        try:
            _, cursor = generation_registry.retrieve_active(CredentialKind.DELIVERY_CURSOR)
            _, certificate_secret = generation_registry.retrieve_active(
                CredentialKind.CERTIFICATION_SIGNING
            )
            auth_kind = (
                CredentialKind.API_KEY
                if server_config.auth_mode == "api-key"
                else CredentialKind.JWT_SECRET
            )
            _, auth_secret = generation_registry.retrieve_active(auth_kind)
            if (
                not hmac.compare_digest(cursor, server_config.delivery_cursor_secret)
                or not hmac.compare_digest(
                    auth_secret,
                    (server_config.api_key or "")
                    if server_config.auth_mode == "api-key"
                    else server_config.jwt_secret or "",
                )
                or generation_record.owner_subject
                != server_config.reranker_activation_operator_subject
                or generation_record.service_subject != server_config.mcp_stdio_principal_subject
            ):
                _fail()
            binding_raw = certificate.get("generation_binding")
            if not isinstance(binding_raw, dict):
                _fail()
            binding = WP17GenerationBindingV2(
                credential_generation_id=UUID(str(binding_raw["credential_generation_id"])),
                activation_generation_id=UUID(str(binding_raw["activation_generation_id"])),
                certificate_generation_id=UUID(str(binding_raw["certificate_generation_id"])),
                final_evidence_generation_id=UUID(str(binding_raw["final_evidence_generation_id"])),
                activation_state_sha256=str(binding_raw["activation_state_sha256"]),
                predecessor_certificate_sha256=str(binding_raw["predecessor_certificate_sha256"]),
            )
            transport_reference = generation_record.observation_convergence_path
            if transport_reference is None:
                _fail()
            transport_path = Path(transport_reference).resolve(strict=True)
            if not transport_path.is_relative_to(registry_path.parent):
                _fail()
            verifier = ProductionGenerationEvidenceAuthority(
                activation_path=activation_path,
                certificate_path=certificate_path,
                transport_parity_path=transport_path,
                final_evidence_path=final_evidence_path,
                cursor_signing_key=_signing_key(server_config),
                certification_signing_key=certificate_secret.encode("utf-8"),
                generation_binding=binding,
                model_profile_fingerprint=profile.fingerprint,
                predecessor_final_evidence_sha256=str(
                    final_evidence["predecessor_final_evidence_sha256"]
                ),
            )
            verifier.verify()
            if (
                _digest(activation_path) != generation_record.activation_sha256
                or _digest(certificate_path) != generation_record.certificate_sha256
                or _digest(final_evidence_path) != generation_record.final_evidence_sha256
                or generation_record.observation_convergence_sha256
                != _digest(verifier.transport_parity_path)
                or not verifier.transport_parity_path.is_relative_to(registry_path.parent)
            ):
                _fail()
        except (KeyError, ValueError, RuntimeError) as exc:
            raise RuntimeError("CERTIFIED_PRODUCTION_BINDING_REJECTED") from exc

    # The binding HMAC incorporates credentials but never exposes them in evidence.
    config_bytes = core_path.read_bytes()
    manifest_bytes = (base / MANIFEST).read_bytes()
    operational_path = _governed_path(base, operational["path"])
    workspace_path = server_config.mutable_workspace_root
    workspace_identity = (
        "read-only"
        if workspace_path is None
        else hashlib.sha256(str(workspace_path.resolve()).encode("utf-8")).hexdigest()
    )
    server_identity = {
        "auth_mode": server_config.auth_mode,
        "stdio_subject": server_config.mcp_stdio_principal_subject,
        "operational_path": str(operational_path),
        "activation_path": str(activation_path),
        "workspace_identity": workspace_identity,
        "reranker_mode": server_config.full_multilingual_v2_reranker_mode,
        "advanced_deadline": server_config.max_advanced_elapsed_milliseconds,
        "final_qa_deadline": server_config.max_final_qa_elapsed_milliseconds,
    }
    configuration_digest = hashlib.sha256(
        config_bytes
        + b"\0"
        + manifest_bytes
        + b"\0"
        + json.dumps(server_identity, sort_keys=True).encode("utf-8")
    ).hexdigest()
    fields: dict[str, str] = {
        "configuration_digest": configuration_digest,
        "database_identity": identity,
        "database_sha256": database_sha,
        "model_profile_fingerprint": profile.fingerprint,
        "embedding_model": embedding.model,
        "embedding_revision": str(embedding.revision),
        "reranker_model": reranker.model,
        "reranker_revision": str(reranker.revision),
        "activation_digest": _digest(activation_path),
        "activation_mode": activation.desired_mode.value,
        "certification_digest": _digest(certificate_path),
        "certification_signature": str(certificate["signature"]),
        "final_qa_operational_identity": hashlib.sha256(
            str(operational_path).encode("utf-8")
        ).hexdigest(),
        "mutable_workspace_identity": workspace_identity,
        "authorization_mode": server_config.auth_mode,
        "stdio_principal_identity": hashlib.sha256(
            server_config.mcp_stdio_principal_subject.encode("utf-8")
        ).hexdigest(),
        "runtime_profile": "certified-full-multilingual-v2",
        "credential_generation_id": (
            str(generation_record.generation_id) if generation_record is not None else "legacy"
        ),
        "final_evidence_digest": _digest(final_evidence_path),
    }
    secret_fields = {
        "api_key": server_config.api_key,
        "jwt_secret": server_config.jwt_secret,
        "operator_subject": server_config.reranker_activation_operator_subject,
        "delivery_cursor_key_id": server_config.delivery_cursor_key_id,
    }
    encoded = json.dumps(
        {"fields": fields, "secret_fields": secret_fields},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    binding_id = hmac.new(
        server_config.delivery_cursor_secret.encode("utf-8"), encoded, hashlib.sha256
    ).hexdigest()
    return config, CertifiedProductionBinding(
        schema_version="mnemo.certified-production-binding/1", binding_id=binding_id, **fields
    )


def record_certified_transport_startup(
    *,
    binding: CertifiedProductionBinding,
    transport: str,
    server_config: ServerConfig,
    root: Path | None = None,
) -> Path:
    """Atomically attest a successfully initialized production transport."""
    if transport not in {"http", "mcp_stdio", "mcp_sse", "external_tunnel"}:
        _fail()
    base = (root or repository_root()).resolve()
    target_dir = _observation_directory(base, server_config)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "mnemo.phase8.8.1-transport-observation/1",
        "transport": transport,
        "binding": binding.payload(),
        "observed_at": datetime.now(UTC).isoformat(),
        "run_id": str(uuid4()),
        "process_id": os.getpid(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["signature"] = hmac.new(
        server_config.delivery_cursor_secret.encode("utf-8"), encoded, hashlib.sha256
    ).hexdigest()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{transport}.", suffix=".tmp", dir=target_dir
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        target = target_dir / f"{transport}.json"
        os.replace(temporary_name, target)
        return target
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def collect_certified_convergence(
    *,
    server_config: ServerConfig,
    expected_binding_id: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Compare four independently recorded, authenticated startup observations."""
    base = (root or repository_root()).resolve()
    target_dir = _observation_directory(base, server_config)
    observations = {}
    for transport in ("http", "mcp_stdio", "mcp_sse", "external_tunnel"):
        record = _document(target_dir / f"{transport}.json")
        signature = record.pop("signature", None)
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = hmac.new(
            server_config.delivery_cursor_secret.encode("utf-8"), encoded, hashlib.sha256
        ).hexdigest()
        if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
            _fail()
        if (
            record.get("schema_version") != "mnemo.phase8.8.1-transport-observation/1"
            or record.get("transport") != transport
            or not isinstance(record.get("binding"), dict)
        ):
            _fail()
        observations[transport] = record
    bindings = [item["binding"] for item in observations.values()]
    if (
        any(item != bindings[0] for item in bindings[1:])
        or bindings[0].get("binding_id") != expected_binding_id
    ):
        _fail()
    return {
        "schema_version": "mnemo.phase8.8.1-convergence/1",
        "result": "PASS",
        "binding_id": bindings[0]["binding_id"],
        "observations": observations,
    }


def write_certified_convergence(*, server_config: ServerConfig, root: Path | None = None) -> Path:
    """Publish evidence only after all four signed observations match current authority."""
    base = (root or repository_root()).resolve()
    _, current = resolve_certified_production_binding(server_config=server_config, root=base)
    document = collect_certified_convergence(
        server_config=server_config, expected_binding_id=current.binding_id, root=base
    )
    target_dir = _observation_directory(base, server_config)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".convergence.", suffix=".tmp", dir=target_dir
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
        target = target_dir / "convergence.json"
        os.replace(temporary_name, target)
        return target
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _observation_directory(base: Path, server_config: ServerConfig) -> Path:
    """Keep certification observations outside every ADR-0077 protected role."""
    target = base / OBSERVATION_DIR
    resolved = target.resolve(strict=False)
    if not resolved.is_relative_to(base):
        _fail()
    inventory = build_protected_storage_inventory(
        application_root=base,
        mnemo_config=MnemoConfig.from_file(base / "mnemo.toml"),
        server_config=server_config,
    )
    for location in inventory.locations:
        protected = location.path.resolve(strict=False)
        if (
            resolved == protected
            or resolved.is_relative_to(protected)
            or protected.is_relative_to(resolved)
        ):
            _fail()
    return target
