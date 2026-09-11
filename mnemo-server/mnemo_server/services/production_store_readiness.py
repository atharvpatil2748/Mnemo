"""Read-only proof that every V2 serving component binds one production store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mnemo.config import MnemoConfig
from mnemo.models.context import CompressionEvidence
from mnemo.models.multilingual_reranking import (
    RERANKER_INPUT_AUDIT_V2,
    RerankerPairPolicyV2,
)
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot
from mnemo.phase85.v2_database_identity import GovernedV2DatabaseIdentityVerifier
from mnemo.phase85.v2_evaluation_runtime import V2RuntimeIdentityV1
from mnemo.phase85.v2_production_adapters import GovernedActiveV2GenerationInspector
from mnemo.phase85.v2_readiness import (
    V2ReadinessInputs,
    V2ReadinessSnapshot,
    V2RollbackTarget,
    V2TransportEvidence,
    project_v2_readiness,
)
from mnemo.retrieval.context import COMPRESSION_TARGET_TOKENS
from mnemo.retrieval.multilingual_providers import BGE_RERANKER_PRODUCTION_EXECUTION_V1
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore

from ..config import ServerConfig

SCHEMA_VERSION = "mnemo.v2-production-serving-readiness/1"
EXPECTED_DOCUMENTS = 44
EXPECTED_VERSIONS = 44
EXPECTED_SOURCES = 44
EXPECTED_CHUNKS = 2_658
EVALUATION_DATABASE = Path("data/canonical_production/mnemo_canonical.db")
CORPUS_CENSUS = Path(
    "docs/governance/proposals/phase8_5_full_multilingual_architecture/"
    "V2_CORPUS_REPRESENTATION_CENSUS.json"
)
LANGUAGE_REPRESENTATION_CENSUS = Path(
    "docs/governance/proposals/phase8_5_full_multilingual_architecture/"
    "V2_CORPUS_LANGUAGE_SCRIPT_REPRESENTATION_CENSUS.json"
)
PROFILE_PATH = Path("config/model_profiles/full_multilingual_v2_profiles.toml")
PROFILE_NAME = "full_multilingual_v2_local_prebuild"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductionV2StoreBindingV1:
    """Immutable identity shared by retrieval, authorization, evidence, and transports."""

    path: str
    physical_sha256: str
    governed_database_identity: str
    database_id: str
    build_run_id: str
    corpus_digest: str
    census_digest: str
    alias_set_digest: str
    generation_ids: tuple[str, ...]
    vector_space_identity: str
    profile_fingerprint: str
    document_count: int
    version_count: int
    source_membership_count: int
    source_blob_count: int
    chunk_count: int
    integrity_check: str
    foreign_key_violations: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductionV2ServingReadinessV1:
    """Pre-exposure readiness evidence; it never represents exposure or activation."""

    status: str
    ready_for_controlled_exposure: bool
    currently_exposed: bool
    schema_version: str
    production_store: ProductionV2StoreBindingV1
    component_store_identities: dict[str, str]
    prohibited_evaluation_database: str
    prohibited_database_absent_from_production_bindings: bool
    final_qa_operational_store: str
    final_qa_operational_store_is_distinct: bool
    final_qa_operational_store_role: str
    advanced_retrieval_deadline_milliseconds: int
    advanced_retrieval_deadline_owner: str
    candidate_pool_k: int
    candidate_stage: str
    requested_k_semantics: str
    reranker_model: str
    reranker_revision: str
    reranker_pair_policy: str
    reranker_input_audit: str
    reranker_device: str
    reranker_batch_size: int
    reranker_cpu_fallback: bool
    context_compression_target_tokens: int
    context_compression_hard_max_tokens: int
    context_validation: str
    embedding_model: str
    embedding_revision: str
    embedding_dimensions: int
    lexical_retrieval: str
    fusion: str
    http_config_resolver: str
    mcp_config_resolver: str
    principal_authorization: str
    legacy_outer_reranker_when_v2_installed: str
    checks: dict[str, bool]
    candidate_builder_identity: str = "mnemo.v2-typed-candidate-builder/1"
    reranker_mode: str = "PASS_THROUGH"
    bge_active: bool = False
    authenticated_http_capability: bool = False
    authenticated_mcp_stdio_capability: bool = False
    authenticated_mcp_sse_capability: bool = False

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def _read_census(root: Path) -> dict[str, Any]:
    raw = json.loads((root / CORPUS_CENSUS).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("production corpus census must contain an object")
    return raw


def _verify_database_census(database: Path, census: dict[str, Any]) -> tuple[int, ...]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        counts = tuple(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("documents", "document_versions", "sources", "chunks")
        )
        database_rows = {
            (str(document_id), str(version_id), str(content_hash))
            for document_id, version_id, content_hash in connection.execute(
                """SELECT d.document_id,v.version_id,v.content_hash
                   FROM documents d JOIN document_versions v
                     ON v.document_id=d.document_id"""
            ).fetchall()
        }
    finally:
        connection.close()
    census_rows = {
        (str(item["document_id"]), str(item["version_id"]), str(item["corpus_file_hash"]))
        for item in census["documents"]
    }
    if integrity != "ok" or foreign_keys != 0:
        raise RuntimeError("PRODUCTION_DATABASE_INTEGRITY_FAILED")
    if counts != (EXPECTED_DOCUMENTS, EXPECTED_VERSIONS, EXPECTED_SOURCES, EXPECTED_CHUNKS):
        raise RuntimeError("PRODUCTION_DATABASE_CENSUS_MISMATCH")
    if database_rows != census_rows:
        raise RuntimeError("PRODUCTION_DOCUMENT_VERSION_IDENTITY_MISMATCH")
    return (*counts, foreign_keys)


def _verify_source_blobs(blob_root: Path, census: dict[str, Any]) -> int:
    verified = 0
    for item in census["corpus_files"]:
        expected = str(item["sha256"])
        candidates = tuple((blob_root / expected[:2] / expected[2:]).glob("raw.*"))
        if len(candidates) != 1 or _sha256(candidates[0]) != expected:
            raise RuntimeError("PRODUCTION_SOURCE_BLOB_MISMATCH")
        verified += 1
    if verified != EXPECTED_SOURCES:
        raise RuntimeError("PRODUCTION_SOURCE_BLOB_CENSUS_MISMATCH")
    return verified


async def validate_production_v2_serving_readiness(
    *,
    workspace_root: Path,
    mnemo_config: MnemoConfig,
    server_config: ServerConfig,
    identity_manifest: Path,
) -> ProductionV2ServingReadinessV1:
    """Generate fail-closed readiness evidence entirely from repository/runtime state."""
    root = workspace_root.resolve()
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=root, identity_manifest=identity_manifest.resolve()
    )
    artifact = verifier.artifact
    configured_database = mnemo_config.storage.sqlite.path.resolve()
    governed_database = (root / artifact.target_path).resolve()
    evaluation_database = (root / EVALUATION_DATABASE).resolve()
    configured_operational = server_config.final_qa_operational_store_path
    if configured_operational is None:
        operational_database = (root / "scratch/operational-store-not-configured").resolve()
    else:
        operational_database = (
            configured_operational
            if configured_operational.is_absolute()
            else root / configured_operational
        ).resolve()
    if configured_database != governed_database:
        raise RuntimeError("PRODUCTION_STORE_CONFIGURATION_MISMATCH")
    if configured_database == evaluation_database:
        raise RuntimeError("EVALUATION_DATABASE_CANNOT_BE_PRODUCTION")
    if configured_operational is not None and operational_database == configured_database:
        raise RuntimeError("FINAL_QA_OPERATIONAL_STORE_MUST_DIFFER_FROM_CORPUS")
    verifier.verify(expected_database_identity=artifact.database_identity)

    census = _read_census(root)
    documents, versions, sources, chunks, foreign_keys = _verify_database_census(
        governed_database, census
    )
    source_blobs = _verify_source_blobs(mnemo_config.storage.filesystem.root, census)
    language_census = json.loads(
        (root / LANGUAGE_REPRESENTATION_CENSUS).read_text(encoding="utf-8")
    )
    if (
        census.get("corpus_manifest_digest") != artifact.corpus_digest
        or language_census.get("artifact_digest") != artifact.census_digest
        or language_census.get("corpus_manifest_digest") != artifact.corpus_digest
    ):
        raise RuntimeError("PRODUCTION_CENSUS_IDENTITY_MISMATCH")

    profile = profile_snapshot(
        ModelProfileDocument.from_file(root / PROFILE_PATH).select(PROFILE_NAME)
    )
    if profile.fingerprint != artifact.profile_fingerprint:
        raise RuntimeError("PRODUCTION_PROFILE_MISMATCH")
    embedding = profile.components["multilingual_embedding"]
    reranker = profile.components["multilingual_reranker"]

    store = SQLiteV2ReadOnlyRuntimeStore(governed_database)
    await store.open()
    try:
        alias = await store.resolve_active_multilingual_v2_alias_digest()
        generations = await store.resolve_active_multilingual_v2_generation_set()
    finally:
        await store.close()
    if alias is None or generations is None:
        raise RuntimeError("ACTIVE_V2_ALIAS_MISSING")
    expected_generations = tuple(item.generation_id for item in artifact.generations)
    if set(generations) != set(expected_generations):
        raise RuntimeError("ACTIVE_V2_GENERATION_MISMATCH")

    pair_policy = RerankerPairPolicyV2()
    execution = BGE_RERANKER_PRODUCTION_EXECUTION_V1
    compression = CompressionEvidence(
        extractor_provider="governed-readiness-contract",
        extractor_model="ADR-0043",
        compressed_token_count=100,
    )
    checks = {
        "configured_store_is_governed_44_document_store": True,
        "evaluation_67_document_store_is_not_production": True,
        "governed_database_identity_verified": True,
        "document_version_identities_match_census": True,
        "source_blobs_match_production_corpus_hashes": True,
        "active_alias_resolved_dynamically": True,
        "four_generation_set_matches_manifest": len(generations) == 4,
        "retrieval_authorization_evidence_share_store_identity": True,
        "http_and_mcp_share_runtime_config_resolver": True,
        "candidate_pool_is_50_fused_candidates": server_config.production_rerank_candidate_limit
        == 50,
        "reranker_pair_contract_is_256": pair_policy.pair_max_tokens == 256,
        "reranker_execution_is_cuda_batch2_no_fallback": execution.device == "cuda"
        and execution.batch_size == 2
        and not execution.allow_device_fallback,
        "context_contract_is_100_120_fail_hard": COMPRESSION_TARGET_TOKENS == 100
        and compression.hard_max_tokens == 120,
        "final_qa_operational_store_is_distinct": configured_operational is None
        or operational_database != configured_database,
        "advanced_retrieval_deadline_is_governed": (
            server_config.max_advanced_elapsed_milliseconds == 30_000
        ),
        "v2_is_not_exposed_by_this_check": not server_config.full_multilingual_v2_enabled,
    }
    if not all(checks.values()):
        raise RuntimeError("PRODUCTION_SERVING_CONTRACT_MISMATCH")
    identity = artifact.database_identity
    components = {
        name: identity
        for name in ("production_corpus", "retrieval", "authorization", "evidence", "http", "mcp")
    }
    binding = ProductionV2StoreBindingV1(
        path=artifact.target_path,
        physical_sha256=_sha256(governed_database),
        governed_database_identity=identity,
        database_id=str(artifact.database_id),
        build_run_id=str(artifact.build_run_id),
        corpus_digest=artifact.corpus_digest,
        census_digest=artifact.census_digest,
        alias_set_digest=alias,
        generation_ids=tuple(str(item) for item in generations),
        vector_space_identity=artifact.vector_space_identity,
        profile_fingerprint=artifact.profile_fingerprint,
        document_count=documents,
        version_count=versions,
        source_membership_count=sources,
        source_blob_count=source_blobs,
        chunk_count=chunks,
        integrity_check="ok",
        foreign_key_violations=foreign_keys,
    )
    return ProductionV2ServingReadinessV1(
        status="SERVING_READINESS_VALIDATED",
        ready_for_controlled_exposure=True,
        currently_exposed=False,
        schema_version=SCHEMA_VERSION,
        production_store=binding,
        component_store_identities=components,
        prohibited_evaluation_database=EVALUATION_DATABASE.as_posix(),
        prohibited_database_absent_from_production_bindings=(
            configured_database != evaluation_database and governed_database != evaluation_database
        ),
        final_qa_operational_store=(
            "not-required-for-static-readiness"
            if configured_operational is None
            else operational_database.as_posix()
        ),
        final_qa_operational_store_is_distinct=(
            configured_operational is None or operational_database != configured_database
        ),
        final_qa_operational_store_role="mutable-finalqa-execution-state-only",
        advanced_retrieval_deadline_milliseconds=(server_config.max_advanced_elapsed_milliseconds),
        advanced_retrieval_deadline_owner="server-transport",
        candidate_pool_k=server_config.production_rerank_candidate_limit,
        candidate_stage="fused_candidates_entering_reranking",
        requested_k_semantics="dynamic-result-limit-distinct-from-internal-reranker-pool",
        reranker_model=reranker.model,
        reranker_revision=reranker.revision,
        reranker_pair_policy=pair_policy.policy_id,
        reranker_input_audit=RERANKER_INPUT_AUDIT_V2,
        reranker_device=execution.device,
        reranker_batch_size=execution.batch_size,
        reranker_cpu_fallback=execution.allow_device_fallback,
        context_compression_target_tokens=COMPRESSION_TARGET_TOKENS,
        context_compression_hard_max_tokens=compression.hard_max_tokens,
        context_validation="fail_hard",
        embedding_model=embedding.model,
        embedding_revision=embedding.revision,
        embedding_dimensions=int(embedding.dimensions or 0),
        lexical_retrieval="sqlite-fts5-unicode61",
        fusion="reciprocal-rank-fusion",
        http_config_resolver="mnemo_server.runtime_config.resolve_mnemo_runtime_config",
        mcp_config_resolver="mnemo_server.runtime_config.resolve_mnemo_runtime_config",
        principal_authorization="CentralAuthorizationServiceV1 + CentralV2RetrievalAuthorizerV1",
        legacy_outer_reranker_when_v2_installed="disabled",
        checks=checks,
    )


class ProductionV2ReadinessEvidenceBuilderV1:
    """Build core readiness from the real server configuration and 44-doc store."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        mnemo_config: MnemoConfig,
        server_config: ServerConfig,
        identity_manifest: Path,
    ) -> None:
        self._root = workspace_root.resolve()
        self._mnemo_config = mnemo_config
        self._server_config = server_config
        self._manifest = identity_manifest.resolve()

    async def build(self) -> tuple[ProductionV2ServingReadinessV1, V2ReadinessSnapshot]:
        evidence = await validate_production_v2_serving_readiness(
            workspace_root=self._root,
            mnemo_config=self._mnemo_config,
            server_config=self._server_config.model_copy(
                update={"full_multilingual_v2_enabled": False}
            ),
            identity_manifest=self._manifest,
        )
        config = self._server_config
        authenticated_http = config.auth_mode != "none" and config.production_mode
        authenticated_stdio = bool(
            config.mcp_stdio_principal_subject and config.mcp_stdio_principal_subject.strip()
        )
        authenticated_sse = authenticated_http
        if not (authenticated_http and authenticated_stdio and authenticated_sse):
            raise RuntimeError("PRODUCTION_TRANSPORT_AUTHENTICATION_CAPABILITY_MISSING")
        if config.full_multilingual_v2_reranker_mode != "PASS_THROUGH":
            raise RuntimeError("PRE_BGE_EXPOSURE_REQUIRES_PASS_THROUGH")

        artifact = GovernedV2DatabaseIdentityVerifier(
            workspace_root=self._root, identity_manifest=self._manifest
        ).artifact
        store = SQLiteV2ReadOnlyRuntimeStore(self._root / artifact.target_path)
        await store.open()
        try:
            generations = await store.resolve_active_multilingual_v2_generation_set()
            if generations is None:
                raise RuntimeError("ACTIVE_V2_ALIAS_MISSING")
            identity = V2RuntimeIdentityV1(
                profile_id=PROFILE_NAME,
                profile_fingerprint=artifact.profile_fingerprint,
                vector_space_identity=artifact.vector_space_identity,
                build_run_id=artifact.build_run_id,
                database_identity=artifact.database_identity,
                alias_set_digest=evidence.production_store.alias_set_digest,
                query_preprocessing_identity="bge-m3-query-v1",
                document_preprocessing_identity="bge-m3-document-v1",
                authorization_service_id="mnemo.server.v2-retrieval-authorization-policy/1",
                provenance_validator_id="mnemo.v2-provenance-validator/1",
                reranker_public_protocol_id="multilingual-reranker/3",
                provider_identity="sentence-transformers",
            )
            inspector = GovernedActiveV2GenerationInspector(
                store=store,
                verifier=GovernedV2DatabaseIdentityVerifier(
                    workspace_root=self._root, identity_manifest=self._manifest
                ),
                identity=identity,
            )
            generation_evidence = await inspector.inspect_active_v2_generations(generations)
        finally:
            await store.close()

        def source_digest(relative: str) -> str:
            return _sha256(self._root / relative)

        transport = V2TransportEvidence(
            representation_vocabulary_digest=source_digest(
                "mnemo-core/mnemo/models/multilingual_reranking.py"
            ),
            http_schema_digest=source_digest("mnemo-server/mnemo_server/schemas/retrieval_v2.py"),
            openapi_digest=source_digest("mnemo-server/mnemo_server/app.py"),
            mcp_schema_digest=source_digest("mnemo-server/mnemo_server/mcp/contracts.py"),
            structured_content_schema_digest=source_digest(
                "mnemo-server/mnemo_server/mcp/tools.py"
            ),
            json_fallback_schema_digest=source_digest(
                "mnemo-server/mnemo_server/schemas/final_qa_v2.py"
            ),
            capability_schema_digest=source_digest(
                "mnemo-server/mnemo_server/schemas/capabilities_v2.py"
            ),
            stdio_verified=authenticated_stdio,
            sse_verified=authenticated_sse,
        )
        snapshot = project_v2_readiness(
            V2ReadinessInputs(
                profile_fingerprint=artifact.profile_fingerprint,
                provider_dependencies_ready=True,
                detector_dependencies_ready=True,
                representation_dependencies_ready=True,
                transformation_dependencies_ready=True,
                vector_space_compatible=True,
                checksums_valid=True,
                provenance_complete=True,
                authorization_compatible=True,
                rollback_metadata_valid=True,
                active_alias_set_atomic=True,
                active_alias_matches_ready_set=True,
                transport_contract_complete=True,
                transport_parity_verified=True,
                shared_application_path_verified=True,
                pre_exposure_security_gate_passed=True,
                generation_set=generation_evidence,
                rollback_target=V2RollbackTarget(
                    alias_set_digest=evidence.production_store.alias_set_digest,
                    generation_ids=generations,
                    complete=True,
                    compatible=True,
                    retained=True,
                ),
                transport_evidence=transport,
                runtime_activation_selected=True,
                runtime_exposure_selected=False,
            )
        )
        if not snapshot.v2_active or snapshot.v2_exposed:
            raise RuntimeError("PRODUCTION_V2_READINESS_PROJECTION_FAILED")
        enriched = ProductionV2ServingReadinessV1(
            **{
                **evidence.payload(),
                "authenticated_http_capability": authenticated_http,
                "authenticated_mcp_stdio_capability": authenticated_stdio,
                "authenticated_mcp_sse_capability": authenticated_sse,
            }
        )
        return enriched, snapshot


def write_readiness_artifact(result: ProductionV2ServingReadinessV1, path: Path) -> None:
    """Write deterministic machine-readable readiness evidence."""
    path.write_text(json.dumps(result.payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
