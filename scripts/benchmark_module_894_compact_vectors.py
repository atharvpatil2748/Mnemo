"""Build an inactive exact-float64 vector sidecar in a fresh disposable SQLite copy.

The successful source runtime is opened read-only and never checkpointed. This
experiment does not activate an alias or alter production/default retrieval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import struct
import sys
import time
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "mnemo-core") not in sys.path:
    sys.path.insert(0, str(ROOT / "mnemo-core"))

from mnemo.models.multilingual_embeddings import MultilingualEmbeddingV3  # noqa: E402
from mnemo.retrieval.final_qa_snapshot import _decode, _encode  # noqa: E402
from mnemo.storage.multilingual import _decode_checked  # noqa: E402

SOURCE = ROOT / "scratch/module_894_multimodal/eval-20261109-01/mnemo.db"
TARGET = ROOT / "scratch/module_894_multimodal/eval-compact-f64-20261111-01/mnemo.db"
EXPECTED_ALIAS = "83b0f6684ffbfc3d3fba3ab2634aedddfa3c3434dfd449c2eb7d1fe61b125c93"
SCHEMA = """CREATE TABLE compact_multilingual_embeddings_v1 (
    embedding_id TEXT PRIMARY KEY,
    notebook_id TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    vector_space TEXT NOT NULL,
    evidence_reference_digest TEXT NOT NULL,
    metadata_payload TEXT NOT NULL,
    vector_blob BLOB NOT NULL,
    record_hash TEXT NOT NULL,
    UNIQUE(evidence_reference_digest,generation_id,vector_space)
)"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compact(value: MultilingualEmbeddingV3, *, encoding: str = "float64") -> tuple[str, bytes, str]:
    metadata = {
        field.name: getattr(value, field.name) for field in fields(value) if field.name != "vector"
    }
    payload = _encode(metadata)
    if encoding == "float64":
        blob = struct.pack(f"<{len(value.vector)}d", *value.vector)
    elif encoding == "float32":
        blob = struct.pack(f"<{len(value.vector)}f", *value.vector)
        roundtrip = struct.unpack(f"<{len(value.vector)}f", blob)
        if tuple(roundtrip) != value.vector:
            raise ValueError("float32 compact encoding is not bit-exact for this vector")
    else:
        raise ValueError("unsupported compact vector encoding")
    digest = hashlib.sha256(payload.encode("utf-8") + blob).hexdigest()
    return payload, blob, digest


def restore(
    payload: str, blob: bytes, digest: str, *, encoding: str = "float64"
) -> MultilingualEmbeddingV3:
    if hashlib.sha256(payload.encode("utf-8") + blob).hexdigest() != digest:
        raise ValueError("compact vector record hash mismatch")
    metadata = _decode(payload)
    if not isinstance(metadata, dict):
        raise ValueError("invalid compact vector metadata or dimension")
    if encoding == "float64" and len(blob) % 8 == 0:
        values = struct.unpack(f"<{len(blob) // 8}d", blob)
    elif encoding == "float32" and len(blob) % 4 == 0:
        values = struct.unpack(f"<{len(blob) // 4}f", blob)
    else:
        raise ValueError("compact vector blob does not match its declared encoding")
    return MultilingualEmbeddingV3(**cast(dict[str, Any], metadata), vector=values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--encoding", choices=("float64", "float32"), default="float64")
    args = parser.parse_args()
    source_path = args.source.resolve()
    target_path = args.target.resolve()
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        raise ValueError("production selector changed")
    if target_path.exists() or target_path.parent.exists():
        raise FileExistsError("fresh disposable compact experiment identity required")
    if not source_path.is_relative_to((ROOT / "scratch").resolve()):
        raise ValueError("compact source is not disposable")
    source_hash = sha256(source_path)
    wal = Path(str(source_path) + "-wal")
    wal_hash = sha256(wal) if wal.is_file() else None
    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    source.execute("PRAGMA query_only=ON")
    alias = source.execute(
        "SELECT alias_set_digest FROM active_multilingual_v2_alias_set WHERE singleton=1"
    ).fetchone()
    if alias != (EXPECTED_ALIAS,):
        source.close()
        raise ValueError("disposable generation alias differs")
    target_path.parent.mkdir(parents=True)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
        target.execute(SCHEMA)
        target.execute(
            "CREATE INDEX idx_compact_v1_scope ON compact_multilingual_embeddings_v1("
            "notebook_id,generation_id,vector_space,evidence_reference_digest)"
        )
        started = time.perf_counter()
        total = 0
        original_bytes = 0
        compact_bytes = 0
        for row in source.execute(
            "SELECT embedding_id,notebook_id,generation_id,vector_space,"
            "evidence_reference_digest,payload,payload_hash "
            "FROM multilingual_embeddings_v2 ORDER BY embedding_id"
        ):
            value = _decode_checked(row[5:])
            if not isinstance(value, MultilingualEmbeddingV3) or str(value.embedding_id) != row[0]:
                raise ValueError("source vector identity or integrity invalid")
            metadata, blob, digest = compact(value, encoding=args.encoding)
            if restore(metadata, blob, digest, encoding=args.encoding) != value:
                raise ValueError(f"{args.encoding} compact roundtrip changed a governed embedding")
            target.execute(
                "INSERT INTO compact_multilingual_embeddings_v1 VALUES(?,?,?,?,?,?,?,?)",
                (*row[:5], metadata, blob, digest),
            )
            total += 1
            original_bytes += len(row[5])
            compact_bytes += len(metadata) + len(blob)
            if total % 1000 == 0:
                print(
                    json.dumps(
                        {"converted": total, "elapsed_seconds": time.perf_counter() - started}
                    ),
                    flush=True,
                )
        actual = target.execute(
            "SELECT count(*) FROM compact_multilingual_embeddings_v1"
        ).fetchone()
        expected = source.execute("SELECT count(*) FROM multilingual_embeddings_v2").fetchone()
        if actual != expected or actual != (total,):
            raise ValueError("compact sidecar coverage incomplete")
        target.commit()
        print(
            json.dumps(
                {
                    "status": "INACTIVE_EXPERIMENT",
                    "rows": total,
                    "source_database_sha256": source_hash,
                    "source_wal_sha256": wal_hash,
                    "source_bytes": original_bytes,
                    "compact_bytes": compact_bytes,
                    "build_seconds": time.perf_counter() - started,
                    "target": str(target_path),
                    "vector_encoding": args.encoding,
                }
            )
        )
    finally:
        target.close()
        source.close()
    if sha256(source_path) != source_hash or (sha256(wal) if wal.is_file() else None) != wal_hash:
        raise RuntimeError("source disposable runtime changed during compact experiment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
