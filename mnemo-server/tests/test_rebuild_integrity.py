"""The build gate is fail-closed and never promotes or repairs indexed state."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mnemo_server.tools import rebuild_integrity
from mnemo_server.tools.isolated_activation import REQUIRED
from mnemo_server.tools.source_manifest import build_source_manifest

from scripts.phase8_5_16_prepare_evaluation import _project_structured_versions


def test_build_only_projection_stage_still_processes_structured_ir() -> None:
    first, second = uuid4(), uuid4()
    seen = []

    async def get_parsed_document(version_id):  # type: ignore[no-untyped-def]
        return object() if version_id == first else None

    async def project_structured_document(version_id, document):  # type: ignore[no-untyped-def]
        seen.append((version_id, document))
        return True

    changed, missing = asyncio.run(
        _project_structured_versions(
            SimpleNamespace(project_structured_document=project_structured_document),
            SimpleNamespace(get_parsed_document=get_parsed_document),
            (first, second),
        )
    )
    assert changed == 1
    assert missing == [str(second)]
    assert len(seen) == 1 and seen[0][0] == first


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    corpus = tmp_path / "originals"
    corpus.mkdir()
    (corpus / "one.txt").write_bytes(b"immutable original")
    manifest = build_source_manifest(corpus=corpus, label="personal_44", expected_count=1)
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    runtime = tmp_path / "scratch" / "two_corpus_rebuilds" / ("a" * 32)
    runtime.mkdir(parents=True)
    database = runtime / "mnemo.db"
    notebook = str(uuid4())
    version = str(uuid4())
    ir_path = runtime / "files" / "parsed" / version[:8] / f"{version}.ir.json"
    ir_path.parent.mkdir(parents=True)
    ir_path.write_text(json.dumps({"blocks": []}), encoding="utf-8")
    occurrence = str(uuid4())
    generation_ids = {name: str(uuid4()) for name in REQUIRED}
    serving_ids = tuple(
        rebuild_integrity.UUID(generation_ids[name]) for name in REQUIRED if name.endswith("_v2")
    )
    status = {
        "notebook_id": notebook,
        "sources": [
            {
                "relative_path": "one.txt",
                "sha256": manifest["sources"][0]["sha256"],
                "byte_size": len(b"immutable original"),
                "prior_document_id": None,
                "prior_version_id": None,
            }
        ],
        "rebuild_owner": {
            "input_identity": manifest["notebook_input_identity"],
            "label": manifest["label"],
        },
    }
    monkeypatch.setattr(rebuild_integrity, "resolve_governed_rebuild_runtime", lambda **_: status)
    monkeypatch.setattr(
        rebuild_integrity,
        "inspect_isolated_ingestion",
        lambda **_: {
            "counts": {"sources": 1},
            "sources": [{"version_id": version}],
        },
    )
    monkeypatch.setattr(
        rebuild_integrity,
        "assess_generation_set",
        lambda **_: {
            "eligible_for_activation": True,
            "expected": {"canonical": 1, "ocr": 1, "vision": 1, "visual": 1},
            "embedding_counts": {"unicode_semantic_text": 1, "ocr_text": 1},
        },
    )
    monkeypatch.setattr(
        rebuild_integrity.ModelProfileDocument,
        "from_file",
        lambda _path: SimpleNamespace(
            select=lambda _name: SimpleNamespace(
                models={"multilingual_embedding": SimpleNamespace(model="model", revision="rev")}
            )
        ),
    )
    artifact = SimpleNamespace(database_identity="identity", generation_ids=serving_ids)
    monkeypatch.setattr(
        rebuild_integrity,
        "IsolatedV2DatabaseIdentityVerifier",
        lambda **_: SimpleNamespace(artifact=artifact, verify=lambda **__: None),
    )

    async def active_alias(_database: Path) -> tuple[tuple[rebuild_integrity.UUID, ...], str]:
        return serving_ids, "digest"

    monkeypatch.setattr(rebuild_integrity, "_active_alias", active_alias)
    stages = {
        name: "complete"
        for name in (
            "canonical_ingestion",
            "paddleocr",
            "vision",
            "visual",
            "projections",
            "multilingual",
        )
    }
    (runtime / "complete-rebuild-status.json").write_text(
        json.dumps(
            {
                "notebook_id": notebook,
                "activation": "complete_v2_build_ready",
                "stages": stages,
                "generations": generation_ids,
                "full_v2_serving": {"alias_set_digest": "digest"},
            }
        ),
        encoding="utf-8",
    )
    (runtime / "multilingual-stage.json").write_text(
        json.dumps({"vector_space": "space"}), encoding="utf-8"
    )
    (runtime / "activation-decision.json").write_text(
        json.dumps({"active": True}), encoding="utf-8"
    )
    (runtime / "full-v2-serving.json").write_text(
        json.dumps(
            {
                "state": "active_internal_only",
                "notebook_id": notebook,
                "alias_set_digest": "digest",
                "generation_ids": [str(item) for item in serving_ids],
            }
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE active_index_generations(generation_id TEXT);"
            "CREATE TABLE index_generations(generation_id TEXT,capability TEXT,state TEXT);"
            "CREATE TABLE structured_table_projections(version_id TEXT,block_ordinal INTEGER,"
            "row_count INTEGER,generation_id TEXT);"
            "CREATE TABLE asset_catalog(asset_id TEXT,content_hash TEXT);"
            "CREATE TABLE asset_occurrences(occurrence_id TEXT,document_id TEXT,"
            "version_id TEXT,asset_id TEXT);"
        )
        connection.executemany(
            "INSERT INTO active_index_generations VALUES(?)",
            [(identifier,) for identifier in generation_ids.values()],
        )
        connection.executemany(
            "INSERT INTO index_generations VALUES(?,?,?)",
            [(identifier, name, "ready") for name, identifier in generation_ids.items()],
        )
        connection.execute("INSERT INTO asset_catalog VALUES('asset','hash')")
        connection.execute(
            "INSERT INTO asset_occurrences VALUES(?,?,?,?)",
            (occurrence, "document", version, "asset"),
        )
    return runtime, manifest_path, database


def test_complete_isolated_notebook_passes_build_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, manifest, _ = _fixture(tmp_path, monkeypatch)
    result = rebuild_integrity.verify_rebuild_integrity(
        workspace=tmp_path, runtime=runtime, source_manifest=manifest, expected_count=1
    )
    assert result["status"] == "pass"
    assert result["source_count"] == 1
    assert len(result["active_generations"]) == len(REQUIRED)


def test_table_block_requires_active_structured_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, manifest, database = _fixture(tmp_path, monkeypatch)
    version = rebuild_integrity.inspect_isolated_ingestion(
        database=database, files=runtime / "files", notebook_id="", sources=()
    )["sources"][0]["version_id"]
    ir_path = runtime / "files" / "parsed" / version[:8] / f"{version}.ir.json"
    ir_path.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "type": "table",
                        "ordinal": 0,
                        "header_row_count": 1,
                        "rows": [["Name"], ["Ada"]],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="structured-table projection coverage"):
        rebuild_integrity.verify_rebuild_integrity(
            workspace=tmp_path, runtime=runtime, source_manifest=manifest, expected_count=1
        )
    structured_id = str(uuid4())
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO index_generations VALUES(?,?,?)",
            (structured_id, "structured_table", "ready"),
        )
        connection.execute("INSERT INTO active_index_generations VALUES(?)", (structured_id,))
        connection.execute(
            "INSERT INTO structured_table_projections VALUES(?,?,?,?)",
            (version, 0, 1, structured_id),
        )
    result = rebuild_integrity.verify_rebuild_integrity(
        workspace=tmp_path, runtime=runtime, source_manifest=manifest, expected_count=1
    )
    assert result["structured_table_projections"] == 1


@pytest.mark.parametrize("fault", ["missing_active", "wrong_alias", "wrong_version", "stage"])
def test_incomplete_isolated_notebook_cannot_pass_build_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    runtime, manifest, database = _fixture(tmp_path, monkeypatch)
    if fault == "missing_active":
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM active_index_generations WHERE rowid=1")
    elif fault == "wrong_version":
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE asset_occurrences SET version_id='foreign'")
    else:
        filename = (
            "full-v2-serving.json" if fault == "wrong_alias" else "complete-rebuild-status.json"
        )
        path = runtime / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        if fault == "wrong_alias":
            payload["alias_set_digest"] = "stale"
        else:
            payload["stages"]["paddleocr"] = "failed"
        path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        rebuild_integrity.verify_rebuild_integrity(
            workspace=tmp_path, runtime=runtime, source_manifest=manifest, expected_count=1
        )


@pytest.mark.parametrize(
    "fault",
    (
        "wrong_source_count",
        "foreign_canary_source",
        "wrong_source_hash",
        "wrong_owner",
        "inactive",
        "generation_missing",
        "coverage_denied",
        "stale_report_alias",
    ),
)
def test_build_integrity_rejects_identity_and_coverage_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    runtime, manifest, _ = _fixture(tmp_path, monkeypatch)
    status = rebuild_integrity.resolve_governed_rebuild_runtime(workspace=tmp_path, runtime=runtime)
    selected: tuple[str, ...] | None = None
    expected_count = 1
    if fault == "wrong_source_count":
        expected_count = 2
    elif fault == "foreign_canary_source":
        selected = ("unknown.txt",)
    elif fault == "wrong_source_hash":
        status["sources"][0]["sha256"] = "0" * 64
    elif fault == "wrong_owner":
        status["rebuild_owner"]["input_identity"] = "foreign"
    elif fault == "coverage_denied":
        monkeypatch.setattr(
            rebuild_integrity,
            "assess_generation_set",
            lambda **_: {"eligible_for_activation": False},
        )
    else:
        path = runtime / "complete-rebuild-status.json"
        complete = json.loads(path.read_text(encoding="utf-8"))
        if fault == "inactive":
            complete["activation"] = "inactive"
        elif fault == "generation_missing":
            complete["generations"].pop("ocr_text")
        else:
            complete["full_v2_serving"]["alias_set_digest"] = "stale"
        path.write_text(json.dumps(complete), encoding="utf-8")
    with pytest.raises(ValueError):
        rebuild_integrity.verify_rebuild_integrity(
            workspace=tmp_path,
            runtime=runtime,
            source_manifest=manifest,
            expected_count=expected_count,
            selected_relative_paths=selected,
        )
