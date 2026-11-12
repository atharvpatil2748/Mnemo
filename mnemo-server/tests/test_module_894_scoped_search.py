"""Internal multi-notebook fan-out, without registering a public operation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from mnemo.cursors import CursorConflictError, CursorExpiredError, CursorInvalidError
from mnemo.interfaces import (
    ConflictError,
    DependencyUnavailableError,
    NotFoundError,
    OperationTimeoutError,
    PrincipalContextV1,
)
from mnemo.interfaces.advanced_retrieval import AdvancedSourcePage
from mnemo.models import (
    AdvancedRetrievalCandidate,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    EvidenceRepresentation,
    FrozenMetadata,
    RetrievalPathEvidenceV2,
    advanced_candidate_id,
)
from mnemo.phase85.projections import ProjectionCompleteness
from mnemo.retrieval.advanced import AdvancedRetrievalService, RetrievalCursorCodec
from mnemo_server.config import ServerConfig
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchResponse
from mnemo_server.schemas.scope_contract_review import ScopeRequestReview
from mnemo_server.services import shared_search
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.scoped_search import ScopedSearchApplicationService


def _engine(tmp_path: Path) -> tuple[object, SQLiteNotebookScopeAuthority]:
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()

    async def get_notebook(value: UUID) -> object | None:
        return object()

    async def list_sources(notebook_id: UUID, limit: int, cursor: str | None) -> object:
        assert limit == 100 and cursor is None
        return SimpleNamespace(items=(), next_cursor=None)

    async def list_generations(capability: str) -> tuple[object, ...]:
        return ()

    async def get_coverage(value: UUID) -> None:
        return None

    async def get_generation_sources(value: UUID) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
        return (), ()

    retrieval = AdvancedRetrievalService(
        sources=(), cursor_codec=RetrievalCursorCodec(b"scoped-search-test-signing-secret!!")
    )
    retrieval._sources = {EvidenceRepresentation.CANONICAL_TEXT: object()}  # type: ignore[attr-defined]
    storage = SimpleNamespace(
        get_notebook=get_notebook,
        list_sources=list_sources,
        list_active_index_generations=list_generations,
        get_index_generation_coverage=get_coverage,
        get_index_generation_sources=get_generation_sources,
    )
    return SimpleNamespace(
        storage=storage, server_scope_authority=authority, advanced_retrieval=retrieval
    ), authority


def _response(
    notebook_id: UUID,
    *,
    status: str = "searched",
    matched: bool = True,
    mode: str = "ranked",
    snapshot: str = "a" * 64,
) -> EvidenceSearchResponse:
    return EvidenceSearchResponse(
        schema_version="mnemo.mcp.contract/v2",
        operation="search_evidence",
        request_id=uuid4(),
        mode=mode,
        scope={"notebook_id": str(notebook_id)},
        items=[
            {
                "candidate_id": str(uuid4()),
                "notebook_id": str(notebook_id),
                "source_id": str(uuid4()),
                "document_id": str(uuid4()),
                "version_id": str(uuid4()),
                "chunk_id": "chunk-1",
                "occurrence_id": None,
                "derivation_id": None,
                "representation": "canonical_text",
                "locator": {},
                "retrieval_paths": [{"path": "canonical", "source_rank": 1}],
            }
        ]
        if matched
        else [],
        completeness="unknown",
        coverage={
            "snapshot_identity": snapshot,
            "representations": [
                {
                    "representation": "canonical_text",
                    "status": status,
                    "returned": int(matched),
                    "reason_code": None if status == "searched" else "source_failed",
                }
            ],
        },
        omissions=[],
        limits={},
        next_cursor=None,
        recommended_next_actions=[],
        diagnostics={},
    )


@pytest.mark.anyio
async def test_full_v2_scoped_admission_uses_atomic_alias_set_not_legacy_active_generation(
    tmp_path: Path,
) -> None:
    notebook, document, text_version, no_text_version = (uuid4() for _ in range(4))
    owner = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=owner.actor_id,
        notebook_id=notebook,
        role="owner",
        operator_id=owner.actor_id,
    )
    capabilities = (
        "representation_derivation_v2",
        "language_text_v2",
        "multilingual_embedding_v2",
        "multilingual_vector_v2",
    )
    generations = tuple(uuid4() for _ in capabilities)
    alias = "a" * 64
    covered = {text_version, no_text_version}
    by_id = {
        generation_id: SimpleNamespace(
            generation_id=generation_id,
            capability=capability,
            state=SimpleNamespace(value="ready"),
            checksum="b" * 64,
            profile="isolated-test",
            model_identity="BAAI/bge-m3@revision" if index >= 2 else None,
            dimensions=1024 if index >= 2 else None,
        )
        for index, (capability, generation_id) in enumerate(
            zip(capabilities, generations, strict=True)
        )
    }

    async def list_sources(notebook_id: UUID, limit: int, cursor: str | None) -> object:
        return SimpleNamespace(
            items=(SimpleNamespace(notebook_id=notebook_id, document_id=document),),
            next_cursor=None,
        )

    async def get_document(document_id: UUID) -> object:
        return SimpleNamespace(
            versions=(
                SimpleNamespace(version_id=text_version),
                SimpleNamespace(version_id=no_text_version),
            )
        )

    async def active_alias() -> str:
        return alias

    async def active_set() -> tuple[UUID, ...]:
        return generations

    async def get_generation(generation_id: UUID) -> object:
        return by_id[generation_id]

    async def get_coverage(generation_id: UUID) -> object:
        return SimpleNamespace(
            completeness=ProjectionCompleteness.COMPLETE,
            failed_count=0,
            checksum="b" * 64,
        )

    async def get_sources(generation_id: UUID) -> tuple[tuple[()], tuple[UUID, ...]]:
        return (), tuple(covered)

    engine.full_multilingual_v2_alias_digest = alias
    engine.storage.list_sources = list_sources
    engine.storage.get_document = get_document
    engine.storage.resolve_active_multilingual_v2_alias_digest = active_alias
    engine.storage.resolve_active_multilingual_v2_generation_set = active_set
    engine.storage.get_index_generation = get_generation
    engine.storage.get_index_generation_coverage = get_coverage
    engine.storage.get_index_generation_sources = get_sources
    engine.advanced_retrieval._sources[EvidenceRepresentation.MULTILINGUAL_TEXT] = object()
    auth = shared_search.ScopedSearchAuthorization(engine)
    selected = await auth.resolve(owner, selected_notebooks=(notebook,), documents=())
    admitted = await auth.inspect_active_sources(
        selected, (EvidenceRepresentation.MULTILINGUAL_TEXT,)
    )
    assert admitted[0].status == "active"
    assert admitted[0].generation_alias == alias
    covered.remove(no_text_version)
    incomplete = await auth.inspect_active_sources(
        selected, (EvidenceRepresentation.MULTILINGUAL_TEXT,)
    )
    assert incomplete[0].status == "incomplete"
    covered.add(no_text_version)
    engine.full_multilingual_v2_alias_digest = "c" * 64
    stale = await auth.inspect_active_sources(selected, (EvidenceRepresentation.MULTILINGUAL_TEXT,))
    assert stale[0].status == "incompatible"
    authority.revoke(actor_id=owner.actor_id, notebook_id=notebook)
    with pytest.raises(NotFoundError):
        await auth.inspect_active_sources(selected, (EvidenceRepresentation.MULTILINGUAL_TEXT,))


@pytest.mark.anyio
async def test_typed_admission_covers_asset_versions_not_unrelated_text_versions(
    tmp_path: Path,
) -> None:
    notebook, document, asset_version, text_version, generation_id = (uuid4() for _ in range(5))
    owner = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=owner.actor_id,
        notebook_id=notebook,
        role="owner",
        operator_id=owner.actor_id,
    )
    covered = {asset_version}

    async def list_sources(notebook_id: UUID, limit: int, cursor: str | None) -> object:
        return SimpleNamespace(
            items=(SimpleNamespace(notebook_id=notebook_id, document_id=document),),
            next_cursor=None,
        )

    async def get_document(document_id: UUID) -> object:
        return SimpleNamespace(
            versions=(
                SimpleNamespace(version_id=asset_version),
                SimpleNamespace(version_id=text_version),
            )
        )

    async def list_asset_occurrences(version_id: UUID) -> tuple[object, ...]:
        return (
            (SimpleNamespace(version_id=version_id, occurrence_id=uuid4()),)
            if version_id == asset_version
            else ()
        )

    async def active_generations(capability: str) -> tuple[object, ...]:
        assert capability == "ocr_text"
        return (
            SimpleNamespace(
                generation_id=generation_id,
                state=SimpleNamespace(value="ready"),
                checksum="b" * 64,
                profile="ocr-test",
                model_identity="ocr@revision",
            ),
        )

    async def get_coverage(value: UUID) -> object:
        return SimpleNamespace(
            completeness=ProjectionCompleteness.COMPLETE,
            failed_count=0,
            checksum="b" * 64,
        )

    async def get_sources(value: UUID) -> tuple[tuple[()], tuple[UUID, ...]]:
        return (), tuple(covered)

    engine.storage.list_sources = list_sources
    engine.storage.get_document = get_document
    engine.storage.list_asset_occurrences = list_asset_occurrences
    engine.storage.list_active_index_generations = active_generations
    engine.storage.get_index_generation_coverage = get_coverage
    engine.storage.get_index_generation_sources = get_sources
    engine.advanced_retrieval._sources[EvidenceRepresentation.OCR_TEXT] = object()
    auth = shared_search.ScopedSearchAuthorization(engine)
    selection = await auth.resolve(owner, selected_notebooks=(notebook,))
    admitted = await auth.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    assert admitted[0].status == "active"
    covered.clear()
    incomplete = await auth.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    assert incomplete[0].status == "incomplete"


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["owner", "reader"])
async def test_ranked_fanout_uses_shared_service_and_global_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    first, second = uuid4(), uuid4()
    owner, reader = PrincipalContextV1(uuid4(), True), PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    for notebook_id in (first, second):
        authority.grant(
            actor_id=owner.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=owner.actor_id,
        )
        authority.grant(
            actor_id=reader.actor_id,
            notebook_id=notebook_id,
            role="reader",
            operator_id=owner.actor_id,
        )
    principal = owner if role == "owner" else reader
    observed: list[tuple[UUID, int, int, str | None]] = []

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            assert actor == principal
            notebook_id = body.scope.notebook_id  # type: ignore[attr-defined]
            observed.append(
                (
                    notebook_id,
                    body.candidate_budget,  # type: ignore[attr-defined]
                    body.max_serialized_bytes,  # type: ignore[attr-defined]
                    automatic_policy_version,
                )
            )
            await asyncio.sleep(0)
            return _response(notebook_id)

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    request = ScopeRequestReview(
        query="find",
        scope={"kind": "selected", "notebook_ids": (first, second)},
        limit=2,
    )
    result = await ScopedSearchApplicationService(
        engine,
        ServerConfig(),  # type: ignore[arg-type]
    ).execute_ranked(request, principal)
    assert {UUID(str(item["notebook_id"])) for item in result.items} == {first, second}
    # No-hint planning reports the four unavailable optional sources honestly.
    assert result.completeness == "partial"
    assert any("ocr_text:source_not_composed" in item for item in result.omissions)
    assert len(observed) == 2
    assert sum(item[1] for item in observed) <= result.candidate_budget
    assert sum(item[2] for item in observed) <= result.byte_budget
    assert all(item[3] and item[3].startswith("scoped-automatic/v1:") for item in observed)


@pytest.mark.anyio
async def test_fanout_denies_private_scope_and_revocation_before_disclosure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, private = uuid4(), uuid4()
    owner, reader = PrincipalContextV1(uuid4(), True), PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    for notebook_id in (first, private):
        authority.grant(
            actor_id=owner.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=owner.actor_id,
        )
    authority.grant(
        actor_id=reader.actor_id,
        notebook_id=first,
        role="reader",
        operator_id=owner.actor_id,
    )
    calls = 0

    class RevokingEvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            nonlocal calls
            calls += 1
            authority.revoke(actor_id=reader.actor_id, notebook_id=first)
            return _response(first)

    monkeypatch.setattr(
        shared_search, "EvidenceRetrievalApplicationService", RevokingEvidenceService
    )
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await service.execute_ranked(
            ScopeRequestReview(
                query="find", scope={"kind": "selected", "notebook_ids": (first, private)}
            ),
            reader,
        )
    assert calls == 0
    with pytest.raises(NotFoundError):
        await service.execute_ranked(
            ScopeRequestReview(query="find", scope={"kind": "selected", "notebook_ids": (first,)}),
            reader,
        )
    assert calls == 1


@pytest.mark.anyio
async def test_searched_zero_is_not_provider_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )
    status = "searched"

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            return _response(notebook_id, status=status, matched=False)

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    request = ScopeRequestReview(
        query="absent",
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
    )
    result = await service.execute_ranked(request, principal)
    assert result.items == ()
    assert result.completeness == "empty"
    status = "failed"
    with pytest.raises(DependencyUnavailableError):
        await service.execute_ranked(request, principal)


@pytest.mark.anyio
async def test_asset_free_partition_is_not_a_failed_typed_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset_notebook, text_only_notebook = uuid4(), uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    for notebook_id in (asset_notebook, text_only_notebook):
        authority.grant(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=principal.actor_id,
        )

    async def admission(
        self: object, selection: object, representations: object
    ) -> tuple[object, ...]:
        return (
            shared_search.ScopedRepresentationAdmission(
                asset_notebook, EvidenceRepresentation.OCR_TEXT, "active", "a" * 64, None
            ),
            shared_search.ScopedRepresentationAdmission(
                text_only_notebook,
                EvidenceRepresentation.OCR_TEXT,
                "not_applicable",
                None,
                "scope_has_no_asset_occurrences",
            ),
        )

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            assert body.scope.notebook_id == asset_notebook  # type: ignore[attr-defined]
            return _response(asset_notebook)

    monkeypatch.setattr(
        shared_search.ScopedSearchAuthorization, "inspect_active_sources", admission
    )
    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    result = await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(  # type: ignore[arg-type]
        ScopeRequestReview(
            query="ocr term",
            scope={"kind": "selected", "notebook_ids": (asset_notebook, text_only_notebook)},
            representations=(EvidenceRepresentation.OCR_TEXT,),
        ),
        principal,
    )
    assert result.omissions == ()
    assert result.completeness != "partial"


@pytest.mark.anyio
async def test_empty_all_authorized_never_searches_global_storage(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    principal = PrincipalContextV1(uuid4(), True)
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await service.execute_ranked(
            ScopeRequestReview(query="find", scope={"kind": "all_authorized"}),
            principal,
        )


@pytest.mark.anyio
async def test_unavailable_representation_is_reported_without_global_fallback(
    tmp_path: Path,
) -> None:
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    owner_id = uuid4()
    authority.grant(
        actor_id=owner_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=owner_id,
    )
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner_id,
    )
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    base = ScopeRequestReview(
        query="find",
        scope={"kind": "all_authorized"},
        representations=(EvidenceRepresentation.OCR_TEXT,),
    )
    with pytest.raises(DependencyUnavailableError):
        await service.execute_ranked(base, principal)
    traversed = await service.execute_traversal(
        base.model_copy(update={"mode": "traversal"}), principal
    )
    assert traversed.items == () and traversed.next_cursor is None
    assert traversed.completeness == "partial"
    assert any("no_admitted_source" in item for item in traversed.omissions)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "config",
    [
        ServerConfig(max_advanced_candidate_budget=1),
        ServerConfig(max_advanced_response_bytes=256),
        ServerConfig(max_advanced_content_characters=1),
    ],
)
async def test_fanout_rejects_budget_multiplication_before_provider_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: ServerConfig
) -> None:
    notebooks = (uuid4(), uuid4())
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    for notebook_id in notebooks:
        authority.grant(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=principal.actor_id,
        )

    class ForbiddenEvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            raise AssertionError("provider must not be constructed")

    monkeypatch.setattr(
        shared_search, "EvidenceRetrievalApplicationService", ForbiddenEvidenceService
    )
    with pytest.raises(DependencyUnavailableError):
        await ScopedSearchApplicationService(engine, config).execute_ranked(  # type: ignore[arg-type]
            ScopeRequestReview(
                query="find",
                scope={"kind": "selected", "notebook_ids": notebooks},
                representations=(EvidenceRepresentation.CANONICAL_TEXT,),
            ),
            principal,
        )


@pytest.mark.anyio
async def test_aggregate_rejects_wrong_mode_partition_count_and_candidate_budget(
    tmp_path: Path,
) -> None:
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    one = uuid4()
    request = ScopeRequestReview(
        query="find",
        scope={"kind": "selected", "notebook_ids": (one,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
    )
    with pytest.raises(ValueError):
        await service.execute_traversal(request, principal)
    with pytest.raises(ValueError):
        await service.execute_ranked(request.model_copy(update={"mode": "traversal"}), principal)
    notebooks = tuple(uuid4() for _ in range(17))
    for notebook_id in notebooks:
        authority.grant(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=principal.actor_id,
        )
    too_many = request.model_copy(
        update={
            "mode": "traversal",
            "scope": request.scope.model_copy(update={"notebook_ids": notebooks}),
        }
    )
    with pytest.raises(DependencyUnavailableError, match="partition count"):
        await service.execute_traversal(too_many, principal)
    small = ScopedSearchApplicationService(
        engine,
        ServerConfig(max_advanced_candidate_budget=1),  # type: ignore[arg-type]
    )
    two = request.model_copy(
        update={
            "mode": "traversal",
            "scope": request.scope.model_copy(update={"notebook_ids": notebooks[:2]}),
        }
    )
    with pytest.raises(DependencyUnavailableError, match="candidate budget"):
        await small.execute_traversal(two, principal)
    tiny_bytes = ScopedSearchApplicationService(
        engine,
        ServerConfig(max_advanced_response_bytes=256),  # type: ignore[arg-type]
    )
    with pytest.raises(DependencyUnavailableError, match="byte budget"):
        await tiny_bytes.execute_traversal(two, principal)


@pytest.mark.anyio
async def test_ranked_rejects_generation_change_and_oversized_child_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )
    change_admission = False
    return_two = False

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            if change_admission:
                engine.advanced_retrieval._sources.clear()  # type: ignore[attr-defined]
            result = _response(notebook_id)
            if return_two:
                result.items.append(dict(result.items[0]))
            return result

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    request = ScopeRequestReview(
        query="find",
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
    )
    tiny = ScopedSearchApplicationService(
        engine,
        ServerConfig(max_advanced_response_bytes=256),  # type: ignore[arg-type]
    )
    with pytest.raises(DependencyUnavailableError, match="one evidence item"):
        await tiny.execute_ranked(request, principal)
    return_two = True
    bounded = await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(  # type: ignore[arg-type]
        request.model_copy(update={"limit": 1}), principal
    )
    assert len(bounded.items) == 1
    assert bounded.completeness == "partial"
    assert "global_result_budget" in bounded.omissions
    change_admission = True
    with pytest.raises(NotFoundError):
        await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(  # type: ignore[arg-type]
            request, principal
        )


@pytest.mark.anyio
async def test_fanout_has_bounded_parallelism_and_cancels_at_global_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebooks = tuple(uuid4() for _ in range(6))
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    for notebook_id in notebooks:
        authority.grant(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=principal.actor_id,
        )
    active = 0
    peak = 0
    entered = asyncio.Event()
    released = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingEvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            if peak == 4:
                entered.set()
            try:
                await released.wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            finally:
                active -= 1
            return _response(body.scope.notebook_id)  # type: ignore[attr-defined]

    monkeypatch.setattr(
        shared_search, "EvidenceRetrievalApplicationService", BlockingEvidenceService
    )
    request = ScopeRequestReview(
        query="find",
        scope={"kind": "selected", "notebook_ids": notebooks},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
    )
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    pending = asyncio.create_task(service.execute_ranked(request, principal))
    await asyncio.wait_for(entered.wait(), timeout=5)
    assert peak == 4 and active == 4
    released.set()
    result = await pending
    assert len(result.items) == 6
    assert peak == 4 and active == 0

    entered.clear()
    released.clear()
    timed = ScopedSearchApplicationService(
        engine,
        ServerConfig(max_advanced_elapsed_milliseconds=100),  # type: ignore[arg-type]
    )
    with pytest.raises(OperationTimeoutError):
        await timed.execute_ranked(request, principal)
    assert cancelled.is_set()
    assert active == 0


@pytest.mark.anyio
async def test_partition_failure_is_partial_but_cross_scope_results_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = uuid4(), uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    for notebook_id in (first, second):
        authority.grant(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=principal.actor_id,
        )
    bad_scope = False

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            if body.scope.notebook_id == first:  # type: ignore[attr-defined]
                raise DependencyUnavailableError("source failed")
            result = _response(second, matched=True)
            if bad_scope:
                result.items[0]["notebook_id"] = str(first)
            return result

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    request = ScopeRequestReview(
        query="find",
        scope={"kind": "selected", "notebook_ids": (first, second)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
    )
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    result = await service.execute_ranked(request, principal)
    assert result.completeness == "partial"
    assert any("partition_execution_failed" in item for item in result.omissions)
    assert UUID(str(result.items[0]["notebook_id"])) == second
    bad_scope = True
    with pytest.raises(NotFoundError):
        await service.execute_ranked(request, principal)


@pytest.mark.anyio
async def test_exact_document_versions_are_separate_provider_partitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook_id, other_notebook = uuid4(), uuid4()
    pairs = ((uuid4(), uuid4()), (uuid4(), uuid4()), (uuid4(), uuid4()))
    notebook_for_document = {
        pairs[0][0]: notebook_id,
        pairs[1][0]: notebook_id,
        pairs[2][0]: other_notebook,
    }
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=other_notebook,
        role="owner",
        operator_id=principal.actor_id,
    )

    async def get_document(document_id: UUID) -> object | None:
        return next(
            (
                SimpleNamespace(versions=(SimpleNamespace(version_id=version_id),))
                for candidate_id, version_id in pairs
                if candidate_id == document_id
            ),
            None,
        )

    async def list_sources_for_document(document_id: UUID) -> tuple[object, ...]:
        return (
            (SimpleNamespace(notebook_id=notebook_for_document[document_id], source_id=uuid4()),)
            if document_id in notebook_for_document
            else ()
        )

    engine.storage.get_document = get_document  # type: ignore[attr-defined]
    engine.storage.list_sources_for_document = list_sources_for_document  # type: ignore[attr-defined]
    observed: list[tuple[tuple[UUID, ...], tuple[UUID, ...]]] = []
    forged_document = False

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            scoped = body.scope  # type: ignore[attr-defined]
            observed.append((scoped.document_ids, scoped.version_ids))
            result = _response(scoped.notebook_id)
            result.items[0]["document_id"] = str(
                uuid4() if forged_document else scoped.document_ids[0]
            )
            result.items[0]["version_id"] = str(scoped.version_ids[0])
            return result

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    request = ScopeRequestReview(
        query="find",
        scope={"kind": "selected", "notebook_ids": (notebook_id, other_notebook)},
        documents=[
            {
                "notebook_id": notebook_for_document[document_id],
                "document_id": document_id,
                "version_id": version_id,
            }
            for document_id, version_id in pairs
        ],
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        limit=2,
    )
    result = await service.execute_ranked(request, principal)
    assert set(observed) == {((document_id,), (version_id,)) for document_id, version_id in pairs}
    assert {UUID(str(item["notebook_id"])) for item in result.items} == {
        notebook_id,
        other_notebook,
    }
    all_results = await service.execute_ranked(request.model_copy(update={"limit": 3}), principal)
    assert {
        (UUID(str(item["document_id"])), UUID(str(item["version_id"])))
        for item in all_results.items
    } == set(pairs)
    forged_document = True
    with pytest.raises(NotFoundError):
        await service.execute_ranked(request, principal)


@pytest.mark.anyio
async def test_aggregate_traversal_replays_each_exact_document_partition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook_id = uuid4()
    pairs = ((uuid4(), uuid4()), (uuid4(), uuid4()))
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )

    async def get_document(document_id: UUID) -> object | None:
        return next(
            (
                SimpleNamespace(versions=(SimpleNamespace(version_id=version_id),))
                for candidate_id, version_id in pairs
                if candidate_id == document_id
            ),
            None,
        )

    async def list_sources_for_document(document_id: UUID) -> tuple[object, ...]:
        return (
            (SimpleNamespace(notebook_id=notebook_id, source_id=uuid4()),)
            if document_id in {item[0] for item in pairs}
            else ()
        )

    engine.storage.get_document = get_document  # type: ignore[attr-defined]
    engine.storage.list_sources_for_document = list_sources_for_document  # type: ignore[attr-defined]
    observed: list[tuple[UUID, UUID]] = []

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            scoped = body.scope  # type: ignore[attr-defined]
            pair = (scoped.document_ids[0], scoped.version_ids[0])
            observed.append(pair)
            result = _response(notebook_id, mode="exhaustive")
            result.items[0]["document_id"] = str(pair[0])
            result.items[0]["version_id"] = str(pair[1])
            return result

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    request = ScopeRequestReview(
        query="find",
        mode="traversal",
        limit=1,
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        documents=[
            {"notebook_id": notebook_id, "document_id": document_id, "version_id": version_id}
            for document_id, version_id in pairs
        ],
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
    )
    first = await service.execute_traversal(request, principal)
    assert len(first.items) == 1 and first.next_cursor is not None
    second = await service.execute_traversal(
        request.model_copy(update={"cursor": first.next_cursor}), principal
    )
    assert len(second.items) == 1 and second.next_cursor is None
    assert second.completeness == "complete"
    assert len(observed) == 4
    assert set(observed[:2]) == set(pairs)
    assert set(observed[2:]) == set(pairs)


@pytest.mark.anyio
async def test_real_shared_retriever_preserves_shared_document_memberships(tmp_path: Path) -> None:
    first, second, document_id, version_id = (uuid4() for _ in range(4))
    source_a, source_b = uuid4(), uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    for notebook_id in (first, second):
        authority.grant(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=principal.actor_id,
        )
    chunk = Chunk(
        id="a" * 64,
        document_id=document_id,
        version_id=version_id,
        text="shared document evidence",
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0, page_number=1),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
        metadata=FrozenMetadata(),
    )
    candidate_id = advanced_candidate_id(
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        document_id=document_id,
        version_id=version_id,
        chunk_id=chunk.id,
        occurrence_id=None,
        derivation_id=None,
    )
    candidates = {
        notebook_id: AdvancedRetrievalCandidate(
            candidate_id=candidate_id,
            notebook_id=notebook_id,
            source_id=source_id,
            document_id=document_id,
            version_id=version_id,
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            chunk=chunk,
            occurrence_id=None,
            derivation_id=None,
            locator=FrozenMetadata({"page_number": 1}),
            document_title="Shared",
            content=chunk.text,
            paths=(
                RetrievalPathEvidenceV2(
                    path="test-canonical",
                    source_rank=1,
                    source_score=None,
                    title_match=False,
                ),
            ),
        )
        for notebook_id, source_id in ((first, source_a), (second, source_b))
    }

    class CanonicalSource:
        representation = EvidenceRepresentation.CANONICAL_TEXT

        async def retrieve(self, plan: object, *, offset: int, limit: int) -> AdvancedSourcePage:
            notebook_id = plan.scope.notebook_id  # type: ignore[attr-defined]
            values = (candidates[notebook_id],) if offset == 0 else ()
            return AdvancedSourcePage(
                representation=self.representation,
                snapshot_identity="a" * 64,
                candidates=values,
                examined=len(values),
                next_offset=None,
                exhausted=True,
            )

        async def expand(self, plan: object, seeds: object, *, limit: int) -> tuple[()]:
            return ()

    async def get_notebook(value: UUID) -> object | None:
        return object() if value in (first, second) else None

    async def get_document(value: UUID) -> object | None:
        return (
            SimpleNamespace(versions=(SimpleNamespace(version_id=version_id),))
            if value == document_id
            else None
        )

    async def list_sources_for_document(value: UUID) -> tuple[object, ...]:
        return (
            (
                SimpleNamespace(notebook_id=first, source_id=source_a),
                SimpleNamespace(notebook_id=second, source_id=source_b),
            )
            if value == document_id
            else ()
        )

    async def list_sources(notebook_id: UUID, limit: int, cursor: str | None) -> object:
        association = source_a if notebook_id == first else source_b
        return SimpleNamespace(
            items=(
                SimpleNamespace(
                    notebook_id=notebook_id, document_id=document_id, source_id=association
                ),
            ),
            next_cursor=None,
        )

    async def active_generations(capability: str) -> tuple[object, ...]:
        return ()

    async def get_coverage(value: UUID) -> None:
        return None

    async def generation_sources(value: UUID) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
        return (), ()

    storage = SimpleNamespace(
        get_notebook=get_notebook,
        get_document=get_document,
        list_sources_for_document=list_sources_for_document,
        list_sources=list_sources,
        list_active_index_generations=active_generations,
        get_index_generation_coverage=get_coverage,
        get_index_generation_sources=generation_sources,
    )
    retrieval = AdvancedRetrievalService(
        sources=(CanonicalSource(),),  # type: ignore[arg-type]
        cursor_codec=RetrievalCursorCodec(b"shared-membership-cursor-secret-32!!"),
    )
    engine = SimpleNamespace(
        storage=storage, server_scope_authority=authority, advanced_retrieval=retrieval
    )
    result = await ScopedSearchApplicationService(
        engine,
        ServerConfig(),  # type: ignore[arg-type]
    ).execute_ranked(
        ScopeRequestReview(
            query="shared",
            scope={"kind": "selected", "notebook_ids": (first, second)},
            representations=(EvidenceRepresentation.CANONICAL_TEXT,),
            limit=2,
        ),
        principal,
    )
    assert len(result.items) == 2
    assert {item["notebook_id"] for item in result.items} == {str(first), str(second)}
    assert {item["candidate_id"] for item in result.items} == {str(candidate_id)}
    assert {item["source_id"] for item in result.items} == {str(source_a), str(source_b)}


@pytest.mark.anyio
async def test_real_no_hint_search_continues_after_canonical_zero_to_admitted_ocr(
    tmp_path: Path,
) -> None:
    notebook_id, document_id, version_id, source_id, occurrence_id, generation_id = (
        uuid4() for _ in range(6)
    )
    principal = PrincipalContextV1(uuid4(), True)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )
    candidate = AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.OCR_TEXT,
            document_id=document_id,
            version_id=version_id,
            chunk_id=None,
            occurrence_id=occurrence_id,
            derivation_id=None,
        ),
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        representation=EvidenceRepresentation.OCR_TEXT,
        chunk=None,
        occurrence_id=occurrence_id,
        derivation_id=None,
        locator=FrozenMetadata({"generation_id": str(generation_id)}),
        document_title=None,
        content="text only visible in OCR",
        paths=(
            RetrievalPathEvidenceV2(
                path="test-ocr", source_rank=1, source_score=None, title_match=False
            ),
        ),
    )

    class Source:
        def __init__(self, representation: EvidenceRepresentation) -> None:
            self.representation = representation

        async def retrieve(self, plan: object, *, offset: int, limit: int) -> AdvancedSourcePage:
            assert plan.scope.notebook_id == notebook_id  # type: ignore[attr-defined]
            candidates = (
                (candidate,)
                if self.representation is EvidenceRepresentation.OCR_TEXT and offset == 0
                else ()
            )
            return AdvancedSourcePage(
                representation=self.representation,
                snapshot_identity="a" * 64,
                candidates=candidates,
                examined=len(candidates),
                next_offset=None,
                exhausted=True,
            )

        async def expand(self, plan: object, seeds: object, *, limit: int) -> tuple[()]:
            return ()

    async def get_notebook(value: UUID) -> object | None:
        return object() if value == notebook_id else None

    async def get_document(value: UUID) -> object | None:
        return (
            SimpleNamespace(versions=(SimpleNamespace(version_id=version_id),))
            if value == document_id
            else None
        )

    async def list_sources(notebook: UUID, limit: int, cursor: str | None) -> object:
        return SimpleNamespace(
            items=(SimpleNamespace(notebook_id=notebook, document_id=document_id),),
            next_cursor=None,
        )

    async def list_sources_for_document(value: UUID) -> tuple[object, ...]:
        return (
            (SimpleNamespace(notebook_id=notebook_id, source_id=source_id),)
            if value == document_id
            else ()
        )

    async def list_generations(capability: str) -> tuple[object, ...]:
        return (
            (
                SimpleNamespace(
                    generation_id=generation_id,
                    profile="ocr-test",
                    model_identity="ocr-model",
                    state=SimpleNamespace(value="ready"),
                    checksum="b" * 64,
                ),
            )
            if capability == "ocr_text"
            else ()
        )

    async def get_coverage(value: UUID) -> object | None:
        return SimpleNamespace(
            completeness=ProjectionCompleteness.COMPLETE,
            failed_count=0,
            checksum="b" * 64,
        )

    async def generation_sources(value: UUID) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
        return (), (version_id,)

    async def list_asset_occurrences(value: UUID) -> tuple[object, ...]:
        assert value == version_id
        return (SimpleNamespace(version_id=version_id, occurrence_id=occurrence_id),)

    engine = SimpleNamespace(
        storage=SimpleNamespace(
            get_notebook=get_notebook,
            get_document=get_document,
            list_sources=list_sources,
            list_sources_for_document=list_sources_for_document,
            list_active_index_generations=list_generations,
            get_index_generation_coverage=get_coverage,
            get_index_generation_sources=generation_sources,
            list_asset_occurrences=list_asset_occurrences,
        ),
        server_scope_authority=authority,
        advanced_retrieval=AdvancedRetrievalService(
            sources=(
                Source(EvidenceRepresentation.CANONICAL_TEXT),
                Source(EvidenceRepresentation.OCR_TEXT),
            ),  # type: ignore[arg-type]
            cursor_codec=RetrievalCursorCodec(b"no-hint-derived-source-test-secret-32!!"),
        ),
    )
    result = await ScopedSearchApplicationService(engine, ServerConfig()).execute_ranked(  # type: ignore[arg-type]
        ScopeRequestReview(
            query="text in picture",
            scope={"kind": "selected", "notebook_ids": (notebook_id,)},
            limit=1,
        ),
        principal,
    )
    assert len(result.items) == 1
    assert result.items[0]["representation"] == "ocr_text"
    assert result.items[0]["occurrence_id"] == str(occurrence_id)
    assert result.items[0]["locator"]["generation_id"] == str(generation_id)
    assert result.completeness == "partial"  # other optional sources were not admitted


@pytest.mark.anyio
async def test_real_aggregate_cursor_reauthorizes_and_rejects_replay(tmp_path: Path) -> None:
    notebook_id, document_id, version_id, source_id = (uuid4() for _ in range(4))
    owner, reader = PrincipalContextV1(uuid4(), True), PrincipalContextV1(uuid4(), True)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    authority.grant(
        actor_id=owner.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=owner.actor_id,
    )
    authority.grant(
        actor_id=reader.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    candidates = []
    for index in range(3):
        chunk = Chunk(
            id=f"{index + 1:064x}",
            document_id=document_id,
            version_id=version_id,
            text=f"evidence {index}",
            chunk_type=ChunkType.PASSAGE,
            position=ChunkPosition(section_index=0, chunk_index_in_section=index, page_number=1),
            source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
            heading_path=(),
            metadata=FrozenMetadata(),
        )
        candidates.append(
            AdvancedRetrievalCandidate(
                candidate_id=advanced_candidate_id(
                    representation=EvidenceRepresentation.CANONICAL_TEXT,
                    document_id=document_id,
                    version_id=version_id,
                    chunk_id=chunk.id,
                    occurrence_id=None,
                    derivation_id=None,
                ),
                notebook_id=notebook_id,
                source_id=source_id,
                document_id=document_id,
                version_id=version_id,
                representation=EvidenceRepresentation.CANONICAL_TEXT,
                chunk=chunk,
                occurrence_id=None,
                derivation_id=None,
                locator=FrozenMetadata(),
                document_title=None,
                content=chunk.text,
                paths=(
                    RetrievalPathEvidenceV2(
                        path="stable-canonical",
                        source_rank=index + 1,
                        source_score=None,
                        title_match=False,
                    ),
                ),
            )
        )

    class CanonicalSource:
        representation = EvidenceRepresentation.CANONICAL_TEXT
        snapshot_identity = "a" * 64

        async def retrieve(self, plan: object, *, offset: int, limit: int) -> AdvancedSourcePage:
            assert plan.scope.notebook_id == notebook_id  # type: ignore[attr-defined]
            selected = tuple(candidates[offset : offset + limit])
            next_offset = (
                offset + len(selected) if offset + len(selected) < len(candidates) else None
            )
            return AdvancedSourcePage(
                representation=self.representation,
                snapshot_identity=self.snapshot_identity,
                candidates=selected,
                examined=len(selected),
                next_offset=next_offset,
                exhausted=next_offset is None,
            )

        async def expand(self, plan: object, seeds: object, *, limit: int) -> tuple[()]:
            return ()

    source = CanonicalSource()

    async def get_notebook(value: UUID) -> object | None:
        return object() if value == notebook_id else None

    async def get_document(value: UUID) -> object | None:
        return (
            SimpleNamespace(versions=(SimpleNamespace(version_id=version_id),))
            if value == document_id
            else None
        )

    async def list_sources_for_document(value: UUID) -> tuple[object, ...]:
        return (
            (SimpleNamespace(notebook_id=notebook_id, source_id=source_id),)
            if value == document_id
            else ()
        )

    async def list_sources(value: UUID, limit: int, cursor: str | None) -> object:
        return SimpleNamespace(
            items=(SimpleNamespace(notebook_id=value, document_id=document_id),),
            next_cursor=None,
        )

    async def active_generations(capability: str) -> tuple[object, ...]:
        return ()

    async def get_coverage(value: UUID) -> None:
        return None

    async def generation_sources(value: UUID) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
        return (), ()

    engine = SimpleNamespace(
        storage=SimpleNamespace(
            get_notebook=get_notebook,
            get_document=get_document,
            list_sources_for_document=list_sources_for_document,
            list_sources=list_sources,
            list_active_index_generations=active_generations,
            get_index_generation_coverage=get_coverage,
            get_index_generation_sources=generation_sources,
        ),
        server_scope_authority=authority,
        advanced_retrieval=AdvancedRetrievalService(
            sources=(source,),  # type: ignore[arg-type]
            cursor_codec=RetrievalCursorCodec(b"child-cursor-secret-for-scoped-v2!!"),
        ),
        full_multilingual_v2_alias_digest=None,
    )
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    request = ScopeRequestReview(
        query="evidence",
        mode="traversal",
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        limit=1,
    )
    first = await service.execute_traversal(request, reader)
    assert first.completeness == "truncated" and first.next_cursor is not None
    assert first.items[0]["content"] == "evidence 0"
    second = await service.execute_traversal(
        request.model_copy(update={"cursor": first.next_cursor}), reader
    )
    assert second.items[0]["content"] == "evidence 1"
    assert second.next_cursor is not None
    for changed in (
        {"query": "different", "cursor": first.next_cursor},
        {"limit": 2, "cursor": first.next_cursor},
        {"representations": (EvidenceRepresentation.OCR_TEXT,), "cursor": first.next_cursor},
    ):
        with pytest.raises(CursorConflictError):
            await service.execute_traversal(request.model_copy(update=changed), reader)
    with pytest.raises(CursorInvalidError):
        await service.execute_traversal(
            request.model_copy(update={"cursor": first.next_cursor[:-1] + "x"}), reader
        )
    with pytest.raises(CursorConflictError):
        await service.execute_traversal(
            request.model_copy(update={"cursor": first.next_cursor}), owner
        )
    service._cursor._clock = lambda: datetime.now(UTC) + timedelta(hours=1)
    with pytest.raises(CursorExpiredError):
        await service.execute_traversal(
            request.model_copy(update={"cursor": first.next_cursor}), reader
        )
    service._cursor._clock = lambda: datetime.now(UTC)
    source.snapshot_identity = "b" * 64
    with pytest.raises(ConflictError):
        await service.execute_traversal(
            request.model_copy(update={"cursor": first.next_cursor}), reader
        )
    source.snapshot_identity = "a" * 64
    authority.revoke(actor_id=reader.actor_id, notebook_id=notebook_id)
    with pytest.raises(NotFoundError):
        await service.execute_traversal(
            request.model_copy(update={"cursor": first.next_cursor}), reader
        )


@pytest.mark.anyio
async def test_completed_partition_snapshot_is_replayed_before_next_notebook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = sorted((uuid4(), uuid4()), key=str)
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    for notebook_id in (first, second):
        authority.grant(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=principal.actor_id,
        )
    snapshots = {first: "a" * 64, second: "b" * 64}
    seen: list[UUID] = []
    reopen_completed = False

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            notebook_id = body.scope.notebook_id  # type: ignore[attr-defined]
            seen.append(notebook_id)
            result = _response(notebook_id, mode="exhaustive", snapshot=snapshots[notebook_id])
            if reopen_completed and notebook_id == first:
                result.next_cursor = "unexpected-reopened-partition"
            return result

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    request = ScopeRequestReview(
        query="find",
        mode="traversal",
        scope={"kind": "selected", "notebook_ids": (first, second)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        limit=1,
    )
    page = await service.execute_traversal(request, principal)
    assert page.next_cursor is not None and seen == [first, second]
    snapshots[first] = "c" * 64
    with pytest.raises(CursorConflictError):
        await service.execute_traversal(
            request.model_copy(update={"cursor": page.next_cursor}), principal
        )
    assert seen == [first, second, first]
    snapshots[first] = "a" * 64
    reopen_completed = True
    with pytest.raises(CursorConflictError, match="completed aggregate partition changed"):
        await service.execute_traversal(
            request.model_copy(update={"cursor": page.next_cursor}), principal
        )
    reopen_completed = False
    terminal = await service.execute_traversal(
        request.model_copy(update={"cursor": page.next_cursor}), principal
    )
    assert terminal.next_cursor is None
    assert terminal.items[0]["notebook_id"] == str(second)
    assert seen == [first, second, first, first, first, second]


@pytest.mark.anyio
async def test_aggregate_traversal_rotates_partitions_before_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = sorted((uuid4(), uuid4()), key=str)
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    for notebook_id in (first, second):
        authority.grant(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=principal.actor_id,
        )
    snapshots = {first: "a" * 64, second: "b" * 64}

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            notebook_id = body.scope.notebook_id  # type: ignore[attr-defined]
            offset = int(body.cursor) if body.cursor is not None else 0  # type: ignore[attr-defined]
            response = _response(notebook_id, mode="exhaustive", snapshot=snapshots[notebook_id])
            response.items[0]["chunk_id"] = f"chunk-{offset}"
            response.next_cursor = str(offset + 1) if offset < 2 else None
            return response

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    request = ScopeRequestReview(
        query="find",
        mode="traversal",
        limit=1,
        scope={"kind": "selected", "notebook_ids": (first, second)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
    )
    seen: list[UUID] = []
    for page_index in range(4):
        if page_index == 1:
            snapshots[second] = "c" * 64
            with pytest.raises(CursorConflictError):
                await service.execute_traversal(request, principal)
            snapshots[second] = "b" * 64
        page = await service.execute_traversal(request, principal)
        assert len(page.items) == 1
        seen.append(UUID(str(page.items[0]["notebook_id"])))
        assert page.next_cursor is not None
        request = request.model_copy(update={"cursor": page.next_cursor})
    assert seen == [first, second, first, second]
    monkeypatch.setattr(service._cursor, "encode", lambda **_kwargs: "x" * 8193)
    with pytest.raises(DependencyUnavailableError, match="cursor exceeds bounded"):
        await service.execute_traversal(request.model_copy(update={"cursor": None}), principal)


@pytest.mark.anyio
async def test_aggregate_continuation_rejects_changed_provider_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )
    provider_status = "searched"

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            result = _response(
                notebook_id,
                mode="exhaustive",
                status=provider_status,
                matched=provider_status == "searched",
            )
            result.next_cursor = "opaque-child" if body.cursor is None else None  # type: ignore[attr-defined]
            return result

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    request = ScopeRequestReview(
        query="find",
        mode="traversal",
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        limit=1,
    )
    first = await service.execute_traversal(request, principal)
    assert first.next_cursor is not None
    provider_status = "failed"
    with pytest.raises(CursorConflictError):
        await service.execute_traversal(
            request.model_copy(update={"cursor": first.next_cursor}), principal
        )


@pytest.mark.anyio
async def test_aggregate_traversal_fails_closed_on_snapshot_scope_budget_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )
    failure = "snapshot"

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            if failure == "timeout":
                await asyncio.sleep(1)
            result = _response(
                notebook_id,
                mode="exhaustive",
                snapshot="not-a-digest" if failure == "snapshot" else "a" * 64,
            )
            if failure == "scope":
                result.items[0]["notebook_id"] = str(uuid4())
            if failure == "admission":
                engine.advanced_retrieval._sources.clear()  # type: ignore[attr-defined]
            return result

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    request = ScopeRequestReview(
        query="find",
        mode="traversal",
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        limit=1,
    )
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    with pytest.raises(CursorInvalidError):
        await service.execute_traversal(request, principal)
    failure = "scope"
    with pytest.raises(NotFoundError):
        await service.execute_traversal(request, principal)
    failure = "bytes"
    tiny = ScopedSearchApplicationService(
        engine,
        ServerConfig(max_advanced_response_bytes=256),  # type: ignore[arg-type]
    )
    with pytest.raises(DependencyUnavailableError, match="byte budget"):
        await tiny.execute_traversal(request, principal)
    failure = "timeout"
    timed = ScopedSearchApplicationService(
        engine,
        ServerConfig(max_advanced_elapsed_milliseconds=100),  # type: ignore[arg-type]
    )
    with pytest.raises(OperationTimeoutError):
        await timed.execute_traversal(request, principal)
    failure = "admission"
    with pytest.raises(CursorConflictError, match="admission"):
        await service.execute_traversal(request, principal)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "corrupt",
    (
        {"next_index": True},
        {"next_index": 1},
        {"states": []},
        {"states": {}},
        {"omissions": "not-a-list"},
        {"omissions": [42]},
        {"state": []},
        {"state": {"done": "yes"}},
        {"state": {"excluded": True, "done": True, "cursor": "extra"}},
        {"state": {"done": False, "snapshot": 42, "status_digest": "a"}},
        {"state": {"done": False, "snapshot": "a", "status_digest": 42}},
        {"state": {"done": False, "snapshot": "a", "status_digest": "b", "cursor": 42}},
        {"state": {"done": True, "snapshot": "a", "status_digest": "b", "last_cursor": 42}},
        {"state": {"done": True, "snapshot": "a", "status_digest": "b", "cursor": "child"}},
        {"state": {"done": False, "snapshot": "a", "status_digest": "b", "last_cursor": "child"}},
    ),
)
async def test_aggregate_cursor_rejects_corrupt_signed_partition_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corrupt: dict[str, object]
) -> None:
    """Even a signed cursor with inconsistent internal state cannot resume."""
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )
    service = ScopedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    key = str(notebook_id)
    state: object = {
        "done": False,
        "snapshot": "a" * 64,
        "status_digest": "b" * 64,
        "cursor": None,
    }
    if "state" in corrupt:
        state = corrupt["state"]
    position: dict[str, object] = {
        "next_index": 0,
        "states": {key: state},
        "omissions": [],
    }
    position.update({name: value for name, value in corrupt.items() if name != "state"})
    monkeypatch.setattr(
        service._cursor, "decode", lambda *_args, **_kwargs: SimpleNamespace(position=position)
    )
    request = ScopeRequestReview(
        query="find",
        mode="traversal",
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        limit=1,
        cursor="signed-but-internally-corrupt",
    )
    with pytest.raises(CursorInvalidError):
        await service.execute_traversal(request, principal)


@pytest.mark.anyio
async def test_traversal_reports_unadmitted_partition_without_searching_it(tmp_path: Path) -> None:
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=principal.actor_id,
    )
    engine.advanced_retrieval._sources.clear()  # type: ignore[attr-defined]
    request = ScopeRequestReview(
        query="find",
        mode="traversal",
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        limit=1,
    )
    result = await ScopedSearchApplicationService(engine, ServerConfig()).execute_traversal(  # type: ignore[arg-type]
        request, principal
    )
    assert result.items == ()
    assert result.next_cursor is None
    assert result.completeness == "partial"
    assert result.omissions == (f"{notebook_id}:no_admitted_source",)


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ("two_items", "stuck_cursor", "response_bytes", "omission"))
async def test_traversal_rejects_invalid_child_pages_and_reports_omissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    engine, authority = _engine(tmp_path)
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(
            self, body: object, actor: object, *, automatic_policy_version: str | None = None
        ) -> EvidenceSearchResponse:
            result = _response(notebook_id, mode="exhaustive")
            if failure == "two_items":
                result.items.append(dict(result.items[0]))
            elif failure == "stuck_cursor":
                result.next_cursor = "same-child-position"
            elif failure == "response_bytes":
                result.items[0]["content"] = "x" * 4096
            else:
                result.omissions.append("provider_budget")
            return result

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    request = ScopeRequestReview(
        query="find",
        mode="traversal",
        scope={"kind": "selected", "notebook_ids": (notebook_id,)},
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        limit=1,
    )
    config = (
        ServerConfig(max_advanced_response_bytes=512)
        if failure == "response_bytes"
        else ServerConfig()
    )
    service = ScopedSearchApplicationService(engine, config)  # type: ignore[arg-type]
    if failure == "two_items":
        with pytest.raises(CursorConflictError, match="one-item budget"):
            await service.execute_traversal(request, principal)
    elif failure == "stuck_cursor":
        first = await service.execute_traversal(request, principal)
        assert first.next_cursor is not None
        with pytest.raises(CursorConflictError, match="did not advance"):
            await service.execute_traversal(
                request.model_copy(update={"cursor": first.next_cursor}), principal
            )
    elif failure == "response_bytes":
        with pytest.raises(DependencyUnavailableError, match="byte budget"):
            await service.execute_traversal(request, principal)
    else:
        result = await service.execute_traversal(request, principal)
        assert result.completeness == "partial"
        assert result.omissions == (f"{notebook_id}:provider_budget",)
