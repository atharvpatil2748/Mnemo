"""Compare frozen sparse and real Full V2 BGE through shared scoped search.

The only writable store is the explicitly named disposable evaluation copy.
No transport, public route, production alias, or external service is started.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from contextlib import AsyncExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo.interfaces.advanced_retrieval import MultilingualAdvancedStoreV1
from mnemo.models import AdvancedRetrievalMode, EvidenceRepresentation
from mnemo.phase85.isolated_v2_identity import (
    IsolatedV2ArtifactIdentity,
    IsolatedV2DatabaseIdentityVerifier,
)
from mnemo.phase85.profiles import ModelProfileDocument
from mnemo.phase85.rebuild_language_capability import load_rebuild_language_capability
from mnemo.phase85.v2_evaluation_runtime import (
    ComposedFullMultilingualV2Runtime,
    V2RuntimeIdentityV1,
)
from mnemo.retrieval.advanced import AdvancedRetrievalService, RetrievalCursorCodec
from mnemo.retrieval.advanced_sources import CanonicalTextAdvancedSource
from mnemo.retrieval.full_multilingual_v2 import PassThroughV2RerankerV1
from mnemo.retrieval.multilingual_providers import (
    BGE_M3_DOCUMENT_PREPROCESSING,
    BGE_M3_QUERY_PREPROCESSING,
    BGEM3EmbeddingProvider,
)
from mnemo.retrieval.multimodal_sources import ProjectedMultilingualAdvancedSource
from mnemo.retrieval.reranker_candidates import V2TypedCandidateBuilderV1
from mnemo.retrieval.sparse import SparseRetriever
from mnemo.storage.sqlite import SQLiteStore
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore
from mnemo_server.config import ServerConfig
from mnemo_server.schemas.retrieval_v2 import EvidenceScopeRequest, EvidenceSearchRequest
from mnemo_server.schemas.scope_contract_review import (
    DocumentSelection,
    ScopeRequestReview,
    SelectedNotebooks,
)
from mnemo_server.services.full_multilingual_v2_production import (
    ProductionFullMultilingualV2ServerDependencyAssemblerV1,
    V2ProductionRuntimeSupportV1,
)
from mnemo_server.services.full_multilingual_v2_registration import (
    ServerOwnedFullMultilingualV2RegistrationV1,
)
from mnemo_server.services.isolated_full_v2_serving import (
    _CommonSpaceAdmission,
    _CommonSpaceQueryLanguageResolver,
)
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.scoped_search import ScopedSearchApplicationService
from verify_module_894_dere import verify

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scratch/module_894_disposable/eval-20261106-04"
MODEL_CACHE = Path("D:/Mnemo/phase8.5.11-models/huggingface/hub")
MANIFEST = ROOT / "evaluation/module_894_dere/manifest.v1.json"
SNAPSHOT = ROOT / "scratch/phase8_5_11/eval-20260825-02"
SOURCE_FILE = ROOT / "goldenDataset/Phase 8.5 Evaluation Corpus/manuscript.pdf"
ACTOR = UUID("7ee69849-d87e-57d1-b2ef-29128d668a5e")
NOTEBOOK = UUID("df9c20cf-85fe-529c-902e-2e9e68193fbe")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class DisposableIdentityVerifier(IsolatedV2DatabaseIdentityVerifier):
    """Reuse the existing exact-generation verifier for this non-governed copy.

    Its run ID denotes this experiment, not a production or governed build run.
    """

    def __init__(self, database: Path) -> None:
        self._database = database
        self._notebook_id = NOTEBOOK
        self._run_id = uuid5(NAMESPACE_URL, f"mnemo:module-894:{database.parent.name}")
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            self._source_hashes = tuple(
                (str(row[0]), str(row[1]))
                for row in connection.execute(
                    "SELECT s.source_id,d.current_hash FROM sources s "
                    "JOIN documents d ON d.document_id=s.document_id "
                    "WHERE s.notebook_id=? ORDER BY s.source_id",
                    (str(NOTEBOOK),),
                )
            )
        finally:
            connection.close()
        self._expected = self._read_identity()
        self.artifact = IsolatedV2ArtifactIdentity(
            target_path=database.relative_to(ROOT).as_posix(),
            notebook_id=NOTEBOOK,
            build_run_id=self._run_id,
            profile_fingerprint=str(self._expected["profile_fingerprint"]),
            vector_space_identity=str(self._expected["vector_space"]),
            database_identity=_digest(self._expected),
            generation_ids=tuple(
                UUID(str(item["id"]))
                for item in cast(list[dict[str, Any]], self._expected["generations"])
            ),
        )


def _ranked(result: Any, target: str) -> dict[str, Any]:
    ranked = []
    for rank, item in enumerate(result.items, 1):
        ranked.append(
            {
                "rank": rank,
                **{
                    key: item.get(key)
                    for key in (
                        "candidate_id",
                        "notebook_id",
                        "source_id",
                        "document_id",
                        "version_id",
                        "chunk_id",
                        "evidence_id",
                        "representation",
                        "fused_score",
                        "retrieval_paths",
                        "locator",
                    )
                },
            }
        )
    found = [value["rank"] for value in ranked if value["chunk_id"] == target]
    return {
        "ranked": ranked,
        "target_rank": min(found) if found else None,
        "recall_at_10": float(bool(found)),
        "precision_at_10": sum(value["chunk_id"] == target for value in ranked) / 10,
        "mrr": 0.0 if not found else 1 / min(found),
        "completeness": result.completeness,
        "omissions": list(result.omissions),
        "admission": [
            {
                "representation": source.representation.value,
                "status": source.status,
                "alias": source.generation_alias,
                "reason": source.reason_code,
            }
            for partition in result.notebooks
            for source in partition.sources
        ],
    }


async def attach_disposable_full_v2(
    runtime: Path,
    engine: KnowledgeEngine,
    harness: SimpleNamespace,
    canonical: CanonicalTextAdvancedSource,
    codec: RetrievalCursorCodec,
    activation: dict[str, Any],
    stack: AsyncExitStack,
) -> tuple[ComposedFullMultilingualV2Runtime, str]:
    """Compose the retained Full V2 stack for the authorized offline experiment only."""
    if (
        runtime.resolve(strict=True) != runtime
        or runtime.parent != RUNTIME.parent
        or not (runtime == RUNTIME or runtime.name.startswith("dere-trace-"))
        or Path(harness.config.storage.sqlite.path).resolve() != runtime / "mnemo.db"
    ):
        raise ValueError("expected isolated experiment database")
    verifier = DisposableIdentityVerifier(runtime / "mnemo.db")
    artifact = verifier.artifact
    if activation["generation_ids"] != [str(item) for item in artifact.generation_ids]:
        raise ValueError("active generation set differs from evaluated identity")
    read_store = SQLiteV2ReadOnlyRuntimeStore(runtime / "mnemo.db")
    await read_store.open()
    try:
        active = await read_store.resolve_active_multilingual_v2_generation_set()
        alias = await read_store.resolve_active_multilingual_v2_alias_digest()
        if active != artifact.generation_ids or alias != activation["alias_set_digest"]:
            raise ValueError("disposable alias changed")
        evidence = await read_store.inspect_active_v2_generations(active)
        profile_id = evidence[0].profile_id
    finally:
        await read_store.close()
    component = (
        ModelProfileDocument.from_file(
            ROOT / "config/model_profiles/full_multilingual_v2_profiles.toml"
        )
        .select("full_multilingual_v2_local_prebuild")
        .models["multilingual_embedding"]
    )
    capability = load_rebuild_language_capability(
        path=ROOT / "config/rebuild/multilingual_embedding_capability.json",
        component=component,
    )
    embedding = BGEM3EmbeddingProvider(
        component,
        generation_id=artifact.generation_ids[2],
        cache_folder=MODEL_CACHE,
        device="cuda",
    )
    stack.push_async_callback(embedding.close)
    await embedding.initialize()
    profile = await embedding.profile()
    if profile.vector_space != artifact.vector_space_identity or profile.dimension != 1024:
        raise ValueError("real BGE query provider differs from document space")
    identity = V2RuntimeIdentityV1(
        profile_id=profile_id,
        profile_fingerprint=artifact.profile_fingerprint,
        vector_space_identity=artifact.vector_space_identity,
        build_run_id=artifact.build_run_id,
        database_identity=artifact.database_identity,
        alias_set_digest=activation["alias_set_digest"],
        query_preprocessing_identity=BGE_M3_QUERY_PREPROCESSING,
        document_preprocessing_identity=BGE_M3_DOCUMENT_PREPROCESSING,
        authorization_service_id="mnemo.server.v2-retrieval-authorization-policy/1",
        provenance_validator_id="mnemo.v2-provenance-validator/1",
        reranker_public_protocol_id="multilingual-reranker/3",
        provider_identity=component.provider,
    )
    storage = engine.storage
    if not isinstance(storage, MultilingualAdvancedStoreV1):
        raise ValueError("disposable storage lacks multilingual advanced retrieval")
    assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
        workspace_root=ROOT,
        identity_manifest=runtime / "bge-disposable-activation-result.json",
        identity=identity,
        support=V2ProductionRuntimeSupportV1(
            query_embedder=embedding,
            candidate_builder_factory=lambda resolver: V2TypedCandidateBuilderV1(resolver=resolver),
            reranker=PassThroughV2RerankerV1(),
            admission=_CommonSpaceAdmission(capability),
            query_language_resolver=_CommonSpaceQueryLanguageResolver(),
            exhaustive_fallback=ProjectedMultilingualAdvancedSource(storage),
        ),
        isolated_verifier=verifier,
        isolated_database=runtime / "mnemo.db",
    )
    stack.push_async_callback(assembler.close)
    registration = ServerOwnedFullMultilingualV2RegistrationV1(
        engine=engine, identity=identity, assembler=assembler
    )
    composed = await registration.compose_internal_runtime()
    harness.advanced_retrieval = AdvancedRetrievalService(
        sources=(canonical, composed.advanced_source), cursor_codec=codec
    )
    harness.full_multilingual_v2_alias_digest = composed.identity.alias_set_digest
    return composed, component.revision


async def run() -> dict[str, Any]:
    if RUNTIME.resolve(strict=True) != RUNTIME or RUNTIME.is_symlink():
        raise ValueError("unexpected disposable target")
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        raise ValueError("production selector changed")
    if (
        hashlib.sha256(SOURCE_FILE.read_bytes()).hexdigest()
        != json.loads(MANIFEST.read_text(encoding="utf-8"))["cases"][0]["source_file_sha256"]
    ):
        raise ValueError("frozen source file changed")
    preflight = verify(MANIFEST, SNAPSHOT)
    if any(item["ancestry"] != "PASS" for item in preflight["cases"]):
        raise ValueError("frozen ancestry preflight failed")
    case = json.loads(MANIFEST.read_text(encoding="utf-8"))["cases"][0]
    if case["notebook_id"] != str(NOTEBOOK):
        raise ValueError("frozen notebook differs")
    activation = json.loads(
        (RUNTIME / "bge-disposable-activation-result.json").read_text(encoding="utf-8")
    )
    authority = SQLiteNotebookScopeAuthority(RUNTIME / "acl.db")
    if not authority.permits(ACTOR, NOTEBOOK):
        raise PermissionError("explicit disposable test owner grant is absent")
    store = SQLiteStore(RUNTIME / "mnemo.db")
    await store.open()
    canonical = CanonicalTextAdvancedSource(store=store, ranked_retriever=SparseRetriever(store))
    codec = RetrievalCursorCodec(b"module-894-full-v2-disposable-cursor-secret!!")
    harness = SimpleNamespace(
        storage=store,
        config=SimpleNamespace(
            storage=SimpleNamespace(sqlite=SimpleNamespace(path=RUNTIME / "mnemo.db"))
        ),
        server_scope_authority=authority,
        advanced_retrieval=AdvancedRetrievalService(sources=(canonical,), cursor_codec=codec),
        full_multilingual_v2_alias_digest=None,
    )
    engine = cast(KnowledgeEngine, harness)
    stack = AsyncExitStack()
    try:
        request = ScopeRequestReview(
            query=case["query"],
            mode="ranked",
            scope=SelectedNotebooks(kind="selected", notebook_ids=(NOTEBOOK,)),
            limit=10,
        )
        principal = PrincipalContextV1(ACTOR, True)
        service = ScopedSearchApplicationService(engine, ServerConfig())
        start = time.perf_counter()
        baseline_result = await service.execute_ranked(request, principal)
        sparse = _ranked(baseline_result, case["evidence_id"])
        sparse["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
        composed, revision = await attach_disposable_full_v2(
            RUNTIME, engine, harness, canonical, codec, activation, stack
        )
        start = time.perf_counter()
        combined_result = await ScopedSearchApplicationService(
            engine, ServerConfig()
        ).execute_ranked(request, principal)
        combined = _ranked(combined_result, case["evidence_id"])
        combined["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
        if not any(
            value["representation"] == "multilingual_text" and value["status"] == "active"
            for value in combined["admission"]
        ):
            raise ValueError("Full V2 was not admitted by shared scoped search")
        config = ServerConfig()
        v2_plan = EvidenceSearchRequest(
            query=case["query"],
            mode=AdvancedRetrievalMode.RANKED,
            scope=EvidenceScopeRequest(notebook_id=NOTEBOOK),
            representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
            candidate_budget=config.max_advanced_candidate_budget,
            evidence_budget=config.max_advanced_evidence_budget,
            max_serialized_bytes=config.max_advanced_response_bytes,
            max_content_characters=config.max_advanced_content_characters,
        ).to_plan(
            max_candidate_budget=config.max_advanced_candidate_budget,
            max_evidence_budget=config.max_advanced_evidence_budget,
            max_response_bytes=config.max_advanced_response_bytes,
            max_content_characters=config.max_advanced_content_characters,
            security_scope_identity=str(ACTOR),
            automatic_policy_version="module-894-dense-diagnostic/1",
        )
        decision = await composed.application.authorize_only(principal=principal, plan=v2_plan)
        language = await _CommonSpaceQueryLanguageResolver().resolve_query_language(
            principal=principal, notebook_id=NOTEBOOK, query=case["query"]
        )
        dense = await composed.application._dense.retrieve(
            decision=decision,
            query=case["query"],
            query_language=language,
            limit=1000,
        )
        dense_target = next(
            (item for item in dense if item.embedding.source.chunk_id == case["evidence_id"]),
            None,
        )
        dense_diagnostic = {
            "query_language": language.value,
            "provider_score_semantics": "L2-normalized BGE-M3 cosine; not calibrated to sparse",
            "candidate_count": len(dense),
            "target_rank_within_1000": None if dense_target is None else dense_target.rank,
            "target_score_within_1000": None if dense_target is None else dense_target.score,
            "top_20": [
                {
                    "rank": item.rank,
                    "score": item.score,
                    "chunk_id": item.embedding.source.chunk_id,
                    "notebook_id": str(item.embedding.source.notebook_id),
                    "source_id": str(item.embedding.source.source_id),
                    "document_id": str(item.embedding.source.document_id),
                    "version_id": str(item.embedding.source.version_id),
                }
                for item in dense[:20]
            ],
        }
        v2_fused = await composed.application.retrieve(
            principal=principal, plan=v2_plan, query_language=language
        )
        target_v2 = next(
            (
                item
                for item in v2_fused.candidates
                if item.candidate.source_reference.chunk_id == case["evidence_id"]
            ),
            None,
        )
        v2_diagnostic = {
            "candidate_count": len(v2_fused.candidates),
            "dense_examined": v2_fused.dense_examined,
            "sparse_examined": v2_fused.sparse_examined,
            "reranked_count": v2_fused.reranked_count,
            "completeness": v2_fused.completeness,
            "omissions": list(v2_fused.omissions),
            "target_rank_within_200": None if target_v2 is None else target_v2.final_rank,
            "target_fused_score": None if target_v2 is None else target_v2.fused_score,
            "target_paths": None if target_v2 is None else list(target_v2.source_paths),
        }
        for group in (sparse, combined):
            for item in group["ranked"]:
                source = await engine.storage.get_source(UUID(item["source_id"]))
                chunk_id = item["chunk_id"]
                chunk = None if chunk_id is None else await engine.storage.get_chunk(chunk_id)
                document = await engine.storage.get_document(UUID(item["document_id"]))
                if (
                    source is None
                    or source.notebook_id != NOTEBOOK
                    or source.document_id != UUID(item["document_id"])
                    or document is None
                    or not any(
                        version.version_id == UUID(item["version_id"])
                        for version in document.versions
                    )
                    or (chunk_id is not None and chunk is None)
                    or (
                        chunk is not None
                        and (
                            chunk.document_id != source.document_id
                            or chunk.version_id != UUID(item["version_id"])
                        )
                    )
                ):
                    raise ValueError("ranked evidence escaped source/document/version ancestry")
        stranger = PrincipalContextV1(uuid5(ACTOR, "ungranted"), True)
        try:
            await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
                request, stranger
            )
        except NotFoundError:
            cross_principal_denied = True
        else:
            raise AssertionError("ungranted actor received evidence")
        wrong_notebook = UUID(int=1)
        try:
            await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
                request.model_copy(
                    update={
                        "scope": SelectedNotebooks(kind="selected", notebook_ids=(wrong_notebook,))
                    }
                ),
                principal,
            )
        except NotFoundError:
            wrong_notebook_denied = True
        else:
            raise AssertionError("nonexistent notebook received evidence")
        wrong_version = UUID(int=2)
        try:
            await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
                ScopeRequestReview(
                    query=case["query"],
                    mode="ranked",
                    scope=SelectedNotebooks(kind="selected", notebook_ids=(NOTEBOOK,)),
                    documents=(
                        DocumentSelection(
                            notebook_id=NOTEBOOK,
                            document_id=UUID(case["document_id"]),
                            version_id=wrong_version,
                        ),
                    ),
                    limit=10,
                ),
                principal,
            )
        except NotFoundError:
            wrong_version_denied = True
        else:
            raise AssertionError("wrong version received evidence")
        reader_id = uuid5(ACTOR, "module-894-disposable-reader")
        authority.grant(actor_id=reader_id, notebook_id=NOTEBOOK, role="reader", operator_id=ACTOR)
        reader = PrincipalContextV1(reader_id, True)
        try:
            reader_result = await ScopedSearchApplicationService(
                engine, ServerConfig()
            ).execute_ranked(request, reader)
            if not reader_result.items:
                raise AssertionError("explicit reader could not retrieve evidence")
            reader_count = len(reader_result.items)
        finally:
            authority.revoke(actor_id=reader_id, notebook_id=NOTEBOOK)
        try:
            await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(
                request, reader
            )
        except NotFoundError:
            revoked_reader_denied = True
        else:
            raise AssertionError("revoked reader received evidence")
        return {
            "schema": "mnemo.module-894-disposable-bge-evaluation/1",
            "case_id": case["case_id"],
            "query": case["query"],
            "target_evidence_id": case["evidence_id"],
            "principal": str(ACTOR),
            "notebook_id": str(NOTEBOOK),
            "limit": request.limit,
            "candidate_budget": ServerConfig().max_advanced_candidate_budget,
            "sparse_only": sparse,
            "sparse_plus_full_v2_bge": combined,
            "bge_dense_diagnostic": dense_diagnostic,
            "v2_fusion_diagnostic": v2_diagnostic,
            "provider_revision": revision,
            "query_document_vector_space": composed.identity.vector_space_identity,
            "active_alias": composed.identity.alias_set_digest,
            "generation_ids": [str(item) for item in composed.generation_ids],
            "cross_principal_denied": cross_principal_denied,
            "wrong_notebook_denied": wrong_notebook_denied,
            "wrong_version_denied": wrong_version_denied,
            "reader_result_count_before_revocation": reader_count,
            "revoked_reader_denied": revoked_reader_denied,
            "acl_revision_after_revocation": authority.revision(NOTEBOOK),
            "human_semantic_relevance": "NOT_ADJUDICATED",
            "identity_note": "disposable experiment run ID, not a governed production build run",
        }
    finally:
        await stack.aclose()
        await store.close()


if __name__ == "__main__":
    result = asyncio.run(run())
    (RUNTIME / "bge-dere-comparison-v4.json").open("x", encoding="utf-8").write(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "sparse": {
                    key: result["sparse_only"][key]
                    for key in ("recall_at_10", "precision_at_10", "mrr")
                },
                "combined": {
                    key: result["sparse_plus_full_v2_bge"][key]
                    for key in ("recall_at_10", "precision_at_10", "mrr")
                },
                "output": str(RUNTIME / "bge-dere-comparison-v4.json"),
            },
            indent=2,
        )
    )
