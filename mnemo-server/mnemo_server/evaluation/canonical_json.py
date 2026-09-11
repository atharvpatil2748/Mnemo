"""Canonical JSON serialization for evaluation-notebook identity bindings."""

from __future__ import annotations

import hashlib
import json


def canonical_json_bytes_v1(value: object) -> bytes:
    """Serialize identity material deterministically as canonical UTF-8 JSON."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256_v1(value: object) -> str:
    """Return the SHA-256 identity of canonical UTF-8 JSON material."""

    return hashlib.sha256(canonical_json_bytes_v1(value)).hexdigest()
