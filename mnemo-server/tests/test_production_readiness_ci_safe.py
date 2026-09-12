from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from mnemo.config import MnemoConfig
from mnemo_server.config import ServerConfig
from mnemo_server.services.production_store_readiness import (
    EVALUATION_DATABASE,
    ProductionV2ReadinessEvidenceBuilderV1,
    ProductionV2ServingReadinessV1,
    ProductionV2StoreBindingV1,
    _read_census,
    _sha256,
    _verify_database_census,
    _verify_source_blobs,
    validate_production_v2_serving_readiness,
    write_readiness_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
    / "V2_DATABASE_ARTIFACT_IDENTITY.json"
)


def test_sha256_helper(tmp_path: Path) -> None:
    sample_file = tmp_path / "sample.bin"
    content = b"deterministic test content for sha256 verification"
    sample_file.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert _sha256(sample_file) == expected


def test_read_census_malformed_raises_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mnemo_server.services import production_store_readiness as subject

    fake_census_path = tmp_path / "census.json"
    fake_census_path.write_text('["not", "a", "dict"]', encoding="utf-8")
    monkeypatch.setattr(subject, "CORPUS_CENSUS", fake_census_path.relative_to(tmp_path))
    with pytest.raises(ValueError, match="production corpus census must contain an object"):
        _read_census(tmp_path)


def test_verify_database_census_integrity_and_foreign_key_failures(tmp_path: Path) -> None:
    db_path = tmp_path / "corrupt.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE child (id INTEGER, parent_id INTEGER REFERENCES parent(id))")
        conn.execute("INSERT INTO child VALUES (1, 999)")  # FK violation
        conn.execute("CREATE TABLE documents (document_id TEXT)")
        conn.execute(
            "CREATE TABLE document_versions (document_id TEXT, version_id TEXT, content_hash TEXT)"
        )
        conn.execute("CREATE TABLE sources (id TEXT)")
        conn.execute("CREATE TABLE chunks (id TEXT)")

    with pytest.raises(RuntimeError, match="PRODUCTION_DATABASE_INTEGRITY_FAILED"):
        _verify_database_census(db_path, {"documents": []})


def test_verify_database_census_count_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "wrong_counts.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE documents (document_id TEXT)")
        conn.execute(
            "CREATE TABLE document_versions (document_id TEXT, version_id TEXT, content_hash TEXT)"
        )
        conn.execute("CREATE TABLE sources (id TEXT)")
        conn.execute("CREATE TABLE chunks (id TEXT)")

    with pytest.raises(RuntimeError, match="PRODUCTION_DATABASE_CENSUS_MISMATCH"):
        _verify_database_census(db_path, {"documents": []})


def test_verify_database_census_row_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "valid_counts_wrong_rows.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE documents (document_id TEXT)")
        conn.execute(
            "CREATE TABLE document_versions (document_id TEXT, version_id TEXT, content_hash TEXT)"
        )
        conn.execute("CREATE TABLE sources (id TEXT)")
        conn.execute("CREATE TABLE chunks (id TEXT)")
        for i in range(44):
            conn.execute("INSERT INTO documents VALUES (?)", (f"doc-{i}",))
            conn.execute(
                "INSERT INTO document_versions VALUES (?, ?, ?)",
                (f"doc-{i}", f"ver-{i}", f"hash-{i}"),
            )
            conn.execute("INSERT INTO sources VALUES (?)", (f"source-{i}",))
        for i in range(2658):
            conn.execute("INSERT INTO chunks VALUES (?)", (f"chunk-{i}",))

    # Census expects different document version tuples
    census = {
        "documents": [
            {
                "document_id": f"different-doc-{i}",
                "version_id": f"ver-{i}",
                "corpus_file_hash": f"hash-{i}",
            }
            for i in range(44)
        ]
    }
    with pytest.raises(RuntimeError, match="PRODUCTION_DOCUMENT_VERSION_IDENTITY_MISMATCH"):
        _verify_database_census(db_path, census)


def test_verify_source_blobs_mismatch_and_census_mismatch(tmp_path: Path) -> None:
    blob_root = tmp_path / "blobs"
    blob_root.mkdir()

    # Missing blob candidate raises PRODUCTION_SOURCE_BLOB_MISMATCH
    fake_hash = "a" * 64
    census = {"corpus_files": [{"sha256": fake_hash}]}
    with pytest.raises(RuntimeError, match="PRODUCTION_SOURCE_BLOB_MISMATCH"):
        _verify_source_blobs(blob_root, census)

    # Corrupt content hash raises PRODUCTION_SOURCE_BLOB_MISMATCH
    target_dir = blob_root / fake_hash[:2] / fake_hash[2:]
    target_dir.mkdir(parents=True)
    (target_dir / "raw.pdf").write_bytes(b"wrong content")
    with pytest.raises(RuntimeError, match="PRODUCTION_SOURCE_BLOB_MISMATCH"):
        _verify_source_blobs(blob_root, census)

    # Valid hash but count != EXPECTED_SOURCES (44) raises PRODUCTION_SOURCE_BLOB_CENSUS_MISMATCH
    valid_content = b"correct content"
    valid_hash = hashlib.sha256(valid_content).hexdigest()
    valid_dir = blob_root / valid_hash[:2] / valid_hash[2:]
    valid_dir.mkdir(parents=True)
    (valid_dir / "raw.pdf").write_bytes(valid_content)

    census_single = {"corpus_files": [{"sha256": valid_hash}]}
    with pytest.raises(RuntimeError, match="PRODUCTION_SOURCE_BLOB_CENSUS_MISMATCH"):
        _verify_source_blobs(blob_root, census_single)


@pytest.mark.anyio
async def test_validate_readiness_evaluation_database_prohibited(tmp_path: Path) -> None:
    eval_db = (ROOT / EVALUATION_DATABASE).resolve()
    mnemo_config = MnemoConfig.from_file(ROOT / "mnemo.toml")
    # Point configured database to evaluation database
    unsafe_config = mnemo_config.model_copy(
        update={
            "storage": mnemo_config.storage.model_copy(
                update={"sqlite": mnemo_config.storage.sqlite.model_copy(update={"path": eval_db})}
            )
        }
    )
    # If configured matches evaluation DB, it fails before serving
    with pytest.raises(RuntimeError, match="PRODUCTION_STORE_CONFIGURATION_MISMATCH"):
        await validate_production_v2_serving_readiness(
            workspace_root=ROOT,
            mnemo_config=unsafe_config,
            server_config=ServerConfig(),
            identity_manifest=MANIFEST,
        )


@pytest.mark.anyio
async def test_validate_readiness_operational_must_differ_from_corpus() -> None:
    from mnemo_server.services.production_store_readiness import (
        GovernedV2DatabaseIdentityVerifier,
    )

    verifier = GovernedV2DatabaseIdentityVerifier(workspace_root=ROOT, identity_manifest=MANIFEST)
    target = (ROOT / verifier.artifact.target_path).resolve()

    mnemo_config = MnemoConfig.from_file(ROOT / "mnemo.toml")
    matching_config = mnemo_config.model_copy(
        update={
            "storage": mnemo_config.storage.model_copy(
                update={"sqlite": mnemo_config.storage.sqlite.model_copy(update={"path": target})}
            )
        }
    )
    server_config = ServerConfig(final_qa_operational_store_path=target)

    with pytest.raises(RuntimeError, match="FINAL_QA_OPERATIONAL_STORE_MUST_DIFFER_FROM_CORPUS"):
        await validate_production_v2_serving_readiness(
            workspace_root=ROOT,
            mnemo_config=matching_config,
            server_config=server_config,
            identity_manifest=MANIFEST,
        )


@pytest.mark.anyio
async def test_builder_authentication_and_reranker_preconditions(tmp_path: Path) -> None:
    mnemo_config = MnemoConfig.from_file(ROOT / "mnemo.toml")

    # Error branch: auth_mode == "none"
    server_unauthenticated = ServerConfig(
        production_mode=True,
        auth_mode="none",
        delivery_cursor_secret="x" * 32,
        mcp_stdio_principal_subject="test-stdio",
        full_multilingual_v2_reranker_mode="PASS_THROUGH",
    )
    builder_unauth = ProductionV2ReadinessEvidenceBuilderV1(
        workspace_root=ROOT,
        mnemo_config=mnemo_config,
        server_config=server_unauthenticated,
        identity_manifest=MANIFEST,
    )

    # Monkeypatch validate_production_v2_serving_readiness to return mock evidence
    async def mock_readiness(*_args: Any, **__kwargs: Any) -> Any:
        return SimpleNamespace(
            production_store=SimpleNamespace(alias_set_digest="a" * 64),
            payload=lambda: {},
        )

    from mnemo_server.services import production_store_readiness as subject

    orig_validate = subject.validate_production_v2_serving_readiness
    subject.validate_production_v2_serving_readiness = mock_readiness  # type: ignore[assignment]
    try:
        with pytest.raises(
            RuntimeError, match="PRODUCTION_TRANSPORT_AUTHENTICATION_CAPABILITY_MISSING"
        ):
            await builder_unauth.build()

        # Error branch: reranker_mode != "PASS_THROUGH"
        server_wrong_reranker = ServerConfig(
            production_mode=True,
            auth_mode="api-key",
            api_key="secret",
            delivery_cursor_secret="x" * 32,
            mcp_stdio_principal_subject="test-stdio",
            full_multilingual_v2_enabled=True,
            full_multilingual_v2_model_cache=ROOT / "scratch/models",
            final_qa_operational_store_path=ROOT / "scratch/test-final-qa-operational.db",
            full_multilingual_v2_reranker_mode="BGE_V2_M3",
        )
        builder_wrong_reranker = ProductionV2ReadinessEvidenceBuilderV1(
            workspace_root=ROOT,
            mnemo_config=mnemo_config,
            server_config=server_wrong_reranker,
            identity_manifest=MANIFEST,
        )
        with pytest.raises(RuntimeError, match="PRE_BGE_EXPOSURE_REQUIRES_PASS_THROUGH"):
            await builder_wrong_reranker.build()
    finally:
        subject.validate_production_v2_serving_readiness = orig_validate  # type: ignore[assignment]


def test_write_readiness_artifact_and_payload_serialization(tmp_path: Path) -> None:
    binding = ProductionV2StoreBindingV1(
        path="test/path/mnemo.db",
        physical_sha256="a" * 64,
        governed_database_identity="b" * 64,
        database_id=str(uuid4()),
        build_run_id=str(uuid4()),
        corpus_digest="c" * 64,
        census_digest="d" * 64,
        alias_set_digest="e" * 64,
        generation_ids=("g1", "g2", "g3", "g4"),
        vector_space_identity="f" * 64,
        profile_fingerprint="0" * 64,
        document_count=44,
        version_count=44,
        source_membership_count=44,
        source_blob_count=44,
        chunk_count=2658,
        integrity_check="ok",
        foreign_key_violations=0,
    )
    readiness = ProductionV2ServingReadinessV1(
        status="SERVING_READINESS_VALIDATED",
        ready_for_controlled_exposure=True,
        currently_exposed=False,
        schema_version="mnemo.v2-production-serving-readiness/1",
        production_store=binding,
        component_store_identities={"corpus": "b" * 64},
        prohibited_evaluation_database="data/canonical_production/mnemo_canonical.db",
        prohibited_database_absent_from_production_bindings=True,
        final_qa_operational_store="scratch/test.db",
        final_qa_operational_store_is_distinct=True,
        final_qa_operational_store_role="mutable-finalqa-execution-state-only",
        advanced_retrieval_deadline_milliseconds=30000,
        advanced_retrieval_deadline_owner="server-transport",
        candidate_pool_k=50,
        candidate_stage="fused_candidates_entering_reranking",
        requested_k_semantics="dynamic-result-limit-distinct-from-internal-reranker-pool",
        reranker_model="BAAI/bge-reranker-v2-m3",
        reranker_revision="rev",
        reranker_pair_policy="policy",
        reranker_input_audit="audit",
        reranker_device="cuda",
        reranker_batch_size=2,
        reranker_cpu_fallback=False,
        context_compression_target_tokens=100,
        context_compression_hard_max_tokens=120,
        context_validation="fail_hard",
        embedding_model="BAAI/bge-m3",
        embedding_revision="rev",
        embedding_dimensions=1024,
        lexical_retrieval="fts5",
        fusion="rrf",
        http_config_resolver="resolver",
        mcp_config_resolver="resolver",
        principal_authorization="authorizer",
        legacy_outer_reranker_when_v2_installed="disabled",
        checks={"check1": True},
        authenticated_http_capability=True,
        authenticated_mcp_stdio_capability=True,
        authenticated_mcp_sse_capability=True,
    )

    payload = readiness.payload()
    assert payload["status"] == "SERVING_READINESS_VALIDATED"
    assert payload["ready_for_controlled_exposure"] is True
    assert payload["production_store"]["document_count"] == 44

    output_path = tmp_path / "readiness.json"
    write_readiness_artifact(readiness, output_path)
    assert output_path.is_file()
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["status"] == "SERVING_READINESS_VALIDATED"
    assert loaded["production_store"]["chunk_count"] == 2658
