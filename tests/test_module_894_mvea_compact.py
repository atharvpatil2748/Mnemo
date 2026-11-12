"""Lossless compact sidecar roundtrip and fail-closed integrity checks."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest
from mnemo.models.multilingual_embeddings import MultilingualEmbeddingV3
from mnemo.storage.multilingual import _decode_checked

from scripts import benchmark_module_894_compact_vectors as compact_benchmark


def test_real_disposable_vector_roundtrips_bit_exactly() -> None:
    database = compact_benchmark.SOURCE
    with closing(sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)) as db:
        row = db.execute(
            "SELECT payload,payload_hash FROM multilingual_embeddings_v2 LIMIT 1"
        ).fetchone()
    original = _decode_checked(row)
    assert isinstance(original, MultilingualEmbeddingV3)
    payload, blob, digest = compact_benchmark.compact(original)
    assert len(blob) == original.profile.dimension * 8
    assert compact_benchmark.restore(payload, blob, digest) == original
    corrupt = bytearray(blob)
    corrupt[0] ^= 1
    with pytest.raises(ValueError, match="record hash mismatch"):
        compact_benchmark.restore(payload, bytes(corrupt), digest)
    with pytest.raises(ValueError, match="record hash mismatch"):
        compact_benchmark.restore(payload, blob[:-8], digest)


def test_float32_sidecar_encoding_is_lossless_for_retained_bge_vectors() -> None:
    database = compact_benchmark.SOURCE
    with closing(sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)) as db:
        row = db.execute(
            "SELECT payload,payload_hash FROM multilingual_embeddings_v2 LIMIT 1"
        ).fetchone()
    original = _decode_checked(row)
    assert isinstance(original, MultilingualEmbeddingV3)
    payload, blob, digest = compact_benchmark.compact(original, encoding="float32")
    assert len(blob) == original.profile.dimension * 4
    assert compact_benchmark.restore(payload, blob, digest, encoding="float32") == original
