"""Disposable tests for the non-serving isolated rebuild canary boundary."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mnemo_server.tools import isolated_activation, isolated_rebuild
from mnemo_server.tools.isolated_rebuild import (
    VerifiedSource,
    assess_canary_coverage,
    inspect_isolated_ingestion,
    run_canary,
    verify_sources,
)
from mnemo_server.tools.source_manifest import build_source_manifest, verify_source_manifest


def test_manifest_authority_needs_no_old_database(tmp_path: Path) -> None:
    corpus = tmp_path / "originals"
    corpus.mkdir()
    original = corpus / "one.txt"
    original.write_bytes(b"independent original\n")
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(build_source_manifest(corpus=corpus, label="isolated", expected_count=1)),
        encoding="utf-8",
    )
    assert verify_source_manifest(manifest=manifest, corpus=corpus)["expected_count"] == 1
    verified = verify_sources(corpus=corpus, source_manifest=manifest, includes=("one.txt",))
    assert verified[0].sha256 == hashlib.sha256(original.read_bytes()).hexdigest()
    assert verified[0].prior_document_id is None
    assert verified[0].prior_version_id is None
    with pytest.raises(ValueError, match="absent"):
        verify_sources(corpus=corpus, source_manifest=manifest, includes=("other.txt",))
    original.write_bytes(b"changed")
    with pytest.raises(ValueError, match="differs"):
        verify_source_manifest(manifest=manifest, corpus=corpus)


def test_manifest_rejects_derived_file_and_duplicate_hash(tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_bytes(b"same")
    (tmp_path / "two.txt").write_bytes(b"same")
    with pytest.raises(ValueError, match="duplicate"):
        build_source_manifest(corpus=tmp_path, label="pair", expected_count=2)
    (tmp_path / "two.txt").write_bytes(b"different")
    (tmp_path / "index.db").write_bytes(b"derived")
    with pytest.raises(ValueError, match="unsupported or derived"):
        build_source_manifest(corpus=tmp_path, label="pair", expected_count=2)


def test_vision_gpu_gate_requires_exact_full_gpu_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, vram: int) -> None:
            self.vram = vram

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "models": [
                    {"name": "vision", "digest": "revision", "size": 100, "size_vram": self.vram}
                ]
            }

    monkeypatch.setattr(isolated_rebuild.httpx, "get", lambda *args, **kwargs: Response(100))
    assert (
        isolated_rebuild._verify_vision_gpu(model="vision", revision="revision")["gpu_bytes"] == 100
    )
    monkeypatch.setattr(isolated_rebuild.httpx, "get", lambda *args, **kwargs: Response(50))
    with pytest.raises(RuntimeError, match="wholly on GPU"):
        isolated_rebuild._verify_vision_gpu(model="vision", revision="revision")


def test_inspect_isolated_ingestion_verifies_original_ir_and_chunk_span(tmp_path: Path) -> None:
    original = b"ordered test source\n"
    digest = hashlib.sha256(original).hexdigest()
    notebook, document, version = (str(uuid4()) for _ in range(3))
    database = tmp_path / "mnemo.db"
    files = tmp_path / "files"
    raw = files / digest[:2] / digest[2:] / "raw.txt"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(original)
    ir = files / "parsed" / version[:8] / f"{version}.ir.json"
    ir.parent.mkdir(parents=True)
    ir.write_text(
        json.dumps({"metadata": {"content_hash": digest}, "blocks": [{"ordinal": 0}]}),
        encoding="utf-8",
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE notebooks(notebook_id TEXT);"
            "CREATE TABLE documents(document_id TEXT,current_version_id TEXT,current_hash TEXT);"
            "CREATE TABLE document_versions(version_id TEXT);"
            "CREATE TABLE sources(notebook_id TEXT,document_id TEXT);"
            "CREATE TABLE asset_catalog(asset_id TEXT,content_hash TEXT);"
            "CREATE TABLE document_binary_references(version_id TEXT,role TEXT,"
            "asset_id TEXT,byte_size INTEGER);"
            "CREATE TABLE chunks(version_id TEXT,position_chunk_index INTEGER,"
            "source_start_ordinal INTEGER,source_end_ordinal INTEGER);"
        )
        connection.execute("INSERT INTO notebooks VALUES(?)", (notebook,))
        connection.execute("INSERT INTO documents VALUES(?,?,?)", (document, version, digest))
        connection.execute("INSERT INTO document_versions VALUES(?)", (version,))
        connection.execute("INSERT INTO sources VALUES(?,?)", (notebook, document))
        connection.execute("INSERT INTO asset_catalog VALUES('asset',?)", (digest,))
        connection.execute(
            "INSERT INTO document_binary_references VALUES(?,'original','asset',?)",
            (version, len(original)),
        )
        connection.execute("INSERT INTO chunks VALUES(?,0,0,0)", (version,))
    source = VerifiedSource(
        relative_path="one.txt",
        sha256=digest,
        byte_size=len(original),
        prior_document_id=document,
        prior_version_id=version,
    )
    result = inspect_isolated_ingestion(
        database=database, files=files, notebook_id=notebook, sources=(source,)
    )
    assert result["counts"]["chunks"] == 1
    assert result["sources"][0]["original_sha256_verified"] is True
    assert result["sources"][0]["block_ordinals_contiguous"] is True


def test_isolated_stage_and_v2_probe_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> object:
        calls.append(command)
        assert kwargs["cwd"] == tmp_path
        if command == ["build", "ocr"]:
            assert kwargs["env"]["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] == "True"
            assert kwargs["env"]["OMP_NUM_THREADS"] == "1"
        return subprocess.CompletedProcess(command, 0, stdout='{"evidence": []}', stderr="")

    monkeypatch.setattr(isolated_rebuild.subprocess, "run", run)
    isolated_rebuild._run_stage(["build", "projection"], workspace=tmp_path, stage="projection")
    isolated_rebuild._run_stage(["build", "ocr"], workspace=tmp_path, stage="paddleocr_inference")
    assert calls[-1] == ["build", "ocr"]
    result = isolated_rebuild._probe_v2_retrieval(
        workspace=tmp_path,
        runtime=tmp_path / "canary",
        query="cutting tool",
        model_cache=tmp_path / "models",
        clip_snapshot=tmp_path / "clip",
    )
    assert result == {"evidence": []}
    assert "--clip-snapshot" in calls[-1]

    monkeypatch.setattr(
        isolated_rebuild.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 2, stdout="", stderr="failed"
        ),
    )
    with pytest.raises(RuntimeError, match="projection failed"):
        isolated_rebuild._run_stage(["build"], workspace=tmp_path, stage="projection")
    with pytest.raises(RuntimeError, match="probe failed"):
        isolated_rebuild._probe_v2_retrieval(
            workspace=tmp_path,
            runtime=tmp_path / "canary",
            query="question",
            model_cache=tmp_path,
            clip_snapshot=tmp_path,
        )


def test_logged_stage_streams_and_preserves_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    isolated_rebuild._run_stage(
        [
            sys.executable,
            "-c",
            "import os; print('live marker ' + "
            "os.environ['MNEMO_REBUILD_LIVE_PROGRESS'], flush=True)",
        ],
        workspace=tmp_path,
        stage="paddleocr_inference",
        log_runtime=runtime,
    )
    assert "live marker" in capsys.readouterr().err
    assert "live marker 1" in (runtime / "logs" / "paddleocr_inference.log").read_text()
    with pytest.raises(RuntimeError, match="failed with exit 7"):
        isolated_rebuild._run_stage(
            [sys.executable, "-c", "print('failure marker', flush=True); raise SystemExit(7)"],
            workspace=tmp_path,
            stage="vision_and_visual_inference",
            log_runtime=runtime,
        )
    assert "failure marker" in capsys.readouterr().err
    assert "failure marker" in (runtime / "logs" / "vision_and_visual_inference.log").read_text()


def test_complete_canary_orchestrates_governed_stages_on_disposable_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    original = corpus / "source.txt"
    original.write_text("immutable source", encoding="utf-8")
    source_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    runtime = tmp_path / "canary"
    runtime.mkdir()
    (runtime / "files").mkdir()
    database = runtime / "mnemo.db"
    notebook = str(uuid4())
    projection_ids = {name: str(uuid4()) for name in isolated_activation.REQUIRED[:3]}
    multilingual_ids = {name: str(uuid4()) for name in isolated_activation.REQUIRED[3:]}
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE index_generations(generation_id TEXT,capability TEXT)")
        connection.executemany(
            "INSERT INTO index_generations VALUES(?,?)",
            [(identifier, capability) for capability, identifier in projection_ids.items()],
        )
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    report = {
        "run_id": "canary-test",
        "notebook_id": notebook,
        "runtime": str(runtime),
        "sources": [{"relative_path": "source.txt", "sha256": source_hash}],
        "stages": {"canonical_ingestion": "complete"},
    }
    monkeypatch.setattr(isolated_rebuild, "run_canary", lambda **kwargs: report)
    monkeypatch.setattr(
        isolated_rebuild,
        "_embedding_model_identity",
        lambda _workspace: "BAAI/bge-m3@revision",
    )

    def stage(
        command: list[str],
        *,
        workspace: Path,
        stage: str,
        timeout_seconds: int = 1200,
        log_runtime: Path | None = None,
    ) -> None:
        assert workspace == tmp_path
        assert "--database" in command or "--runtime" in command
        if stage in {"paddleocr_inference", "vision_and_visual_inference"}:
            payload = {
                "counts": {
                    name: 1 for name in ("ocr_results", "vision_results", "visual_embeddings")
                }
            }
            Path(command[command.index("--output") + 1]).write_text(
                json.dumps(payload), encoding="utf-8"
            )
        elif stage == "text_and_visual_projections":
            payload = {
                "statuses": [
                    {"generation_id": identifier} for identifier in projection_ids.values()
                ]
            }
            (runtime / "projection-stage.json").write_text(json.dumps(payload), encoding="utf-8")
        else:
            assert stage == "multilingual_embeddings"
            payload = {"generations": multilingual_ids, "vector_space": "space"}
            (runtime / "multilingual-stage.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(isolated_rebuild, "_run_stage", stage)

    async def activate(**kwargs: object) -> dict[str, object]:
        assert kwargs["notebook_id"] == UUID(notebook)
        assert set(kwargs["generation_ids"]) == set(isolated_activation.REQUIRED)
        return {"active": True, "eligible_for_activation": True}

    async def compose(**kwargs: object) -> dict[str, object]:
        assert kwargs["runtime"] == runtime
        return {"state": "active_internal_only", "alias_set_digest": "a" * 64}

    monkeypatch.setattr(isolated_rebuild, "activate_isolated_generation_set", activate)
    monkeypatch.setattr(isolated_activation, "compose_isolated_full_v2_alias", compose)
    monkeypatch.setattr(
        isolated_rebuild,
        "_probe_v2_retrieval",
        lambda **kwargs: {
            "representation_decisions": [
                {"representation": name, "status": "searched"}
                for name in ("canonical_text", "ocr_text", "vision_analysis", "multilingual_text")
            ],
            "evidence": [{"representation": "ocr_text"}],
        },
    )
    result = isolated_rebuild.run_complete_canary(
        workspace=tmp_path,
        corpus=corpus,
        source_database=database,
        includes=("source.txt",),
        paddle_detection_dir=model_dir,
        paddle_recognition_dir=model_dir,
        paddle_detection_sha256="b" * 64,
        paddle_recognition_sha256="c" * 64,
        paddle_language="en",
        vision_model="vision-model",
        vision_revision="revision",
        clip_snapshot=model_dir,
        visual_model="clip-model",
        visual_revision="revision",
        bge_cache=model_dir,
    )
    assert result["activation"] == "complete_v2_retrieval_ready"
    assert result["full_v2_serving"]["alias_set_digest"] == "a" * 64
    assert original.read_bytes() == b"immutable source"
    monkeypatch.setattr(
        isolated_rebuild,
        "_probe_v2_retrieval",
        lambda **_: (_ for _ in ()).throw(AssertionError("build must not query")),
    )
    build_only = isolated_rebuild.run_complete_canary(
        workspace=tmp_path,
        corpus=corpus,
        source_database=database,
        includes=("source.txt",),
        paddle_detection_dir=model_dir,
        paddle_recognition_dir=model_dir,
        paddle_detection_sha256="b" * 64,
        paddle_recognition_sha256="c" * 64,
        paddle_language="en",
        vision_model="vision-model",
        vision_revision="revision",
        clip_snapshot=model_dir,
        visual_model="clip-model",
        visual_revision="revision",
        bge_cache=model_dir,
        perform_v2_probe=False,
    )
    assert build_only["activation"] == "complete_v2_build_ready"


def _source_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.txt").write_bytes(b"immutable source truth\n")
    digest = hashlib.sha256((corpus / "one.txt").read_bytes()).hexdigest()
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE documents(document_id TEXT,current_version_id TEXT,current_hash TEXT)"
        )
        connection.execute(
            "INSERT INTO documents VALUES('prior-document','prior-version',?)", (digest,)
        )
    return corpus, database, digest


def test_verified_source_requires_prior_indexed_exact_bytes(tmp_path: Path) -> None:
    corpus, database, digest = _source_fixture(tmp_path)
    selected = verify_sources(corpus=corpus, source_database=database, includes=("one.txt",))
    assert selected[0].sha256 == digest
    assert selected[0].prior_version_id == "prior-version"
    with pytest.raises(ValueError, match="unique"):
        verify_sources(corpus=corpus, source_database=database, includes=("one.txt", "one.txt"))
    with pytest.raises(ValueError, match="inside the corpus"):
        verify_sources(corpus=corpus, source_database=database, includes=("../source.db",))
    (corpus / "one.txt").write_bytes(b"changed")
    with pytest.raises(ValueError, match="absent or ambiguous"):
        verify_sources(corpus=corpus, source_database=database, includes=("one.txt",))


def test_failed_ingestion_remains_isolated_and_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, database, _ = _source_fixture(tmp_path)

    def failure(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=7, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", failure)
    report = run_canary(
        workspace=tmp_path, corpus=corpus, source_database=database, includes=("one.txt",)
    )
    assert report["activation"] == "inactive"
    assert report["stages"]["canonical_ingestion"] == "failed"
    assert report["ingestion_exit_code"] == 7
    assert (Path(report["runtime"]) / "rebuild-status.json").is_file()


def test_fresh_notebook_identity_and_no_implicit_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, database, _ = _source_fixture(tmp_path)
    commands: list[list[str]] = []

    def success(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", success)
    monkeypatch.setattr(isolated_rebuild, "inspect_isolated_ingestion", lambda **_: {"ok": True})
    monkeypatch.setattr(
        isolated_rebuild,
        "assess_canary_coverage",
        lambda _: {"eligible_for_activation": False},
    )
    first = run_canary(
        workspace=tmp_path,
        corpus=corpus,
        source_database=database,
        includes=("one.txt",),
    )
    second = run_canary(
        workspace=tmp_path,
        corpus=corpus,
        source_database=database,
        includes=("one.txt",),
    )
    assert first["notebook_id"] != second["notebook_id"]
    assert first["runtime"] != second["runtime"]
    assert all(report["activation"] == "inactive" for report in (first, second))
    assert all(report["stages"]["canonical_ingestion"] == "complete" for report in (first, second))
    assert all(command.count("--include") == 1 for command in commands)


def test_coverage_gate_rejects_unbuilt_modalities(tmp_path: Path) -> None:
    database = tmp_path / "canary.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE asset_catalog(asset_id TEXT,mime_type TEXT);"
            "CREATE TABLE asset_occurrences(asset_id TEXT,occurrence_id TEXT);"
            "INSERT INTO asset_catalog VALUES('asset','image/jpeg');"
            "INSERT INTO asset_occurrences VALUES('asset','occurrence');"
            "CREATE TABLE chunks(id TEXT); INSERT INTO chunks VALUES('chunk');"
            "CREATE TABLE multilingual_embeddings_v2(occurrence_id TEXT);"
            "CREATE TABLE index_generations(generation_id TEXT,capability TEXT,state TEXT);"
            "CREATE TABLE active_index_generations(generation_id TEXT);"
        )
        for table in (
            "ocr_results",
            "vision_results",
            "visual_embeddings",
            "ocr_projection_rows",
            "vision_text_projection_rows",
            "visual_vector_projection_rows",
        ):
            connection.execute(f"CREATE TABLE {table}(occurrence_id TEXT)")
    coverage = assess_canary_coverage(database)
    assert coverage["expected_raster_occurrences"] == 1
    assert not coverage["eligible_for_activation"]
    assert "ocr" in coverage["blockers"]
    assert "canonical_multilingual_embeddings" in coverage["blockers"]


def test_complete_canary_orchestrates_exact_isolated_generation_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    original = corpus / "one.txt"
    original.write_bytes(b"immutable original source\n")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    runtime = tmp_path / "scratch" / "isolated_rebuilds" / uuid4().hex
    runtime.mkdir(parents=True)
    (runtime / "files").mkdir()
    database = runtime / "mnemo.db"
    ids = {name: uuid4() for name in isolated_rebuild.REQUIRED}
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE index_generations(generation_id TEXT,capability TEXT)")
        for name in ("ocr_text", "vision_text", "visual_vector"):
            connection.execute("INSERT INTO index_generations VALUES(?,?)", (str(ids[name]), name))
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    monkeypatch.setattr(
        isolated_rebuild,
        "run_canary",
        lambda **_: {
            "run_id": runtime.name,
            "runtime": str(runtime),
            "notebook_id": str(uuid4()),
            "stages": {"canonical_ingestion": "complete"},
            "sources": [{"relative_path": "one.txt", "sha256": digest}],
            "activation": "inactive",
        },
    )
    monkeypatch.setattr(
        isolated_rebuild,
        "_embedding_model_identity",
        lambda _workspace: "BAAI/bge-m3@revision",
    )
    invoked: list[str] = []

    def stage(
        command: list[str],
        *,
        workspace: Path,
        stage: str,
        timeout_seconds: int = 1200,
        log_runtime: Path | None = None,
    ) -> None:
        assert workspace == tmp_path
        invoked.append(stage)
        output = Path(command[command.index("--output") + 1])
        if stage in {"paddleocr_inference", "vision_and_visual_inference"}:
            payload = {"counts": {"ocr_results": 1, "vision_results": 1, "visual_embeddings": 1}}
        elif stage == "text_and_visual_projections":
            payload = {
                "statuses": [
                    {"generation_id": str(ids[name])}
                    for name in ("ocr_text", "vision_text", "visual_vector")
                ]
            }
        else:
            payload = {
                "vector_space": "space",
                "generations": {
                    name: str(ids[name])
                    for name in (
                        "representation_derivation_v2",
                        "language_text_v2",
                        "multilingual_embedding_v2",
                        "multilingual_vector_v2",
                    )
                },
            }
        output.write_text(json.dumps(payload), encoding="utf-8")

    async def activate(**kwargs: object) -> dict[str, object]:
        assert kwargs["generation_ids"] == ids
        return {"active": True, "eligible_for_activation": True}

    monkeypatch.setattr(isolated_rebuild, "_run_stage", stage)
    monkeypatch.setattr(isolated_rebuild, "activate_isolated_generation_set", activate)

    async def compose(**kwargs: object) -> dict[str, object]:
        assert kwargs["runtime"] == runtime
        return {"state": "active_internal_only", "alias_set_digest": "a" * 64}

    monkeypatch.setattr(isolated_activation, "compose_isolated_full_v2_alias", compose)
    monkeypatch.setattr(
        isolated_rebuild,
        "_probe_v2_retrieval",
        lambda **_: {
            "representation_decisions": [
                {"representation": name, "status": "searched"}
                for name in ("canonical_text", "ocr_text", "vision_analysis", "multilingual_text")
            ],
            "evidence": [{"representation": "ocr_text"}],
        },
    )
    arguments = dict(
        workspace=tmp_path,
        corpus=corpus,
        source_database=database,
        includes=("one.txt",),
        paddle_detection_dir=model_dir,
        paddle_recognition_dir=model_dir,
        paddle_detection_sha256="a" * 64,
        paddle_recognition_sha256="b" * 64,
        paddle_language="en",
        vision_model="vision",
        vision_revision="revision",
        clip_snapshot=model_dir,
        visual_model="visual",
        visual_revision="revision",
        bge_cache=model_dir,
    )
    report = isolated_rebuild.run_complete_canary(**arguments)
    assert invoked == [
        "paddleocr_inference",
        "vision_and_visual_inference",
        "text_and_visual_projections",
        "multilingual_embeddings",
    ]
    assert report["activation"] == "complete_v2_retrieval_ready"
    assert report["blockers"] == []
    assert set(report["generations"]) == set(isolated_rebuild.REQUIRED)
    assert (runtime / "complete-rebuild-status.json").is_file()
    monkeypatch.setattr(
        isolated_rebuild,
        "_probe_v2_retrieval",
        lambda **_: {
            "representation_decisions": [
                {"representation": "canonical_text", "status": "searched"},
                {"representation": "ocr_text", "status": "searched"},
                {"representation": "vision_analysis", "status": "searched"},
                {"representation": "multilingual_text", "status": "unavailable"},
            ],
            "evidence": [{"representation": "ocr_text"}],
        },
    )
    incomplete = isolated_rebuild.run_complete_canary(**arguments)
    assert incomplete["activation"] == "index_aliases_active_in_isolated_runtime_only"
    assert "multilingual_text" in incomplete["failure"]
    assert incomplete["blockers"] == ["RuntimeError"]


def test_complete_canary_probe_requires_valid_v2_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout='{"evidence": []}', stderr=""),
        subprocess.CompletedProcess(args=[], returncode=7, stdout="", stderr="failed"),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
    ]

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["cwd"] == tmp_path
        assert kwargs["timeout"] == 600
        return responses.pop(0)

    monkeypatch.setattr(subprocess, "run", run)
    assert isolated_rebuild._probe_v2_retrieval(
        workspace=tmp_path,
        runtime=tmp_path,
        query="bounded question",
        model_cache=tmp_path,
        clip_snapshot=tmp_path,
    ) == {"evidence": []}
    with pytest.raises(RuntimeError, match="probe failed"):
        isolated_rebuild._probe_v2_retrieval(
            workspace=tmp_path,
            runtime=tmp_path,
            query="bounded question",
            model_cache=tmp_path,
            clip_snapshot=tmp_path,
        )
    with pytest.raises(RuntimeError, match="invalid response"):
        isolated_rebuild._probe_v2_retrieval(
            workspace=tmp_path,
            runtime=tmp_path,
            query="bounded question",
            model_cache=tmp_path,
            clip_snapshot=tmp_path,
        )
