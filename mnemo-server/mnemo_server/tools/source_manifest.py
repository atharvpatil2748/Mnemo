"""Immutable, database-independent source inventory for isolated rebuilds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "mnemo.rebuild-source-manifest/1"
SUPPORTED = frozenset(
    {
        ".csv",
        ".docx",
        ".html",
        ".jpeg",
        ".jpg",
        ".js",
        ".json",
        ".md",
        ".pdf",
        ".pptx",
        ".py",
        ".txt",
        ".xlsx",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(sources: list[dict[str, Any]]) -> str:
    encoded = json.dumps(sources, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_source_manifest(*, corpus: Path, label: str, expected_count: int) -> dict[str, Any]:
    """Inventory original files; reject symlinks, unsupported and duplicate content."""
    root = corpus.resolve(strict=True)
    if not root.is_dir() or not label or expected_count < 1:
        raise ValueError("invalid source corpus specification")
    sources: list[dict[str, Any]] = []
    hashes: set[str] = set()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError("source corpus contains a symlink")
        if not path.is_file():
            continue
        extension = path.suffix.casefold()
        if extension not in SUPPORTED:
            raise ValueError("source corpus contains an unsupported or derived file")
        digest = _sha256(path)
        if digest in hashes:
            raise ValueError("source corpus contains duplicate content hashes")
        hashes.add(digest)
        sources.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "filename": path.name,
                "file_type": extension,
                "byte_size": path.stat().st_size,
                "sha256": digest,
            }
        )
    if len(sources) != expected_count:
        raise ValueError("source corpus count differs from the expected count")
    return {
        "schema": SCHEMA,
        "label": label,
        "corpus_root": str(root),
        "expected_count": expected_count,
        "notebook_input_identity": _identity(sources),
        "sources": sources,
    }


def verify_source_manifest(*, manifest: Path, corpus: Path) -> dict[str, Any]:
    """Require the manifest to match every current original byte, not an old index."""
    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(recorded, dict) or recorded.get("schema") != SCHEMA:
        raise ValueError("unsupported source manifest")
    root = corpus.resolve(strict=True)
    if recorded.get("corpus_root") != str(root):
        raise ValueError("source manifest corpus root mismatch")
    rebuilt = build_source_manifest(
        corpus=root,
        label=recorded["label"],
        expected_count=recorded["expected_count"],
    )
    if rebuilt != recorded:
        raise ValueError("source manifest differs from current original bytes")
    return rebuilt
