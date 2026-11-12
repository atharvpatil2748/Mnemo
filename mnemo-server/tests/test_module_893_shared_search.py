"""Internal shared-search contract; retained public V2 routes have separate snapshots."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mnemo.interfaces import DependencyUnavailableError, NotFoundError, PrincipalContextV1
from mnemo.models import EvidenceRepresentation
from mnemo.phase85.projections import ProjectionCompleteness
from mnemo.retrieval.advanced import AdvancedRetrievalService, RetrievalCursorCodec
from mnemo_server.config import ServerConfig
from mnemo_server.schemas.automatic_query_v2 import AutomaticQueryV2Request
from mnemo_server.schemas.retrieval_v2 import (
    EvidenceScopeRequest,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
)
from mnemo_server.schemas.structured_v2 import StructuredRetrievalResponse
from mnemo_server.services import shared_search
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.shared_search import (
    ScopedDocumentSelection,
    ScopedSearchAuthorization,
    SharedEvidenceReference,
    SharedSearchApplicationService,
    SharedSearchEnvelope,
    SharedSearchKind,
    SharedSearchRequest,
    SharedSearchSafeError,
)
from mnemo_server.typed_errors import ErrorCategory


def _evidence_response(
    notebook_id: object, *, source_status: str = "searched"
) -> EvidenceSearchResponse:
    return EvidenceSearchResponse(
        schema_version="mnemo.mcp.contract/v2",
        operation="search_evidence",
        request_id=uuid4(),
        mode="ranked",
        scope={"notebook_id": str(notebook_id)},
        items=[
            {
                "notebook_id": str(notebook_id),
                "source_id": str(uuid4()),
                "document_id": str(uuid4()),
                "version_id": str(uuid4()),
                "chunk_id": "chunk-1",
                "occurrence_id": None,
                "derivation_id": None,
            }
        ],
        completeness="unknown",
        coverage={
            "representations": [
                {
                    "representation": "canonical_text",
                    "status": source_status,
                    "returned": 1 if source_status == "searched" else 0,
                    "reason_code": None if source_status == "searched" else "source_unavailable",
                }
            ]
        },
        omissions=[] if source_status == "searched" else ["canonical_text:source_unavailable"],
        limits={"requested_k": 20},
        next_cursor=None,
        recommended_next_actions=[],
        diagnostics={},
    )


def test_internal_contract_is_versioned_and_rejects_fabricated_ancestry() -> None:
    schema = SharedSearchEnvelope.model_json_schema()
    assert "evidence" in schema["properties"]
    assert "membership_revision" in schema["properties"]
    with pytest.raises(ValueError, match="dataset identity"):
        SharedEvidenceReference(
            kind="row",
            notebook_id=uuid4(),
            source_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            row_id="row-1",
        )
    with pytest.raises(TypeError, match="operation and request"):
        SharedSearchRequest(SharedSearchKind.EVIDENCE, AutomaticQueryV2Request(query="find"))
    safe = SharedSearchSafeError(category=ErrorCategory.NOT_FOUND, correlation_id=uuid4())
    assert "message" not in safe.model_dump()
    assert SharedSearchSafeError.model_validate_json(safe.model_dump_json()) == safe


def test_internal_source_status_preserves_searched_zero_vs_unavailable() -> None:
    notebook_id = uuid4()
    searched = _evidence_response(notebook_id)
    searched.coverage["representations"][0]["returned"] = 0
    unavailable = _evidence_response(notebook_id, source_status="unavailable")
    found = shared_search._evidence_statuses(searched)[0]
    missing = shared_search._evidence_statuses(unavailable)[0]
    assert (found.status, found.matched) == ("searched", 0)
    assert (missing.status, missing.matched, missing.reason_code) == (
        "unavailable",
        None,
        "source_unavailable",
    )


@pytest.mark.anyio
async def test_multi_scope_authority_precedes_any_provider_access(tmp_path: Path) -> None:
    first, second, private = uuid4(), uuid4(), uuid4()
    owner, reader, stranger = (PrincipalContextV1(uuid4(), True) for _ in range(3))
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    for notebook_id in (first, second, private):
        authority.grant(
            actor_id=owner.actor_id,
            notebook_id=notebook_id,
            role="owner",
            operator_id=owner.actor_id,
        )
    for notebook_id in (first, second):
        authority.grant(
            actor_id=reader.actor_id,
            notebook_id=notebook_id,
            role="reader",
            operator_id=owner.actor_id,
        )
    reads: list[object] = []

    async def get_notebook(notebook_id: object) -> object | None:
        reads.append(notebook_id)
        return object() if notebook_id in (first, second, private) else None

    engine = SimpleNamespace(
        server_scope_authority=authority,
        storage=SimpleNamespace(get_notebook=get_notebook),
    )
    planner = ScopedSearchAuthorization(engine)  # type: ignore[arg-type]
    selection = await planner.resolve(reader, selected_notebooks=(first, second))
    assert tuple(scope.notebook_id for scope in selection.notebooks) == (first, second)
    assert reads == [first, second, first, second]
    await planner.revalidate(selection)

    reads.clear()
    for selected in ((private,), (uuid4(),), (first, private)):
        with pytest.raises(NotFoundError, match="authorized resource was not found"):
            await planner.resolve(reader, selected_notebooks=selected)
        assert reads == []
    with pytest.raises(NotFoundError):
        await planner.resolve(stranger, selected_notebooks=None)
    with pytest.raises(PermissionError):
        await planner.resolve(PrincipalContextV1(uuid4(), False), selected_notebooks=(first,))
    authority.revoke(actor_id=reader.actor_id, notebook_id=second)
    with pytest.raises(NotFoundError):
        await planner.revalidate(selection)


@pytest.mark.anyio
async def test_multi_scope_exact_version_is_checked_after_membership(
    tmp_path: Path,
) -> None:
    notebook_id, other_id, document_id, version_id = (uuid4() for _ in range(4))
    principal = PrincipalContextV1(uuid4(), True)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )
    inspected: list[str] = []

    async def get_notebook(value: object) -> object | None:
        return object() if value == notebook_id else None

    async def get_document(value: object) -> object | None:
        inspected.append("document")
        return (
            SimpleNamespace(versions=(SimpleNamespace(version_id=version_id),))
            if value == document_id
            else None
        )

    async def list_sources(value: object) -> tuple[object, ...]:
        inspected.append("sources")
        return (
            (SimpleNamespace(notebook_id=notebook_id, source_id=uuid4()),)
            if value == document_id
            else ()
        )

    engine = SimpleNamespace(
        server_scope_authority=authority,
        storage=SimpleNamespace(
            get_notebook=get_notebook,
            get_document=get_document,
            list_sources_for_document=list_sources,
        ),
    )
    planner = ScopedSearchAuthorization(engine)  # type: ignore[arg-type]
    exact = ScopedDocumentSelection(notebook_id, document_id, version_id)
    with pytest.raises(NotFoundError):
        await planner.resolve(principal, selected_notebooks=(other_id,), documents=(exact,))
    assert inspected == []
    allowed = await planner.resolve(
        principal, selected_notebooks=(notebook_id,), documents=(exact,)
    )
    assert allowed.documents == (exact,)
    assert inspected == ["document", "sources"]
    with pytest.raises(ValueError, match="unique"):
        await planner.resolve(
            principal, selected_notebooks=(notebook_id,), documents=(exact, exact)
        )
    missing_authority = ScopedSearchAuthorization(  # type: ignore[arg-type]
        SimpleNamespace(storage=engine.storage)
    )
    with pytest.raises(DependencyUnavailableError, match="membership authority"):
        await missing_authority.resolve(principal, selected_notebooks=(notebook_id,))
    with pytest.raises(DependencyUnavailableError, match="membership authority"):
        await missing_authority.revalidate(allowed)
    engine.advanced_retrieval = None
    with pytest.raises(DependencyUnavailableError, match="governed V2 retrieval"):
        await planner.inspect_active_sources(allowed, (EvidenceRepresentation.CANONICAL_TEXT,))
    with pytest.raises(NotFoundError):
        await planner.resolve(
            principal,
            selected_notebooks=(notebook_id,),
            documents=(ScopedDocumentSelection(notebook_id, document_id, uuid4()),),
        )
    authority.revoke(actor_id=principal.actor_id, notebook_id=notebook_id)
    with pytest.raises(NotFoundError):
        await planner.revalidate(allowed)


@pytest.mark.anyio
async def test_per_scope_generation_admission_reports_incomplete_and_unavailable(
    tmp_path: Path,
) -> None:
    first, second, document_a, document_b, version_a, version_b = (uuid4() for _ in range(6))
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
    generation_id = uuid4()
    generation = SimpleNamespace(
        generation_id=generation_id,
        profile="ocr-test",
        model_identity="ocr-model",
        state=SimpleNamespace(value="ready"),
        checksum="a" * 64,
    )
    coverage = SimpleNamespace(
        completeness=ProjectionCompleteness.COMPLETE,
        failed_count=0,
        checksum="a" * 64,
    )
    observed: list[str] = []
    conflicting_profile = False
    generation_missing = False

    async def get_notebook(value: object) -> object | None:
        return object() if value in (first, second) else None

    async def get_document(value: object) -> object | None:
        versions = {document_a: version_a, document_b: version_b}
        return (
            SimpleNamespace(versions=(SimpleNamespace(version_id=versions[value]),))
            if value in versions
            else None
        )

    async def list_sources(value: object) -> tuple[object, ...]:
        notebook = {document_a: first, document_b: second}.get(value)
        return (
            () if notebook is None else (SimpleNamespace(notebook_id=notebook, source_id=uuid4()),)
        )

    async def active_generations(capability: str) -> tuple[object, ...]:
        observed.append(capability)
        if capability != "ocr_text":
            return ()
        if generation_missing:
            return ()
        if conflicting_profile:
            return (
                generation,
                SimpleNamespace(profile="other-profile", model_identity="other-model"),
            )
        return (generation,)

    async def get_coverage(value: object) -> object | None:
        return coverage if value == generation_id else None

    async def get_sources(value: object) -> tuple[tuple[object, ...], tuple[object, ...]]:
        return (), (version_a,) if value == generation_id else ()

    async def list_asset_occurrences(value: object) -> tuple[object, ...]:
        assert value in (version_a, version_b)
        return (SimpleNamespace(version_id=value),)

    retrieval = AdvancedRetrievalService(
        sources=(), cursor_codec=RetrievalCursorCodec(b"scope-admission-signing-secret-32!!")
    )
    retrieval._sources = {  # type: ignore[attr-defined]
        EvidenceRepresentation.CANONICAL_TEXT: object(),
        EvidenceRepresentation.OCR_TEXT: object(),
    }
    engine = SimpleNamespace(
        server_scope_authority=authority,
        storage=SimpleNamespace(
            get_notebook=get_notebook,
            get_document=get_document,
            list_sources_for_document=list_sources,
            list_active_index_generations=active_generations,
            get_index_generation_coverage=get_coverage,
            get_index_generation_sources=get_sources,
            list_asset_occurrences=list_asset_occurrences,
        ),
        advanced_retrieval=retrieval,
    )
    planner = ScopedSearchAuthorization(engine)  # type: ignore[arg-type]
    selection = await planner.resolve(
        principal,
        selected_notebooks=(first, second),
        documents=(
            shared_search.ScopedDocumentSelection(first, document_a, version_a),
            shared_search.ScopedDocumentSelection(second, document_b, version_b),
        ),
    )
    matrix = await planner.inspect_active_sources(
        selection,
        (
            EvidenceRepresentation.CANONICAL_TEXT,
            EvidenceRepresentation.OCR_TEXT,
            EvidenceRepresentation.VISION_ANALYSIS,
        ),
    )
    assert [(item.notebook_id, item.representation.value, item.status) for item in matrix] == [
        (first, "canonical_text", "active"),
        (first, "ocr_text", "active"),
        (first, "vision_analysis", "unavailable"),
        (second, "canonical_text", "active"),
        (second, "ocr_text", "incomplete"),
        (second, "vision_analysis", "unavailable"),
    ]
    assert observed == ["ocr_text", "ocr_text"]
    retrieval._sources[EvidenceRepresentation.MULTILINGUAL_TEXT] = object()  # type: ignore[attr-defined]
    multilingual = await planner.inspect_active_sources(
        selection, (EvidenceRepresentation.MULTILINGUAL_TEXT,)
    )
    assert all(
        item.status == "unavailable" and item.reason_code == "governed_multilingual_alias_missing"
        for item in multilingual
    )
    assert observed == ["ocr_text", "ocr_text"]
    coverage.checksum = "b" * 64
    damaged = await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    assert all(item.status == "incomplete" for item in damaged)
    conflicting_profile = True
    incompatible = await planner.inspect_active_sources(
        selection, (EvidenceRepresentation.OCR_TEXT,)
    )
    assert all(item.status == "incompatible" for item in incompatible)
    conflicting_profile = False
    coverage.checksum = "a" * 64
    generation_missing = True
    absent = await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    assert all(item.status == "unavailable" for item in absent)
    generation_missing = False
    generation.state.value = "building"
    unready = await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    assert all(item.status == "incomplete" for item in unready)
    generation.state.value = "ready"
    coverage.failed_count = 1
    failed = await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    assert all(item.status == "incomplete" for item in failed)
    coverage.failed_count = 0
    coverage.completeness = ProjectionCompleteness.PARTIAL
    partial = await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    assert all(item.status == "incomplete" for item in partial)
    coverage.completeness = ProjectionCompleteness.COMPLETE

    async def no_asset_occurrences(value: object) -> tuple[object, ...]:
        return ()

    engine.storage.list_asset_occurrences = no_asset_occurrences
    inapplicable = await planner.inspect_active_sources(
        selection, (EvidenceRepresentation.OCR_TEXT,)
    )
    assert all(item.status == "not_applicable" for item in inapplicable)

    async def wrong_version_occurrence(value: object) -> tuple[object, ...]:
        return (SimpleNamespace(version_id=uuid4()),)

    engine.storage.list_asset_occurrences = wrong_version_occurrence
    with pytest.raises(NotFoundError):
        await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    del engine.storage.list_asset_occurrences
    with pytest.raises(DependencyUnavailableError, match="asset occurrence inspection"):
        await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    engine.storage.list_asset_occurrences = list_asset_occurrences
    del engine.storage.get_index_generation_sources
    with pytest.raises(DependencyUnavailableError, match="generation inspection"):
        await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    engine.storage.get_index_generation_sources = get_sources
    observed.clear()
    authority.revoke(actor_id=principal.actor_id, notebook_id=second)
    with pytest.raises(NotFoundError):
        await planner.inspect_active_sources(selection, (EvidenceRepresentation.OCR_TEXT,))
    assert observed == []


@pytest.mark.anyio
async def test_shared_service_preserves_public_response_and_server_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notebook_id = uuid4()
    request = EvidenceSearchRequest(
        query="find",
        mode="ranked",
        scope=EvidenceScopeRequest(notebook_id=notebook_id),
        representations=("canonical_text",),
    )
    public = _evidence_response(notebook_id)
    seen: list[object] = []

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(self, body: object, principal: object) -> EvidenceSearchResponse:
            seen.extend((body, principal))
            return public

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    principal = PrincipalContextV1(uuid4(), True)
    result = await SharedSearchApplicationService(
        SimpleNamespace(server_scope_authority=None),
        ServerConfig(),  # type: ignore[arg-type]
    ).execute(SharedSearchRequest(SharedSearchKind.EVIDENCE, request), principal)
    assert seen == [request, principal]
    assert result.response is public
    assert result.plan.actor_id == principal.actor_id
    assert result.plan.notebook_id == notebook_id
    assert SharedSearchEnvelope.model_validate_json(result.envelope.model_dump_json()) == (
        result.envelope
    )
    assert result.envelope.evidence[0].kind == "canonical"
    assert result.envelope.sources[0].status == "searched"
    assert result.envelope.sources[0].matched == 1
    assert result.completeness == "unknown"


def test_structured_row_identity_uses_authoritative_catalog_not_payload_claim() -> None:
    notebook_id, source_id, document_id, version_id = (uuid4() for _ in range(4))
    candidate_id, dataset_id = uuid4(), uuid4()
    dataset = SimpleNamespace(
        candidate=SimpleNamespace(candidate_id=candidate_id),
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        dataset_id=dataset_id,
    )
    ancestry = {
        "candidate_id": str(candidate_id),
        "notebook_id": str(notebook_id),
        "source_id": str(source_id),
        "document_id": str(document_id),
        "version_id": str(version_id),
        "chunk_id": "chunk-7",
    }
    response = StructuredRetrievalResponse(
        contract_version="mnemo.structured/v2",
        schema_version="mnemo.structured/v2",
        operation="query",
        request_id=uuid4(),
        snapshot_identity="snapshot",
        scope={"notebook_id": str(notebook_id)},
        representations_requested=["structured_table"],
        representations_searched=["structured_table"],
        completeness="complete",
        coverage={},
        items=[{"record_id": str(uuid4()), "provenance": [ancestry]}],
        next_cursor=None,
        limits={},
        omissions=[],
        recommended_next_actions=[],
        structured={"matched_count": 1},
    )
    references = shared_search._structured_references(response, (dataset,))
    assert len(references) == 1
    assert references[0].dataset_id == dataset_id
    assert references[0].kind == "row"
    assert references[0].row_id == response.items[0]["record_id"]
    response.items[0]["provenance"][0]["source_id"] = str(uuid4())
    with pytest.raises(NotFoundError):
        shared_search._structured_references(response, (dataset,))


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["owner", "reader"])
async def test_shared_boundary_rechecks_acl_before_disclosure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    notebook_id = uuid4()
    owner = PrincipalContextV1(uuid4(), True)
    reader = PrincipalContextV1(uuid4(), True)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    if role == "reader":
        authority.grant(
            actor_id=reader.actor_id,
            notebook_id=notebook_id,
            role="reader",
            operator_id=owner.actor_id,
        )
    principal = owner if role == "owner" else reader

    async def get_notebook(value: object) -> object | None:
        return object() if value == notebook_id else None

    engine = SimpleNamespace(
        storage=SimpleNamespace(get_notebook=get_notebook), server_scope_authority=authority
    )
    request = EvidenceSearchRequest(
        query="find",
        mode="ranked",
        scope=EvidenceScopeRequest(notebook_id=notebook_id),
        representations=("canonical_text",),
    )
    public = _evidence_response(notebook_id)

    class EvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(self, body: object, actor: object) -> EvidenceSearchResponse:
            assert body == request and actor == principal
            return public

    monkeypatch.setattr(shared_search, "EvidenceRetrievalApplicationService", EvidenceService)
    service = SharedSearchApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    allowed = await service.execute(
        SharedSearchRequest(SharedSearchKind.EVIDENCE, request), principal
    )
    assert allowed.plan.membership_revision == authority.revision(notebook_id)
    authority.revoke(actor_id=principal.actor_id, notebook_id=notebook_id)
    with pytest.raises(NotFoundError):
        await service.execute(SharedSearchRequest(SharedSearchKind.EVIDENCE, request), principal)


@pytest.mark.anyio
async def test_shared_boundary_rejects_revocation_during_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook_id = uuid4()
    principal = PrincipalContextV1(uuid4(), True)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    authority.grant(
        actor_id=principal.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=principal.actor_id,
    )

    async def get_notebook(value: object) -> object | None:
        return object() if value == notebook_id else None

    engine = SimpleNamespace(
        storage=SimpleNamespace(get_notebook=get_notebook), server_scope_authority=authority
    )
    request = EvidenceSearchRequest(
        query="find",
        mode="ranked",
        scope=EvidenceScopeRequest(notebook_id=notebook_id),
        representations=("canonical_text",),
    )

    class RevokingEvidenceService:
        def __init__(self, engine: object, config: object) -> None:
            pass

        async def execute(self, body: object, actor: object) -> EvidenceSearchResponse:
            authority.revoke(actor_id=principal.actor_id, notebook_id=notebook_id)
            return _evidence_response(notebook_id)

    monkeypatch.setattr(
        shared_search, "EvidenceRetrievalApplicationService", RevokingEvidenceService
    )
    with pytest.raises(NotFoundError):
        await SharedSearchApplicationService(
            engine,
            ServerConfig(),  # type: ignore[arg-type]
        ).execute(SharedSearchRequest(SharedSearchKind.EVIDENCE, request), principal)
