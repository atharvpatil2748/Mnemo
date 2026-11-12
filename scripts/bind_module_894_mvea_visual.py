"""Bind inspected original images to immutable Vision and CLIP engineering targets.

No retrieval or model inference is performed here. The blueprint was authored
from original image blobs, independently of search results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, cast

_SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))

from scripts.bind_module_894_mvea_language import (  # noqa: E402
    EXPECTED_ALIAS,
    EXPECTED_SNAPSHOT_SHA256,
    LOGS,
    PLAN,
    ROOT,
    RUNTIME,
    _read_only,
    sha256,
)
from scripts.bind_module_894_mvea_language import OUTPUT as LANGUAGE_QREL  # noqa: E402

BLUEPRINT = ROOT / "config/evaluation/module_894_mvea_visual.v1.json"
OUTPUT = ROOT / "evaluation/module_894_mvea/visual-identity.v1.json"
EXPECTED_SPACE = "openai/clip-vit-large-patch14@32bd64288804d66eefd0ccbe215aa642df71cc41"


def _one(db: sqlite3.Connection, sql: str, args: tuple[object, ...]) -> tuple[Any, ...]:
    rows = db.execute(sql, args).fetchall()
    if len(rows) != 1:
        raise ValueError("expected one retained visual evidence record")
    return cast(tuple[Any, ...], rows[0])


def _asset_blob(asset_hash: str) -> Path:
    if len(asset_hash) != 64 or any(char not in "0123456789abcdef" for char in asset_hash):
        raise ValueError("invalid asset hash")
    folder = RUNTIME / "files" / asset_hash[:2] / asset_hash[2:]
    files = list(folder.glob("raw.*"))
    if len(files) != 1 or sha256(files[0]) != asset_hash:
        raise ValueError("original visual asset missing or corrupt")
    return files[0]


def bind() -> dict[str, Any]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    run = json.loads((LOGS / "run_manifest.json").read_text(encoding="utf-8"))
    state = json.loads((LOGS / "run_state.json").read_text(encoding="utf-8"))
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
        or state["status"] != "SUCCEEDED"
        or run["run_id"] != "phase86-three-languages-with-retained-original-v1-b153f2faa728599a"
        or sha256(ROOT / plan["existing_notebook"]["snapshot"]) != EXPECTED_SNAPSHOT_SHA256
        or not LANGUAGE_QREL.is_file()
    ):
        raise ValueError("visual binding safety preflight failed")
    blueprint = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
    if (
        blueprint["schema"] != "mnemo.module-894-mvea-visual-blueprint/1"
        or blueprint["judgment_method"] != "DETERMINISTIC_ENGINEERING"
        or blueprint["semantic_relevance_adjudicated"] is not False
        or len(blueprint["targets"]) != 10
    ):
        raise ValueError("invalid visual blueprint")
    cases: list[dict[str, Any]] = []
    seen_occurrences: set[str] = set()
    with (
        closing(
            _read_only(ROOT / plan["existing_notebook"]["snapshot"], immutable=True)
        ) as historical,
        closing(_read_only(RUNTIME / "mnemo.db")) as current,
    ):
        active = _one(
            current,
            "SELECT alias_set_digest FROM active_multilingual_v2_alias_set WHERE singleton=1",
            (),
        )
        if active != (EXPECTED_ALIAS,):
            raise ValueError("disposable alias changed")
        for index, target in enumerate(blueprint["targets"]):
            derivation = str(target["vision_derivation_id"])
            row = _one(
                current,
                "SELECT v.document_id,v.version_id,v.occurrence_id,v.asset_id,"
                "a.content_hash,p.generation_id,p.text_hash,e.derivation_id,"
                "e.generation_id,e.dimensions,e.metric,e.normalization,e.shared_space_id,"
                "e.vector_hash,q.generation_id "
                "FROM vision_results v "
                "JOIN asset_catalog a ON a.asset_id=v.asset_id "
                "JOIN vision_text_projection_rows p ON p.derivation_id=v.derivation_id "
                "JOIN visual_embeddings e ON e.occurrence_id=v.occurrence_id "
                "JOIN visual_vector_projection_rows q ON q.derivation_id=e.derivation_id "
                "WHERE v.derivation_id=?",
                (derivation,),
            )
            (
                document_id,
                version_id,
                occurrence_id,
                asset_id,
                asset_hash,
                vision_generation,
                text_hash,
                clip_derivation,
                clip_source_generation,
                dimensions,
                metric,
                normalization,
                space,
                vector_hash,
                clip_generation,
            ) = row
            if (
                occurrence_id in seen_occurrences
                or dimensions != 768
                or metric != "cosine"
                or normalization != "unit"
                or space != EXPECTED_SPACE
            ):
                raise ValueError(f"duplicate or incompatible visual target: {target['id']}")
            seen_occurrences.add(occurrence_id)
            _asset_blob(asset_hash)
            old = _one(
                historical,
                "SELECT v.document_id,v.version_id,v.occurrence_id,v.asset_id,a.content_hash "
                "FROM vision_results v JOIN asset_catalog a ON a.asset_id=v.asset_id "
                "WHERE v.derivation_id=?",
                (derivation,),
            )
            if old != (document_id, version_id, occurrence_id, asset_id, asset_hash):
                raise ValueError(f"historical image ancestry differs: {target['id']}")
            document = _one(
                current,
                "SELECT current_version_id,current_hash FROM documents WHERE document_id=?",
                (document_id,),
            )
            if document[0] != version_id:
                raise ValueError("visual derivation belongs to stale document version")
            memberships = current.execute(
                "SELECT notebook_id,source_id FROM sources WHERE document_id=? "
                "ORDER BY notebook_id",
                (document_id,),
            ).fetchall()
            permitted = {plan["existing_notebook"]["id"], *run["notebooks"].values()}
            if len(memberships) != 2 or {r[0] for r in memberships} - permitted:
                raise ValueError("visual source membership differs")
            selected = (
                [memberships[1][0]]
                if index % 2 == 0
                else [*run["notebooks"].values(), plan["existing_notebook"]["id"]]
            )
            for representation, evidence_id, generation_id in (
                ("vision_text", derivation, vision_generation),
                ("visual_vector", clip_derivation, clip_generation),
            ):
                cases.append(
                    {
                        "case_id": f"MVEA-{representation.upper()}-{target['id']}",
                        "query": target["query"],
                        "query_language": "en",
                        "representation": representation,
                        "visual_feature": target["visual_feature"],
                        "selected_notebooks": selected,
                        "targets": [
                            {
                                "notebook_id": notebook,
                                "source_id": source,
                                "document_id": document_id,
                                "version_id": version_id,
                                "evidence_id": evidence_id,
                                "occurrence_id": occurrence_id,
                                "asset_id": asset_id,
                                "asset_sha256": asset_hash,
                                "source_file_sha256": document[1],
                                "generation_id": generation_id,
                                "vision_text_hash": text_hash,
                                "clip_vector_hash": vector_hash,
                                "clip_source_generation_id": clip_source_generation,
                            }
                            for notebook, source in memberships
                            if notebook in selected
                        ],
                        "judgment_method": "DETERMINISTIC_ENGINEERING",
                        "human_relevance_reviewed": False,
                    }
                )
    if len(cases) != 20 or any(not case["targets"] for case in cases):
        raise ValueError("visual cohort incomplete")
    return {
        "schema": "mnemo.module-894-mvea-visual-identity/1",
        "judgment_method": "DETERMINISTIC_ENGINEERING",
        "semantic_relevance_adjudicated": False,
        "run_id": run["run_id"],
        "runtime_database": str((RUNTIME / "mnemo.db").relative_to(ROOT)),
        "snapshot_sha256": EXPECTED_SNAPSHOT_SHA256,
        "active_alias_digest": EXPECTED_ALIAS,
        "language_qrel_sha256": sha256(LANGUAGE_QREL),
        "blueprint_sha256": sha256(BLUEPRINT),
        "clip_shared_space": EXPECTED_SPACE,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = bind()
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    digest = hashlib.sha256(payload).hexdigest()
    if not args.check:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open("xb") as stream:
            stream.write(payload)
            stream.flush()
        if sha256(OUTPUT) != digest:
            raise RuntimeError("visual QREL readback mismatch")
    print(json.dumps({"cases": len(value["cases"]), "digest": digest, "written": not args.check}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
