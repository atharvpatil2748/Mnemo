"""Transport-level WP-12 execution, replay, authorization, and modality proofs."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from mnemo.config import MnemoConfig
from mnemo.engine import EngineState
from mnemo.interfaces import ConflictError, IntegrityError, OperationTimeoutError
from mnemo.models import FrozenMetadata
from mnemo.models.advanced_retrieval import RetrievalCompleteness
from mnemo.models.final_qa_execution import FinalQAExecutionSnapshotPhase, FinalQAExecutionState
from mnemo.models.multimodal import (
    EvidenceAuthorityV2,
    EvidenceCandidateV2,
    EvidenceKindV2,
    FinalQAExecutionSnapshotV2,
    FinalQAExecutionV2,
    MultimodalGenerationRequestV1,
    MultimodalGenerationResultV1,
    MultimodalProviderCapabilitiesV1,
    MultimodalRetrievalDiagnosticsV2,
    MultimodalRetrievalResultV2,
    ProviderModalityState,
    evidence_candidate_v2_id,
)
from mnemo.retrieval import FinalQAV2Orchestrator, MultimodalContextBuilder
from mnemo.storage import SQLiteFinalQAOperationalStore
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import get_engine, get_server_config
from mnemo_server.errors import register_error_handlers
from mnemo_server.mcp.tools import execute_mcp_tool
from mnemo_server.routers.final_qa_v2 import router
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.final_qa_v2 import FinalQAV2ApplicationService

NOTEBOOK_ID = UUID(int=10)


class Counter:
    @property
    def tokenizer_id(self) -> str:
        return "test/words/v1"

    def count(self, text: str) -> int:
        return max(1, len(text.split()))


class Provider:
    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.requests: list[MultimodalGenerationRequestV1] = []
        self.unsupported: set[EvidenceKindV2] = set()
        self.states: dict[EvidenceKindV2, ProviderModalityState] = {}

    def capabilities(self) -> MultimodalProviderCapabilitiesV1:
        return MultimodalProviderCapabilitiesV1(
            provider="fake",
            model="transport",
            profile="final_qa_v2:transport",
            configuration_digest="a" * 64,
            modality_states=FrozenMetadata(
                {
                    kind.value: (
                        self.states.get(
                            kind,
                            ProviderModalityState.UNSUPPORTED
                            if kind in self.unsupported
                            else ProviderModalityState.SUPPORTED,
                        ).value
                    )
                    for kind in EvidenceKindV2
                }
            ),
            max_context_tokens=50_000,
            max_output_tokens=4096,
        )

    async def complete(
        self, request: MultimodalGenerationRequestV1
    ) -> MultimodalGenerationResultV1:
        self.requests.append(request)
        answer = self.answers.pop(0)
        return MultimodalGenerationResultV1(
            answer=answer,
            provider="fake",
            model="transport",
            prompt_tokens=20,
            answer_tokens=max(1, len(answer.split())),
        )


class Authorizer:
    def __init__(self) -> None:
        self.allowed = True

    async def authorize_evidence(
        self, actor_id: UUID, notebook_id: UUID, candidate: EvidenceCandidateV2
    ) -> bool:
        del actor_id
        return self.allowed and notebook_id == candidate.notebook_id

    async def generation_is_active(self, candidate: EvidenceCandidateV2) -> bool:
        del candidate
        return True


class Store:
    def __init__(self) -> None:
        self.executions: dict[UUID, FinalQAExecutionV2] = {}
        self.snapshots: dict[
            tuple[UUID, FinalQAExecutionSnapshotPhase], FinalQAExecutionSnapshotV2
        ] = {}

    async def get_notebook(self, notebook_id: UUID):  # type: ignore[no-untyped-def]
        return object() if notebook_id == NOTEBOOK_ID else None

    async def create_final_qa_v2_execution(self, execution: FinalQAExecutionV2) -> bool:
        if execution.assistant_turn_id in self.executions:
            return False
        self.executions[execution.assistant_turn_id] = execution
        return True

    async def get_final_qa_v2_execution(self, assistant_turn_id: UUID) -> FinalQAExecutionV2 | None:
        return self.executions.get(assistant_turn_id)

    async def put_final_qa_v2_snapshot(self, snapshot: FinalQAExecutionSnapshotV2) -> None:
        self.snapshots[(snapshot.execution_id, snapshot.phase)] = snapshot

    async def get_final_qa_v2_snapshot(
        self, execution_id: UUID, phase: FinalQAExecutionSnapshotPhase
    ) -> FinalQAExecutionSnapshotV2 | None:
        return self.snapshots.get((execution_id, phase))

    async def transition_final_qa_v2_execution(
        self,
        execution_id: UUID,
        expected: FinalQAExecutionState,
        target: FinalQAExecutionState,
        *,
        retry_count: int | None = None,
        failure_classification: str | None = None,
    ) -> bool:
        current = next(
            (item for item in self.executions.values() if item.execution_id == execution_id), None
        )
        if current is None or current.state is not expected:
            return False
        updated = replace(
            current,
            state=target,
            retry_count=current.retry_count if retry_count is None else retry_count,
            failure_classification=failure_classification,
            updated_at=datetime.now(UTC),
        )
        self.executions[current.assistant_turn_id] = updated
        return True

    async def put_final_qa_v2_citations(self, citations) -> None:  # type: ignore[no-untyped-def]
        del citations


def candidate(
    kind: EvidenceKindV2 = EvidenceKindV2.CANONICAL_CHUNK,
    *,
    index: int = 1,
    content: str = "Canonical evidence",
) -> EvidenceCandidateV2:
    document_id = UUID(int=100 + index)
    version_id = UUID(int=200 + index)
    occurrence_id = UUID(int=400 + index) if kind is not EvidenceKindV2.CANONICAL_CHUNK else None
    derived = kind in {EvidenceKindV2.OCR_REGION, EvidenceKindV2.VISION_OBSERVATION}
    return EvidenceCandidateV2(
        candidate_id=evidence_candidate_v2_id(
            kind=kind,
            document_id=document_id,
            version_id=version_id,
            authoritative_id=f"evidence-{index}",
        ),
        notebook_id=NOTEBOOK_ID,
        source_id=UUID(int=300 + index),
        document_id=document_id,
        version_id=version_id,
        kind=kind,
        authority=EvidenceAuthorityV2.DERIVED if derived else EvidenceAuthorityV2.ORIGINAL,
        authoritative_id=f"evidence-{index}",
        chunk_id=f"{index:064x}" if kind is EvidenceKindV2.CANONICAL_CHUNK else None,
        asset_id=UUID(int=600 + index) if occurrence_id else None,
        occurrence_id=occurrence_id,
        derivation_id=UUID(int=500 + index) if derived else None,
        document_title=f"Document {index}",
        content=content,
        resource_handle=f"asset://occurrence/{occurrence_id}" if occurrence_id else None,
        media_type="image/png" if occurrence_id else None,
        locator=FrozenMetadata({"language": "hi" if index == 2 else "mr"}),
        final_rank=index,
        completeness=RetrievalCompleteness.COMPLETE,
    )


def retrieval(
    items: tuple[EvidenceCandidateV2, ...],
    query: str,
    completeness: RetrievalCompleteness = RetrievalCompleteness.COMPLETE,
) -> MultimodalRetrievalResultV2:
    return MultimodalRetrievalResultV2(
        query=query,
        query_fingerprint=hashlib.sha256(query.encode()).hexdigest(),
        snapshot_identity=hashlib.sha256(
            ",".join(str(item.candidate_id) for item in items).encode()
        ).hexdigest(),
        completeness=completeness,
        candidates=items,
        diagnostics=MultimodalRetrievalDiagnosticsV2(
            recalled=len(items),
            deduplicated=len(items),
            fused=len(items),
            reranked=len(items),
            returned=len(items),
            modality_counts=FrozenMetadata(),
            omitted_reasons=FrozenMetadata(),
            elapsed_milliseconds=1,
        ),
    )


def payload(question: str, assistant_turn_id: UUID) -> dict[str, object]:
    return {
        "notebook_id": str(NOTEBOOK_ID),
        "session_id": str(UUID(int=2)),
        "user_turn_id": str(UUID(int=3)),
        "assistant_turn_id": str(assistant_turn_id),
        "question": question,
        "provider_profile": "final_qa_v2:transport",
        "publication_policy": "require_complete",
        "evidence_request_or_snapshot": {
            "query": question,
            "mode": "ranked",
            "scope": {"notebook_id": str(NOTEBOOK_ID)},
            "representations": ["canonical_text"],
        },
    }


def fixture(answers: list[str]):  # type: ignore[no-untyped-def]
    store = Store()
    provider = Provider(answers)
    authorizer = Authorizer()
    orchestrator = FinalQAV2Orchestrator(
        store, provider, MultimodalContextBuilder(authorizer, Counter()), Counter(), authorizer
    )
    engine = SimpleNamespace(
        state=EngineState.READY,
        storage=store,
        final_qa_v2=orchestrator,
        advanced_retrieval=object(),
    )
    return engine, store, provider, authorizer


@pytest.mark.anyio
async def test_final_qa_retrieval_uses_server_owned_deadline() -> None:
    class SlowRetrieval:
        async def execute(self, plan, *, cursor=None):  # type: ignore[no-untyped-def]
            del plan, cursor
            await asyncio.sleep(0.05)

    engine = SimpleNamespace(advanced_retrieval=SlowRetrieval())
    config = ServerConfig(max_advanced_elapsed_milliseconds=1)
    service = FinalQAV2ApplicationService(engine, config)
    request = EvidenceSearchRequest.model_validate(
        payload("Deadline proof", uuid4())["evidence_request_or_snapshot"]
    )
    with pytest.raises(OperationTimeoutError, match="exceeded deadline"):
        await service._retrieval_result("Deadline proof", request)


def app_for(engine, subject: str = "anonymous") -> FastAPI:  # type: ignore[no-untyped-def]
    app = FastAPI()

    @app.middleware("http")
    async def claims(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth = {"sub": request.headers.get("x-test-sub", subject)}
        return await call_next(request)

    app.include_router(router, prefix="/v2")
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_server_config] = lambda: ServerConfig()
    register_error_handlers(app)
    return app


@pytest.mark.anyio
async def test_http_and_mcp_replay_zero_provider_calls_and_conflict(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    engine, store, provider, _ = fixture(["Grounded [source:1]"])
    question = "What is stated?"
    result = retrieval((candidate(),), question)

    async def fake_retrieval(self, query, request):  # type: ignore[no-untyped-def]
        del self, request
        return replace(
            result, query=query, query_fingerprint=hashlib.sha256(query.encode()).hexdigest()
        )

    monkeypatch.setattr(FinalQAV2ApplicationService, "_retrieval_result", fake_retrieval)
    turn_id = uuid4()
    body = payload(question, turn_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(engine)), base_url="http://test"
    ) as client:
        first = await client.post(f"/v2/notebooks/{NOTEBOOK_ID}/final-qa", json=body)
        second = await client.post(f"/v2/notebooks/{NOTEBOOK_ID}/final-qa", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["execution_id"] == second.json()["execution_id"]
    assert second.json()["replayed"] is True
    assert len(provider.requests) == 1
    assert "[source:1]" in provider.requests[0].system_prompt
    assert "[source:2]" in provider.requests[0].system_prompt

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(engine)), base_url="http://test"
    ) as client:
        unauthorized = await client.post(
            f"/v2/notebooks/{NOTEBOOK_ID}/final-qa",
            json=body,
            headers={"x-test-sub": "different-actor"},
        )
        forged = await client.post(
            f"/v2/notebooks/{NOTEBOOK_ID}/final-qa",
            json={**body, "principal_id": str(uuid4())},
        )
    assert unauthorized.status_code == 404
    assert unauthorized.json()["error"]["message"] == "authorized resource was not found"
    assert forged.status_code == 422
    assert len(provider.requests) == 1
    http_execution = store.executions[turn_id]

    mcp_first = await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    mcp_second = await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert mcp_first[0].text == mcp_second[0].text  # type: ignore[union-attr]
    mcp_payload = json.loads(mcp_first[0].text)  # type: ignore[union-attr]
    assert mcp_payload["execution_id"] == str(http_execution.execution_id)
    assert store.executions[turn_id].request_fingerprint == http_execution.request_fingerprint
    assert len(provider.requests) == 1

    changed = payload("Different question", turn_id)
    with pytest.raises(ConflictError):
        await execute_mcp_tool(engine, "run_final_qa_v2", changed, ServerConfig())
    with pytest.raises(Exception, match="principal_id"):
        await execute_mcp_tool(
            engine,
            "run_final_qa_v2",
            {**body, "principal_id": str(uuid4())},
            ServerConfig(),
        )

    execution = store.executions[turn_id]
    published_key = (execution.execution_id, FinalQAExecutionSnapshotPhase.PUBLISHED)
    store.snapshots[published_key] = SimpleNamespace(payload="{corrupt")  # type: ignore[assignment]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(engine)), base_url="http://test"
    ) as client:
        corrupt = await client.post(f"/v2/notebooks/{NOTEBOOK_ID}/final-qa", json=body)
    assert corrupt.status_code >= 400
    assert len(provider.requests) == 1


@pytest.mark.anyio
async def test_transport_citation_retry_multimodal_and_multilingual(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    engine, _, provider, _ = fixture(["Bad [Source:1]", "Fixed [source:1] [source:2]"])
    question = "मराठी आणि हिन्दी चित्राचे वर्णन करा"
    items = (
        candidate(EvidenceKindV2.ASSET_OCCURRENCE, index=1, content="मराठी चित्र"),
        candidate(EvidenceKindV2.OCR_REGION, index=2, content="हिन्दी पाठ"),
    )
    result = retrieval(items, question)

    async def fake_retrieval(self, query, request):  # type: ignore[no-untyped-def]
        del self, request
        return replace(
            result, query=query, query_fingerprint=hashlib.sha256(query.encode()).hexdigest()
        )

    monkeypatch.setattr(FinalQAV2ApplicationService, "_retrieval_result", fake_retrieval)
    body = payload(question, uuid4())
    content = await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert len(provider.requests) == 2
    assert "मराठी चित्र" in provider.requests[0].rendered_context
    assert "हिन्दी पाठ" in provider.requests[0].rendered_context
    assert "occurrence" in provider.requests[0].resource_handles[0]
    assert "citation_resolved" in content[0].text  # type: ignore[union-attr]
    await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert len(provider.requests) == 2


@pytest.mark.anyio
async def test_mcp_first_execution_and_replay_use_one_provider_call(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    engine, _, provider, _ = fixture(["Grounded [source:1]"])
    question = "MCP replay proof"
    result = retrieval((candidate(),), question)

    async def fake_retrieval(self, query, request):  # type: ignore[no-untyped-def]
        del self, request
        return replace(
            result,
            query=query,
            query_fingerprint=hashlib.sha256(query.encode()).hexdigest(),
        )

    monkeypatch.setattr(FinalQAV2ApplicationService, "_retrieval_result", fake_retrieval)
    body = payload(question, uuid4())
    first = await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert len(provider.requests) == 1
    second = await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert len(provider.requests) == 1
    first_payload = json.loads(first[0].text)  # type: ignore[union-attr]
    second_payload = json.loads(second[0].text)  # type: ignore[union-attr]
    assert first_payload["execution_id"] == second_payload["execution_id"]
    assert first_payload["answer"] == second_payload["answer"]
    assert second_payload["replayed"] is True


@pytest.mark.anyio
async def test_transport_rejects_incomplete_profile_and_unauthorized_replay(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    engine, _, provider, authorizer = fixture(["Grounded [source:1]"])
    question = "Evidence?"
    complete = retrieval((candidate(),), question)

    incomplete_state = [RetrievalCompleteness.PARTIAL]

    async def partial(self, query, request):  # type: ignore[no-untyped-def]
        del self, request
        return replace(
            complete,
            query=query,
            query_fingerprint=hashlib.sha256(query.encode()).hexdigest(),
            completeness=incomplete_state[0],
        )

    monkeypatch.setattr(FinalQAV2ApplicationService, "_retrieval_result", partial)
    for state in (
        RetrievalCompleteness.PARTIAL,
        RetrievalCompleteness.TRUNCATED,
    ):
        incomplete_state[0] = state
        body = payload(question, uuid4())
        with pytest.raises(Exception, match="complete evidence"):
            await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert not provider.requests

    body["provider_profile"] = "caller-selected:model"
    with pytest.raises(Exception, match="profile"):
        await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())

    async def complete_result(self, query, request):  # type: ignore[no-untyped-def]
        del self, request
        return replace(
            complete,
            query=query,
            query_fingerprint=hashlib.sha256(query.encode()).hexdigest(),
        )

    monkeypatch.setattr(FinalQAV2ApplicationService, "_retrieval_result", complete_result)
    body["provider_profile"] = "final_qa_v2:transport"
    await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert len(provider.requests) == 1

    authorizer.allowed = False
    with pytest.raises(IntegrityError, match="authorization denied"):
        await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert len(provider.requests) == 1

    authorizer.allowed = True
    provider.unsupported.add(EvidenceKindV2.OCR_REGION)
    ocr = retrieval((candidate(EvidenceKindV2.OCR_REGION, content="हिन्दी पाठ"),), question)

    async def unsupported_result(self, query, request):  # type: ignore[no-untyped-def]
        del self, request
        return replace(
            ocr,
            query=query,
            query_fingerprint=hashlib.sha256(query.encode()).hexdigest(),
        )

    monkeypatch.setattr(FinalQAV2ApplicationService, "_retrieval_result", unsupported_result)
    unsupported_body = payload(question, uuid4())
    with pytest.raises(Exception, match="modalities"):
        await execute_mcp_tool(engine, "run_final_qa_v2", unsupported_body, ServerConfig())
    assert len(provider.requests) == 1

    provider.unsupported.clear()
    provider.states[EvidenceKindV2.OCR_REGION] = ProviderModalityState.UNAVAILABLE
    unavailable_body = payload(question, uuid4())
    with pytest.raises(Exception, match="modalities"):
        await execute_mcp_tool(engine, "run_final_qa_v2", unavailable_body, ServerConfig())
    assert len(provider.requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "completeness",
    [
        RetrievalCompleteness.PARTIAL,
        RetrievalCompleteness.TRUNCATED,
    ],
)
async def test_partial_publication_policy_remains_truthful(
    monkeypatch, completeness: RetrievalCompleteness
) -> None:  # type: ignore[no-untyped-def]
    engine, _, provider, _ = fixture(["Grounded [source:1]"])
    question = "Bounded evidence"
    result = retrieval((candidate(),), question, completeness)

    async def fake_retrieval(self, query, request):  # type: ignore[no-untyped-def]
        del self, request
        return replace(
            result,
            query=query,
            query_fingerprint=hashlib.sha256(query.encode()).hexdigest(),
        )

    monkeypatch.setattr(FinalQAV2ApplicationService, "_retrieval_result", fake_retrieval)
    body = payload(question, uuid4())
    body["publication_policy"] = "allow_partial"
    content = await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    result_body = json.loads(content[0].text)  # type: ignore[union-attr]
    assert result_body["completeness"] == completeness.value
    assert len(provider.requests) == 1


@pytest.mark.anyio
async def test_transport_rejects_two_invalid_citation_attempts_without_replay_generation(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    engine, _, provider, _ = fixture(["Bad [Source:1]", "Still bad [SOURCE:1]"])
    question = "Citation failure"
    result = retrieval((candidate(),), question)

    async def fake_retrieval(self, query, request):  # type: ignore[no-untyped-def]
        del self, request
        return replace(
            result,
            query=query,
            query_fingerprint=hashlib.sha256(query.encode()).hexdigest(),
        )

    monkeypatch.setattr(FinalQAV2ApplicationService, "_retrieval_result", fake_retrieval)
    body = payload(question, uuid4())
    with pytest.raises(IntegrityError, match="citation_compliance"):
        await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert len(provider.requests) == 2
    with pytest.raises(IntegrityError, match="citation_compliance"):
        await execute_mcp_tool(engine, "run_final_qa_v2", body, ServerConfig())
    assert len(provider.requests) == 2


def _jwt(subject: str, secret: str, *, expires_at: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    claims = (
        base64.urlsafe_b64encode(json.dumps({"sub": subject, "exp": expires_at}).encode())
        .rstrip(b"=")
        .decode()
    )
    signature = (
        base64.urlsafe_b64encode(
            hmac.new(secret.encode(), f"{header}.{claims}".encode(), hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{claims}.{signature}"


def _production_chat_app(
    tmp_path: Path,
    operational: SQLiteFinalQAOperationalStore,
    provider: Provider,
    *,
    auth_mode: str = "api-key",
    timeout_ms: int = 180_000,
):  # type: ignore[no-untyped-def]
    class NotebookReader:
        async def get_notebook(self, notebook_id: UUID):  # type: ignore[no-untyped-def]
            return object() if notebook_id == NOTEBOOK_ID else None

    reader = NotebookReader()
    authorizer = Authorizer()
    engine = SimpleNamespace(
        state=EngineState.READY,
        certified_read_only=True,
        storage=reader,
        final_qa_v2_execution_store=operational,
        final_qa_v2=FinalQAV2Orchestrator(
            operational,
            provider,
            MultimodalContextBuilder(authorizer, Counter()),
            Counter(),
            authorizer,
        ),
    )

    async def lifecycle() -> None:
        return None

    engine.initialize = lifecycle
    engine.shutdown = lifecycle
    core = MnemoConfig.from_file(Path("mnemo.toml"))
    core = core.model_copy(
        update={
            "storage": core.storage.model_copy(
                update={
                    "sqlite": core.storage.sqlite.model_copy(
                        update={"path": tmp_path / "certified" / "corpus.db"}
                    ),
                    "filesystem": core.storage.filesystem.model_copy(
                        update={"root": tmp_path / "certified" / "blobs"}
                    ),
                }
            )
        }
    )
    engine.config = core
    config = ServerConfig(
        production_mode=True,
        auth_mode=auth_mode,
        api_key="chat-key" if auth_mode == "api-key" else None,
        jwt_secret="chat-jwt-secret-32-bytes-minimum-long" if auth_mode == "jwt" else None,
        delivery_cursor_secret="cursor-secret-32-bytes-minimum-long",
        final_qa_operational_store_path=operational.path,
        max_final_qa_elapsed_milliseconds=timeout_ms,
    )
    return create_app(
        server_config=config,
        mnemo_config=core,
        engine=engine,
        provision_tokenizer_on_startup=False,
    ), engine


@pytest.mark.anyio
@pytest.mark.parametrize("auth_mode", ["api-key", "jwt"])
async def test_production_http_chat_authentication_replay_and_isolated_store(
    tmp_path: Path, monkeypatch, auth_mode: str
) -> None:  # type: ignore[no-untyped-def]
    operational = SQLiteFinalQAOperationalStore(tmp_path / "operational" / "final_qa_v2.db")
    await operational.open()
    provider = Provider(["Grounded [source:1]"])
    app, engine = _production_chat_app(tmp_path, operational, provider, auth_mode=auth_mode)
    question = "What is stated?"
    seen_principals = []

    class AuthorizedRetrieval:
        async def execute_authorized(self, *, principal, plan, cursor=None):  # type: ignore[no-untyped-def]
            del cursor
            seen_principals.append(principal)
            assert plan.scope.notebook_id == NOTEBOOK_ID
            return SimpleNamespace(
                query_fingerprint=hashlib.sha256(question.encode()).hexdigest(),
                snapshot_identity=hashlib.sha256(b"authorized-snapshot").hexdigest(),
                completeness=RetrievalCompleteness.COMPLETE,
                examined_count=1,
                diagnostics=SimpleNamespace(elapsed_milliseconds=1),
            )

    engine.advanced_retrieval = AuthorizedRetrieval()
    monkeypatch.setattr(
        "mnemo_server.services.final_qa_v2.candidates_from_retrieval",
        lambda raw: (candidate(),),
    )
    body = payload(question, uuid4())
    credentials = (
        {"Authorization": "Bearer chat-key"}
        if auth_mode == "api-key"
        else {
            "Authorization": "Bearer "
            + _jwt(
                "chat-user",
                "chat-jwt-secret-32-bytes-minimum-long",
                expires_at=int(time.time()) + 60,
            )
        }
    )
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            path = f"/v2/notebooks/{NOTEBOOK_ID}/final-qa"
            missing = await client.post(path, json=body)
            invalid = await client.post(
                path, json=body, headers={"Authorization": "Bearer invalid"}
            )
            assert missing.status_code == invalid.status_code == 401
            if auth_mode == "jwt":
                expired = await client.post(
                    path,
                    json=body,
                    headers={
                        "Authorization": "Bearer "
                        + _jwt(
                            "chat-user",
                            "chat-jwt-secret-32-bytes-minimum-long",
                            expires_at=int(time.time()) - 100,
                        )
                    },
                )
                assert expired.status_code == 401
            for key in ("principal_id", "storage_role", "workspace_root", "database_path"):
                rejected = await client.post(
                    path, json={**body, key: "client-value"}, headers=credentials
                )
                assert rejected.status_code == 422
            wrong_path = await client.post(
                f"/v2/notebooks/{UUID(int=999)}/final-qa", json=body, headers=credentials
            )
            assert wrong_path.status_code == 422
            unknown = await client.post(
                f"/v2/notebooks/{UUID(int=999)}/final-qa",
                json={
                    **body,
                    "notebook_id": str(UUID(int=999)),
                    "evidence_request_or_snapshot": {
                        **body["evidence_request_or_snapshot"],
                        "scope": {"notebook_id": str(UUID(int=999))},
                    },
                },
                headers=credentials,
            )
            assert unknown.status_code == 404
            assert unknown.json()["error"]["message"] == "authorized resource was not found"
            first = await client.post(path, json=body, headers=credentials)
            replay = await client.post(path, json=body, headers=credentials)
            assert first.status_code == replay.status_code == 200
            assert first.json()["execution_id"] == replay.json()["execution_id"]
            assert replay.json()["replayed"] is True
            assert first.json()["citations"][0]["document_id"] == str(UUID(int=101))
            assert first.json()["snapshot_identity"]
            assert len(provider.requests) == 1
            assert len(seen_principals) == 2
            expected_subject = "api-key" if auth_mode == "api-key" else "chat-user"
            assert seen_principals[0] == principal_from_claims({"sub": expected_subject})
            if auth_mode == "jwt":
                other_actor = await client.post(
                    path,
                    json=body,
                    headers={
                        "Authorization": "Bearer "
                        + _jwt(
                            "other-chat-user",
                            "chat-jwt-secret-32-bytes-minimum-long",
                            expires_at=int(time.time()) + 60,
                        )
                    },
                )
                assert other_actor.status_code == 404
                assert other_actor.json()["error"]["message"] == (
                    "authorized resource was not found"
                )
                assert len(provider.requests) == 1
        persisted = await operational.get_final_qa_v2_execution(UUID(body["assistant_turn_id"]))
        assert persisted is not None
        assert persisted.actor_id == seen_principals[0].actor_id
        assert persisted.state is FinalQAExecutionState.PUBLISHED
        assert (tmp_path / "operational" / "final_qa_v2.db").exists()
        assert not (tmp_path / "certified" / "corpus.db").exists()
    finally:
        await operational.close()


@pytest.mark.anyio
async def test_production_http_chat_full_deadline_records_terminal_state(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    class BlockingProvider(Provider):
        async def complete(self, request):  # type: ignore[no-untyped-def]
            del request
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    operational = SQLiteFinalQAOperationalStore(tmp_path / "operational" / "final_qa_v2.db")
    await operational.open()
    # Give the replay's authorization/persistence reads room under a busy full
    # suite; the provider remains deterministically blocked until the deadline.
    app, _ = _production_chat_app(tmp_path, operational, BlockingProvider([]), timeout_ms=500)
    question = "Timed out publication"
    evidence = retrieval((candidate(),), question)

    async def authorized_retrieval(self, query, request, principal):  # type: ignore[no-untyped-def]
        del self, request, principal
        return replace(evidence, query=query)

    monkeypatch.setattr(
        FinalQAV2ApplicationService, "_retrieval_result_authorized", authorized_retrieval
    )
    body = payload(question, uuid4())
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            path = f"/v2/notebooks/{NOTEBOOK_ID}/final-qa"
            response = await client.post(
                path, json=body, headers={"Authorization": "Bearer chat-key"}
            )
            assert response.status_code == 504
            assert response.json()["error"]["code"] == "contract.timeout"
            assert response.json()["error"]["details"]["execution_id"]
            replay = await client.post(
                path, json=body, headers={"Authorization": "Bearer chat-key"}
            )
            assert replay.status_code == 409
        persisted = await operational.get_final_qa_v2_execution(UUID(body["assistant_turn_id"]))
        assert persisted is not None
        assert persisted.state is FinalQAExecutionState.TIMED_OUT
        assert persisted.failure_classification == "operation_timeout"
        assert not (tmp_path / "certified" / "corpus.db").exists()
    finally:
        await operational.close()


@pytest.mark.anyio
async def test_production_http_chat_stalled_timeout_reconciliation_fails_safely(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    class BlockingProvider(Provider):
        async def complete(self, request):  # type: ignore[no-untyped-def]
            del request
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    operational = SQLiteFinalQAOperationalStore(tmp_path / "operational" / "final_qa_v2.db")
    await operational.open()
    app, _ = _production_chat_app(tmp_path, operational, BlockingProvider([]), timeout_ms=20)
    evidence = retrieval((candidate(),), "Timeout reconciliation")

    async def authorized_retrieval(self, query, request, principal):  # type: ignore[no-untyped-def]
        del self, request, principal
        return replace(evidence, query=query)

    async def stalled_reconciliation(body, principal, store):  # type: ignore[no-untyped-def]
        del body, principal, store
        await asyncio.Event().wait()

    monkeypatch.setattr(
        FinalQAV2ApplicationService, "_retrieval_result_authorized", authorized_retrieval
    )
    monkeypatch.setattr(
        FinalQAV2ApplicationService, "_record_timeout", staticmethod(stalled_reconciliation)
    )
    monkeypatch.setattr("mnemo_server.services.final_qa_v2._TIMEOUT_RECONCILIATION_SECONDS", 0.01)
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            response = await client.post(
                f"/v2/notebooks/{NOTEBOOK_ID}/final-qa",
                json=payload("Timeout reconciliation", uuid4()),
                headers={"Authorization": "Bearer chat-key"},
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "contract.dependency_unavailable"
            assert response.json()["error"]["details"]["execution_id"]
    finally:
        await operational.close()
