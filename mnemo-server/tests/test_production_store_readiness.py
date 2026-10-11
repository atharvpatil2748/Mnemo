"""Same-store production readiness tests; no provider inference or exposure."""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from pathlib import Path

import pytest
from mnemo.config import MnemoConfig
from mnemo_server.config import ServerConfig
from mnemo_server.runtime_config import resolve_mnemo_runtime_config
from mnemo_server.services.production_store_readiness import (
    EVALUATION_DATABASE,
    ProductionV2ReadinessEvidenceBuilderV1,
    _verify_database_census,
    _verify_source_blobs,
    validate_production_v2_serving_readiness,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
    / "V2_DATABASE_ARTIFACT_IDENTITY.json"
)

EXPECTED_PRODUCTION_DOCUMENT_COUNT = 44


def test_disposable_database_census_checks_counts_and_version_ancestry(tmp_path: Path) -> None:
    database = tmp_path / "fixture.db"
    documents = [
        {
            "document_id": f"document-{index}",
            "version_id": f"version-{index}",
            "corpus_file_hash": f"hash-{index}",
        }
        for index in range(44)
    ]
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE documents(document_id TEXT PRIMARY KEY);"
            "CREATE TABLE document_versions(version_id TEXT PRIMARY KEY,"
            "document_id TEXT REFERENCES documents(document_id),content_hash TEXT);"
            "CREATE TABLE sources(source_id TEXT PRIMARY KEY);"
            "CREATE TABLE chunks(chunk_id INTEGER PRIMARY KEY);"
        )
        connection.executemany(
            "INSERT INTO documents VALUES(?)", ((item["document_id"],) for item in documents)
        )
        connection.executemany(
            "INSERT INTO document_versions VALUES(?,?,?)",
            (
                (item["version_id"], item["document_id"], item["corpus_file_hash"])
                for item in documents
            ),
        )
        connection.executemany(
            "INSERT INTO sources VALUES(?)", ((f"source-{index}",) for index in range(44))
        )
        connection.executemany("INSERT INTO chunks VALUES(?)", ((index,) for index in range(2658)))
    census = {"documents": documents}
    assert _verify_database_census(database, census) == (44, 44, 44, 2658, 0)
    with pytest.raises(RuntimeError, match="VERSION_IDENTITY_MISMATCH"):
        _verify_database_census(database, {"documents": documents[:-1]})
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM chunks WHERE chunk_id=0")
    with pytest.raises(RuntimeError, match="DATABASE_CENSUS_MISMATCH"):
        _verify_database_census(database, census)


def test_disposable_source_blob_census_rejects_missing_and_changed_bytes(
    tmp_path: Path,
) -> None:
    blobs = tmp_path / "blobs"
    corpus_files = []
    for index in range(44):
        payload = f"source-{index}".encode()
        digest = hashlib.sha256(payload).hexdigest()
        target = blobs / digest[:2] / digest[2:] / "raw.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        corpus_files.append({"sha256": digest})
    assert _verify_source_blobs(blobs, {"corpus_files": corpus_files}) == 44
    (blobs / corpus_files[0]["sha256"][:2] / corpus_files[0]["sha256"][2:] / "raw.txt").write_bytes(
        b"changed"
    )
    with pytest.raises(RuntimeError, match="SOURCE_BLOB_MISMATCH"):
        _verify_source_blobs(blobs, {"corpus_files": corpus_files})
    with pytest.raises(RuntimeError, match="SOURCE_BLOB_CENSUS_MISMATCH"):
        _verify_source_blobs(blobs, {"corpus_files": []})


def _require_full_production_database(store_path: Path) -> None:
    """Skip unless the *real* 44-document production database is present."""
    if not store_path.exists():
        pytest.skip("Governed production database not present in environment")
    try:
        conn = sqlite3.connect(f"file:{store_path.as_posix()}?mode=ro&immutable=1", uri=True)
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        conn.close()
    except Exception:
        pytest.skip("Governed production database not readable or schema mismatch")
    if count != EXPECTED_PRODUCTION_DOCUMENT_COUNT:
        pytest.skip(
            f"Database has {count} documents; expected {EXPECTED_PRODUCTION_DOCUMENT_COUNT}."
            " Skipping: not the full production database."
        )


@pytest.mark.local_database
def test_http_and_mcp_shared_config_resolves_governed_44_document_store() -> None:
    config = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    store_path = (ROOT / config.storage.sqlite.path).resolve()
    _require_full_production_database(store_path)
    result = asyncio.run(
        validate_production_v2_serving_readiness(
            workspace_root=ROOT,
            mnemo_config=config,
            server_config=ServerConfig(),
            identity_manifest=MANIFEST,
        )
    )
    assert result.ready_for_controlled_exposure is True
    assert result.currently_exposed is False
    assert result.production_store.document_count == 44
    assert result.production_store.chunk_count == 2_658
    assert result.production_store.source_blob_count == 44
    assert len(set(result.component_store_identities.values())) == 1
    assert result.candidate_pool_k == 50
    assert result.requested_k_semantics.startswith("dynamic-result-limit")
    assert result.advanced_retrieval_deadline_milliseconds == 30_000
    assert result.advanced_retrieval_deadline_owner == "server-transport"
    assert result.reranker_pair_policy == "bge-reranker-v2-m3-pair-256-contextual-v1"
    assert result.reranker_device == "cuda"
    assert result.reranker_batch_size == 2
    assert result.reranker_cpu_fallback is False
    assert result.context_compression_target_tokens == 100
    assert result.context_compression_hard_max_tokens == 120


def test_evaluation_database_cannot_be_selected_as_production() -> None:
    original = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    unsafe = original.model_copy(
        update={
            "storage": original.storage.model_copy(
                update={
                    "sqlite": original.storage.sqlite.model_copy(
                        update={"path": (ROOT / EVALUATION_DATABASE).resolve()}
                    )
                }
            )
        }
    )
    with pytest.raises(RuntimeError, match="PRODUCTION_STORE_CONFIGURATION_MISMATCH"):
        asyncio.run(
            validate_production_v2_serving_readiness(
                workspace_root=ROOT,
                mnemo_config=unsafe,
                server_config=ServerConfig(),
                identity_manifest=MANIFEST,
            )
        )


def test_explicit_config_has_precedence_for_both_transport_processes() -> None:
    config = MnemoConfig.from_file(ROOT / "mnemo.toml")
    assert resolve_mnemo_runtime_config(config) is config


@pytest.mark.local_database
def test_production_owned_builder_proves_ready_but_not_exposed() -> None:
    config = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    store_path = (ROOT / config.storage.sqlite.path).resolve()
    _require_full_production_database(store_path)
    server = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="test",
        delivery_cursor_secret="x" * 32,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_model_cache=ROOT / "scratch/models",
        final_qa_operational_store_path=ROOT / "scratch/test-final-qa-operational.db",
        mcp_stdio_principal_subject="mnemo-production-stdio",
    )
    evidence, snapshot = asyncio.run(
        ProductionV2ReadinessEvidenceBuilderV1(
            workspace_root=ROOT,
            mnemo_config=config,
            server_config=server,
            identity_manifest=MANIFEST,
        ).build()
    )
    assert evidence.reranker_mode == "PASS_THROUGH"
    assert evidence.bge_active is False
    assert evidence.authenticated_http_capability is True
    assert evidence.authenticated_mcp_stdio_capability is True
    assert evidence.authenticated_mcp_sse_capability is True
    assert evidence.final_qa_operational_store_is_distinct is True
    assert evidence.final_qa_operational_store.endswith("test-final-qa-operational.db")
    assert snapshot.v2_ready is True
    assert snapshot.v2_active is True
    assert snapshot.v2_exposed is False


def test_readiness_rejects_corpus_as_final_qa_operational_store() -> None:
    config = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    # The live default is deliberately UNINDEXED and points elsewhere. Bind
    # this narrow pre-verification path check to the historical manifest's
    # declared target without opening or rebuilding that retired database.
    governed = ROOT / "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db"
    config = config.model_copy(
        update={
            "storage": config.storage.model_copy(
                update={"sqlite": config.storage.sqlite.model_copy(update={"path": governed})}
            )
        }
    )
    server = ServerConfig(
        final_qa_operational_store_path=governed,
    )
    with pytest.raises(RuntimeError, match="FINAL_QA_OPERATIONAL_STORE_MUST_DIFFER"):
        asyncio.run(
            validate_production_v2_serving_readiness(
                workspace_root=ROOT,
                mnemo_config=config,
                server_config=server,
                identity_manifest=MANIFEST,
            )
        )
