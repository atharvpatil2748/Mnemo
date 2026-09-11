from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot
from mnemo.phase85.projections import ProjectionGenerationSpec
from mnemo.retrieval.language_detection import ConfiguredUnicodeScriptDetectorV1

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
ARTIFACTS = (
    "V2_PROVIDER_CAPABILITY_CLAIMS.json",
    "V2_PROVIDER_READINESS_EVIDENCE.json",
    "V2_CORPUS_REPRESENTATION_CENSUS.json",
    "V2_CORPUS_LANGUAGE_SCRIPT_REPRESENTATION_CENSUS.json",
    "V2_LANGUAGE_OBSERVATION_POLICY.json",
    "V2_SCRIPT_DETECTOR_POLICY.json",
    "V2_REPRESENTATION_DETECTOR_POLICY.json",
    "V2_GOVERNED_COVERAGE_LIMITATION_POLICY.json",
    "V2_LEGACY_TRANSFORMATION_DECISION.json",
    "V2_MODEL_PROFILE_BINDING.json",
    "V2_DISPOSABLE_DATABASE_MANIFEST.json",
    "V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json",
    "V2_INDEX_BUILD_AUTHORIZATION.json",
)


def _load(name: str) -> dict[str, object]:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_configuration_artifact_schema_and_self_digests() -> None:
    schema = _load("V2_CONFIGURATION_ARTIFACT.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for name in ARTIFACTS:
        value = _load(name)
        validator.validate(value)
        claimed = value.pop("artifact_digest")
        assert claimed == _digest(value), name


def test_buildability_configuration_schema() -> None:
    schema = _load("V2_BUILDABILITY_CONFIGURATION.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for name in (
        "V2_LANGUAGE_OBSERVATION_POLICY.json",
        "V2_SCRIPT_DETECTOR_POLICY.json",
        "V2_REPRESENTATION_DETECTOR_POLICY.json",
        "V2_GOVERNED_COVERAGE_LIMITATION_POLICY.json",
        "V2_CORPUS_LANGUAGE_SCRIPT_REPRESENTATION_CENSUS.json",
    ):
        validator.validate(_load(name))


def test_provider_claims_are_operation_scoped_and_do_not_promote_lifecycle() -> None:
    value = _load("V2_PROVIDER_CAPABILITY_CLAIMS.json")
    assert value["broader_provider_language_claim"]["status"] == "UNVERIFIED"
    assert {item["language"] for item in value["claims"]} == {"en", "hi", "mr"}
    for item in value["claims"]:
        state = item["lifecycle"]
        assert state["model_supported"] and state["implemented"] and state["configured"]
        assert state["buildable"]
        assert not any(
            state[key]
            for key in ("ready", "active", "exposed", "evaluated", "verified", "certified")
        )
        assert item["claim_strength"] == "deployment_probe_observed_only"


def test_profile_and_binding_are_exact_and_non_exposed() -> None:
    document = ModelProfileDocument.from_file(
        ROOT / "config/model_profiles/full_multilingual_v2_profiles.toml"
    )
    selected = document.select("full_multilingual_v2_local_prebuild")
    binding = _load("V2_MODEL_PROFILE_BINDING.json")
    snapshot = profile_snapshot(selected, http_enabled=False, mcp_enabled=False)
    assert snapshot.fingerprint == binding["profile_fingerprint"]
    assert binding["runtime_exposure_enabled"] is False
    assert binding["embedding"]["revision"] == "5617a9f61b028005a4858fdac845db406aefb181"
    assert binding["embedding"]["vector_dimension"] == 1024
    assert binding["embedding"]["metric"] == "cosine"
    assert binding["embedding"]["normalization"] == "l2"
    assert binding["reranker"]["revision"] == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    assert binding["reranker"]["audited_pair_token_limit"] == 256


def test_census_keeps_language_script_and_representation_independent() -> None:
    value = _load("V2_CORPUS_REPRESENTATION_CENSUS.json")
    assert value["counts"]["documents"] == 44
    assert value["counts"]["versions"] == 44
    assert value["counts"]["canonical_chunks"] == 2658
    by_hash = {item["corpus_file_hash"]: item for item in value["documents"]}
    manuscript = by_hash["31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085"]
    assert manuscript["language_observation"]["value"] == "mr"
    assert manuscript["script_observation"]["value"] == "Deva"
    assert manuscript["representation_observation"]["value"] == "unicode_semantic_text"
    ramayana = by_hash["759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75"]
    assert ramayana["language_observation"]["value"] == "hi"
    assert ramayana["script_observation"]["value"] == "Zzzz"
    assert ramayana["representation_observation"]["value"] == "legacy_font_encoded_text"


def test_legacy_transformation_fails_closed_without_invented_mapping() -> None:
    value = _load("V2_LEGACY_TRANSFORMATION_DECISION.json")
    assert value["runtime_profile_status"] == "UNRESOLVED"
    assert value["mapping_source"]["registration_authority"] == "SIL International"
    assert value["mapping_source"]["sha256"] == (
        "3ff5befa3b026d6931e0f71f6ddff6d2a388a437755e7f09adff9791e873871c"
    )
    assert value["license"]["spdx"] == "MIT"
    assert value["failure_policy"] == "fail_closed_no_output_no_canonical_mutation"
    assert value["dispatch_policy"] == "representation_observation_only"
    assert value["buildability_effect"] == "non_blocking_under_governed_limited_coverage"


def test_full_evidence_census_and_detector_policies_are_generic_and_complete() -> None:
    census = _load("V2_CORPUS_LANGUAGE_SCRIPT_REPRESENTATION_CENSUS.json")
    assert census["counts"]["evidence_items"] == len(census["records"])
    assert census["counts"]["canonical_chunks"] == 2658
    assert census["counts"]["transformation_unresolved_governed_exclusions"] == 504
    assert census["provenance_complete"] is True
    assert {item["language"]["language"] for item in census["records"]} >= {"und", "hi", "mr"}
    language = _load("V2_LANGUAGE_OBSERVATION_POLICY.json")
    assert language["unknown_language"] == "und"
    assert language["script_to_language_inference"] is False
    script = _load("V2_SCRIPT_DETECTOR_POLICY.json")
    assert script["identity_standard"] == "ISO-15924"
    assert script["unicode_version"] == "17.0.0"
    assert {"Latn", "Deva", "Zyyy", "Zinh"} <= set(script["ranges"])
    representation = _load("V2_REPRESENTATION_DETECTOR_POLICY.json")
    assert representation["filename_dispatch"] is False
    assert "mixed" in representation["types"]


def test_frozen_unicode_script_ranges_detect_mixed_scripts_without_language_claim() -> None:
    script = _load("V2_SCRIPT_DETECTOR_POLICY.json")
    detector = ConfiguredUnicodeScriptDetectorV1(
        {key: tuple(tuple(pair) for pair in value) for key, value in script["ranges"].items()}
    )
    observation = asyncio.run(
        detector.detect_scripts(
            actor_id=uuid4(), notebook_id=uuid4(), target_id="mixed", text="Mnemo मराठी"
        )
    )
    assert {item.script.value for item in observation.hypotheses} == {"Deva", "Latn"}
    assert observation.mixed_script is True


def test_legacy_exclusion_is_explicit_and_does_not_remove_a_document() -> None:
    value = _load("V2_GOVERNED_COVERAGE_LIMITATION_POLICY.json")
    assert value["corpus_documents_retained"] == 44
    assert value["excluded_source_documents"] == 0
    assert value["excluded_from_transformation_dependent_generations"] == 504
    assert value["excluded_counts_by_representation"] == {
        "legacy_font_encoded_text": 502,
        "pdf_encoding_anomaly": 2,
    }
    assert value["silent_discard"] is False
    assert value["canonical_mutation"] is False


def test_governed_build_target_is_bound_and_unequal_to_historical_databases() -> None:
    value = _load("V2_DISPOSABLE_DATABASE_MANIFEST.json")
    target = ROOT / value["target_path"]
    assert value["disposable"] is True
    assert value["database_creation_authorization_mode"] == (
        "typed_build_authorization_v1_required"
    )
    if target.exists():
        import sqlite3

        authorization = _load("V2_INDEX_BUILD_AUTHORIZATION.json")
        connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                """SELECT authorization_id,target_database_path,profile_fingerprint,
                          vector_space_identity,state
                   FROM v2_build_runs WHERE run_id=?""",
                (authorization["run_id"],),
            ).fetchone()
            assert row == (
                authorization["authorization_id"],
                authorization["target_database_path"],
                authorization["profile_fingerprint"],
                authorization["vector_space_identity"],
                "ready",
            )
            assert connection.execute(
                "SELECT count(*) FROM active_multilingual_v2_alias_set"
            ).fetchone() == (1,)
        finally:
            connection.close()
    else:
        assert not Path(str(target) + "-wal").exists()
        assert not Path(str(target) + "-shm").exists()
    assert all(item["equal"] is False for item in value["protected_path_inequality"])


def test_build_manifest_is_deterministic_complete_and_next_phase_only() -> None:
    value = _load("V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json")
    assert value["authorization_state"] == "TYPED_BUILD_AUTHORIZATION_REQUIRED"
    assert value["buildability"] == "PASS"
    assert value["buildability_blockers"] == []
    assert {item["capability"] for item in value["generation_specifications"]} == {
        "representation_derivation_v2",
        "language_text_v2",
        "multilingual_embedding_v2",
        "multilingual_vector_v2",
    }
    for raw in value["generation_specifications"]:
        spec = ProjectionGenerationSpec.from_manifest_payload(raw)
        assert str(spec.generation_id) == raw["generation_id"]
        assert spec.contract_digest == raw["contract_digest"]


def test_typed_build_authorization_schema_and_bindings() -> None:
    schema = _load("V2_BUILD_AUTHORIZATION.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_load("V2_INDEX_BUILD_AUTHORIZATION.json"))
    authorization = _load("V2_INDEX_BUILD_AUTHORIZATION.json")
    storage = _load("V2_DISPOSABLE_DATABASE_MANIFEST.json")
    build = _load("V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json")
    assert authorization["authorized"] is True
    assert authorization["run_id"] == storage["run_id"]
    assert authorization["target_database_path"] == storage["target_path"]
    assert authorization["profile_fingerprint"] == storage["profile_fingerprint"]
    assert (
        authorization["vector_space_identity"]
        == storage["vector_space_profile_identity"]
        == build["vector_space_profile_identity"]
    )
    assert authorization["storage_manifest_digest"] == storage["artifact_digest"]
    assert authorization["build_manifest_digest"] == build["artifact_digest"]


def test_new_v2_production_modules_have_no_language_allowlist_branch() -> None:
    files = (
        "mnemo-core/mnemo/retrieval/full_multilingual_v2.py",
        "mnemo-core/mnemo/retrieval/full_multilingual_advanced_v2.py",
        "mnemo-core/mnemo/retrieval/multilingual_dense_v2.py",
        "mnemo-core/mnemo/retrieval/multilingual_sparse_v2.py",
        "mnemo-core/mnemo/retrieval/language_detection.py",
        "mnemo-core/mnemo/retrieval/text_representations.py",
        "mnemo-core/mnemo/phase85/full_multilingual_v2.py",
        "mnemo-core/mnemo/phase85/language_capabilities.py",
        "mnemo-core/mnemo/phase85/v2_readiness.py",
    )
    pattern = re.compile(r"(?:==|\bin\s*\()[^\n]{0,80}['\"](?:en|hi|mr)['\"]")
    assert not {
        name: pattern.findall((ROOT / name).read_text(encoding="utf-8"))
        for name in files
        if pattern.search((ROOT / name).read_text(encoding="utf-8"))
    }
