"""Read-only DERE provenance/admission preflight for an explicit isolated snapshot.

This does not execute retrieval or certify semantic relevance. It refuses to
produce ranking metrics when notebook ACL and active-generation admission are
not established in the selected disposable store.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def verify(manifest_path: Path, snapshot: Path) -> dict[str, Any]:
    """Verify identity receipts without opening source bytes or writing stores."""
    snapshot = snapshot.resolve(strict=True)
    expected_root = (Path(__file__).resolve().parents[1] / "scratch" / "phase8_5_11").resolve()
    if not snapshot.is_relative_to(expected_root) or not snapshot.name.startswith("eval-"):
        raise ValueError("DERE preflight requires an explicit isolated evaluation snapshot")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != "mnemo.dere/1"
        or manifest.get("judgment_method") != "DETERMINISTIC_ENGINEERING"
        or manifest.get("human_adjudication_claimed") is not False
    ):
        raise ValueError("invalid DERE manifest contract")
    if manifest["snapshot"]["identity"] != "/".join(snapshot.parts[-2:]):
        raise ValueError("selected snapshot identity differs from manifest")
    source_manifest_bytes = (snapshot / "source-manifest.json").read_bytes()
    if (
        hashlib.sha256(source_manifest_bytes).hexdigest()
        != manifest["snapshot"]["source_manifest_sha256"]
    ):
        raise ValueError("source manifest digest differs")
    source_manifest = json.loads(source_manifest_bytes)
    wal = snapshot / "mnemo.db-wal"
    if wal.exists() and wal.stat().st_size:
        raise ValueError(
            "snapshot has a nonempty WAL; immutable read would omit uncheckpointed state"
        )
    # immutable prevents SQLite from creating a journal or updating the snapshot.
    db_uri = (snapshot / "mnemo.db").resolve().as_uri() + "?mode=ro&immutable=1"
    db = sqlite3.connect(db_uri, uri=True)
    try:
        cases: list[dict[str, Any]] = []
        case_ids: set[str] = set()
        for case in manifest["cases"]:
            if case["case_id"] in case_ids or not case["query"].strip():
                raise ValueError("duplicate case ID or empty query")
            case_ids.add(case["case_id"])
            if (
                case["evaluation_protocol_version"] != manifest["protocol_version"]
                or case["judgment_method"] != manifest["judgment_method"]
                or case["snapshot_identity"] != manifest["snapshot"]["identity"]
            ):
                raise ValueError(f"case contract differs from manifest: {case['case_id']}")
            if case["representation"] != "canonical_text":
                raise ValueError("this preflight only validates canonical chunk ancestry")
            source = db.execute(
                "SELECT notebook_id, document_id FROM sources WHERE source_id=?",
                (case["source_id"],),
            ).fetchone()
            version = db.execute(
                "SELECT document_id, content_hash FROM document_versions WHERE version_id=?",
                (case["version_id"],),
            ).fetchone()
            chunk = db.execute(
                "SELECT document_id, version_id, text FROM chunks WHERE id=?",
                (case["evidence_id"],),
            ).fetchone()
            if (
                source != (case["notebook_id"], case["document_id"])
                or version != (case["document_id"], case["source_file_sha256"])
                or chunk is None
                or chunk[:2] != (case["document_id"], case["version_id"])
                or hashlib.sha256(chunk[2].encode()).hexdigest() != case["evidence_content_sha256"]
            ):
                raise ValueError(f"ancestry mismatch: {case['case_id']}")
            if not any(
                item["sha256"] == case["source_file_sha256"] for item in source_manifest["files"]
            ):
                raise ValueError(f"source receipt mismatch: {case['case_id']}")
            if case["evidence_id"] not in case["positive_evidence_ids"]:
                raise ValueError(f"target absent from positive identities: {case['case_id']}")
            for negative in case["negative_evidence_ids"]:
                negative_row = db.execute(
                    "SELECT document_id, version_id FROM chunks WHERE id=?", (negative,)
                ).fetchone()
                if negative_row is None or negative_row == (
                    case["document_id"],
                    case["version_id"],
                ):
                    raise ValueError(
                        f"negative identity not outside exact scope: {case['case_id']}"
                    )
            cases.append({"case_id": case["case_id"], "ancestry": "PASS"})
        active = db.execute("SELECT count(*) FROM active_index_generations").fetchone()[0]
        return {
            "protocol": "DERE-1",
            "cases": cases,
            "source_receipt": "PASS",
            "source_bytes": "NOT_VERIFIED",
            "active_generation_count": active,
            "authorized_scoped_search": "NOT_RUN",
            "ranking_metrics": "NOT_RUN",
            "admission": "BLOCKED_NO_ACTIVE_GENERATION_OR_ATTACHED_ACL"
            if active == 0
            else "NOT_VERIFIED_ACL_AND_PROVIDER_BINDING",
            "human_semantic_relevance": "NOT_ADJUDICATED",
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.manifest, args.snapshot), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
