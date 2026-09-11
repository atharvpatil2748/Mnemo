"""Compare two isolated oversized-structure ingestion runs without modifying them."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mnemo.tokenizers import O200KBaseTokenCounter
from mnemo_server.tokenizer_provisioning import provisioned_tokenizer_path

_CHUNK_QUERY = """
SELECT document_id, version_id, position_section_index, position_chunk_index,
       id, text, chunk_type, position_page_number, position_start_offset,
       position_end_offset, source_start_ordinal, source_end_ordinal,
       heading_path, parent_chunk_id, sibling_ids, metadata,
       position_page_start, position_page_end
FROM chunks
ORDER BY document_id, position_section_index, position_chunk_index, id
"""


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _database(runtime: Path) -> Path:
    database = runtime.resolve() / "mnemo.db"
    if not database.is_file():
        raise FileNotFoundError(f"run database is absent: {database}")
    return database


def _canonical_json(value: str) -> str:
    return json.dumps(json.loads(value), sort_keys=True, separators=(",", ":"))


def _read_chunks(database: Path, counter: O200KBaseTokenCounter) -> list[dict[str, Any]]:
    uri = database.as_uri() + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(_CHUNK_QUERY).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "document_id": row[0],
                "version_id": row[1],
                "section_index": row[2],
                "chunk_index": row[3],
                "chunk_id": row[4],
                "text": row[5],
                "token_count": counter.count(row[5]),
                "chunk_type": row[6],
                "page_number": row[7],
                "start_offset": row[8],
                "end_offset": row[9],
                "source_start_ordinal": row[10],
                "source_end_ordinal": row[11],
                "heading_path": _canonical_json(row[12]),
                "parent_chunk_id": row[13],
                "sibling_ids": _canonical_json(row[14]),
                "metadata": _canonical_json(row[15]),
                "page_start": row[16],
                "page_end": row[17],
            }
        )
    return result


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    args = _arguments()
    first_database = _database(args.first)
    second_database = _database(args.second)
    counter = O200KBaseTokenCounter(provisioned_tokenizer_path())
    first = _read_chunks(first_database, counter)
    second = _read_chunks(second_database, counter)
    first_digest = _digest(first)
    second_digest = _digest(second)
    equivalent = first == second
    result = {
        "schema": "mnemo.oversized-atomic-repeatability/1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if equivalent else "FAIL",
        "read_only": True,
        "tokenizer_id": counter.tokenizer_id,
        "maximum_allowed_tokens": 1024,
        "first": {
            "runtime": args.first.as_posix(),
            "database": first_database.as_posix(),
            "chunks": len(first),
            "maximum_observed_tokens": max(item["token_count"] for item in first),
            "canonical_chunk_digest": first_digest,
        },
        "second": {
            "runtime": args.second.as_posix(),
            "database": second_database.as_posix(),
            "chunks": len(second),
            "maximum_observed_tokens": max(item["token_count"] for item in second),
            "canonical_chunk_digest": second_digest,
        },
        "comparisons": {
            "chunk_count": len(first) == len(second),
            "chunk_ids": [item["chunk_id"] for item in first]
            == [item["chunk_id"] for item in second],
            "ordering": [
                (item["document_id"], item["section_index"], item["chunk_index"]) for item in first
            ]
            == [
                (item["document_id"], item["section_index"], item["chunk_index"]) for item in second
            ],
            "semantic_text": [item["text"] for item in first] == [item["text"] for item in second],
            "token_counts": [item["token_count"] for item in first]
            == [item["token_count"] for item in second],
            "provenance_and_metadata": [
                {key: value for key, value in item.items() if key not in {"text", "token_count"}}
                for item in first
            ]
            == [
                {key: value for key, value in item.items() if key not in {"text", "token_count"}}
                for item in second
            ],
            "all_chunks_within_limit": all(
                item["token_count"] <= 1024 for item in (*first, *second)
            ),
            "canonical_digest": first_digest == second_digest,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = (
        "DETERMINISTIC_REPEATABILITY_PASS" if equivalent else "DETERMINISTIC_REPEATABILITY_FAIL"
    )
    print(f"RESULT: {status}")
    print(args.output.resolve())
    return 0 if equivalent else 1


if __name__ == "__main__":
    raise SystemExit(main())
