from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.models import IndexGeneration, IndexGenerationState
from mnemo.models.multilingual import LanguageEvidenceKindV3, LanguageObservationScope
from mnemo.phase85.projections import ProjectionBuildResult, ProjectionGenerationSpec
from mnemo.phase85.v2_index_build import (
    FullMultilingualV2IndexBuildOperator,
    V2BuildArtifacts,
    V2BuildPreflight,
    _complete_result,
    _digest,
    _encoded_dataclass_vector,
    _mapping_sequence,
    _scope,
    _vision_text,
)
from mnemo.retrieval.multilingual_providers import BGEM3EmbeddingProvider
from mnemo.storage.sqlite import SQLiteStore

ROOT = Path(__file__).resolve().parents[3]
PROPOSALS = ROOT / "docs/governance/proposals/phase8_5_full_multilingual_architecture"


def _fixture_generation_specs() -> tuple[ProjectionGenerationSpec, ...]:
    """Use governed specification data without opening a retired build target."""
    build = V2BuildArtifacts.load(PROPOSALS).build
    return tuple(
        ProjectionGenerationSpec.from_manifest_payload(item)
        for item in _mapping_sequence(
            build["generation_specifications"], "generation_specifications"
        )
    )


def test_v2_build_artifacts_are_digest_valid_and_ready_only() -> None:
    artifacts = V2BuildArtifacts.load(PROPOSALS)
    assert artifacts.authorization.authorization_scope == (
        "create_isolated_database_and_build_generations_to_ready_only"
    )
    assert artifacts.binding["runtime_exposure_enabled"] is False
    assert artifacts.storage["alias_namespace"] == "full_multilingual_v2_aliases"


def _disposable_operator(tmp_path: Path) -> FullMultilingualV2IndexBuildOperator:
    """Rebind governed test artifacts to three real rows in a disposable source DB."""
    proposal = tmp_path / "proposal"
    proposal.mkdir()
    artifacts = {
        source.name: json.loads(source.read_text(encoding="utf-8"))
        for source in PROPOSALS.glob("V2_*.json")
    }
    source = tmp_path / "scratch/phase8_5_wp16/eval-20260828-01/mnemo.db"
    source.parent.mkdir(parents=True)
    census = artifacts["V2_CORPUS_LANGUAGE_SCRIPT_REPRESENTATION_CENSUS.json"]
    records = [
        next(row for row in census["records"] if row["evidence_kind"] == kind)
        for kind in ("canonical_chunk", "ocr_region", "vision_derivation")
    ]
    texts = ("Fixture canonical evidence", "Fixture OCR evidence", "Fixture vision evidence")
    for record, value in zip(records, texts, strict=True):
        record["source_content_hash"] = hashlib.sha256(value.encode()).hexdigest()
    with sqlite3.connect(source) as connection:
        connection.executescript(
            "CREATE TABLE sources(document_id TEXT,source_id TEXT,notebook_id TEXT);"
            "CREATE TABLE document_versions(version_id TEXT,created_at TEXT);"
            "CREATE TABLE chunks(id TEXT,version_id TEXT,text TEXT,position_page_number INTEGER,"
            "position_section_index INTEGER,heading_path TEXT);"
            "CREATE TABLE ocr_regions(region_id TEXT,derivation_id TEXT,"
            "text TEXT,page_number INTEGER);"
            "CREATE TABLE ocr_results(derivation_id TEXT,document_id TEXT,version_id TEXT,"
            "occurrence_id TEXT,generation_id TEXT,created_at TEXT);"
            "CREATE TABLE vision_results(derivation_id TEXT,payload TEXT,created_at TEXT);"
            "CREATE TABLE asset_occurrences(occurrence_id TEXT,locator TEXT);"
        )
        notebook_id = str(uuid4())
        for record in records:
            connection.execute(
                "INSERT INTO sources VALUES(?,?,?)",
                (record["document_id"], str(uuid4()), notebook_id),
            )
            connection.execute(
                "INSERT INTO document_versions VALUES(?,?)",
                (record["version_id"], "2026-09-01T00:00:00+00:00"),
            )
        connection.execute(
            "INSERT INTO chunks VALUES(?,?,?,?,?,?)",
            (records[0]["evidence_id"], records[0]["version_id"], texts[0], 1, 0, "[]"),
        )
        connection.execute(
            "INSERT INTO ocr_regions VALUES(?,?,?,?)",
            (records[1]["evidence_id"], records[1]["derivation_id"], texts[1], 1),
        )
        connection.execute(
            "INSERT INTO ocr_results VALUES(?,?,?,?,?,?)",
            (
                records[1]["derivation_id"],
                records[1]["document_id"],
                records[1]["version_id"],
                records[1]["occurrence_id"],
                records[1]["source_generation_id"],
                "2026-09-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO vision_results VALUES(?,?,?)",
            (
                records[2]["derivation_id"],
                json.dumps({"captions": [{"text": texts[2]}]}),
                "2026-09-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO asset_occurrences VALUES(?,?)",
            (records[1]["occurrence_id"], json.dumps({"page_number": 1})),
        )
    corpus_root = tmp_path / "goldenDataset/Phase 8.5 Evaluation Corpus"
    corpus_root.mkdir(parents=True)
    corpus_file = corpus_root / "fixture.txt"
    corpus_file.write_text("Disposable corpus", encoding="utf-8")
    corpus_files = [
        {
            "name": corpus_file.name,
            "sha256": hashlib.sha256(corpus_file.read_bytes()).hexdigest(),
            "size": corpus_file.stat().st_size,
        }
    ]
    corpus_digest = _digest(corpus_files)
    corpus_census = artifacts["V2_CORPUS_REPRESENTATION_CENSUS.json"]
    corpus_census["corpus_files"] = corpus_files
    corpus_census["corpus_manifest_digest"] = corpus_digest
    corpus_census["source_database_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    census["records"] = records

    def save(name: str) -> str:
        value = artifacts[name]
        value["artifact_digest"] = _digest(
            {key: item for key, item in value.items() if key != "artifact_digest"}
        )
        (proposal / name).write_text(json.dumps(value), encoding="utf-8")
        return str(value["artifact_digest"])

    save("V2_CORPUS_REPRESENTATION_CENSUS.json")
    census_digest = save("V2_CORPUS_LANGUAGE_SCRIPT_REPRESENTATION_CENSUS.json")
    storage = artifacts["V2_DISPOSABLE_DATABASE_MANIFEST.json"]
    storage["corpus_digest"] = corpus_digest
    storage["census_digest"] = census_digest
    storage_digest = save("V2_DISPOSABLE_DATABASE_MANIFEST.json")
    build = artifacts["V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json"]
    build["source_database_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    build["source_corpus_digest"] = corpus_digest
    build["source_evidence_census_digest"] = census_digest
    build["storage_manifest_digest"] = storage_digest
    build["expected_coverage"]["evidence_items"] = len(records)
    build_digest = save("V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json")
    authorization = artifacts["V2_INDEX_BUILD_AUTHORIZATION.json"]
    authorization["corpus_digest"] = corpus_digest
    authorization["census_digest"] = census_digest
    authorization["storage_manifest_digest"] = storage_digest
    authorization["build_manifest_digest"] = build_digest
    from mnemo.phase85.v2_build_authorization import V2BuildAuthorizationV1

    authorized = V2BuildAuthorizationV1(
        **{
            key: value
            for key, value in authorization.items()
            if key not in {"artifact_digest", "authorization_id", "schema_version"}
        }
    )
    authorization["authorization_id"] = str(authorized.authorization_id)
    save("V2_INDEX_BUILD_AUTHORIZATION.json")
    for name in artifacts:
        if not (proposal / name).exists():
            (proposal / name).write_text(json.dumps(artifacts[name]), encoding="utf-8")
    return FullMultilingualV2IndexBuildOperator(workspace_root=tmp_path, proposal_root=proposal)


def test_v2_operator_preflight_is_manifest_bound_and_non_mutating(tmp_path: Path) -> None:
    operator = _disposable_operator(tmp_path)
    preflight = operator.preflight()
    assert (
        preflight.target
        == (tmp_path / "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db").resolve()
    )
    assert [item.capability for item in preflight.generation_specs] == [
        "representation_derivation_v2",
        "language_text_v2",
        "multilingual_embedding_v2",
        "multilingual_vector_v2",
    ]


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("orphan-sidecar", "sidecar exists"),
        ("changed-source-database", "source database digest mismatch"),
        ("missing-source-file", "corpus file is absent"),
        ("changed-source-bytes", "Golden Dataset differs"),
        ("profile-binding", "profile fingerprint binding mismatch"),
        ("vector-binding", "vector-space bindings disagree"),
        ("generation-order", "generation order is not canonical"),
        ("unowned-checkpoint", "no governed build identity"),
    ],
)
def test_disposable_v2_preflight_refuses_stale_or_incompatible_inputs(
    tmp_path: Path, defect: str, message: str
) -> None:
    operator = _disposable_operator(tmp_path)
    source = tmp_path / "scratch/phase8_5_wp16/eval-20260828-01/mnemo.db"
    target = tmp_path / "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db"
    corpus_file = tmp_path / "goldenDataset/Phase 8.5 Evaluation Corpus/fixture.txt"
    if defect == "orphan-sidecar":
        target.parent.mkdir(parents=True)
        Path(f"{target}-wal").write_bytes(b"orphan")
    elif defect == "changed-source-database":
        with sqlite3.connect(source) as connection:
            connection.execute("CREATE TABLE unexpected(value TEXT)")
    elif defect == "missing-source-file":
        corpus_file.unlink()
    elif defect == "changed-source-bytes":
        corpus_file.write_bytes(b"changed")
    elif defect == "profile-binding":
        cast(dict[str, Any], operator._artifacts.binding)["profile_fingerprint"] = "different"
    elif defect == "vector-binding":
        cast(dict[str, Any], operator._artifacts.binding["embedding"])[
            "vector_space_profile_identity"
        ] = "different"
    elif defect == "generation-order":
        cast(list[dict[str, Any]], operator._artifacts.build["generation_specifications"]).reverse()
    else:
        target.parent.mkdir(parents=True)
        with sqlite3.connect(target) as connection:
            connection.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises((ContractValidationError, IntegrityError), match=message):
        operator.preflight()


def test_v2_operator_loads_all_governed_evidence_kinds_without_mutation(tmp_path: Path) -> None:
    """The identity-bound census resolves canonical, OCR, and Vision evidence."""
    operator = _disposable_operator(tmp_path)
    preflight = operator.preflight()
    before = preflight.source_database.stat().st_size

    evidence = operator._load_evidence(preflight.source_database)

    coverage = cast(dict[str, int], operator._artifacts.build["expected_coverage"])
    assert len(evidence) == coverage["evidence_items"]
    assert {item.source.kind for item in evidence} == {
        LanguageEvidenceKindV3.CANONICAL_CHUNK,
        LanguageEvidenceKindV3.OCR_REGION,
        LanguageEvidenceKindV3.VISION_DERIVATION,
    }
    assert all(item.text.strip() for item in evidence)
    assert all(item.representation.content_hash for item in evidence)
    assert preflight.source_database.stat().st_size == before


def test_v2_operator_rejects_tampered_authorization(tmp_path: Path) -> None:
    proposal = tmp_path / "proposal"
    proposal.mkdir()
    for source in PROPOSALS.glob("V2_*.json"):
        (proposal / source.name).write_bytes(source.read_bytes())
    authorization_path = proposal / "V2_INDEX_BUILD_AUTHORIZATION.json"
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    # Altering a security binding without regenerating its governed digest fails closed.
    authorization["target_database_path"] = "scratch/phase8_5_full_multilingual_v2/x/mnemo.db"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    with pytest.raises(ContractValidationError, match="artifact digest mismatch"):
        FullMultilingualV2IndexBuildOperator(
            workspace_root=ROOT,
            proposal_root=proposal,
        )


def test_v2_vector_audit_reads_the_canonical_snapshot_envelope() -> None:
    payload = {
        "schema_version": 1,
        "payload": {"$ref": "1"},
        "objects": {"1": {"fields": {"vector": {"$tuple": [0.0, 1.0]}}}},
    }
    assert _encoded_dataclass_vector(payload) == (0.0, 1.0)


def test_v2_build_helpers_validate_manifests_scopes_and_vision_payloads() -> None:
    assert _mapping_sequence([{"a": 1}], "items") == ({"a": 1},)
    for invalid in cast(tuple[object, ...], (None, {}, ["not-an-object"])):
        with pytest.raises(ContractValidationError, match="array of objects"):
            _mapping_sequence(invalid, "items")
    assert _scope(LanguageEvidenceKindV3.CANONICAL_CHUNK) is LanguageObservationScope.CHUNK
    assert _scope(LanguageEvidenceKindV3.OCR_REGION) is LanguageObservationScope.OCR_REGION
    assert _scope(LanguageEvidenceKindV3.VISION_DERIVATION) is LanguageObservationScope.ASSET
    assert (
        _vision_text(
            json.dumps(
                {
                    "captions": [{"text": "caption"}, {"text": " "}],
                    "observations": [{"value": "observation"}],
                    "entities": [{"name": "entity"}],
                }
            )
        )
        == "caption\nobservation\nentity"
    )
    result = _complete_result(["b", "a"])
    assert result.expected_count == result.succeeded_count == 2
    assert result.failed_count == result.skipped_count == 0
    with pytest.raises(IntegrityError, match="malformed"):
        _encoded_dataclass_vector({})


def _audit_operator(tmp_path: Path) -> tuple[FullMultilingualV2IndexBuildOperator, Path]:
    target = tmp_path / "target.db"
    authorization = SimpleNamespace(
        run_id=uuid4(),
        authorization_id=uuid4(),
        target_database_path=str(target.relative_to(tmp_path)),
        corpus_digest="a" * 64,
        census_digest="b" * 64,
        profile_fingerprint="c" * 64,
        vector_space_identity="d" * 64,
        build_manifest_digest="e" * 64,
        storage_manifest_digest="f" * 64,
    )
    operator = object.__new__(FullMultilingualV2IndexBuildOperator)
    operator._root = tmp_path.resolve()
    cast(Any, operator)._artifacts = SimpleNamespace(authorization=authorization)
    return operator, target


def test_build_audit_checkpoint_is_restartable_and_identity_bound(tmp_path: Path) -> None:
    """Build audit metadata resumes only the same governed authorization."""
    operator, target = _audit_operator(tmp_path)
    operator._initialize_build_audit(target)
    started = operator._run_started_at()
    assert started.tzinfo is not None

    operator._checkpoint("language_text_v2", 2, ["b", "a"])
    operator._checkpoint("language_text_v2", 3, ["c", "b", "a"])
    operator._initialize_build_audit(target)
    operator._validate_existing_target(target)
    operator._finish_run(target, "ready")

    with sqlite3.connect(target) as connection:
        state, completed = connection.execute(
            "SELECT state, completed_at FROM v2_build_runs"
        ).fetchone()
        count, digest = connection.execute(
            "SELECT completed_count, checkpoint_digest FROM v2_build_checkpoints"
        ).fetchone()
    assert state == "ready" and datetime.fromisoformat(completed).tzinfo is not None
    assert count == 3 and len(digest) == 64

    cast(Any, operator._artifacts.authorization).corpus_digest = "0" * 64
    with pytest.raises(ContractValidationError, match="authorization mismatch"):
        operator._validate_existing_target(target)


def test_build_audit_helpers_clone_and_fail_closed(tmp_path: Path) -> None:
    """SQLite cloning preserves rows while absent and foreign checkpoints fail closed."""
    source = tmp_path / "source.db"
    target = tmp_path / "clone.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('preserved')")
    FullMultilingualV2IndexBuildOperator._clone_source(source, target)
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("preserved",)

    operator, governed_target = _audit_operator(tmp_path / "audit")
    governed_target.parent.mkdir()
    connection = sqlite3.connect(governed_target)
    connection.execute("CREATE TABLE unrelated(value INTEGER)")
    connection.commit()
    connection.close()
    with pytest.raises(ContractValidationError, match="no governed build identity"):
        operator._validate_existing_target(governed_target)

    missing = governed_target.parent / "missing.db"
    operator._finish_run(missing, "failed")
    governed_target.unlink()
    operator._initialize_build_audit(governed_target)
    connection = sqlite3.connect(governed_target)
    connection.execute("DELETE FROM v2_build_runs")
    connection.commit()
    connection.close()
    with pytest.raises(IntegrityError, match="run identity is absent"):
        operator._run_started_at()


@pytest.mark.anyio
async def test_v2_execute_runs_governed_stage_order_and_closes_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mnemo.phase85 import v2_index_build as subject

    target = tmp_path / "target.db"
    target.write_bytes(b"checkpoint")
    specifications = tuple(SimpleNamespace(generation_id=uuid4()) for _ in range(4))
    preflight = V2BuildPreflight(
        target=target,
        source_database=tmp_path / "source.db",
        corpus_root=tmp_path / "corpus",
        generation_specs=cast(tuple[ProjectionGenerationSpec, ...], specifications),
    )
    events: list[str] = []

    class Store:
        def __init__(self, path: Path) -> None:
            assert path == target

        async def open(self) -> None:
            events.append("store-open")

        async def close(self) -> None:
            events.append("store-close")

    class Provider:
        async def initialize(self) -> None:
            events.append("provider-initialize")

        async def profile(self) -> object:
            return SimpleNamespace(vector_space="space")

        async def close(self) -> None:
            events.append("provider-close")

    provider = Provider()
    # Dynamic stand-in isolates orchestration order from model inference.
    operator: Any = object.__new__(FullMultilingualV2IndexBuildOperator)
    operator._artifacts = SimpleNamespace(
        build={"expected_coverage": {"evidence_items": 2}, "vector_space_profile_identity": "space"}
    )
    operator.preflight = lambda: preflight
    operator._initialize_build_audit = lambda _target: events.append("audit-init")
    operator._load_evidence = lambda _target: (
        SimpleNamespace(excluded=False),
        SimpleNamespace(excluded=True),
    )
    operator._embedding_provider = lambda _spec: provider

    async def stage(name: str) -> None:
        events.append(name)

    operator._build_representation = lambda *_args: stage("representation")
    operator._build_sparse = lambda *_args: stage("sparse")
    operator._build_embeddings = lambda *_args: stage("embeddings")
    operator._build_vector = lambda *_args: stage("vector")
    operator._audit = lambda *_args: {"status": "READY"}
    operator._finish_run = lambda _target, state: events.append(f"finish-{state}")
    monkeypatch.setattr(subject, "SQLiteStore", Store)

    result = await operator.execute()

    assert result == {"status": "READY"}
    assert events == [
        "audit-init",
        "store-open",
        "provider-initialize",
        "representation",
        "sparse",
        "embeddings",
        "vector",
        "finish-ready",
        "provider-close",
        "store-close",
    ]


@pytest.mark.anyio
async def test_v2_build_stages_persist_governed_evidence_and_vectors(
    tmp_path: Path,
) -> None:
    """Each build family persists identity-bound rows and completes its generation."""
    operator = _disposable_operator(tmp_path)
    preflight = operator.preflight()
    evidence = operator._load_evidence(preflight.source_database)[:1]
    operator._run_started_at = lambda: datetime.now(UTC)  # type: ignore[method-assign]
    specs = {item.capability: item for item in preflight.generation_specs}
    calls: list[str] = []

    class Store:
        async def put_language_observation_v2(self, _value: object) -> bool:
            calls.append("language")
            return True

        async def put_script_observation_v1(self, _value: object) -> bool:
            calls.append("script")
            return True

        async def put_representation_observation_v1(self, _value: object) -> bool:
            calls.append("representation")
            return True

        async def put_multilingual_text_projection_row_v2(self, value: object) -> bool:
            assert value.text == evidence[0].text  # type: ignore[attr-defined]
            calls.append("sparse")
            return True

        async def put_multilingual_embedding_v3(self, _value: object) -> bool:
            calls.append("embedding")
            return True

    async def begin(_store: object, spec: object) -> bool:
        calls.append(f"begin:{spec.capability}")  # type: ignore[attr-defined]
        return True

    async def complete(_store: object, spec: object, result: object, population: object) -> None:
        assert result.succeeded_count == 1  # type: ignore[attr-defined]
        assert len(population) == 1  # type: ignore[arg-type]
        calls.append(f"complete:{spec.capability}")  # type: ignore[attr-defined]

    cast(Any, operator)._begin_generation = begin
    cast(Any, operator)._complete_generation = complete
    operator._checkpoint = lambda stage, *_args: calls.append(f"checkpoint:{stage}")  # type: ignore[method-assign]
    store = Store()
    await operator._build_representation(
        cast(SQLiteStore, store),
        specs["representation_derivation_v2"],
        evidence,
    )
    await operator._build_sparse(store, specs["language_text_v2"], evidence)  # type: ignore[arg-type]

    class Provider:
        async def embed_documents_v3(self, values):  # type: ignore[no-untyped-def]
            assert len(values) == 1
            return (
                SimpleNamespace(
                    profile=SimpleNamespace(
                        vector_space=operator._artifacts.authorization.vector_space_identity
                    )
                ),
            )

    operator._existing_embedding_source_digests = lambda *_args: set()  # type: ignore[method-assign]
    operator._embedding_ids = lambda *_args: ["embedding-id"]  # type: ignore[method-assign]
    await operator._build_embeddings(
        store,  # type: ignore[arg-type]
        tmp_path / "unused.db",
        specs["multilingual_embedding_v2"],
        evidence,
        Provider(),  # type: ignore[arg-type]
    )
    assert {"language", "script", "representation", "sparse", "embedding"} <= set(calls)

    vector_db = tmp_path / "vectors.db"
    vector = [1.0] + [0.0] * 1023
    payload = json.dumps(
        {
            "schema_version": 1,
            "payload": {"$ref": "1"},
            "objects": {"1": {"fields": {"vector": {"$tuple": vector}}}},
        }
    )
    with sqlite3.connect(vector_db) as connection:
        connection.execute(
            "CREATE TABLE multilingual_embeddings_v2("
            "embedding_id TEXT, vector_space TEXT, payload TEXT, generation_id TEXT)"
        )
        connection.execute(
            "INSERT INTO multilingual_embeddings_v2 VALUES(?,?,?,?)",
            (
                "embedding-id",
                operator._artifacts.authorization.vector_space_identity,
                payload,
                str(specs["multilingual_vector_v2"].source_generation_ids[0]),
            ),
        )
    operator._eligible_evidence_stub = lambda *_args: evidence  # type: ignore[method-assign]
    await operator._build_vector(store, vector_db, specs["multilingual_vector_v2"])  # type: ignore[arg-type]
    assert "complete:multilingual_vector_v2" in calls


@pytest.mark.anyio
async def test_v2_execute_marks_failed_and_closes_store_on_evidence_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mnemo.phase85 import v2_index_build as subject

    target = tmp_path / "target.db"
    target.write_bytes(b"checkpoint")
    preflight = V2BuildPreflight(
        target=target,
        source_database=tmp_path / "source.db",
        corpus_root=tmp_path / "corpus",
        generation_specs=cast(
            tuple[ProjectionGenerationSpec, ...],
            tuple(SimpleNamespace(generation_id=uuid4()) for _ in range(4)),
        ),
    )
    events: list[str] = []

    class Store:
        def __init__(self, _path: Path) -> None:
            pass

        async def open(self) -> None:
            events.append("open")

        async def close(self) -> None:
            events.append("close")

    operator: Any = object.__new__(FullMultilingualV2IndexBuildOperator)
    operator._artifacts = SimpleNamespace(build={"expected_coverage": {"evidence_items": 2}})
    operator.preflight = lambda: preflight
    operator._initialize_build_audit = lambda _target: None
    operator._load_evidence = lambda _target: ()
    operator._finish_run = lambda _target, state: events.append(state)
    monkeypatch.setattr(subject, "SQLiteStore", Store)
    with pytest.raises(IntegrityError, match="evidence count"):
        await operator.execute()
    assert events == ["open", "failed", "close"]


@pytest.mark.local_database
@pytest.mark.anyio
async def test_generation_start_is_restart_safe_and_contract_bound() -> None:
    operator = FullMultilingualV2IndexBuildOperator(
        workspace_root=ROOT,
        proposal_root=PROPOSALS,
    )
    spec = _fixture_generation_specs()[0]
    ready = spec.new_generation(datetime.now(UTC))
    ready = replace(ready, state=IndexGenerationState.READY)
    building = replace(ready, state=IndexGenerationState.BUILDING)
    failed = replace(ready, state=IndexGenerationState.FAILED)

    class Store:
        existing: IndexGeneration | None = None
        created = True

        async def get_index_generation(self, _identifier: object) -> object:
            return self.existing

        async def create_index_generation(self, value: object) -> bool:
            assert cast(IndexGeneration, value).state is IndexGenerationState.BUILDING
            return self.created

        async def put_index_generation_sources(self, **values: object) -> None:
            assert values["generation_id"] == spec.generation_id

    store = Store()
    store.existing = ready
    assert await operator._begin_generation(store, spec) is False  # type: ignore[arg-type]
    store.existing = building
    assert await operator._begin_generation(store, spec) is True  # type: ignore[arg-type]
    store.existing = failed
    with pytest.raises(IntegrityError, match="cannot be resumed"):
        await operator._begin_generation(store, spec)  # type: ignore[arg-type]
    store.existing = replace(building, profile="different")
    with pytest.raises(IntegrityError, match="incompatible"):
        await operator._begin_generation(store, spec)  # type: ignore[arg-type]
    store.existing = None
    store.created = False
    with pytest.raises(IntegrityError, match="could not create"):
        await operator._begin_generation(store, spec)  # type: ignore[arg-type]
    store.created = True
    assert await operator._begin_generation(store, spec) is True  # type: ignore[arg-type]


@pytest.mark.local_database
@pytest.mark.anyio
async def test_generation_completion_rejects_partial_and_failed_ready_transition() -> None:
    operator = FullMultilingualV2IndexBuildOperator(
        workspace_root=ROOT,
        proposal_root=PROPOSALS,
    )
    spec = _fixture_generation_specs()[0]
    evidence = (
        SimpleNamespace(
            language=SimpleNamespace(value="en"),
            script_observation=SimpleNamespace(hypotheses=()),
            representation=SimpleNamespace(representation_type=SimpleNamespace(value="canonical")),
            source=SimpleNamespace(kind=SimpleNamespace(value="canonical_chunk")),
        ),
    )
    operator._run_started_at = lambda: datetime(2026, 1, 1, tzinfo=UTC)  # type: ignore[method-assign]

    class Store:
        current: IndexGeneration | None = None

        async def put_index_generation_coverage(self, _value: object) -> bool:
            return True

        async def put_multilingual_coverage_manifest_v2(self, value: object) -> bool:
            assert value.generation_id == spec.generation_id  # type: ignore[attr-defined]
            return True

        async def transition_index_generation(self, *_args: object, **_kwargs: object) -> bool:
            return False

        async def get_index_generation(self, _identifier: object) -> object:
            return self.current

    store = Store()
    partial = ProjectionBuildResult(
        expected_count=1,
        succeeded_count=0,
        failed_count=1,
        skipped_count=0,
        checksum="a" * 64,
    )
    with pytest.raises(IntegrityError, match="coverage is partial"):
        await operator._complete_generation(store, spec, partial, evidence)  # type: ignore[arg-type]

    complete = _complete_result(["evidence"])
    with pytest.raises(IntegrityError, match="READY transition failed"):
        await operator._complete_generation(store, spec, complete, evidence)  # type: ignore[arg-type]
    store.current = replace(
        spec.new_generation(datetime.now(UTC)), state=IndexGenerationState.READY
    )
    await operator._complete_generation(store, spec, complete, evidence)  # type: ignore[arg-type]


@pytest.mark.local_database
@pytest.mark.anyio
async def test_build_stages_skip_completed_generations_without_writes() -> None:
    operator = FullMultilingualV2IndexBuildOperator(
        workspace_root=ROOT,
        proposal_root=PROPOSALS,
    )
    specs = _fixture_generation_specs()

    async def already_ready(*_args: object) -> bool:
        return False

    cast(Any, operator)._begin_generation = already_ready
    store = SimpleNamespace()
    await operator._build_representation(store, specs[0], ())  # type: ignore[arg-type]
    await operator._build_sparse(store, specs[1], ())  # type: ignore[arg-type]
    await operator._build_embeddings(
        cast(SQLiteStore, store),
        Path("unused"),
        specs[2],
        (),
        cast(BGEM3EmbeddingProvider, SimpleNamespace()),
    )
    await operator._build_vector(store, Path("unused"), specs[3])  # type: ignore[arg-type]
