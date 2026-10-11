"""Disposable source inventories must reject incomplete or changed originals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mnemo_server.tools.source_manifest import build_source_manifest, verify_source_manifest


def test_source_manifest_rejects_invalid_specification(tmp_path: Path) -> None:
    for label, count in (("", 1), ("fixture", 0)):
        with pytest.raises(ValueError, match="invalid source corpus"):
            build_source_manifest(corpus=tmp_path, label=label, expected_count=count)


def test_source_manifest_rejects_unsupported_and_duplicate_bytes(tmp_path: Path) -> None:
    (tmp_path / "original.txt").write_bytes(b"original")
    (tmp_path / "derived.bin").write_bytes(b"derived")
    with pytest.raises(ValueError, match="unsupported or derived"):
        build_source_manifest(corpus=tmp_path, label="fixture", expected_count=1)
    (tmp_path / "derived.bin").unlink()
    (tmp_path / "duplicate.txt").write_bytes(b"original")
    with pytest.raises(ValueError, match="duplicate content hashes"):
        build_source_manifest(corpus=tmp_path, label="fixture", expected_count=2)


def test_source_manifest_rejects_missing_member_and_changed_bytes(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    original = corpus / "original.txt"
    original.write_bytes(b"original")
    with pytest.raises(ValueError, match="count differs"):
        build_source_manifest(corpus=corpus, label="fixture", expected_count=2)
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(build_source_manifest(corpus=corpus, label="fixture", expected_count=1)),
        encoding="utf-8",
    )
    assert len(verify_source_manifest(manifest=manifest, corpus=corpus)["sources"]) == 1
    original.write_bytes(b"changed")
    with pytest.raises(ValueError, match="differs from current original bytes"):
        verify_source_manifest(manifest=manifest, corpus=corpus)


def test_source_manifest_rejects_wrong_root_and_schema(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "original.txt").write_bytes(b"original")
    manifest = tmp_path / "sources.json"
    payload = build_source_manifest(corpus=corpus, label="fixture", expected_count=1)
    payload["schema"] = "unknown"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported source manifest"):
        verify_source_manifest(manifest=manifest, corpus=corpus)
    payload["schema"] = "mnemo.rebuild-source-manifest/1"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="corpus root mismatch"):
        verify_source_manifest(manifest=manifest, corpus=other)
