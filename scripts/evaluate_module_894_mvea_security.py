"""Execute frozen engineering negative controls against read-only disposable search.

Revocation is exercised only in fresh SQLite ACL backups, never in the successful
Phase 8.6 runtime. This does not adjudicate semantic no-answer quality.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import AsyncExitStack, closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mnemo.engine import KnowledgeEngine  # noqa: E402
from mnemo.interfaces import NotFoundError, PrincipalContextV1  # noqa: E402
from mnemo.retrieval.advanced import AdvancedRetrievalService, RetrievalCursorCodec  # noqa: E402
from mnemo.retrieval.advanced_sources import CanonicalTextAdvancedSource  # noqa: E402
from mnemo.retrieval.sparse import SparseRetriever  # noqa: E402
from mnemo_server.config import ServerConfig  # noqa: E402
from mnemo_server.schemas.scope_contract_review import (  # noqa: E402
    ScopeRequestReview,
    SelectedNotebooks,
)
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority  # noqa: E402
from mnemo_server.services.scoped_search import ScopedSearchApplicationService  # noqa: E402

from scripts.evaluate_phase86_four_notebooks import (  # noqa: E402
    ReadOnlyEvaluationStore,
    _ranked_identity,
    preflight_evaluation,
)
from scripts.run_phase86_four_notebooks import notebook_ids  # noqa: E402

QRELS = ROOT / "evaluation/module_894_mvea/security-controls.v1.json"
QRELS_DIGEST = "389d2cf156d9775b9cd8c518225d202c17df03cb5f25d3d073a73609fcbfa942"
ADAPTER = ROOT / "evaluation/module_894_mvea/language-phase86-adapter.v1.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup_acl(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError("negative-control ACL copy already exists")
    with closing(sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)) as old:
        old.execute("PRAGMA query_only=ON")
        with closing(sqlite3.connect(target)) as new:
            old.backup(new)
    if not target.is_file():
        raise RuntimeError("ACL backup did not persist")


def append_progress(path: Path, case_id: str, event: str) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"case_id": case_id, "event": event}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


async def run() -> dict[str, Any]:
    if digest(QRELS) != QRELS_DIGEST:
        raise ValueError("frozen negative controls changed")
    plan, runtime, _logs = preflight_evaluation(ADAPTER)
    run_name = "mvea-security-" + uuid4().hex
    output = ROOT / "scratch/module_894_multimodal" / run_name
    output.mkdir(exist_ok=False)
    original_acl = runtime / "acl.db"
    original_hash = digest(original_acl)
    expected_notebooks = {UUID(str(plan["existing_notebook"]["id"])), *notebook_ids(plan).values()}
    actor = UUID(str(plan["disposable_actor_id"]))
    cases = json.loads(QRELS.read_text(encoding="utf-8"))["cases"]
    if len(cases) != 20:
        raise ValueError("frozen negative-control cohort incomplete")
    store = ReadOnlyEvaluationStore(runtime / "mnemo.db")
    async with AsyncExitStack() as stack:
        await store.open()
        stack.push_async_callback(store.close)
        canonical = CanonicalTextAdvancedSource(
            store=store, ranked_retriever=SparseRetriever(store)
        )
        results: list[dict[str, Any]] = []
        for case in cases:
            append_progress(output / "progress.jsonl", str(case["case_id"]), "started")
            selected = tuple(UUID(value) for value in case["selected_notebooks"])
            if not selected or any(value not in expected_notebooks for value in selected):
                raise ValueError("negative case escaped exact disposable notebooks")
            acl_copy = output / f"{case['case_id']}-acl.db"
            backup_acl(original_acl, acl_copy)
            authority = SQLiteNotebookScopeAuthority(acl_copy)
            principal_id = (
                uuid5(actor, str(case["case_id"]))
                if case["control"] == "ungranted_principal"
                else actor
            )
            if case["control"] == "revoked_membership":
                if not authority.permits(actor, selected[0]):
                    raise PermissionError(
                        "original disposable actor grant absent before revocation"
                    )
                authority.revoke(actor_id=actor, notebook_id=selected[0])
                if authority.permits(actor, selected[0]):
                    raise PermissionError("ACL copy revocation did not take effect")
            harness = SimpleNamespace(
                storage=store,
                server_scope_authority=authority,
                advanced_retrieval=AdvancedRetrievalService(
                    sources=(canonical,),
                    cursor_codec=RetrievalCursorCodec(
                        b"mvea-negative-disposable-evaluation-signing-key-v1"
                    ),
                ),
                full_multilingual_v2_alias_digest=None,
                config=SimpleNamespace(
                    storage=SimpleNamespace(sqlite=SimpleNamespace(path=runtime / "mnemo.db"))
                ),
            )
            service = ScopedSearchApplicationService(cast(KnowledgeEngine, harness), ServerConfig())
            request = ScopeRequestReview(
                query=case["query"],
                mode="ranked",
                limit=10,
                scope=SelectedNotebooks(kind="selected", notebook_ids=selected),
            )
            denial = case["control"] in {"ungranted_principal", "revoked_membership"}
            try:
                response = await service.execute_ranked(
                    request, PrincipalContextV1(principal_id, True)
                )
            except NotFoundError:
                if not denial:
                    raise
                result: dict[str, Any] = {
                    "case_id": case["case_id"],
                    "status": "PASS",
                    "denied": True,
                }
            else:
                if denial:
                    raise PermissionError(f"negative principal received results: {case['case_id']}")
                if any(UUID(str(item["notebook_id"])) not in selected for item in response.items):
                    raise PermissionError("negative control returned out-of-scope notebook")
                if case["control"] == "wrong_notebook":
                    target = case["target"]
                    target_identity = tuple(
                        str(target[key])
                        for key in (
                            "notebook_id",
                            "source_id",
                            "document_id",
                            "version_id",
                            "evidence_id",
                        )
                    )
                    if any(
                        tuple(
                            str(_ranked_identity(item)[key])
                            for key in (
                                "notebook_id",
                                "source_id",
                                "document_id",
                                "version_id",
                                "evidence_id",
                            )
                        )
                        == target_identity
                        for item in response.items
                    ):
                        raise PermissionError(
                            f"out-of-scope target was returned: {case['case_id']}"
                        )
                elif any(
                    str(case["exact_identifier"]) in str(item.get("content", ""))
                    for item in response.items
                ):
                    raise ValueError("unverified exact identifier appeared in returned text")
                result = {
                    "case_id": case["case_id"],
                    "status": "PASS",
                    "denied": False,
                    "returned_count": len(response.items),
                    "semantic_no_answer_claimed": False,
                }
            results.append(result)
            append_progress(output / "progress.jsonl", str(case["case_id"]), "completed")
        if digest(original_acl) != original_hash:
            raise RuntimeError("successful Phase 8.6 ACL was modified")
    receipt = {
        "schema": "mnemo.module-894-mvea-security-results/1",
        "qrel_sha256": QRELS_DIGEST,
        "runtime": str(runtime),
        "status": "PASS" if len(results) == 20 else "PARTIAL",
        "controls": results,
        "semantic_no_answer_adjudicated": False,
    }
    (output / "result.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2), encoding="utf-8"
    )
    return {
        "artifact": str(output / "result.json"),
        "status": receipt["status"],
        "cases": len(results),
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run())))
