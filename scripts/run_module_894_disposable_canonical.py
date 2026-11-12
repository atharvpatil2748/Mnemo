"""Run the frozen DERE query via real scoped search on an explicit disposable copy.

The source snapshot is verified read-only. Only the separately named disposable
SQLite database may be opened for migrations/search. No model or alias is faked.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4, uuid5

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo.retrieval.advanced import AdvancedRetrievalService, RetrievalCursorCodec
from mnemo.retrieval.advanced_sources import CanonicalTextAdvancedSource
from mnemo.retrieval.sparse import SparseRetriever
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.config import ServerConfig
from mnemo_server.schemas.scope_contract_review import (
    DocumentSelection,
    ScopeRequestReview,
    SelectedNotebooks,
)
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.scoped_search import ScopedSearchApplicationService
from verify_module_894_dere import verify

ROOT = Path(__file__).resolve().parents[1]
DISPOSABLE_ROOT = (ROOT / "scratch" / "module_894_disposable").resolve()


async def run(
    disposable: Path, manifest_path: Path, snapshot: Path, source_file: Path
) -> dict[str, object]:
    disposable = disposable.resolve(strict=True)
    if not disposable.is_relative_to(DISPOSABLE_ROOT):
        raise ValueError("only a selected disposable evaluation store may be opened")
    preflight = verify(manifest_path, snapshot)
    if any(item["ancestry"] != "PASS" for item in preflight["cases"]):
        raise ValueError("DERE ancestry preflight failed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(manifest["cases"]) != 1:
        raise ValueError("this first-run harness requires one frozen case")
    case = manifest["cases"][0]
    source_file = source_file.resolve(strict=True)
    evaluation_corpus = (ROOT / "goldenDataset" / "Phase 8.5 Evaluation Corpus").resolve()
    if not source_file.is_relative_to(evaluation_corpus):
        raise ValueError("source file is outside the declared evaluation corpus")
    if hashlib.sha256(source_file.read_bytes()).hexdigest() != case["source_file_sha256"]:
        raise ValueError("evaluation source bytes differ from frozen manifest")
    actor = UUID("7ee69849-d87e-57d1-b2ef-29128d668a5e")
    principal = PrincipalContextV1(actor, True)
    authority = SQLiteNotebookScopeAuthority((disposable / "acl.db").resolve())
    notebook = UUID(case["notebook_id"])
    if not authority.permits(actor, notebook) or authority.revision(notebook) is None:
        raise PermissionError("explicit disposable test membership is absent")
    store = SQLiteStore(disposable / "mnemo.db")
    await store.open()
    try:
        source = await store.get_source(UUID(case["source_id"]))
        if (
            source is None
            or source.notebook_id != notebook
            or source.document_id != UUID(case["document_id"])
        ):
            raise ValueError("disposable source ancestry differs from frozen manifest")
        document = await store.get_document(UUID(case["document_id"]))
        target_chunk = await store.get_chunk(case["evidence_id"])
        if (
            document is None
            or not any(
                version.version_id == UUID(case["version_id"])
                and version.content_hash == case["source_file_sha256"]
                for version in document.versions
            )
            or target_chunk is None
            or target_chunk.document_id != UUID(case["document_id"])
            or target_chunk.version_id != UUID(case["version_id"])
            or hashlib.sha256(target_chunk.text.encode()).hexdigest()
            != case["evidence_content_sha256"]
        ):
            raise ValueError("disposable target differs from frozen manifest")
        retrieval = AdvancedRetrievalService(
            sources=(
                CanonicalTextAdvancedSource(store=store, ranked_retriever=SparseRetriever(store)),
            ),
            cursor_codec=RetrievalCursorCodec(b"module-894-disposable-canonical-only!!"),
        )
        engine = cast(
            KnowledgeEngine,
            SimpleNamespace(
                storage=store, server_scope_authority=authority, advanced_retrieval=retrieval
            ),
        )
        request = ScopeRequestReview(
            query=case["query"],
            mode="ranked",
            scope=SelectedNotebooks(kind="selected", notebook_ids=(notebook,)),
            limit=10,
        )
        result = await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
            request, principal
        )
        ranked = [
            {
                "rank": index,
                "candidate_id": item.get("candidate_id"),
                "notebook_id": item.get("notebook_id"),
                "source_id": item.get("source_id"),
                "document_id": item.get("document_id"),
                "version_id": item.get("version_id"),
                "chunk_id": item.get("chunk_id"),
                "fused_score": item.get("fused_score"),
                "retrieval_paths": item.get("retrieval_paths"),
            }
            for index, item in enumerate(result.items, 1)
        ]
        for item in ranked:
            candidate_source = await store.get_source(UUID(str(item["source_id"])))
            candidate_chunk = await store.get_chunk(str(item["chunk_id"]))
            if (
                candidate_source is None
                or candidate_source.notebook_id != notebook
                or candidate_source.document_id != UUID(str(item["document_id"]))
                or candidate_chunk is None
                or candidate_chunk.document_id != candidate_source.document_id
                or candidate_chunk.version_id != UUID(str(item["version_id"]))
            ):
                raise ValueError("ranked item failed disposable source/chunk ancestry check")
        positives = set(case["positive_evidence_ids"])
        found = [cast(int, item["rank"]) for item in ranked if item["chunk_id"] in positives]
        denied: dict[str, bool] = {}
        stranger = PrincipalContextV1(uuid5(actor, "DERE-894-ungranted-principal"), True)
        try:
            await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
                request, stranger
            )
        except NotFoundError:
            denied["cross_principal"] = True
        else:
            raise AssertionError("ungranted principal received protected evidence")
        nonexistent = UUID("00000000-0000-0000-0000-000000000001")
        try:
            await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
                request.model_copy(
                    update={
                        "scope": SelectedNotebooks(kind="selected", notebook_ids=(nonexistent,))
                    }
                ),
                principal,
            )
        except NotFoundError:
            denied["wrong_notebook"] = True
        else:
            raise AssertionError("unowned notebook selection disclosed evidence")
        wrong_version = UUID("00000000-0000-0000-0000-000000000002")
        try:
            await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
                ScopeRequestReview(
                    query=case["query"],
                    mode="ranked",
                    scope=SelectedNotebooks(kind="selected", notebook_ids=(notebook,)),
                    documents=(
                        DocumentSelection(
                            notebook_id=notebook,
                            document_id=UUID(case["document_id"]),
                            version_id=wrong_version,
                        ),
                    ),
                    limit=10,
                ),
                principal,
            )
        except NotFoundError:
            denied["wrong_version"] = True
        else:
            raise AssertionError("wrong version selection disclosed evidence")
        reader_id = uuid4()
        authority.grant(
            actor_id=reader_id,
            notebook_id=notebook,
            role="reader",
            operator_id=actor,
        )
        reader = PrincipalContextV1(reader_id, True)
        try:
            reader_result = await ScopedSearchApplicationService(
                engine, ServerConfig()
            ).execute_ranked(request, reader)
            if not reader_result.items:
                raise AssertionError("permitted reader could not retrieve canonical evidence")
        finally:
            authority.revoke(actor_id=reader_id, notebook_id=notebook)
        try:
            await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
                request, reader
            )
        except NotFoundError:
            denied["revoked_reader"] = True
        else:
            raise AssertionError("revoked reader received protected evidence")
        return {
            "case_id": case["case_id"],
            "query": case["query"],
            "hints": None,
            "actor_id": str(actor),
            "acl_revision_after_revocation": authority.revision(notebook),
            "disposable": str(disposable),
            "source_snapshot_preflight": preflight,
            "source_file_sha256_verified": True,
            "ranked": ranked,
            "safe_denial": denied,
            "ranked_provenance_verified": len(ranked),
            "ranked_provenance_total": len(ranked),
            "recall_at_10": float(bool(found)),
            "precision_at_10": sum(item["chunk_id"] in positives for item in ranked) / 10,
            "mrr": 0.0 if not found else 1 / min(found),
            "human_semantic_relevance": "NOT_ADJUDICATED",
        }
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disposable", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.disposable, args.manifest, args.snapshot, args.source_file))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        output = args.output.resolve(strict=False)
        if not output.is_relative_to(args.disposable.resolve(strict=True)):
            raise ValueError("evaluation output must remain inside its disposable store")
        with output.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
        print(f"Wrote disposable evaluation result: {output}")


if __name__ == "__main__":
    main()
