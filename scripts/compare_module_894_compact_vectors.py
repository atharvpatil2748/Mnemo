"""Read-only exact-vector sidecar comparison; no generation or alias changes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "mnemo-core") not in sys.path:
    sys.path.insert(0, str(ROOT / "mnemo-core"))

from mnemo.models.multilingual_embeddings import MultilingualEmbeddingV3  # noqa: E402
from mnemo.retrieval.multilingual_dense_v2 import _cosine  # noqa: E402
from mnemo.storage.multilingual import _decode_checked  # noqa: E402

from scripts.benchmark_module_894_compact_vectors import (  # noqa: E402
    SOURCE,
    TARGET,
    restore,
    sha256,
)


def ranked(
    conn: sqlite3.Connection, table: str, query: tuple[float, ...]
) -> tuple[int, int, float, str, float, float, float]:
    started = time.perf_counter()
    count = 0
    payload_bytes = 0
    fetch_seconds = 0.0
    decode_seconds = 0.0
    score_seconds = 0.0
    scores: list[tuple[float, str]] = []
    if table == "original":
        statement = (
            "SELECT embedding_id,payload,payload_hash FROM multilingual_embeddings_v2 "
            "ORDER BY embedding_id"
        )
    else:
        statement = (
            "SELECT embedding_id,metadata_payload,vector_blob,record_hash "
            "FROM compact_multilingual_embeddings_v1 ORDER BY embedding_id"
        )
    cursor = conn.execute(statement)
    while True:
        fetch_started = time.perf_counter()
        row = cursor.fetchone()
        fetch_seconds += time.perf_counter() - fetch_started
        if row is None:
            break
        decode_started = time.perf_counter()
        value = _decode_checked(row[1:]) if table == "original" else restore(row[1], row[2], row[3])
        if not isinstance(value, MultilingualEmbeddingV3) or str(value.embedding_id) != row[0]:
            raise ValueError("vector identity mismatch")
        decode_seconds += time.perf_counter() - decode_started
        count += 1
        payload_bytes += len(row[1]) + (len(row[2]) if table != "original" else 0)
        score_started = time.perf_counter()
        scores.append((_cosine(query, value.vector), row[0]))
        score_seconds += time.perf_counter() - score_started
    top = sorted(scores, key=lambda item: (-item[0], item[1]))[:10]
    digest = hashlib.sha256(json.dumps(top, separators=(",", ":")).encode()).hexdigest()
    return (
        count,
        payload_bytes,
        time.perf_counter() - started,
        digest,
        fetch_seconds,
        decode_seconds,
        score_seconds,
    )


def main() -> int:
    state = json.loads((ROOT / "config/production/runtime-selection.json").read_text())
    if state["state"] != "UNINDEXED":
        raise ValueError("production selector changed")
    if not SOURCE.is_file() or not TARGET.is_file():
        raise FileNotFoundError("verified disposable source and inactive sidecar required")
    before = sha256(SOURCE)
    source = sqlite3.connect(f"file:{SOURCE.resolve().as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(f"file:{TARGET.resolve().as_posix()}?mode=ro", uri=True)
    source.execute("PRAGMA query_only=ON")
    target.execute("PRAGMA query_only=ON")
    try:
        first = source.execute(
            "SELECT payload,payload_hash FROM multilingual_embeddings_v2 "
            "ORDER BY embedding_id LIMIT 1"
        ).fetchone()
        if first is None:
            raise ValueError("source generation has no embeddings")
        probe = _decode_checked(first)
        if not isinstance(probe, MultilingualEmbeddingV3):
            raise ValueError("unexpected source vector type")
        original = ranked(source, "original", probe.vector)
        compact = ranked(target, "compact", probe.vector)
        result = {
            "source_rows": original[0],
            "compact_rows": compact[0],
            "source_payload_bytes": original[1],
            "compact_payload_bytes": compact[1],
            "source_read_decode_score_seconds": original[2],
            "compact_read_decode_score_seconds": compact[2],
            "source_top10_digest": original[3],
            "compact_top10_digest": compact[3],
            "source_fetch_seconds": original[4],
            "compact_fetch_seconds": compact[4],
            "source_decode_validate_seconds": original[5],
            "compact_decode_validate_seconds": compact[5],
            "source_score_seconds": original[6],
            "compact_score_seconds": compact[6],
            "exact_top10_equivalence": original[3] == compact[3],
            "production_state": "UNINDEXED",
        }
        print(json.dumps(result), flush=True)
        if original[0] != 10931 or original[0] != compact[0] or original[3] != compact[3]:
            raise ValueError("inactive compact path changes exact retrieval ranking")
    finally:
        source.close()
        target.close()
    if sha256(SOURCE) != before:
        raise RuntimeError("source disposable database changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
