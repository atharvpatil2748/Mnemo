"""Disposable Full V2 serving identity refuses incomplete or changed evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from mnemo.phase85.isolated_v2_identity import IsolatedV2DatabaseIdentityVerifier

CAPABILITIES = (
    "representation_derivation_v2",
    "language_text_v2",
    "multilingual_embedding_v2",
    "multilingual_vector_v2",
)


def _payload_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _fixture(root: Path) -> tuple[Path, tuple[str, ...]]:
    run = uuid4()
    notebook = uuid5(NAMESPACE_URL, f"mnemo:isolated-rebuild-canary:{run.hex}")
    runtime = root / "scratch/isolated_rebuilds" / run.hex
    runtime.mkdir(parents=True)
    database = runtime / "mnemo.db"
    ids = tuple(str(uuid4()) for _ in CAPABILITIES)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE notebooks(notebook_id TEXT);"
            "CREATE TABLE sources(notebook_id TEXT,document_id TEXT);"
            "CREATE TABLE documents(document_id TEXT,current_hash TEXT);"
            "CREATE TABLE index_generations(generation_id TEXT,capability TEXT,profile TEXT,"
            "model_identity TEXT,configuration_digest TEXT,dimensions INTEGER,state TEXT,"
            "item_count INTEGER,checksum TEXT);"
            "CREATE TABLE index_generation_coverage(generation_id TEXT,completeness TEXT,"
            "expected_count INTEGER,succeeded_count INTEGER,failed_count INTEGER,"
            "skipped_count INTEGER);"
            "CREATE TABLE multilingual_coverage_manifests_v2(generation_id TEXT,"
            "profile_fingerprint TEXT,payload TEXT,payload_hash TEXT);"
            "CREATE TABLE multilingual_embeddings_v2(generation_id TEXT,vector_space TEXT);"
            "CREATE TABLE index_generation_sources(generation_id TEXT,source_id TEXT,"
            "source_kind TEXT);"
        )
        connection.execute("INSERT INTO notebooks VALUES(?)", (str(notebook),))
        connection.execute("INSERT INTO documents VALUES(?,?)", ("fixture-document", "a" * 64))
        connection.execute("INSERT INTO sources VALUES(?,?)", (str(notebook), "fixture-document"))
        for capability, identifier in zip(CAPABILITIES, ids, strict=True):
            vector = capability in CAPABILITIES[2:]
            connection.execute(
                "INSERT INTO index_generations VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    capability,
                    f"isolated-rebuild:{notebook}",
                    "BAAI/bge-m3@revision" if vector else None,
                    "c" * 64,
                    1024 if vector else None,
                    "ready",
                    1,
                    "d" * 64,
                ),
            )
            connection.execute(
                "INSERT INTO index_generation_coverage VALUES(?,?,?,?,?,?)",
                (identifier, "complete", 1, 1, 0, 0),
            )
            payload = {"generation": identifier, "coverage": 1}
            connection.execute(
                "INSERT INTO multilingual_coverage_manifests_v2 VALUES(?,?,?,?)",
                (identifier, "e" * 64, json.dumps(payload), _payload_hash(payload)),
            )
        connection.execute("INSERT INTO multilingual_embeddings_v2 VALUES(?,?)", (ids[2], "f" * 64))
        connection.execute(
            "INSERT INTO index_generation_sources VALUES(?,?,?)",
            (ids[3], ids[2], "generation"),
        )
    (runtime / "rebuild-status.json").write_text(
        json.dumps(
            {
                "runtime": str(runtime.resolve()),
                "activation": "inactive",
                "notebook_id": str(notebook),
                "run_id": run.hex,
                "sources": [{"relative_path": "fixture.txt", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    return runtime, ids


def test_isolated_full_v2_identity_binds_exact_ready_generation_set(tmp_path: Path) -> None:
    runtime, ids = _fixture(tmp_path)
    verifier = IsolatedV2DatabaseIdentityVerifier(workspace_root=tmp_path, runtime=runtime)
    artifact = verifier.artifact
    assert tuple(str(value) for value in artifact.generation_ids) == ids
    verifier.verify(expected_database_identity=artifact.database_identity)
    binding = verifier.resolve_vector_embedding_generation(
        active_generation_ids=artifact.generation_ids,
        expected_database_identity=artifact.database_identity,
    )
    assert str(binding.embedding_generation_id) == ids[2]
    with pytest.raises(ValueError, match="DATABASE_BINDING_MISMATCH"):
        verifier.verify(expected_database_identity="0" * 64)
    with sqlite3.connect(runtime / "mnemo.db") as connection:
        connection.execute(
            "UPDATE index_generations SET checksum=? WHERE generation_id IN (?,?)",
            ("0" * 64, ids[2], ids[3]),
        )
    with pytest.raises(ValueError, match="ISOLATED_V2_BUILD_CHANGED"):
        verifier.verify(expected_database_identity=artifact.database_identity)


def test_isolated_full_v2_identity_rejects_incomplete_and_external_path(tmp_path: Path) -> None:
    runtime, ids = _fixture(tmp_path)
    with sqlite3.connect(runtime / "mnemo.db") as connection:
        connection.execute(
            "UPDATE index_generation_coverage SET failed_count=1 WHERE generation_id=?",
            (ids[3],),
        )
    with pytest.raises(ValueError, match="not complete"):
        IsolatedV2DatabaseIdentityVerifier(workspace_root=tmp_path, runtime=runtime)
    with pytest.raises(ValueError, match="not a governed isolated rebuild"):
        IsolatedV2DatabaseIdentityVerifier(workspace_root=tmp_path, runtime=tmp_path)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("DELETE FROM notebooks", "notebook identity"),
        ("DELETE FROM index_generations WHERE capability='language_text_v2'", "incomplete"),
        (
            "UPDATE multilingual_coverage_manifests_v2 SET profile_fingerprint='wrong' "
            "WHERE generation_id=(SELECT generation_id FROM index_generations "
            "WHERE capability='language_text_v2')",
            "profile fingerprints",
        ),
        (
            "UPDATE index_generations SET dimensions=768 WHERE capability='multilingual_vector_v2'",
            "incompatible",
        ),
        ("DELETE FROM multilingual_embeddings_v2", "space"),
        ("UPDATE index_generation_sources SET source_id='wrong'", "dependency"),
        (
            "UPDATE multilingual_coverage_manifests_v2 SET payload_hash='wrong' "
            "WHERE generation_id=(SELECT generation_id FROM index_generations "
            "WHERE capability='language_text_v2')",
            "not complete",
        ),
    ],
)
def test_isolated_full_v2_identity_rejects_independent_evidence_corruption(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    runtime, _ = _fixture(tmp_path)
    with sqlite3.connect(runtime / "mnemo.db") as connection:
        connection.execute(mutation)
    with pytest.raises(ValueError, match=expected):
        IsolatedV2DatabaseIdentityVerifier(workspace_root=tmp_path, runtime=runtime)
