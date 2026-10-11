"""Portable corpus identity is not a notebook registry or a serving grant."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from mnemo.corpus_identity import DEPLOYMENT_SCHEMA, CorpusDeploymentIdentityV1


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _inputs(root: str) -> tuple[dict[str, object], dict[str, object]]:
    sources = [
        {
            "relative_path": "a.pdf",
            "filename": "a.pdf",
            "file_type": ".pdf",
            "byte_size": 3,
            "sha256": _digest("source-a"),
        },
        {
            "relative_path": "nested/b.png",
            "filename": "b.png",
            "file_type": ".png",
            "byte_size": 4,
            "sha256": _digest("source-b"),
        },
    ]
    manifest: dict[str, object] = {
        "schema": "mnemo.rebuild-source-manifest/1",
        "label": "personal",
        "corpus_root": root,
        "expected_count": 2,
        "sources": sources,
        "notebook_input_identity": _digest(sources),
    }
    declaration: dict[str, object] = {
        "schema": DEPLOYMENT_SCHEMA,
        "deployment_key": "production-personal",
        "source_manifest_digest": _digest(sources),
        "profile_fingerprint": _digest("profile"),
        "parser_digest": _digest("parser"),
        "retrieval_policy_digest": _digest("retrieval"),
        "storage_schema_version": 16,
        "capability_digests": {"canonical": _digest("canonical"), "ocr": _digest("ocr")},
    }
    return declaration, manifest


def test_identity_is_path_independent_and_generation_bound() -> None:
    left = CorpusDeploymentIdentityV1.from_declaration(*_inputs("C:/machine-a/corpus"))
    right = CorpusDeploymentIdentityV1.from_declaration(*_inputs("D:/machine-b/corpus"))
    assert left.corpus_identity == right.corpus_identity
    assert left.deployment_identity == right.deployment_identity
    generations = {"canonical": _digest("generation-a"), "ocr": _digest("generation-b")}
    assert left.index_identity(generations) == right.index_identity(generations)
    assert left.index_identity(generations) != left.index_identity(
        {"canonical": _digest("generation-a"), "ocr": _digest("generation-c")}
    )


def test_changed_source_inventory_or_profile_fails_closed() -> None:
    declaration, manifest = _inputs("C:/corpus")
    changed = deepcopy(manifest)
    changed_sources = cast(list[dict[str, object]], changed["sources"])
    changed_sources[0]["sha256"] = _digest("different")
    with pytest.raises(ValueError, match="identity differs"):
        CorpusDeploymentIdentityV1.from_declaration(declaration, changed)
    declaration["source_manifest_digest"] = _digest("wrong")
    with pytest.raises(ValueError, match="configured source manifest"):
        CorpusDeploymentIdentityV1.from_declaration(declaration, manifest)


def test_index_requires_exact_capability_set() -> None:
    identity = CorpusDeploymentIdentityV1.from_declaration(*_inputs("C:/corpus"))
    with pytest.raises(ValueError, match="capability set"):
        identity.index_identity({"canonical": _digest("generation-a")})
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        identity.index_identity({"canonical": "bad", "ocr": _digest("generation-b")})


@pytest.mark.parametrize("path", ["../secret", "/absolute", "nested/../secret", "a\\b"])
def test_manifest_rejects_nonportable_source_paths(path: str) -> None:
    declaration, manifest = _inputs("C:/corpus")
    sources = cast(list[dict[str, object]], deepcopy(manifest["sources"]))
    sources[0]["relative_path"] = path
    manifest["sources"] = sources
    manifest["notebook_input_identity"] = _digest(sources)
    declaration["source_manifest_digest"] = _digest(sources)
    with pytest.raises(ValueError, match="path"):
        CorpusDeploymentIdentityV1.from_declaration(declaration, manifest)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"schema": "unknown"}, "schema"),
        ({"expected_count": 3}, "count"),
        ({"expected_count": True}, "incomplete"),
        ({"sources": []}, "incomplete"),
        ({"notebook_input_identity": "0" * 64}, "identity differs"),
    ],
)
def test_source_inventory_rejects_unverified_manifest_structure(
    change: dict[str, object], error: str
) -> None:
    declaration, manifest = _inputs("C:/corpus")
    manifest.update(change)
    with pytest.raises(ValueError, match=error):
        CorpusDeploymentIdentityV1.from_declaration(declaration, manifest)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("relative_path", "a.pdf", "unique and normalized"),
        ("relative_path", "C:/absolute.pdf", "unique and normalized"),
        ("sha256", "INVALID", "lowercase SHA-256"),
        ("byte_size", -1, "byte size"),
        ("byte_size", True, "byte size"),
    ],
)
def test_source_inventory_rejects_duplicate_or_malformed_entry(
    field: str, value: object, error: str
) -> None:
    declaration, manifest = _inputs("C:/corpus")
    sources = cast(list[dict[str, object]], deepcopy(manifest["sources"]))
    sources[1][field] = value
    manifest["sources"] = sources
    manifest["notebook_input_identity"] = _digest(sources)
    declaration["source_manifest_digest"] = _digest(sources)
    with pytest.raises(ValueError, match=error):
        CorpusDeploymentIdentityV1.from_declaration(declaration, manifest)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("schema", "unknown", "schema"),
        ("capability_digests", [], "capability digests"),
        ("deployment_key", "INVALID", "deployment key"),
        ("profile_fingerprint", "bad", "lowercase SHA-256"),
        ("storage_schema_version", 0, "storage schema version"),
        ("capability_digests", {}, "capability names"),
        ("capability_digests", {"Bad Name": "a" * 64}, "capability name"),
    ],
)
def test_deployment_identity_rejects_invalid_authority_inputs(
    field: str, value: object, error: str
) -> None:
    declaration, manifest = _inputs("C:/corpus")
    declaration[field] = value
    with pytest.raises(ValueError, match=error):
        CorpusDeploymentIdentityV1.from_declaration(declaration, manifest)


def test_index_identity_requires_generation_evidence() -> None:
    identity = CorpusDeploymentIdentityV1.from_declaration(*_inputs("C:/corpus"))
    with pytest.raises(ValueError, match="evidence is missing"):
        identity.index_identity({})


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("non-dict", "source entry is invalid"),
        ("missing-hash", "source hash is missing"),
        ("reordered", "ordering is not deterministic"),
    ],
)
def test_source_inventory_rejects_untyped_or_unordered_members(change: str, error: str) -> None:
    declaration, manifest = _inputs("C:/corpus")
    sources = cast(list[dict[str, object]], deepcopy(manifest["sources"]))
    if change == "non-dict":
        sources[1] = cast(dict[str, object], "bad-entry")
    elif change == "missing-hash":
        del sources[1]["sha256"]
    else:
        sources.reverse()
    manifest["sources"] = sources
    manifest["notebook_input_identity"] = _digest(sources)
    declaration["source_manifest_digest"] = _digest(sources)
    with pytest.raises(ValueError, match=error):
        CorpusDeploymentIdentityV1.from_declaration(declaration, manifest)


def test_capability_digest_and_index_generation_cannot_be_unverified() -> None:
    declaration, manifest = _inputs("C:/corpus")
    declaration["capability_digests"] = {"canonical": "bad"}
    with pytest.raises(ValueError, match="capability digest must be a lowercase SHA-256"):
        CorpusDeploymentIdentityV1.from_declaration(declaration, manifest)


def test_file_hash_helper_uses_actual_disposable_bytes(tmp_path: Path) -> None:
    source = tmp_path / "original.bin"
    source.write_bytes(b"fixture original bytes")
    assert (
        CorpusDeploymentIdentityV1.file_sha256(source)
        == hashlib.sha256(b"fixture original bytes").hexdigest()
    )
