"""Bind predeclared Phase 8.6 identity anchors to audited disposable memberships.

These are engineering identity checks, not human semantic relevance judgments.
No target is selected from retrieval output. The historical query text and
target filename are checked against their original, hash-frozen definition.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, cast
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "config/evaluation/phase86_dere3_identity_qrels.v1.json"
BOUND_NAME = "phase86_dere3_qrels.bound.json"


def _sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _historical_queries(path: Path) -> dict[str, dict[str, Any]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "queries" for target in node.targets
        ):
            queries = ast.literal_eval(node.value)
            return {str(item["qid"]): cast(dict[str, Any], item) for item in queries}
    raise ValueError("historical query definitions are unavailable")


def load_blueprint(plan: dict[str, Any], records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    value = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
    if (
        value.get("schema") != "mnemo.phase86-four-notebook-identity-blueprint/1"
        or value.get("judgment_method") != "DETERMINISTIC_ENGINEERING"
        or value.get("human_adjudication_claimed") is not False
        or value.get("semantic_relevance_adjudicated") is not False
        or not value.get("cases")
        or value.get("snapshot_sha256") != plan["existing_notebook"]["snapshot_sha256"]
    ):
        raise ValueError("unreviewed or empty identity QREL blueprint")
    query_path = ROOT / str(value["historical_queries"])
    if _sha(query_path) != value["historical_queries_sha256"]:
        raise ValueError("historical query definitions changed")
    historical = _historical_queries(query_path)
    snapshot = ROOT / plan["existing_notebook"]["snapshot"]
    if _sha(snapshot) != value["snapshot_sha256"]:
        raise ValueError("protected snapshot changed")
    seen: set[str] = set()
    with sqlite3.connect(
        f"file:{snapshot.resolve().as_posix()}?mode=ro&immutable=1", uri=True
    ) as db:
        for case in value["cases"]:
            case_id = str(case["case_id"])
            if case_id in seen:
                raise ValueError("duplicate identity case ID")
            seen.add(case_id)
            qid = str(case["historical_qid"])
            original = historical.get(qid)
            if original is None or (
                case["query"] != original["query"]
                or case["target_file"] != original["target_file"]
                or f"{case['query_language']}->{case['target_language']}" != original["direction"]
            ):
                raise ValueError(f"historical query/target identity differs: {case_id}")
            anchors = case["anchor_phrases"]
            if not anchors or any(anchor not in original["target_keywords"] for anchor in anchors):
                raise ValueError(f"anchor was not historically authored: {case_id}")
            selected = case["selected_partitions"]
            memberships = case["target_memberships"]
            if (
                not selected
                or len(selected) != len(set(selected))
                or any(item not in {"existing", "hi", "mr", "en"} for item in selected)
                or not memberships
                or len(memberships) != len(set(memberships))
                or any(item not in selected for item in memberships)
                or any(item not in {"existing", case["target_language"]} for item in memberships)
                or case["target_file"] not in plan["notebooks"][case["target_language"]]["files"]
            ):
                raise ValueError(f"unapproved identity QREL scope: {case_id}")
            target = case["target"]
            if records[case["target_file"]]["sha256"] != target["source_file_sha256"]:
                raise ValueError(f"source hash differs from verified inventory: {case_id}")
            rows = db.execute(
                "SELECT s.source_id,c.text FROM sources s "
                "JOIN documents d ON d.document_id=s.document_id "
                "JOIN document_versions v ON v.version_id=d.current_version_id "
                "JOIN chunks c ON c.document_id=d.document_id AND c.version_id=v.version_id "
                "WHERE s.notebook_id=? AND d.current_hash=? AND d.document_id=? "
                "AND v.version_id=? AND v.content_hash=? AND c.id=?",
                (
                    plan["existing_notebook"]["id"],
                    target["source_file_sha256"],
                    target["document_id"],
                    target["version_id"],
                    target["source_file_sha256"],
                    target["evidence_id"],
                ),
            ).fetchall()
            if (
                len(rows) != 1
                or hashlib.sha256(rows[0][1].encode()).hexdigest()
                != target["evidence_content_sha256"]
            ):
                raise ValueError(f"snapshot chunk ancestry or text hash differs: {case_id}")
            if not all(anchor.casefold() in rows[0][1].casefold() for anchor in anchors):
                raise ValueError(f"historical anchor is absent from target chunk: {case_id}")
            matches = db.execute(
                "SELECT text FROM chunks WHERE document_id=? AND version_id=?",
                (target["document_id"], target["version_id"]),
            ).fetchall()
            if (
                sum(
                    all(anchor.casefold() in row[0].casefold() for anchor in anchors)
                    for row in matches
                )
                != 1
            ):
                raise ValueError(
                    f"historical anchor does not uniquely identify one chunk: {case_id}"
                )
    return cast(dict[str, Any], value)


def bind_qrels(
    plan: dict[str, Any],
    records: dict[str, dict[str, Any]],
    runtime: Path,
    logs: Path,
    notebook_ids: dict[str, UUID],
) -> Path:
    """Resolve only persisted source IDs after the post-promotion audit passes."""
    blueprint = load_blueprint(plan, records)
    notebooks = {"existing": UUID(str(plan["existing_notebook"]["id"])), **notebook_ids}
    cases: list[dict[str, Any]] = []
    database_uri = f"file:{(runtime / 'mnemo.db').resolve().as_posix()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as db:
        for case in blueprint["cases"]:
            target = case["target"]
            resolved: list[dict[str, str]] = []
            for membership in case["target_memberships"]:
                notebook = str(notebooks[membership])
                rows = db.execute(
                    "SELECT s.source_id,c.text FROM sources s "
                    "JOIN documents d ON d.document_id=s.document_id "
                    "JOIN document_versions v ON v.version_id=d.current_version_id "
                    "JOIN chunks c ON c.document_id=d.document_id AND c.version_id=v.version_id "
                    "WHERE s.notebook_id=? AND d.current_hash=? AND d.document_id=? "
                    "AND v.version_id=? AND v.content_hash=? AND c.id=?",
                    (
                        notebook,
                        target["source_file_sha256"],
                        target["document_id"],
                        target["version_id"],
                        target["source_file_sha256"],
                        target["evidence_id"],
                    ),
                ).fetchall()
                if (
                    len(rows) != 1
                    or hashlib.sha256(rows[0][1].encode()).hexdigest()
                    != target["evidence_content_sha256"]
                ):
                    raise ValueError(f"target membership/ancestry is not unique: {case['case_id']}")
                resolved.append(
                    {
                        "notebook_id": notebook,
                        "source_id": str(rows[0][0]),
                        **{
                            key: str(target[key])
                            for key in (
                                "document_id",
                                "version_id",
                                "evidence_id",
                                "source_file_sha256",
                                "evidence_content_sha256",
                            )
                        },
                    }
                )
            cases.append(
                {
                    "case_id": case["case_id"],
                    "historical_qid": case["historical_qid"],
                    "query": case["query"],
                    "query_language": case["query_language"],
                    "target_language": case["target_language"],
                    "selected_notebooks": [
                        str(notebooks[item]) for item in case["selected_partitions"]
                    ],
                    "targets": resolved,
                }
            )
    bound = {
        "schema": "mnemo.phase86-four-notebook-dere/1",
        "judgment_method": "DETERMINISTIC_ENGINEERING",
        "judgment_subtype": blueprint["judgment_subtype"],
        "human_adjudication_claimed": False,
        "semantic_relevance_adjudicated": False,
        "blueprint_sha256": _sha(BLUEPRINT),
        "snapshot_sha256": blueprint["snapshot_sha256"],
        "cases": cases,
    }
    destination = logs / BOUND_NAME
    serialized = json.dumps(bound, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if destination.exists():
        if destination.read_text(encoding="utf-8") != serialized:
            raise ValueError(
                "previous bound QREL record differs from current persisted memberships"
            )
    else:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
    return destination
