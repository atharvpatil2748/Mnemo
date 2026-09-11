from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from mnemo.phase85.v2_database_identity import GovernedV2DatabaseIdentityVerifier

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
IDENTITY_MANIFEST = (
    WORKSPACE_ROOT
    / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
    / "V2_DATABASE_ARTIFACT_IDENTITY.json"
)


def _write_reidentified_manifest(tmp_path: Path, raw: dict[str, object]) -> Path:
    payload = {key: value for key, value in raw.items() if key != "database_identity"}
    raw["database_identity"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    target = tmp_path / "identity.json"
    target.write_text(json.dumps(raw), encoding="utf-8")
    return target


def _verifier() -> GovernedV2DatabaseIdentityVerifier:
    return GovernedV2DatabaseIdentityVerifier(
        workspace_root=WORKSPACE_ROOT,
        identity_manifest=IDENTITY_MANIFEST,
    )


def test_database_identity_is_deterministic_and_bound_to_governed_artifact() -> None:
    first = _verifier()
    second = _verifier()
    assert first.artifact.database_identity == second.artifact.database_identity
    assert first.artifact.database_identity == first.artifact.canonical_identity
    first.verify(expected_database_identity=first.artifact.database_identity)


def test_database_identity_rejects_unrelated_identity() -> None:
    with pytest.raises(ValueError, match="DATABASE_BINDING_MISMATCH"):
        _verifier().verify(expected_database_identity="f" * 64)


def test_database_identity_manifest_rejects_altered_canonical_envelope(
    tmp_path: Path,
) -> None:
    raw = json.loads(IDENTITY_MANIFEST.read_text(encoding="utf-8"))
    raw["profile_fingerprint"] = "e" * 64
    altered = tmp_path / "identity.json"
    altered.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical build envelope"):
        GovernedV2DatabaseIdentityVerifier(
            workspace_root=WORKSPACE_ROOT,
            identity_manifest=altered,
        )


def test_vector_generation_resolves_distinct_manifest_backed_embedding_generation() -> None:
    verifier = _verifier()
    binding = verifier.resolve_vector_embedding_generation(
        active_generation_ids=tuple(value.generation_id for value in verifier.artifact.generations),
        expected_database_identity=verifier.artifact.database_identity,
    )
    vector = next(
        value
        for value in verifier.artifact.generations
        if value.capability == "multilingual_vector_v2"
    )
    embedding = next(
        value
        for value in verifier.artifact.generations
        if value.capability == "multilingual_embedding_v2"
    )
    assert binding.vector_generation_id == vector.generation_id
    assert binding.embedding_generation_id == embedding.generation_id
    assert binding.vector_generation_id != binding.embedding_generation_id
    assert vector.source_generation_ids == (embedding.generation_id,)
    assert binding.model_identity == embedding.model_identity
    assert binding.dimensions == 1024


def test_vector_embedding_resolution_rejects_non_active_generation_set() -> None:
    verifier = _verifier()
    with pytest.raises(ValueError, match="ACTIVE_GENERATION_MISMATCH"):
        verifier.resolve_vector_embedding_generation(
            active_generation_ids=tuple(
                value.generation_id for value in verifier.artifact.generations[:-1]
            ),
            expected_database_identity=verifier.artifact.database_identity,
        )


@pytest.mark.parametrize("mutation", ["missing_relationship", "wrong_model"])
def test_vector_embedding_resolution_rejects_manifest_dependency_or_model_mismatch(
    tmp_path: Path, mutation: str
) -> None:
    raw = json.loads(IDENTITY_MANIFEST.read_text(encoding="utf-8"))
    generations = raw["generations"]
    assert isinstance(generations, list)
    vector = next(
        value
        for value in generations
        if isinstance(value, dict) and value.get("capability") == "multilingual_vector_v2"
    )
    if mutation == "missing_relationship":
        vector["source_generation_ids"] = []
    else:
        vector["model_identity"] = "BAAI/bge-m3@wrong-revision"
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=WORKSPACE_ROOT,
        identity_manifest=_write_reidentified_manifest(tmp_path, raw),
    )
    with pytest.raises(ValueError, match=r"DATABASE_GENERATION_(?:BINDING|DEPENDENCY)_MISMATCH"):
        verifier.resolve_vector_embedding_generation(
            active_generation_ids=tuple(
                value.generation_id for value in verifier.artifact.generations
            ),
            expected_database_identity=verifier.artifact.database_identity,
        )
