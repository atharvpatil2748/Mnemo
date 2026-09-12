import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from mnemo.interfaces.errors import IntegrityError
from mnemo.models import IndexGenerationState
from mnemo.models.multilingual import LanguageCode, LanguageEvidenceKindV3, ScriptCode
from mnemo.models.text_representations import TextRepresentationType
from mnemo.phase85.projections import (
    ProjectionBuildResult,
    ProjectionGenerationSpec,
)
from mnemo.phase85.v2_index_build import (
    _BUILD_TABLES,
    FullMultilingualV2IndexBuildOperator,
    V2BuildArtifacts,
    _complete_result,
)

ROOT = Path(__file__).resolve().parents[3]
PROPOSALS = ROOT / "docs/governance/proposals/phase8_5_full_multilingual_architecture"


def _operator_and_specs(
    tmp_path: Path,
) -> tuple[FullMultilingualV2IndexBuildOperator, tuple[ProjectionGenerationSpec, ...]]:
    artifacts = V2BuildArtifacts.load(PROPOSALS)
    specs = tuple(
        ProjectionGenerationSpec.from_manifest_payload(item)
        for item in artifacts.build["generation_specifications"]
    )
    operator = object.__new__(FullMultilingualV2IndexBuildOperator)
    operator._root = tmp_path
    operator._artifacts = artifacts
    operator._run_started_at = lambda: datetime(2026, 1, 1, tzinfo=UTC)
    target_db = tmp_path / "target.db"
    operator._authorized_target = lambda: target_db
    with sqlite3.connect(target_db) as conn:
        conn.executescript(_BUILD_TABLES)
    return operator, specs


@pytest.mark.anyio
async def test_ci_safe_generation_start_is_restart_safe_and_contract_bound(tmp_path: Path) -> None:
    operator, specs = _operator_and_specs(tmp_path)
    spec = specs[0]
    from dataclasses import replace

    ready = spec.new_generation(datetime.now(UTC))
    ready = replace(ready, state=IndexGenerationState.READY)
    building = replace(ready, state=IndexGenerationState.BUILDING)
    failed = replace(ready, state=IndexGenerationState.FAILED)

    class Store:
        existing = None
        created = True

        async def get_index_generation(self, _identifier: object) -> object:
            return self.existing

        async def create_index_generation(self, value: object) -> bool:
            assert value.state is IndexGenerationState.BUILDING  # type: ignore[attr-defined]
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


@pytest.mark.anyio
async def test_ci_safe_generation_completion_rejects_partial_and_failed_ready_transition(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    operator, specs = _operator_and_specs(tmp_path)
    spec = specs[0]
    mock_item = SimpleNamespace(
        language=LanguageCode("en"),
        script_observation=SimpleNamespace(
            hypotheses=(SimpleNamespace(script=ScriptCode("Latn")),)
        ),
        representation=SimpleNamespace(
            representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT
        ),
        source=SimpleNamespace(kind=LanguageEvidenceKindV3.CANONICAL_CHUNK),
    )
    evidence = [mock_item]

    class Store:
        current = None

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


@pytest.mark.anyio
async def test_ci_safe_build_stages_skip_completed_generations_without_writes(
    tmp_path: Path,
) -> None:
    operator, specs = _operator_and_specs(tmp_path)

    async def already_ready(*_args: object) -> bool:
        return False

    operator._begin_generation = already_ready  # type: ignore[method-assign]
    store = SimpleNamespace()
    await operator._build_representation(store, specs[0], ())  # type: ignore[arg-type]
    await operator._build_sparse(store, specs[1], ())  # type: ignore[arg-type]
    await operator._build_embeddings(  # type: ignore[arg-type]
        store, Path("unused"), specs[2], (), SimpleNamespace()
    )
    await operator._build_vector(store, Path("unused"), specs[3])  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_ci_safe_build_stages_persist_governed_evidence_and_vectors(
    tmp_path: Path,
) -> None:
    import json
    import sqlite3
    from dataclasses import replace

    operator, specs_tuple = _operator_and_specs(tmp_path)
    rec = operator._artifacts.census["records"][0]

    source_db = tmp_path / "source.db"
    conn = sqlite3.connect(source_db)
    conn.execute("CREATE TABLE sources (document_id TEXT, source_id TEXT, notebook_id TEXT)")
    conn.execute("CREATE TABLE document_versions (version_id TEXT, created_at TEXT)")
    conn.execute(
        "CREATE TABLE chunks (id TEXT, version_id TEXT, text TEXT, position_page_number INT, "
        "position_section_index INT, heading_path TEXT)"
    )
    conn.execute(
        "CREATE TABLE ocr_results (derivation_id TEXT, document_id TEXT, version_id TEXT, "
        "occurrence_id TEXT, generation_id TEXT, created_at TEXT)"
    )
    conn.execute("CREATE TABLE ocr_regions (region_id TEXT, derivation_id TEXT, text TEXT)")
    conn.execute("CREATE TABLE vision_results (derivation_id TEXT)")
    conn.execute("CREATE TABLE asset_occurrences (occurrence_id TEXT, locator TEXT)")

    conn.execute(
        "INSERT INTO sources VALUES (?,?,?)",
        (
            rec["document_id"],
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ),
    )
    conn.execute(
        "INSERT INTO document_versions VALUES (?,?)",
        (rec["version_id"], "2026-01-01T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO chunks VALUES (?,?,?,?,?,?)",
        (rec["evidence_id"], rec["version_id"], "Sample Text", 1, 0, "[]"),
    )
    conn.commit()
    conn.close()

    operator._artifacts = replace(operator._artifacts, census={"records": [rec]})
    evidence = operator._load_evidence(source_db)
    specs = {item.capability: item for item in specs_tuple}
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

    operator._begin_generation = begin  # type: ignore[method-assign]
    operator._complete_generation = complete  # type: ignore[method-assign]
    operator._checkpoint = lambda stage, *_args: calls.append(f"checkpoint:{stage}")  # type: ignore[method-assign]

    store = Store()
    await operator._build_representation(
        store,
        specs["representation_derivation_v2"],
        evidence,
    )
    await operator._build_sparse(store, specs["language_text_v2"], evidence)

    class Provider:
        async def embed_documents_v3(self, values: object) -> object:
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
            "embedding_id TEXT, vector_space TEXT, evidence_reference_digest TEXT, "
            "payload TEXT, generation_id TEXT)"
        )
        connection.execute(
            "INSERT INTO multilingual_embeddings_v2 VALUES(?,?,?,?,?)",
            (
                "embedding-id",
                operator._artifacts.authorization.vector_space_identity,
                "0" * 64,
                payload,
                str(specs["multilingual_vector_v2"].source_generation_ids[0]),
            ),
        )
    operator._eligible_evidence_stub = lambda *_args: evidence  # type: ignore[method-assign]
    await operator._build_vector(store, vector_db, specs["multilingual_vector_v2"])  # type: ignore[arg-type]
    assert "complete:multilingual_vector_v2" in calls

    # Test real static helper methods on vector_db
    digests = FullMultilingualV2IndexBuildOperator._existing_embedding_source_digests(
        vector_db, specs["multilingual_vector_v2"].source_generation_ids[0]
    )
    assert isinstance(digests, set)
    ids = FullMultilingualV2IndexBuildOperator._embedding_ids(
        vector_db, specs["multilingual_vector_v2"].source_generation_ids[0]
    )
    assert ids == ["embedding-id"]


def test_ci_safe_file_digest_helper(tmp_path: Path) -> None:
    import hashlib

    from mnemo.phase85.v2_index_build import _file_digest

    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"governed digest verification content")
    expected = hashlib.sha256(b"governed digest verification content").hexdigest()
    assert _file_digest(sample) == expected


@pytest.mark.anyio
async def test_ci_safe_build_representation_with_exclusion(tmp_path: Path) -> None:
    import sqlite3

    from mnemo.phase85.v2_index_build import _BUILD_TABLES

    operator, specs_tuple = _operator_and_specs(tmp_path)
    specs = {item.capability: item for item in specs_tuple}

    target_db = tmp_path / "target.db"
    with sqlite3.connect(target_db) as conn:
        conn.executescript(_BUILD_TABLES)

    async def begin_gen(*_a: object) -> bool:
        return True

    operator._authorized_target = lambda: target_db
    operator._begin_generation = begin_gen  # type: ignore[method-assign]
    operator._checkpoint = lambda *_a: None  # type: ignore[method-assign]

    mock_excluded = SimpleNamespace(
        source=SimpleNamespace(
            identity_digest="0" * 64,
            kind=LanguageEvidenceKindV3.CANONICAL_CHUNK,
            evidence_id="0" * 64,
            source_content_hash="0" * 64,
        ),
        language_observation=SimpleNamespace(observation_id="obs1"),
        script_observation=SimpleNamespace(
            hypotheses=(SimpleNamespace(script=ScriptCode("Latn")),)
        ),
        representation_observation=SimpleNamespace(observation_id="rep1"),
        representation=SimpleNamespace(
            representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT
        ),
        language=LanguageCode("en"),
        position=None,
        excluded=True,
        transformation_requirement="required_unavailable_excluded",
    )

    class Store:
        async def put_language_observation_v2(self, _v: object) -> bool:
            return True

        async def put_script_observation_v1(self, _v: object) -> bool:
            return True

        async def put_representation_observation_v1(self, _v: object) -> bool:
            return True

        async def put_index_generation_coverage(self, _v: object) -> bool:
            return True

        async def put_multilingual_coverage_manifest_v2(self, _v: object) -> bool:
            return True

        async def transition_index_generation(self, *_a: object, **_k: object) -> bool:
            return True

        async def get_index_generation(self, _id: object) -> object:
            return SimpleNamespace(state=IndexGenerationState.READY)

    await operator._build_representation(
        Store(),  # type: ignore[arg-type]
        specs["representation_derivation_v2"],
        (mock_excluded,),  # type: ignore[arg-type]
    )

    with sqlite3.connect(target_db) as conn:
        count = conn.execute("SELECT count(*) FROM v2_build_exclusions").fetchone()[0]
    assert count == 1


@pytest.mark.anyio
async def test_ci_safe_build_vector_validation_errors(tmp_path: Path) -> None:
    import json
    import sqlite3

    operator, specs_tuple = _operator_and_specs(tmp_path)
    specs = {item.capability: item for item in specs_tuple}

    async def begin_gen(*_a: object) -> bool:
        return True

    operator._begin_generation = begin_gen  # type: ignore[method-assign]
    vector_spec = specs["multilingual_vector_v2"]

    vector_db = tmp_path / "vec_err.db"
    with sqlite3.connect(vector_db) as conn:
        conn.execute(
            "CREATE TABLE multilingual_embeddings_v2("
            "embedding_id TEXT, vector_space TEXT, payload TEXT, generation_id TEXT)"
        )

    # 1. Invalid length vector raises IntegrityError
    invalid_payload = json.dumps(
        {
            "schema_version": 1,
            "payload": {"$ref": "1"},
            "objects": {"1": {"fields": {"vector": {"$tuple": [1.0, 2.0]}}}},
        }
    )
    with sqlite3.connect(vector_db) as conn:
        conn.execute(
            "INSERT INTO multilingual_embeddings_v2 VALUES(?,?,?,?)",
            (
                "emb-bad",
                operator._artifacts.authorization.vector_space_identity,
                invalid_payload,
                str(vector_spec.source_generation_ids[0]),
            ),
        )
    with pytest.raises(IntegrityError, match="stored embedding vector is invalid"):
        await operator._build_vector(SimpleNamespace(), vector_db, vector_spec)  # type: ignore[arg-type]

    # 2. Non-L2-normalized vector raises IntegrityError
    unnormalized_payload = json.dumps(
        {
            "schema_version": 1,
            "payload": {"$ref": "1"},
            "objects": {"1": {"fields": {"vector": {"$tuple": [2.0] + [0.0] * 1023}}}},
        }
    )
    with sqlite3.connect(vector_db) as conn:
        conn.execute("DELETE FROM multilingual_embeddings_v2")
        conn.execute(
            "INSERT INTO multilingual_embeddings_v2 VALUES(?,?,?,?)",
            (
                "emb-unnorm",
                operator._artifacts.authorization.vector_space_identity,
                unnormalized_payload,
                str(vector_spec.source_generation_ids[0]),
            ),
        )
    with pytest.raises(IntegrityError, match="stored embedding vector is not L2 normalized"):
        await operator._build_vector(SimpleNamespace(), vector_db, vector_spec)  # type: ignore[arg-type]
