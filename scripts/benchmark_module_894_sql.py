"""Disposable-only comparison of the governed V2 semantic-page query plan.

Never opens the source for writing. Creates an SQLite online-backup copy and
adds the candidate index only to that copy; prints measured results to stdout.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scratch/module_894_multimodal/eval-20261109-01/mnemo.db"
TARGET = ROOT / "scratch/module_894_multimodal/eval-sql-index-20261110-01/mnemo.db"
NOTEBOOKS = (
    "81a3bea2-8b15-5c6f-944d-24634fbf835d",
    "cbad96d6-a75a-5b6a-a872-ffbee64c58ad",
)
QUERY = (
    "SELECT payload,payload_hash FROM language_text_projection_rows_v2 "
    "WHERE notebook_id=? AND generation_id=? "
    "ORDER BY evidence_reference_digest,representation_reference_id LIMIT ? OFFSET ?"
)
INDEX = (
    "CREATE INDEX idx_language_text_projection_v2_page "
    "ON language_text_projection_rows_v2("
    "notebook_id,generation_id,evidence_reference_digest,representation_reference_id)"
)


def _read_only(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path.resolve(strict=True).as_posix()}?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    return db


def _measure(db: sqlite3.Connection, notebook: str, generation: str) -> dict[str, object]:
    plan = db.execute("EXPLAIN QUERY PLAN " + QUERY, (notebook, generation, 2000, 0)).fetchall()
    observations: list[dict[str, object]] = []
    for offset in (0, 2000, 4000):
        started = time.perf_counter()
        rows = db.execute(QUERY, (notebook, generation, 2000, offset)).fetchall()
        elapsed = time.perf_counter() - started
        observations.append(
            {
                "offset": offset,
                "count": len(rows),
                "elapsed_seconds": elapsed,
                "payload_bytes": sum(len(row[0]) for row in rows),
                "hashes_sha256": hashlib.sha256(
                    "".join(str(row[1]) for row in rows).encode()
                ).hexdigest(),
            }
        )
    return {"plan": [str(row[3]) for row in plan], "pages": observations}


def main() -> None:
    selector = json.loads((ROOT / "config/production/runtime-selection.json").read_text())
    if selector.get("state") != "UNINDEXED":
        raise RuntimeError("production selector is not UNINDEXED")
    if TARGET.exists() or TARGET.parent.exists():
        raise FileExistsError("disposable SQL benchmark target already exists")
    if not SOURCE.resolve(strict=True).is_relative_to((ROOT / "scratch").resolve()):
        raise ValueError("source must be disposable")
    source = _read_only(SOURCE)
    try:
        generation_row = source.execute(
            "SELECT generation_id FROM index_generations "
            "WHERE capability='language_text_v2' AND state='ready' "
            "ORDER BY generation_id LIMIT 1"
        ).fetchone()
        if generation_row is None:
            raise RuntimeError("no ready disposable V2 semantic generation")
        generation = str(generation_row[0])
        before = {notebook: _measure(source, notebook, generation) for notebook in NOTEBOOKS}
        TARGET.parent.mkdir(parents=True)
        copy = sqlite3.connect(TARGET)
        try:
            source.backup(copy)
            copy.execute(INDEX)
            copy.commit()
        finally:
            copy.close()
    finally:
        source.close()
    indexed = _read_only(TARGET)
    try:
        after = {notebook: _measure(indexed, notebook, generation) for notebook in NOTEBOOKS}
    finally:
        indexed.close()
    for notebook in NOTEBOOKS:
        before_pages = cast(list[dict[str, object]], before[notebook]["pages"])
        after_pages = cast(list[dict[str, object]], after[notebook]["pages"])
        if [p["hashes_sha256"] for p in before_pages] != [p["hashes_sha256"] for p in after_pages]:
            raise RuntimeError("semantic-page ordering or content changed")
    print(
        json.dumps(
            {"source": str(SOURCE), "copy": str(TARGET), "before": before, "after": after},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
