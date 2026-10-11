"""Bounded local V2 query against a previously created non-serving canary."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from pathlib import Path
from uuid import uuid4

from mnemo.config import MnemoConfig
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models.advanced_retrieval import AdvancedRetrievalMode
from mnemo.phase85.rebuild_runtime import resolve_governed_rebuild_runtime
from mnemo.retrieval.advanced import RetrievalCursorCodec
from mnemo.retrieval.full_multilingual_advanced_v2 import FullMultilingualAdvancedSourceV2
from mnemo_server.config import ServerConfig
from mnemo_server.schemas.automatic_query_v2 import AutomaticQueryV2Request
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest
from mnemo_server.services.automatic_query_v2 import (
    AutomaticEvidencePlanner,
    AutomaticQueryV2ApplicationService,
)
from mnemo_server.services.isolated_full_v2_serving import install_isolated_full_v2


async def _query(
    runtime: Path,
    query: str,
    config_path: Path,
    model_cache: Path,
    debug_source: bool,
    clip_snapshot: Path | None,
    check_continuation: bool,
) -> dict[str, object]:
    runtime = runtime.resolve(strict=True)
    root = Path(__file__).resolve().parents[1]
    status = resolve_governed_rebuild_runtime(workspace=root, runtime=runtime)
    decision_path = runtime / "activation-decision.json"
    if decision_path.is_file():
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        if decision.get("notebook_id") != status["notebook_id"] or not decision.get("active"):
            raise ValueError("isolated generation activation decision is invalid")
    os.environ["MNEMO_STORAGE_SQLITE_PATH"] = str(runtime / "mnemo.db")
    os.environ["MNEMO_STORAGE_FILESYSTEM_ROOT"] = str(runtime / "files")
    engine = KnowledgeEngine(
        MnemoConfig.from_file(config_path),
        advanced_retrieval_cursor_codec=RetrievalCursorCodec(
            b"isolated-canary-disposable-cursor-key!"
        ),
    )
    await engine.initialize()
    installed = None
    try:
        installed = await install_isolated_full_v2(
            engine=engine,
            workspace=root,
            runtime=runtime,
            model_cache=model_cache,
            clip_snapshot=clip_snapshot,
        )
        if debug_source:
            principal = PrincipalContextV1(uuid4(), True)
            scope, representations, _ = await AutomaticEvidencePlanner(engine).plan(principal)
            config = ServerConfig()
            plan = EvidenceSearchRequest(
                query=query,
                mode=AdvancedRetrievalMode.RANKED,
                scope=scope,
                representations=representations,
            ).to_plan(
                max_candidate_budget=config.max_advanced_candidate_budget,
                max_evidence_budget=config.max_advanced_evidence_budget,
                max_response_bytes=config.max_advanced_response_bytes,
                max_content_characters=config.max_advanced_content_characters,
                max_rerank_candidates=config.production_rerank_candidate_limit,
                automatic_policy_version="automatic-evidence-plan/v1",
                security_scope_identity=str(principal.actor_id),
            )
            try:
                source = engine._full_multilingual_v2_source
                if not isinstance(source, FullMultilingualAdvancedSourceV2):
                    raise TypeError("isolated Full V2 source is not installed")
                await source.retrieve_authorized(principal=principal, plan=plan, offset=0, limit=20)
            except Exception:
                traceback.print_exc(file=sys.stderr)
        response = await AutomaticQueryV2ApplicationService(engine, ServerConfig()).execute(
            AutomaticQueryV2Request(query=query), PrincipalContextV1(uuid4(), True)
        )
        if str(response.notebook_id) != status["notebook_id"]:
            raise RuntimeError("V2 retrieval escaped the isolated notebook")
        continuation: dict[str, object] | None = None
        if check_continuation:
            service = AutomaticQueryV2ApplicationService(engine, ServerConfig())
            principal = PrincipalContextV1(uuid4(), True)
            base = AutomaticQueryV2Request(
                query=query,
                mode=AdvancedRetrievalMode.EXHAUSTIVE,
                candidate_budget=20,
                evidence_budget=2,
            )
            pages = []
            cursor = None
            for _ in range(30):
                page = await service.execute(base.model_copy(update={"cursor": cursor}), principal)
                pages.append(page)
                cursor = page.evidence.next_cursor
                if cursor is None:
                    break
            else:
                raise RuntimeError("isolated V2 continuation did not terminate")
            if len(pages) < 2:
                raise RuntimeError("isolated V2 continuation did not span pages")
            conflict_checks = {}
            first_cursor = pages[0].evidence.next_cursor
            if first_cursor is None:
                raise RuntimeError("isolated V2 first page lacks a continuation")
            variants = {
                "actor": (
                    base.model_copy(update={"cursor": first_cursor}),
                    PrincipalContextV1(uuid4(), True),
                ),
                "query": (
                    base.model_copy(update={"query": query + " changed", "cursor": first_cursor}),
                    principal,
                ),
                "limit": (
                    base.model_copy(update={"candidate_budget": 21, "cursor": first_cursor}),
                    principal,
                ),
                "tamper": (
                    base.model_copy(
                        update={
                            "cursor": first_cursor[:-1] + ("A" if first_cursor[-1] != "A" else "B")
                        }
                    ),
                    principal,
                ),
            }
            for name, (variant, actor) in variants.items():
                try:
                    await service.execute(variant, actor)
                except Exception as error:
                    conflict_checks[name] = type(error).__name__
                else:
                    raise RuntimeError(f"isolated V2 {name} cursor replay was accepted")
            continuation = {
                "pages": len(pages),
                "items": sum(len(page.evidence.items) for page in pages),
                "terminal": pages[-1].evidence.next_cursor is None,
                "last_completeness": pages[-1].evidence.completeness,
                "representations": sorted(
                    {item["representation"] for page in pages for item in page.evidence.items}
                ),
                "conflicts": conflict_checks,
            }
        return {
            "notebook_id": str(response.notebook_id),
            "answer_status": response.answer_status,
            "visual_status": installed.visual_status,
            "continuation": continuation,
            "serving_alias_digest": installed.identity.alias_set_digest,
            "serving_database_identity": installed.identity.database_identity,
            "serving_generation_ids": [str(item) for item in installed.generation_ids],
            "representation_decisions": [
                {
                    "representation": item.representation,
                    "status": item.status,
                    "reason": item.reason,
                }
                for item in response.representation_decisions
            ],
            "evidence": [
                {
                    key: item.get(key)
                    for key in (
                        "representation",
                        "notebook_id",
                        "source_id",
                        "document_id",
                        "version_id",
                        "chunk_id",
                        "occurrence_id",
                        "derivation_id",
                        "content",
                        "locator",
                        "retrieval_paths",
                        "rank",
                    )
                }
                for item in response.evidence.items
            ],
        }
    finally:
        if installed is not None:
            await installed.close()
        await engine.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--config", type=Path, default=Path("mnemo.toml"))
    parser.add_argument("--cache-folder", type=Path, required=True)
    parser.add_argument("--debug-source", action="store_true")
    parser.add_argument("--clip-snapshot", type=Path)
    parser.add_argument("--check-continuation", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                _query(
                    args.runtime,
                    args.query,
                    args.config,
                    args.cache_folder,
                    args.debug_source,
                    args.clip_snapshot,
                    args.check_continuation,
                )
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
