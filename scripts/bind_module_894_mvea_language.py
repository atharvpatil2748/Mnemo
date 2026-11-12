"""Freeze independently authored, snapshot-bound Module 8.9.4 language identity cases.

The blueprint is authored from retained chunks before retrieval. Binding never
executes search, scores candidates, or changes the disposable SQLite runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "config/evaluation/module_894_mvea_language.v1.json"
PLAN = ROOT / "config/evaluation/phase86_four_notebooks.v1.json"
RUN_ID = "phase86-three-languages-with-retained-original-v1-b153f2faa728599a"
RUNTIME = ROOT / "scratch/module_894_multimodal/eval-20261109-01"
LOGS = ROOT / "logs/evaluation_ingestion" / RUN_ID
OUTPUT = ROOT / "evaluation/module_894_mvea/language-identity.v1.json"
EXPECTED_SNAPSHOT_SHA256 = "1902c3a46b2c4cba3bab7efae237af178b0830df7298fc26073c49047ad91c93"
EXPECTED_ALIAS = "83b0f6684ffbfc3d3fba3ab2634aedddfa3c3434dfd449c2eb7d1fe61b125c93"
LANGUAGES = ("en", "hi", "mr")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_only(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    if not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f"unavailable or external evaluation database: {path}")
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    db = sqlite3.connect(f"file:{path.resolve().as_posix()}{suffix}", uri=True)
    db.execute("PRAGMA query_only=ON")
    return db


def bind() -> dict[str, Any]:
    production = json.loads((ROOT / "config/production/runtime-selection.json").read_text())
    if production["state"] != "UNINDEXED":
        raise ValueError("production selector is not UNINDEXED")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    snapshot = ROOT / plan["existing_notebook"]["snapshot"]
    if sha256(snapshot) != EXPECTED_SNAPSHOT_SHA256:
        raise ValueError("protected snapshot identity changed")
    if json.loads((LOGS / "run_state.json").read_text())["status"] != "SUCCEEDED":
        raise ValueError("four-notebook run is not successful")
    run_manifest = json.loads((LOGS / "run_manifest.json").read_text())
    if run_manifest["run_id"] != RUN_ID or run_manifest["snapshot_sha256"] != sha256(snapshot):
        raise ValueError("four-notebook run identity changed")
    sources_path = ROOT / plan["source_manifest"]
    if sha256(sources_path) != plan["source_manifest_sha256"]:
        raise ValueError("source inventory identity changed")
    source_manifest = json.loads(sources_path.read_text(encoding="utf-8"))
    source_root = Path(source_manifest["corpus_root"])
    by_name = {row["filename"]: row for row in source_manifest["sources"]}
    blueprint = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
    if (
        blueprint["schema"] != "mnemo.module-894-mvea-language-blueprint/1"
        or blueprint["judgment_method"] != "DETERMINISTIC_ENGINEERING"
        or blueprint["semantic_relevance_adjudicated"] is not False
        or len(blueprint["targets"]) != 30
    ):
        raise ValueError("incomplete or ungoverned language blueprint")
    # The configured notebook IDs live in the successful run manifest, not the plan.
    notebook_ids = run_manifest["notebooks"]
    original = plan["existing_notebook"]["id"]
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_chunks: set[str] = set()
    verified_files: set[str] = set()
    with (
        closing(_read_only(snapshot, immutable=True)) as historical,
        closing(_read_only(RUNTIME / "mnemo.db")) as current,
    ):
        active = current.execute(
            "SELECT alias_set_digest FROM active_multilingual_v2_alias_set WHERE singleton=1"
        ).fetchone()
        if active != (EXPECTED_ALIAS,):
            raise ValueError("disposable active alias differs from frozen identity")
        for index, target in enumerate(blueprint["targets"]):
            target_id = str(target["id"])
            document_language = target_id[:2].lower()
            file_name = str(target["file"])
            chunk_id = str(target["chunk"])
            anchor = str(target["anchor"])
            if (
                target_id in seen_ids
                or chunk_id in seen_chunks
                or document_language not in LANGUAGES
                or file_name not in plan["notebooks"][document_language]["files"]
                or set(target["queries"]) != set(LANGUAGES)
                or not anchor.strip()
            ):
                raise ValueError(f"invalid or repeated target: {target_id}")
            seen_ids.add(target_id)
            seen_chunks.add(chunk_id)
            source_row = by_name[file_name]
            file_sha = source_row["sha256"]
            if file_name not in verified_files:
                path = source_root / source_row["relative_path"]
                if path.stat().st_size != source_row["byte_size"] or sha256(path) != file_sha:
                    raise ValueError(f"source file differs from frozen inventory: {file_name}")
                verified_files.add(file_name)
            old = historical.execute(
                "SELECT s.source_id,d.document_id,d.current_version_id,c.text "
                "FROM sources s JOIN documents d ON d.document_id=s.document_id "
                "JOIN chunks c ON c.document_id=d.document_id "
                "AND c.version_id=d.current_version_id "
                "WHERE s.notebook_id=? AND d.current_hash=? AND c.id=?",
                (original, file_sha, chunk_id),
            ).fetchall()
            if len(old) != 1 or anchor.casefold() not in old[0][3].casefold():
                raise ValueError(f"target is not grounded in protected snapshot: {target_id}")
            text_hash = hashlib.sha256(old[0][3].encode("utf-8")).hexdigest()
            selected = [notebook_ids[document_language]]
            if index % 2:
                selected = [original, *notebook_ids.values()]
            targets: list[dict[str, str]] = []
            for notebook in [original, notebook_ids[document_language]] if index % 2 else selected:
                rows = current.execute(
                    "SELECT s.source_id,d.document_id,d.current_version_id,c.text "
                    "FROM sources s JOIN documents d ON d.document_id=s.document_id "
                    "JOIN chunks c ON c.document_id=d.document_id "
                    "AND c.version_id=d.current_version_id "
                    "WHERE s.notebook_id=? AND d.current_hash=? AND c.id=?",
                    (notebook, file_sha, chunk_id),
                ).fetchall()
                if len(rows) != 1 or rows[0][1:] != old[0][1:]:
                    raise ValueError(f"disposable ancestry differs from snapshot: {target_id}")
                targets.append(
                    {
                        "notebook_id": notebook,
                        "source_id": rows[0][0],
                        "document_id": rows[0][1],
                        "version_id": rows[0][2],
                        "evidence_id": chunk_id,
                        "source_file_sha256": file_sha,
                        "evidence_content_sha256": text_hash,
                    }
                )
            for query_language in LANGUAGES:
                query = str(target["queries"][query_language])
                if not query.strip() or query != unicodedata.normalize("NFC", query):
                    raise ValueError(f"unnormalized query: {target_id}/{query_language}")
                cases.append(
                    {
                        "case_id": f"MVEA-LANG-{target_id}-{query_language.upper()}",
                        "query": query,
                        "query_language": query_language,
                        "document_language": document_language,
                        "representation": "canonical_text",
                        "selected_notebooks": selected,
                        "targets": targets,
                        "judgment_method": "DETERMINISTIC_ENGINEERING",
                        "judgment_provenance": (
                            "authored source-content question; hash-verified snapshot chunk"
                        ),
                        "anchor": anchor,
                    }
                )
    cells = Counter((case["query_language"], case["document_language"]) for case in cases)
    if len(cases) != 90 or any(
        cells[(query, document)] != 10 for query in LANGUAGES for document in LANGUAGES
    ):
        raise ValueError("language matrix does not have ten cases per cell")
    return {
        "schema": "mnemo.module-894-mvea-language-identity/1",
        "protocol": "MVEA-DETERMINISTIC-IDENTITY/1",
        "judgment_method": "DETERMINISTIC_ENGINEERING",
        "semantic_relevance_adjudicated": False,
        "human_relevance_reviewed": False,
        "run_id": RUN_ID,
        "runtime_database": str((RUNTIME / "mnemo.db").relative_to(ROOT)),
        "snapshot_sha256": EXPECTED_SNAPSHOT_SHA256,
        "source_manifest_sha256": sha256(sources_path),
        "blueprint_sha256": sha256(BLUEPRINT),
        "active_alias_digest": EXPECTED_ALIAS,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="validate without writing the bound QREL"
    )
    args = parser.parse_args()
    manifest = bind()
    payload = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    digest = hashlib.sha256(payload).hexdigest()
    if not args.check:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open("xb") as stream:
            stream.write(payload)
            stream.flush()
        if sha256(OUTPUT) != digest:
            raise RuntimeError("bound language QREL readback differs")
    print(
        json.dumps(
            {
                "cases": len(manifest["cases"]),
                "digest": digest,
                "output": str(OUTPUT),
                "written": not args.check,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
