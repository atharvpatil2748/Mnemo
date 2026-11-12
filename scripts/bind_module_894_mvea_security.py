"""Freeze twenty engineering security/negative controls before their retrieval run.

No-answer controls assert only exact-identifier absence, never semantic irrelevance.
Revocation controls require a separate disposable ACL copy at execution time.
"""

from __future__ import annotations

import hashlib
import json
import sys
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

_SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))

from scripts.bind_module_894_mvea_language import (  # noqa: E402
    EXPECTED_ALIAS,
    LOGS,
    PLAN,
    ROOT,
    RUNTIME,
    _read_only,
    sha256,
)
from scripts.bind_module_894_mvea_language import OUTPUT as LANGUAGE_QREL  # noqa: E402

EXPECTED_LANGUAGE = "9498ec0f4f873f92aa99ebed3ac3afa78854e3ce3966f82071b7db6bec5185c0"
OUTPUT = ROOT / "evaluation/module_894_mvea/security-controls.v1.json"
SEED_IDS = (
    "MVEA-LANG-EN01-EN",
    "MVEA-LANG-EN05-HI",
    "MVEA-LANG-HI01-HI",
    "MVEA-LANG-HI06-MR",
    "MVEA-LANG-MR01-MR",
)


def bind() -> dict[str, Any]:
    if sha256(LANGUAGE_QREL) != EXPECTED_LANGUAGE:
        raise ValueError("frozen language QREL differs")
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
        or json.loads((LOGS / "run_state.json").read_text())["status"] != "SUCCEEDED"
    ):
        raise ValueError("disposable evaluation safety preflight failed")
    language = json.loads(LANGUAGE_QREL.read_text(encoding="utf-8"))
    selected_cases = {case["case_id"]: case for case in language["cases"]}
    notebooks = json.loads((LOGS / "run_manifest.json").read_text())["notebooks"]
    original_notebook = json.loads(PLAN.read_text(encoding="utf-8"))["existing_notebook"]["id"]
    cases: list[dict[str, Any]] = []
    with (
        closing(_read_only(RUNTIME / "mnemo.db")) as db,
        closing(_read_only(RUNTIME / "acl.db")) as acl,
    ):
        alias = db.execute(
            "SELECT alias_set_digest FROM active_multilingual_v2_alias_set WHERE singleton=1"
        ).fetchone()
        if alias != (EXPECTED_ALIAS,):
            raise ValueError("disposable alias differs")
        for index, case_id in enumerate(SEED_IDS):
            source = selected_cases[case_id]
            target = source["targets"][0]
            target_document = target["document_id"]
            alternatives = [
                notebook
                for notebook in notebooks.values()
                if not db.execute(
                    "SELECT 1 FROM sources WHERE notebook_id=? AND document_id=?",
                    (notebook, target_document),
                ).fetchone()
            ]
            if not alternatives:
                raise ValueError("wrong-scope negative has no verified absent membership")
            wrong_notebook = alternatives[0]
            actor = str(uuid5(NAMESPACE_URL, f"mnemo-mvea-ungranted-{case_id}"))
            if acl.execute(
                "SELECT 1 FROM notebook_grants WHERE actor_id=? AND status='active'",
                (actor,),
            ).fetchone():
                raise ValueError("negative principal unexpectedly has notebook grant")
            nonce = str(uuid5(NAMESPACE_URL, f"mnemo-mvea-absent-{case_id}"))
            for table, column in (
                ("chunks", "text"),
                ("ocr_regions", "text"),
                ("vision_results", "payload"),
            ):
                if db.execute(
                    f"SELECT 1 FROM {table} WHERE instr({column},?)>0 LIMIT 1", (nonce,)
                ).fetchone():
                    raise ValueError("no-answer identifier occurs in retained evidence")
            common = {
                "seed_case_id": case_id,
                "query_language": source["query_language"],
                "document_language": source["document_language"],
                "target": target,
                "judgment_method": "DETERMINISTIC_ENGINEERING",
                "human_relevance_reviewed": False,
            }
            cases.extend(
                (
                    {
                        **common,
                        "case_id": f"MVEA-NEG-ABSENT-{index + 1:02}",
                        "control": "exact_identifier_absence",
                        "query": f"Find the record containing exact identifier {nonce}",
                        "selected_notebooks": [original_notebook, *notebooks.values()],
                        "exact_identifier": nonce,
                        "expected": "NO_EXACT_IDENTITY_MATCH",
                        "semantic_no_answer_adjudicated": False,
                    },
                    {
                        **common,
                        "case_id": f"MVEA-NEG-SCOPE-{index + 1:02}",
                        "control": "wrong_notebook",
                        "query": source["query"],
                        "selected_notebooks": [wrong_notebook],
                        "expected": "TARGET_IDENTITY_ABSENT",
                    },
                    {
                        **common,
                        "case_id": f"MVEA-NEG-PRINCIPAL-{index + 1:02}",
                        "control": "ungranted_principal",
                        "query": source["query"],
                        "selected_notebooks": source["selected_notebooks"],
                        "principal_id": actor,
                        "expected": "AUTHORIZATION_DENIED",
                    },
                    {
                        **common,
                        "case_id": f"MVEA-NEG-REVOKE-{index + 1:02}",
                        "control": "revoked_membership",
                        "query": source["query"],
                        "selected_notebooks": source["selected_notebooks"],
                        "execution_environment": "ISOLATED_ACL_COPY_ONLY",
                        "expected": "AUTHORIZATION_DENIED_AFTER_REVOCATION",
                    },
                )
            )
    if len(cases) != 20 or len({case["case_id"] for case in cases}) != 20:
        raise ValueError("security-control cohort incomplete")
    return {
        "schema": "mnemo.module-894-mvea-security-controls/1",
        "judgment_method": "DETERMINISTIC_ENGINEERING",
        "semantic_relevance_adjudicated": False,
        "language_qrel_sha256": EXPECTED_LANGUAGE,
        "active_alias_digest": EXPECTED_ALIAS,
        "cases": cases,
    }


def main() -> int:
    payload = (json.dumps(bind(), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    digest = hashlib.sha256(payload).hexdigest()
    if not OUTPUT.exists():
        with OUTPUT.open("xb") as stream:
            stream.write(payload)
    if OUTPUT.read_bytes() != payload:
        raise ValueError("existing security-control QREL differs")
    print(json.dumps({"cases": 20, "digest": digest, "path": str(OUTPUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
