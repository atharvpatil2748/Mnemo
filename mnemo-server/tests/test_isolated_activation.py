"""Disposable coverage and ancestry tests for the isolated activation gate."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mnemo_server.tools import isolated_activation
from mnemo_server.tools.isolated_activation import REQUIRED, assess_generation_set


def _fixture(tmp_path: Path) -> tuple[Path, UUID, dict[str, UUID]]:
    database = tmp_path / "isolated.db"
    notebook, document, version, occurrence, asset = (uuid4() for _ in range(5))
    generations = {capability: uuid4() for capability in REQUIRED}
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE notebooks(notebook_id TEXT);"
            "CREATE TABLE sources(notebook_id TEXT,document_id TEXT,source_id TEXT);"
            "CREATE TABLE document_versions(version_id TEXT,document_id TEXT);"
            "CREATE TABLE asset_catalog(asset_id TEXT,mime_type TEXT);"
            "CREATE TABLE asset_occurrences(occurrence_id TEXT,document_id TEXT,asset_id TEXT);"
            "CREATE TABLE chunks(id TEXT);"
            "CREATE TABLE ocr_results(derivation_id TEXT,completeness TEXT,"
            "occurrence_id TEXT,document_id TEXT,version_id TEXT);"
            "CREATE TABLE ocr_regions(region_id TEXT,derivation_id TEXT,text TEXT);"
            "CREATE TABLE vision_results(derivation_id TEXT,completeness TEXT,"
            "occurrence_id TEXT,document_id TEXT,version_id TEXT);"
            "CREATE TABLE visual_embeddings(derivation_id TEXT,occurrence_id TEXT,"
            "document_id TEXT,version_id TEXT);"
            "CREATE TABLE index_generations(generation_id TEXT,capability TEXT,state TEXT,"
            "item_count INTEGER,checksum TEXT,model_identity TEXT,dimensions INTEGER);"
            "CREATE TABLE index_generation_coverage(generation_id TEXT,expected_count INTEGER,"
            "succeeded_count INTEGER,failed_count INTEGER,skipped_count INTEGER,"
            "completeness TEXT);"
            "CREATE TABLE index_generation_sources(generation_id TEXT,source_kind TEXT,"
            "source_id TEXT);"
            "CREATE TABLE multilingual_coverage_manifests_v2(generation_id TEXT,"
            "capability TEXT,expected_count INTEGER,succeeded_count INTEGER,"
            "failed_count INTEGER,skipped_count INTEGER,provenance_complete INTEGER,"
            "authorization_compatible INTEGER,payload TEXT,payload_hash TEXT);"
            "CREATE TABLE ocr_projection_rows(generation_id TEXT,occurrence_id TEXT,"
            "document_id TEXT,version_id TEXT,derivation_id TEXT,region_id TEXT);"
            "CREATE TABLE vision_text_projection_rows(generation_id TEXT,occurrence_id TEXT,"
            "document_id TEXT,version_id TEXT,derivation_id TEXT);"
            "CREATE TABLE visual_vector_projection_rows(generation_id TEXT,occurrence_id TEXT,"
            "document_id TEXT,version_id TEXT,derivation_id TEXT);"
            "CREATE TABLE multilingual_embeddings_v2(generation_id TEXT,notebook_id TEXT,"
            "document_id TEXT,version_id TEXT,occurrence_id TEXT,derivation_id TEXT,"
            "representation_type TEXT,vector_space TEXT);"
        )
        connection.execute("INSERT INTO notebooks VALUES(?)", (str(notebook),))
        connection.execute("INSERT INTO sources VALUES(?,?,?)", (str(notebook), str(document), "s"))
        connection.execute(
            "INSERT INTO document_versions VALUES(?,?)", (str(version), str(document))
        )
        connection.execute("INSERT INTO asset_catalog VALUES(?,?)", (str(asset), "image/jpeg"))
        connection.execute(
            "INSERT INTO asset_occurrences VALUES(?,?,?)",
            (str(occurrence), str(document), str(asset)),
        )
        connection.execute("INSERT INTO chunks VALUES('chunk')")
        connection.execute(
            "INSERT INTO ocr_results VALUES(?,?,?,?,?)",
            ("ocr-derivation", "complete", str(occurrence), str(document), str(version)),
        )
        connection.execute(
            "INSERT INTO ocr_regions VALUES('region-1','ocr-derivation','found text')"
        )
        connection.execute(
            "INSERT INTO vision_results VALUES(?,?,?,?,?)",
            ("vision-derivation", "complete", str(occurrence), str(document), str(version)),
        )
        connection.execute(
            "INSERT INTO visual_embeddings VALUES(?,?,?,?)",
            ("visual-derivation", str(occurrence), str(document), str(version)),
        )
        for capability, identifier in generations.items():
            count = (
                3
                if capability
                in {
                    "representation_derivation_v2",
                    "language_text_v2",
                    "multilingual_embedding_v2",
                    "multilingual_vector_v2",
                }
                else 1
            )
            connection.execute(
                "INSERT INTO index_generations VALUES(?,?,?,?,?,?,?)",
                (
                    str(identifier),
                    capability,
                    "ready",
                    count,
                    "a" * 64,
                    "BAAI/bge-m3@revision" if capability.startswith("multilingual_") else "model",
                    1024 if capability.startswith("multilingual_") else None,
                ),
            )
            connection.execute(
                "INSERT INTO index_generation_coverage VALUES(?,?,?,?,?,?)",
                (str(identifier), count, count, 0, 0, "complete"),
            )
            connection.execute(
                "INSERT INTO index_generation_sources VALUES(?,?,?)",
                (str(identifier), "version", str(version)),
            )
            if capability in {
                "representation_derivation_v2",
                "language_text_v2",
                "multilingual_embedding_v2",
                "multilingual_vector_v2",
            }:
                payload = json.dumps({"generation_id": str(identifier), "capability": capability})
                connection.execute(
                    "INSERT INTO multilingual_coverage_manifests_v2 VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(identifier),
                        capability,
                        count,
                        count,
                        0,
                        0,
                        1,
                        1,
                        payload,
                        hashlib.sha256(payload.encode()).hexdigest(),
                    ),
                )
        for table, capability, derivation in (
            ("ocr_projection_rows", "ocr_text", "ocr-derivation"),
            ("vision_text_projection_rows", "vision_text", "vision-derivation"),
            ("visual_vector_projection_rows", "visual_vector", "visual-derivation"),
        ):
            values = (
                str(generations[capability]),
                str(occurrence),
                str(document),
                str(version),
                derivation,
            )
            connection.execute(
                f"INSERT INTO {table} VALUES({','.join('?' for _ in values)}"
                + (",?)" if capability == "ocr_text" else ")"),
                (*values, "region-1") if capability == "ocr_text" else values,
            )
        for kind, occurrence_value, derivation in (
            ("unicode_semantic_text", None, None),
            ("ocr_text", str(occurrence), "ocr-derivation"),
            ("vision_text", str(occurrence), "vision-derivation"),
        ):
            connection.execute(
                "INSERT INTO multilingual_embeddings_v2 VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(generations["multilingual_embedding_v2"]),
                    str(notebook),
                    str(document),
                    str(version),
                    occurrence_value,
                    derivation,
                    kind,
                    "space",
                ),
            )
    return database, notebook, generations


def test_missing_applicable_ocr_derivation_denies_activation(tmp_path: Path) -> None:
    database, notebook, generations = _fixture(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM ocr_results")
    decision = assess_generation_set(
        database=database,
        notebook_id=notebook,
        generation_ids=generations,
        vector_space="space",
        embedding_model_identity="BAAI/bge-m3@revision",
    )
    assert decision["eligible_for_activation"] is False
    assert "ocr:applicable_occurrence_coverage_incomplete" in decision["blockers"]


def test_isolated_gate_rejects_missing_or_mismatched_generation(tmp_path: Path) -> None:
    database, notebook, generations = _fixture(tmp_path)
    selected = dict(generations)
    selected.pop("ocr_text")
    missing = assess_generation_set(
        database=database,
        notebook_id=notebook,
        generation_ids=selected,
        vector_space="space",
        embedding_model_identity="BAAI/bge-m3@revision",
    )
    assert not missing["eligible_for_activation"]
    assert "generation_set_incomplete_or_duplicated" in missing["blockers"]
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE index_generations SET state='building' WHERE capability='ocr_text'"
        )
    incomplete = assess_generation_set(
        database=database,
        notebook_id=notebook,
        generation_ids=generations,
        vector_space="space",
        embedding_model_identity="BAAI/bge-m3@revision",
    )
    assert not incomplete["eligible_for_activation"]
    assert "ocr_text:not_complete_ready" in incomplete["blockers"]


def test_isolated_gate_requires_exact_coverage_and_identity(tmp_path: Path) -> None:
    database, notebook, generations = _fixture(tmp_path)
    result = assess_generation_set(
        database=database,
        notebook_id=notebook,
        generation_ids=generations,
        vector_space="space",
        embedding_model_identity="BAAI/bge-m3@revision",
    )
    assert result["expected"] == {"canonical": 1, "ocr": 1, "vision": 1, "visual": 1}
    assert result["eligible_for_activation"]
    assert (
        "multilingual_embedding_v2:unicode_semantic_text_coverage_incomplete"
        not in result["blockers"]
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM multilingual_embeddings_v2 WHERE representation_type='ocr_text'"
        )
    missing = assess_generation_set(
        database=database,
        notebook_id=notebook,
        generation_ids=generations,
        vector_space="space",
        embedding_model_identity="BAAI/bge-m3@revision",
    )
    assert "multilingual_embedding_v2:ocr_text_coverage_incomplete" in missing["blockers"]


@pytest.mark.parametrize(
    ("statement", "blocker"),
    [
        (
            "UPDATE notebooks SET notebook_id='wrong'",
            "isolated_notebook_identity_mismatch",
        ),
        (
            "DELETE FROM document_versions",
            "source_versions_absent",
        ),
        (
            "DELETE FROM index_generations WHERE capability='visual_vector'",
            "visual_vector:generation_missing_or_wrong_capability",
        ),
        (
            "UPDATE index_generation_coverage SET failed_count=1 "
            "WHERE generation_id IN "
            "(SELECT generation_id FROM index_generations WHERE capability='vision_text')",
            "vision_text:not_complete_ready",
        ),
        (
            "UPDATE index_generations SET model_identity='wrong' "
            "WHERE capability='multilingual_embedding_v2'",
            "multilingual_embedding_v2:embedding_model_incompatible",
        ),
        (
            "UPDATE multilingual_embeddings_v2 SET occurrence_id=NULL "
            "WHERE representation_type='ocr_text'",
            "multilingual_embedding_v2:derived_ancestry_missing",
        ),
        (
            "UPDATE visual_vector_projection_rows SET derivation_id='wrong'",
            "visual_vector:projection_derivation_ancestry_invalid",
        ),
        (
            "UPDATE multilingual_embeddings_v2 SET vector_space='wrong' "
            "WHERE representation_type='vision_text'",
            "multilingual_embedding_v2:scope_or_space_mismatch",
        ),
        (
            "UPDATE ocr_projection_rows SET version_id='wrong'",
            "ocr_text:projection_version_ancestry_invalid",
        ),
        (
            "UPDATE ocr_projection_rows SET derivation_id='wrong'",
            "ocr_text:projection_derivation_ancestry_invalid",
        ),
        (
            "UPDATE ocr_projection_rows SET region_id='wrong'",
            "ocr_text:projection_region_ancestry_invalid",
        ),
        (
            "DELETE FROM vision_text_projection_rows",
            "vision_text:projection_coverage_incomplete",
        ),
        (
            "UPDATE index_generation_sources SET source_id='wrong' "
            "WHERE source_kind='version' AND generation_id IN "
            "(SELECT generation_id FROM index_generations WHERE capability='ocr_text')",
            "ocr_text:source_version_ancestry_invalid",
        ),
        (
            "DELETE FROM multilingual_coverage_manifests_v2 WHERE capability='language_text_v2'",
            "language_text_v2:coverage_manifest_invalid",
        ),
        (
            "UPDATE multilingual_coverage_manifests_v2 SET payload_hash='wrong' "
            "WHERE capability='multilingual_embedding_v2'",
            "multilingual_embedding_v2:coverage_manifest_invalid",
        ),
        (
            "DROP TABLE multilingual_coverage_manifests_v2",
            "language_text_v2:coverage_manifest_invalid",
        ),
    ],
)
def test_isolated_gate_rejects_broken_ancestry_or_compatibility(
    tmp_path: Path, statement: str, blocker: str
) -> None:
    database, notebook, generations = _fixture(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(statement)
    result = assess_generation_set(
        database=database,
        notebook_id=notebook,
        generation_ids=generations,
        vector_space="space",
        embedding_model_identity="BAAI/bge-m3@revision",
    )
    assert not result["eligible_for_activation"]
    assert blocker in result["blockers"]


def test_activation_never_promotes_incomplete_or_changed_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "activation.json"
    selected = {name: uuid4() for name in REQUIRED}
    notebook = uuid4()
    opened: list[str] = []

    class Store:
        def __init__(self, database: Path) -> None:
            assert database == tmp_path / "isolated.db"

        async def open(self) -> None:
            opened.append("open")

        async def promote_index_generation_set(self, identifiers: tuple[UUID, ...]) -> bool:
            assert identifiers == tuple(selected[name] for name in REQUIRED)
            opened.append("promote")
            return False

        async def close(self) -> None:
            opened.append("close")

    monkeypatch.setattr(isolated_activation, "SQLiteStore", Store)
    monkeypatch.setattr(
        isolated_activation,
        "assess_generation_set",
        lambda **_: {
            "notebook_id": str(notebook),
            "eligible_for_activation": False,
            "blockers": ["missing_ocr"],
        },
    )
    args = dict(
        database=tmp_path / "isolated.db",
        notebook_id=notebook,
        generation_ids=selected,
        vector_space="space",
        embedding_model_identity="model",
        report_path=report_path,
    )
    denied = asyncio.run(isolated_activation.activate_isolated_generation_set(**args))
    assert denied["blockers"] == ["missing_ocr"]
    assert opened == []
    monkeypatch.setattr(
        isolated_activation,
        "assess_generation_set",
        lambda **_: {"notebook_id": str(notebook), "eligible_for_activation": True, "blockers": []},
    )
    changed = asyncio.run(isolated_activation.activate_isolated_generation_set(**args))
    assert opened == ["open", "promote", "close"]
    assert changed["active"] is False
    assert changed["blockers"] == ["generation_changed_before_atomic_promotion"]
    assert json.loads(report_path.read_text(encoding="utf-8")) == changed

    async def promote_success(self: Store, identifiers: tuple[UUID, ...]) -> bool:
        assert identifiers == tuple(selected[name] for name in REQUIRED)
        return True

    monkeypatch.setattr(Store, "promote_index_generation_set", promote_success)
    admitted = asyncio.run(isolated_activation.activate_isolated_generation_set(**args))
    assert admitted["active"] is True
    assert admitted["blockers"] == []
