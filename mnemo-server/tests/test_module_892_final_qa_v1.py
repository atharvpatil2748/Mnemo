"""Real persisted V1 FinalQA route under a disposable membership authority."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    CitationResolutionResult,
    CitationResolutionStatus,
    ContextBuildResult,
    ContextEmptyReason,
    ContextItem,
    ContextItemKind,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FinalQARequest,
    FusedChunkResult,
    FusionEvidence,
    GenerationEvidence,
    GroundedAnswerResult,
    GroundedAnswerStatus,
    MetadataFilter,
    Notebook,
    RerankedChunkResult,
    RerankFallbackReason,
    RerankPolicy,
    RetrievalFusionResult,
    RetrievalIntent,
    RetrievalInvocationTrace,
    RetrievalMode,
    RetrievalPlan,
    RetrievalRerankResult,
    ScoredChunk,
    Session,
    Source,
    SubQuery,
    Turn,
    TurnRole,
)
from mnemo.retrieval import CitationEngine
from mnemo.retrieval.final_qa import FinalQAOrchestrator
from mnemo.retrieval.scope import StorageDocumentScopeResolverV1, StorageSourceAssociationReaderV1
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.trusted_actor import TrustedJWTActorMapper
from test_module_892_v1_acl_routes import _SECRET, _headers


class _Stage:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0
        self.on_generate: Callable[[], None] | None = None

    async def plan(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        return self.result

    async def execute(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        if isinstance(self.result, RetrievalRerankResult):
            assert isinstance(args[1], RetrievalFusionResult)
            results = tuple(
                RerankedChunkResult(fused_result=item, rerank_evidence=None, reranked_rank=index)
                for index, item in enumerate(args[1].results, 1)
            )
            return replace(self.result, fusion_result=args[1], results=results)
        return self.result

    async def build(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        if isinstance(self.result, ContextBuildResult):
            assert isinstance(args[0], RetrievalRerankResult)
            if self.result.items:
                selected = args[0].results[0]
                item = replace(self.result.items[0], reranked_result=selected)
                return replace(self.result, rerank_result=args[0], items=(item,))
            return replace(self.result, rerank_result=args[0])
        return self.result

    async def generate(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        if self.on_generate is not None:
            self.on_generate()
        if isinstance(self.result, GroundedAnswerResult):
            assert isinstance(args[0], ContextBuildResult)
            return replace(self.result, context_result=args[0])
        return self.result

    def final_qa_execution_descriptor(self) -> tuple[str, str, dict[str, str], str]:
        return "test", "model", {"temperature": "fixed"}, "test/tokenizer"

    async def resolve_and_persist(
        self, answer: GroundedAnswerResult, *, assistant_turn: object, document_labels: object
    ) -> CitationResolutionResult:
        self.calls += 1
        return CitationResolutionResult(
            answer_result=answer,
            assistant_turn=None,
            status=CitationResolutionStatus.NO_CONTEXT,
            citations=(),
            persisted=False,
        )


@pytest.mark.anyio
async def test_v1_final_qa_route_persisted_replay_is_acl_bound(tmp_path: Path) -> None:
    """Owner can run and replay; other actors and stale revisions cannot read snapshots."""
    store = SQLiteStore(tmp_path / "data.db")
    await store.open()
    notebook_id, session_id, user_id, assistant_id = (uuid4() for _ in range(4))
    now = datetime.now(UTC)
    await store.upsert_notebook(
        Notebook(notebook_id=notebook_id, title="private", created_at=now, updated_at=now)
    )
    await store.upsert_session(
        Session(
            session_id=session_id,
            notebook_id=notebook_id,
            created_at=now,
            updated_at=now,
            turns=(
                Turn(
                    turn_id=user_id,
                    session_id=session_id,
                    sequence=0,
                    role=TurnRole.USER,
                    content="What is duty?",
                    created_at=now,
                ),
            ),
        )
    )
    plan = RetrievalPlan(
        intent=RetrievalIntent.FACTUAL,
        sub_queries=(
            SubQuery(
                query_text="What is duty?",
                retrieval_mode=RetrievalMode.DENSE,
                filters=MetadataFilter(),
                max_results=1,
            ),
        ),
        requires_multi_hop=False,
        requires_multi_doc=False,
    )
    fusion = RetrievalFusionResult(plan=plan, invocations=(), results=())
    rerank = RetrievalRerankResult(
        query="What is duty?", fusion_result=fusion, policy=RerankPolicy.UNCHANGED_EMPTY, results=()
    )
    context = ContextBuildResult(
        rerank_result=rerank,
        tokenizer_id="test/tokenizer",
        context_budget=1000,
        fixed_overhead_tokens=10,
        available_context_tokens=990,
        context_tokens=0,
        rendered_context="",
        items=(),
        omitted_results=(),
        compression_available=False,
        empty_reason=ContextEmptyReason.NO_CANDIDATES,
    )
    answer = GroundedAnswerResult(
        context_result=context,
        query="What is duty?",
        status=GroundedAnswerStatus.NO_CONTEXT,
        answer=None,
        generation_evidence=None,
    )
    planner, fuser, reranker, builder, generator, citation = (
        _Stage(value) for value in (plan, fusion, rerank, context, answer, answer)
    )
    orchestrator = FinalQAOrchestrator(
        planner,
        fuser,
        reranker,
        builder,
        generator,
        citation,
        store,
        lambda: datetime.now(UTC),
        execution_store=store,
    )
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1]).actor_id
    reader = mapper.from_token(_headers("bob")["Authorization"].split()[1]).actor_id
    authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.storage = store
    engine.final_qa = orchestrator
    engine.server_scope_authority = authority
    engine.server_actor_mapper = mapper
    engine.document_scope_resolver = StorageDocumentScopeResolverV1(
        store, StorageSourceAssociationReaderV1(store)
    )
    config = ServerConfig(
        auth_mode="jwt",
        jwt_secret=_SECRET,
        delivery_cursor_secret="fixture-delivery-cursor-secret-32-bytes",
    )
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    path = f"/v1/notebooks/{notebook_id}/final-qa"
    body = {
        "session_id": str(session_id),
        "user_turn_id": str(user_id),
        "assistant_turn_id": str(assistant_id),
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post(path, headers=_headers("bob"), json=body)).status_code == 404
            assert (await client.post(path, json=body)).status_code != 200
            # Simulate a persisted pre-ACL V1 execution. A valid result snapshot
            # alone must never become an authorized replay after ACL attachment.
            unbound_id = uuid4()
            await orchestrator.execute(
                FinalQARequest(
                    query="What is duty?",
                    metadata_filter=MetadataFilter(notebook_id=notebook_id),
                    global_limit=10,
                    context_budget=1000,
                    system_prompt="Grounded answer only",
                    max_output_tokens=100,
                    session_id=session_id,
                    user_turn_id=user_id,
                    assistant_turn_id=unbound_id,
                )
            )
            unbound = await client.post(
                path,
                headers=_headers("alice"),
                json={**body, "assistant_turn_id": str(unbound_id)},
            )
            assert unbound.status_code == 404
            assert "Grounded" not in unbound.text
            fuser.calls = 0
            first = await client.post(path, headers=_headers("alice"), json=body)
            assert first.status_code == 200, first.text
            assert first.json()["execution"] == "new"
            assert first.json()["status"] == "no_context"
            assert fuser.calls == 1
            replay = await client.post(path, headers=_headers("alice"), json=body)
            assert replay.status_code == 200, replay.text
            assert replay.json()["execution"] == "replay"
            assert fuser.calls == 1
            document_id, version_id, source_id = uuid4(), uuid4(), uuid4()
            content_hash = hashlib.sha256(b"protected source").hexdigest()
            await store.upsert_document(
                Document(
                    document_id=document_id,
                    versions=(
                        DocumentVersion(
                            version_id=version_id,
                            document_id=document_id,
                            content_hash=content_hash,
                            metadata=DocumentMetadata(
                                content_hash=content_hash, title="Private source"
                            ),
                            status=DocumentVersionStatus.CURRENT,
                            created_at=now,
                        ),
                    ),
                    current_version_id=version_id,
                    current_hash=content_hash,
                    status=DocumentStatus.INDEXED,
                    created_at=now,
                    updated_at=now,
                )
            )
            await store.upsert_source(
                Source(
                    source_id=source_id,
                    notebook_id=notebook_id,
                    document_id=document_id,
                    created_at=now,
                )
            )
            chunk = Chunk(
                id=hashlib.sha256(b"canonical private passage").hexdigest(),
                document_id=document_id,
                version_id=version_id,
                text="canonical private passage",
                chunk_type=ChunkType.PASSAGE,
                position=ChunkPosition(section_index=0, chunk_index_in_section=0),
                source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
                heading_path=(),
            )
            scored = ScoredChunk(chunk=chunk, score=1.0, source="dense", rank=1)
            trace = RetrievalInvocationTrace(
                invocation_id="sq-1:dense",
                subquery_index=1,
                declared_mode=RetrievalMode.DENSE,
                effective_mode=RetrievalMode.DENSE,
                query_text="What is duty?",
                filters=MetadataFilter(),
                requested_top_k=1,
                raw_results=(scored,),
                promoted_results=(scored,),
            )
            fused = FusedChunkResult(
                chunk=chunk,
                rrf_score=1 / 61,
                global_rank=1,
                evidence=(
                    FusionEvidence(
                        invocation_id="sq-1:dense",
                        subquery_index=1,
                        declared_mode=RetrievalMode.DENSE,
                        effective_mode=RetrievalMode.DENSE,
                        result=scored,
                        identity_introduced_by_parent_promotion=False,
                    ),
                ),
            )
            fused_result = RetrievalFusionResult(plan=plan, invocations=(trace,), results=(fused,))
            ranked = RerankedChunkResult(fused_result=fused, rerank_evidence=None, reranked_rank=1)
            ranked_result = RetrievalRerankResult(
                query="What is duty?",
                fusion_result=fused_result,
                policy=RerankPolicy.RRF_FALLBACK,
                results=(ranked,),
                fallback_reason=RerankFallbackReason.PROVIDER_UNAVAILABLE,
            )
            rendered = "=== Source [1] ===\ncanonical private passage"
            item = ContextItem(
                source_number=1,
                reranked_result=ranked,
                kind=ContextItemKind.VERBATIM,
                content=chunk.text,
                content_token_count=3,
                rendered_text=rendered,
                rendered_token_count=8,
            )
            built = ContextBuildResult(
                rerank_result=ranked_result,
                tokenizer_id="test/tokenizer",
                context_budget=1000,
                fixed_overhead_tokens=10,
                available_context_tokens=990,
                context_tokens=8,
                rendered_context=rendered,
                items=(item,),
                omitted_results=(),
                compression_available=False,
            )
            generated = GroundedAnswerResult(
                context_result=built,
                query="What is duty?",
                status=GroundedAnswerStatus.GENERATED,
                answer="Grounded [source:1]",
                generation_evidence=GenerationEvidence(
                    provider="test",
                    model="test",
                    tokenizer_id="test/tokenizer",
                    prompt_token_count=10,
                    max_output_tokens=100,
                    answer_token_count=10,
                ),
            )
            fuser.result = fused_result
            reranker.result = ranked_result
            builder.result = built
            generator.result = generated
            orchestrator._citation = CitationEngine(store, lambda: datetime.now(UTC))
            answered_id = uuid4()
            answered_body = {**body, "assistant_turn_id": str(answered_id)}
            answered = await client.post(path, headers=_headers("alice"), json=answered_body)
            assert answered.status_code == 200, answered.text
            assert answered.json()["answer"] == "Grounded [source:1]"
            assert answered.json()["citations"][0]["document_id"] == str(document_id)
            await store.close()
            await store.open()
            answered_replay = await client.post(path, headers=_headers("alice"), json=answered_body)
            assert answered_replay.status_code == 200, answered_replay.text
            assert answered_replay.json()["execution"] == "replay"
            await store.delete_source(source_id)
            stale_source = await client.post(path, headers=_headers("alice"), json=answered_body)
            assert stale_source.status_code == 404
            assert "Grounded" not in stale_source.text
            await store.upsert_source(
                Source(
                    source_id=source_id,
                    notebook_id=notebook_id,
                    document_id=document_id,
                    created_at=now,
                )
            )
            authority.grant(
                actor_id=reader, notebook_id=notebook_id, role="reader", operator_id=owner
            )
            assert (await client.post(path, headers=_headers("bob"), json=body)).status_code == 404
            stale = await client.post(path, headers=_headers("alice"), json=answered_body)
            assert stale.status_code == 404
            assert fuser.calls == 2
            interrupted_session_id, interrupted_user_id = uuid4(), uuid4()
            await store.upsert_session(
                Session(
                    session_id=interrupted_session_id,
                    notebook_id=notebook_id,
                    created_at=now,
                    updated_at=now,
                    turns=(
                        Turn(
                            turn_id=interrupted_user_id,
                            session_id=interrupted_session_id,
                            sequence=0,
                            role=TurnRole.USER,
                            content="What is duty?",
                            created_at=now,
                        ),
                    ),
                )
            )
            interrupted_id = uuid4()
            generator.on_generate = lambda: authority.revoke(
                actor_id=owner, notebook_id=notebook_id
            )
            interrupted = await client.post(
                path,
                headers=_headers("alice"),
                json={
                    "session_id": str(interrupted_session_id),
                    "user_turn_id": str(interrupted_user_id),
                    "assistant_turn_id": str(interrupted_id),
                },
            )
            assert interrupted.status_code == 404
            assert await store.get_final_qa_execution(interrupted_id) is not None
            assert fuser.calls == 3
            generator.on_generate = None
            assert (
                await client.post(path, headers=_headers("alice"), json=body)
            ).status_code == 404
    finally:
        await store.close()
