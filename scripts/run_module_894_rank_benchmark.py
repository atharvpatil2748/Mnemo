"""Offline DERE-2 benchmark. Creates a fresh isolated clone; never starts a server."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import math
import shutil
import sqlite3
import time
from contextlib import AsyncExitStack, closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo.models.multilingual_index import MultilingualTextProjectionRowV2
from mnemo.retrieval.advanced import RetrievalCursorCodec
from mnemo.retrieval.advanced_sources import CanonicalTextAdvancedSource
from mnemo.retrieval.sparse import SparseRetriever
from mnemo.storage.multilingual import _decode_checked
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.config import ServerConfig
from mnemo_server.schemas.scope_contract_review import (
    DocumentSelection,
    ScopeRequestReview,
    SelectedNotebooks,
)
from mnemo_server.services.authorized_scope import AuthorizedNotebookScopeResolver
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.scoped_search import ScopedSearchApplicationService
from module_894_rank_trace import RankTrace
from run_module_894_disposable_bge import (
    ACTOR,
    NOTEBOOK,
    ROOT,
    RUNTIME,
    SNAPSHOT,
    attach_disposable_full_v2,
)

MANIFEST = ROOT / "evaluation/module_894_dere/manifest.v2.json"
KEYS = ("notebook_id", "source_id", "document_id", "version_id", "evidence_id")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key(item: dict[str, Any]) -> tuple[str, ...]:
    return tuple(item[k] for k in KEYS)


def clone(name: str) -> Path:
    if not name.startswith("dere-trace-") or not all(c.isalnum() or c == "-" for c in name):
        raise ValueError("expected fresh disposable run name")
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        raise ValueError("production selector is not UNINDEXED")
    dest = RUNTIME.parent / name
    if RUNTIME.resolve(strict=True) != RUNTIME or dest.resolve() != dest:
        raise ValueError("unexpected disposable location")
    dest.mkdir(exist_ok=False)
    for file in ("mnemo.db", "acl.db", "bge-disposable-activation-result.json"):
        source = RUNTIME / file
        wal = Path(str(source) + "-wal")
        if source.is_symlink() or (wal.exists() and wal.stat().st_size):
            raise ValueError("not a checkpointed ordinary source file")
        before = sha(source.read_bytes())
        shutil.copyfile(source, dest / file)
        if before != sha((dest / file).read_bytes()) or before != sha(source.read_bytes()):
            raise ValueError("source changed during copy")
    return dest


def provenance(runtime: Path, manifest: dict[str, Any]) -> set[tuple[str, ...]]:
    receipt_bytes = (SNAPSHOT / "source-manifest.json").read_bytes()
    inv = (
        ROOT
        / "docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack"
        / "V2_GOVERNED_CASE_INVENTORY.proposed.json"
    )
    if (
        sha(receipt_bytes) != manifest["source_manifest_sha256"]
        or sha(inv.read_bytes()) != manifest["inventory_sha256"]
        or sha(MANIFEST.with_name("manifest.v1.json").read_bytes())
        != manifest["baseline_manifest_sha256"]
    ):
        raise ValueError("upstream frozen evidence changed")
    receipt = json.loads(receipt_bytes)
    filemap = {f["sha256"]: f["relative_path"] for f in receipt["files"]}
    allowed: set[tuple[str, ...]] = set()
    with closing(
        sqlite3.connect((runtime / "mnemo.db").as_uri() + "?mode=ro&immutable=1", uri=True)
    ) as db:
        chunks = db.execute(
            "SELECT s.notebook_id,s.source_id,v.document_id,v.version_id,c.id "
            "FROM sources s JOIN document_versions v ON v.document_id=s.document_id "
            "JOIN chunks c ON c.document_id=v.document_id AND c.version_id=v.version_id "
            "WHERE s.notebook_id=?",
            (str(NOTEBOOK),),
        )
        allowed.update(chunks)
        for row in db.execute(
            "SELECT payload,payload_hash FROM language_text_projection_rows_v2 WHERE notebook_id=?",
            (str(NOTEBOOK),),
        ):
            projection = _decode_checked(row)
            if not isinstance(projection, MultilingualTextProjectionRowV2):
                raise ValueError("invalid typed projection")
            s = projection.source
            ident = tuple(str(getattr(s, k)) for k in KEYS)
            if s.occurrence_id:
                join = db.execute(
                    "SELECT 1 FROM sources s JOIN asset_occurrences o "
                    "ON s.document_id=o.document_id "
                    "JOIN asset_derivations d ON d.occurrence_id=o.occurrence_id "
                    "WHERE s.notebook_id=? AND s.source_id=? "
                    "AND o.document_id=? AND o.version_id=? "
                    "AND o.occurrence_id=? AND d.derivation_id=?",
                    (*ident[:4], str(s.occurrence_id), str(s.derivation_id)),
                ).fetchone()
                if not join:
                    raise ValueError("unbound derived evidence")
                allowed.add(ident)
            elif ident not in allowed:
                raise ValueError("unbound canonical projection")
        for case in manifest["cases"]:
            for target in case["targets"]:
                if key(target) not in allowed:
                    raise ValueError("unbound target")
                data = db.execute(
                    "SELECT c.text,v.content_hash FROM chunks c JOIN document_versions v "
                    "ON v.document_id=c.document_id AND v.version_id=c.version_id "
                    "WHERE c.id=? AND c.version_id=?",
                    (target["evidence_id"], target["version_id"]),
                ).fetchone()
                if (
                    not data
                    or sha(data[0].encode()) != target["evidence_content_sha256"]
                    or data[1] != target["source_file_sha256"]
                ):
                    raise ValueError("target bytes/version mismatch")
                root = Path(receipt["corpus_root"]).resolve()
                source = (root / filemap[data[1]]).resolve(strict=True)
                if not source.is_relative_to(root) or sha(source.read_bytes()) != data[1]:
                    raise ValueError("source bytes differ")
    return allowed


def metrics(rows: list[dict[str, Any]], targets: set[tuple[str, ...]], k: int) -> dict[str, Any]:
    # Each positive identity can earn credit only once, even across representations.
    seen: set[tuple[str, ...]] = set()
    ranks = []
    for i, item in enumerate(rows[:k], 1):
        ident = key(item)
        if ident in targets and ident not in seen:
            ranks.append(i)
            seen.add(ident)
    return {
        "recall": len(seen) / len(targets),
        "precision": len(seen) / k,
        "rr": 1 / ranks[0] if ranks else 0.0,
        "ndcg": sum(1 / math.log2(i + 1) for i in ranks)
        / sum(1 / math.log2(i + 1) for i in range(1, min(k, len(targets)) + 1)),
        "target_positions": [i for i, r in enumerate(rows, 1) if key(r) in targets],
    }


def checked_trace(trace: dict[str, Any], allowed: set[tuple[str, ...]]) -> None:
    for stage in (
        "dense",
        "sparse",
        "full_v2_rrf_before_limits",
        "rerank_before_result_limit",
        "full_v2_selected",
        "advanced_before_dedup",
        "advanced_after_dedup",
        "combined_before_fusion_limit",
        "advanced_before_output_bounds",
        "advanced_selected",
        "final",
    ):
        if any(key(item) not in allowed for item in trace[stage]):
            raise PermissionError("discard trace: out-of-scope identity")
    for part in trace["partitions"]:
        if any(key(item) not in allowed for item in part["items"]):
            raise PermissionError("discard trace: out-of-scope partition identity")


def stable_item(item: dict[str, Any]) -> dict[str, Any]:
    # A fresh authorization decision has its own issue time/ID on each call.
    # Compare every other field, including generation, ancestry, score and order.
    locator = dict(item["locator"])
    if item["representation"] == "multilingual_text":
        receipt = locator.pop("authorization_decision_fingerprint")
        if len(bytes.fromhex(receipt)) != 32:
            raise ValueError("missing signed-context decision fingerprint")
    return {**item, "locator": locator}


async def evaluate(runtime: Path) -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_bytes())
    activation = json.loads((runtime / "bge-disposable-activation-result.json").read_bytes())
    authority = SQLiteNotebookScopeAuthority(runtime / "acl.db")
    if (
        not authority.permits(ACTOR, NOTEBOOK)
        or activation["alias_set_digest"] != manifest["active_alias"]
    ):
        raise PermissionError("expected explicit owner and frozen generation alias")
    allowed = provenance(runtime, manifest)
    config = ServerConfig()
    principal = PrincipalContextV1(ACTOR, True)
    store = SQLiteStore(runtime / "mnemo.db")
    async with AsyncExitStack() as stack:
        await store.open()
        stack.push_async_callback(store.close)
        canonical = CanonicalTextAdvancedSource(
            store=store, ranked_retriever=SparseRetriever(store)
        )
        codec = RetrievalCursorCodec(b"offline-dere-v2-cursor-not-a-production-key")
        harness = SimpleNamespace(
            storage=store,
            server_scope_authority=authority,
            config=SimpleNamespace(
                storage=SimpleNamespace(sqlite=SimpleNamespace(path=runtime / "mnemo.db"))
            ),
            full_multilingual_v2_alias_digest=None,
        )
        engine = cast(KnowledgeEngine, harness)
        composed, _ = await attach_disposable_full_v2(
            runtime, engine, harness, canonical, codec, activation, stack
        )
        app = composed.application
        resolver = AuthorizedNotebookScopeResolver(store, authority)
        service = ScopedSearchApplicationService(engine, config)
        results = []
        for index, case in enumerate(manifest["cases"]):
            request = ScopeRequestReview(
                query=case["query"],
                mode="ranked",
                limit=10,
                scope=SelectedNotebooks(kind="selected", notebook_ids=(NOTEBOOK,)),
            )
            scopes = await resolver.resolve(principal, (NOTEBOOK,))
            expected = await service.execute_ranked(request, principal)
            observer = RankTrace()
            start = time.perf_counter()
            with observer.observe(app):
                observed = await service.execute_ranked(request, principal)
            latency = (time.perf_counter() - start) * 1000
            if (
                [stable_item(i) for i in observed.items] != [stable_item(i) for i in expected.items]
                or observed.omissions != expected.omissions
                or observed.completeness != expected.completeness
            ):
                raise AssertionError("trace changed output or omissions")
            trace = observer.snapshot(observed)
            checked_trace(trace, allowed)
            targets = {key(t) for t in case["targets"]}
            scores = {
                s: metrics(trace[s], targets, 10)
                for s in (
                    "dense",
                    "sparse",
                    "full_v2_rrf_before_limits",
                    "full_v2_selected",
                    "combined_before_fusion_limit",
                    "advanced_selected",
                    "final",
                )
            }
            trace.update(
                case_id=case["case_id"],
                manifest_sha256=sha(MANIFEST.read_bytes()),
                alias=manifest["active_alias"],
                acl_revision=scopes[0].membership_revision,
            )
            # Validate immediately before release; an error never serializes the buffer.
            await resolver.revalidate(principal, scopes)
            fname = f"case-{index + 1:02}.json.gz"
            with gzip.open(runtime / fname, "xt", encoding="utf8") as output:
                json.dump(trace, output, separators=(",", ":"))
            results.append(
                {
                    "case_id": case["case_id"],
                    "type": case["case_type"],
                    "trace": fname,
                    "metrics": scores,
                    "stage_counts": {s: len(trace[s]) for s in scores},
                    "cut_reason": trace["advanced_cut_reason"],
                    "representation_exposure": {
                        r: sum(i["representation"] == r for i in trace["final"])
                        for r in sorted({i["representation"] for i in trace["final"]})
                    },
                    "observed_ms": round(latency, 3),
                    "deadline_ms": config.max_advanced_elapsed_milliseconds,
                    "output_equal": True,
                    "candidate_budget": observed.candidate_budget,
                    "requested_k": observed.requested_k,
                }
            )
        controls = manifest["negative_controls"]
        wrong_doc = manifest["cases"][0]["targets"][0]
        other_version = next(
            t["version_id"]
            for c in manifest["cases"]
            for t in c["targets"]
            if t["document_id"] != wrong_doc["document_id"]
        )
        for name, req, actor in (
            (
                "wrong_notebook",
                request.model_copy(
                    update={
                        "scope": SelectedNotebooks(
                            kind="selected", notebook_ids=(UUID(controls["wrong_notebook"]),)
                        )
                    }
                ),
                principal,
            ),
            (
                "wrong_version",
                request.model_copy(
                    update={
                        "documents": (
                            DocumentSelection(
                                notebook_id=NOTEBOOK,
                                document_id=UUID(wrong_doc["document_id"]),
                                version_id=UUID(other_version),
                            ),
                        )
                    }
                ),
                principal,
            ),
            (
                "ungranted_actor",
                request,
                PrincipalContextV1(UUID(controls["ungranted_actor"]), True),
            ),
        ):
            for enabled in (False, True):
                observer = RankTrace()
                try:
                    with ExitProbe(observer, app, enabled):
                        await service.execute_ranked(req, actor)
                except NotFoundError:
                    if observer.raw:
                        raise AssertionError("denied trace retained") from None
                else:
                    raise AssertionError(f"negative control passed: {name}")
        return {
            "manifest_sha256": sha(MANIFEST.read_bytes()),
            "alias": manifest["active_alias"],
            "cases": results,
            "verified_identities": len(allowed),
            "negative_controls": "all three denied with and without diagnostics",
        }


def ExitProbe(observer: RankTrace, app: Any, enabled: bool) -> Any:
    from contextlib import nullcontext

    return observer.observe(app) if enabled else nullcontext()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("run_name")
    directory = clone(cli.parse_args().run_name)
    output = asyncio.run(evaluate(directory))
    with (directory / "result.json").open("x", encoding="utf8") as report:
        json.dump(output, report, indent=2)
    print(f"Verified {len(output['cases'])} cases: {directory}")
