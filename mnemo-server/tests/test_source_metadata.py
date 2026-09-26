"""Authorized source presentation metadata and identity regression tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    NotFoundError,
    PrincipalContextV1,
    ResolvedDocumentScope,
)
from mnemo.interfaces.scope import ScopeResolutionKind
from mnemo.models import (
    DeliveryAttribution,
    DeliveryCompleteness,
    DeliveryItem,
    DeliveryResourceKind,
    DeliveryResponse,
    DeliveryUsage,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
)
from mnemo_server.config import ServerConfig
from mnemo_server.schemas.structured_v2 import StructuredRetrievalResponse
from mnemo_server.services.delivery import authorized_delivery_response_body
from mnemo_server.services.source_metadata import (
    AuthorizedSourceMetadataResolverV1,
    SourceMetadataReferenceV1,
)
from mnemo_server.services.structured_v2 import StructuredRetrievalApplicationService


def _document(
    document_id: UUID, version_id: UUID, *, title: str | None, optional: dict[str, str]
) -> Document:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metadata = DocumentMetadata(
        content_hash="a" * 64, title=title, metadata=FrozenMetadata(optional)
    )
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=metadata.content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    return Document(
        document_id=document_id,
        versions=(version,),
        current_version_id=version_id,
        current_hash=metadata.content_hash,
        status=DocumentStatus.INDEXED,
        created_at=now,
        updated_at=now,
    )


def _fixture(
    *, title: str | None, optional: dict[str, str]
) -> tuple[KnowledgeEngine, SourceMetadataReferenceV1]:
    engine = MagicMock(spec=KnowledgeEngine)
    notebook_id, source_id, document_id, version_id = (uuid4() for _ in range(4))
    reference = SourceMetadataReferenceV1(
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
    )
    engine.document_scope_resolver.resolve_document_scope = AsyncMock(
        return_value=ResolvedDocumentScope(
            notebook_id,
            source_id,
            document_id,
            version_id,
            ScopeResolutionKind.EXPLICIT,
        )
    )
    engine.storage.get_notebook = AsyncMock(return_value=object())
    engine.storage.get_document = AsyncMock(
        return_value=_document(document_id, version_id, title=title, optional=optional)
    )
    return engine, reference


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("title", "optional", "expected_filename", "expected_display"),
    [
        (
            "Version title",
            {"original_filename": "same.csv", "mime_type": "text/csv"},
            "same.csv",
            "Version title",
        ),
        (None, {"filename": "legacy.csv"}, "legacy.csv", "legacy.csv"),
        (None, {}, None, None),
        ("C:\\private\\secret", {"filename": "../private.csv"}, None, None),
    ],
)
async def test_nullable_authorized_metadata_never_invents_paths(
    title: str | None,
    optional: dict[str, str],
    expected_filename: str | None,
    expected_display: str | None,
) -> None:
    engine, reference = _fixture(title=title, optional=optional)
    principal = PrincipalContextV1(uuid4(), True)
    resolved = await AuthorizedSourceMetadataResolverV1(engine).resolve(principal, reference)
    assert resolved.source_id == reference.source_id
    assert resolved.document_id == reference.document_id
    assert resolved.version_id == reference.version_id
    assert resolved.original_filename == expected_filename
    assert resolved.display_name == expected_display
    assert "private" not in resolved.model_dump_json()


@pytest.mark.anyio
async def test_source_identity_and_bounded_deduplicated_lookup() -> None:
    engine, reference = _fixture(title="Same title", optional={"filename": "same.csv"})
    principal = PrincipalContextV1(uuid4(), True)
    resolver = AuthorizedSourceMetadataResolverV1(engine)
    result = await resolver.resolve_many(principal, (reference, reference))
    assert len(result) == 1
    engine.storage.get_document.assert_awaited_once()
    with pytest.raises(ValueError, match="bounded limit"):
        await resolver.resolve_many(principal, (reference,) * 201)
    engine.storage.get_document.assert_awaited_once()
    with pytest.raises(PermissionError):
        await resolver.resolve(PrincipalContextV1(uuid4(), False), reference)
    engine.storage.get_document.assert_awaited_once()


@pytest.mark.anyio
async def test_resolver_empty_two_hundred_unique_and_over_limit_are_bounded() -> None:
    engine, first = _fixture(title="Title", optional={"filename": "shared.csv"})
    principal = PrincipalContextV1(uuid4(), True)
    resolver = AuthorizedSourceMetadataResolverV1(engine)
    assert await resolver.resolve_many(principal, ()) == {}
    engine.storage.get_document.assert_not_awaited()

    references = tuple(
        SourceMetadataReferenceV1(
            notebook_id=first.notebook_id,
            source_id=first.source_id,
            document_id=first.document_id,
            version_id=uuid4(),
        )
        for _ in range(200)
    )

    async def scope_for_version(
        _principal: PrincipalContextV1,
        _document_id: UUID,
        version_id: UUID,
        _notebook_id: UUID,
    ) -> ResolvedDocumentScope:
        return ResolvedDocumentScope(
            first.notebook_id,
            first.source_id,
            first.document_id,
            version_id,
            ScopeResolutionKind.EXPLICIT,
        )

    engine.document_scope_resolver.resolve_document_scope = AsyncMock(side_effect=scope_for_version)
    document = engine.storage.get_document.return_value
    engine.storage.get_document.return_value = Document(
        document_id=first.document_id,
        versions=tuple(
            DocumentVersion(
                version_id=reference.version_id,
                document_id=first.document_id,
                content_hash=f"{index + 1:064x}",
                metadata=replace(document.versions[0].metadata, content_hash=f"{index + 1:064x}"),
                status=(
                    DocumentVersionStatus.CURRENT
                    if index == 0
                    else DocumentVersionStatus.SUPERSEDED
                ),
                created_at=document.created_at,
            )
            for index, reference in enumerate(references)
        ),
        current_version_id=references[0].version_id,
        current_hash=f"{1:064x}",
        status=DocumentStatus.INDEXED,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    resolved = await resolver.resolve_many(principal, references)
    assert len(resolved) == 200
    assert {value.version_id for value in resolved.values()} == {
        reference.version_id for reference in references
    }
    assert {value.original_filename for value in resolved.values()} == {"shared.csv"}
    assert engine.storage.get_document.await_count <= 200
    with pytest.raises(ValueError, match="bounded limit"):
        await resolver.resolve_many(principal, (*references, first))
    assert engine.storage.get_document.await_count <= 200


@pytest.mark.anyio
async def test_mismatched_or_missing_version_fails_without_metadata_disclosure() -> None:
    engine, reference = _fixture(title="Protected", optional={"filename": "secret.csv"})
    principal = PrincipalContextV1(uuid4(), True)
    mismatched = SourceMetadataReferenceV1(
        notebook_id=reference.notebook_id,
        source_id=uuid4(),
        document_id=reference.document_id,
        version_id=reference.version_id,
    )
    with pytest.raises(NotFoundError, match="authorized resource was not found"):
        await AuthorizedSourceMetadataResolverV1(engine).resolve(principal, mismatched)
    engine.storage.get_document.assert_not_awaited()
    engine.storage.get_document.return_value = None
    with pytest.raises(NotFoundError, match="authorized resource was not found"):
        await AuthorizedSourceMetadataResolverV1(engine).resolve(principal, reference)


@pytest.mark.anyio
async def test_renamed_versions_keep_stable_document_and_distinct_version_metadata() -> None:
    engine, current = _fixture(title="Renamed", optional={"filename": "new.csv"})
    old_id = uuid4()
    now = datetime(2025, 1, 1, tzinfo=UTC)
    old_metadata = DocumentMetadata(
        content_hash="b" * 64,
        title="Original",
        metadata=FrozenMetadata({"filename": "old.csv"}),
    )
    old_version = DocumentVersion(
        version_id=old_id,
        document_id=current.document_id,
        content_hash=old_metadata.content_hash,
        metadata=old_metadata,
        status=DocumentVersionStatus.SUPERSEDED,
        created_at=now,
    )
    document = engine.storage.get_document.return_value
    engine.storage.get_document.return_value = Document(
        document_id=current.document_id,
        versions=(old_version, *document.versions),
        current_version_id=current.version_id,
        current_hash=document.current_hash,
        status=DocumentStatus.INDEXED,
        created_at=now,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    old = SourceMetadataReferenceV1(
        notebook_id=current.notebook_id,
        source_id=current.source_id,
        document_id=current.document_id,
        version_id=old_id,
    )

    async def resolved_scope(
        _principal: PrincipalContextV1,
        _document_id: UUID,
        requested_version_id: UUID,
        _notebook_id: UUID,
    ) -> ResolvedDocumentScope:
        return ResolvedDocumentScope(
            current.notebook_id,
            current.source_id,
            current.document_id,
            requested_version_id,
            ScopeResolutionKind.EXPLICIT,
        )

    engine.document_scope_resolver.resolve_document_scope = AsyncMock(side_effect=resolved_scope)
    principal = PrincipalContextV1(uuid4(), True)
    envelopes = await AuthorizedSourceMetadataResolverV1(engine).resolve_many(
        principal, (old, current)
    )
    assert envelopes[old].original_filename == "old.csv"
    assert envelopes[current].original_filename == "new.csv"
    assert envelopes[old].source_id == envelopes[current].source_id
    assert envelopes[old].version_id != envelopes[current].version_id


@pytest.mark.anyio
async def test_asset_and_image_delivery_use_same_bounded_authorized_envelope() -> None:
    engine, reference = _fixture(title="Diagram", optional={"filename": "diagram.png"})
    principal = PrincipalContextV1(uuid4(), True)
    attribution = DeliveryAttribution(
        notebook_id=reference.notebook_id,
        source_id=reference.source_id,
        document_id=reference.document_id,
        version_id=reference.version_id,
        asset_id=uuid4(),
        occurrence_id=uuid4(),
        modality="image",
    )
    for kind in (DeliveryResourceKind.ASSET_INVENTORY, DeliveryResourceKind.ANALYSIS):
        response = DeliveryResponse(
            resource_kind=kind,
            snapshot_identity="c" * 64,
            completeness=DeliveryCompleteness.COMPLETE,
            items=(
                DeliveryItem(
                    index=0,
                    kind="image",
                    attribution=attribution,
                    payload={"status": "available"},
                    byte_size=9,
                ),
            ),
            usage=DeliveryUsage(items=1, bytes=9),
        )
        body = await authorized_delivery_response_body(
            response, engine, principal, max_response_bytes=16_384
        )
        assert body.source_metadata is not None
        assert body.source_metadata["source_id"] == str(reference.source_id)
        assert body.items[0].source_metadata == body.source_metadata
        with pytest.raises(ContractValidationError, match="byte ceiling"):
            await authorized_delivery_response_body(
                response, engine, principal, max_response_bytes=100
            )


@pytest.mark.anyio
async def test_structured_dataset_and_nested_evidence_share_authorized_metadata() -> None:
    engine, reference = _fixture(title="Dataset", optional={"filename": "table.csv"})
    identity = {
        "notebook_id": str(reference.notebook_id),
        "source_id": str(reference.source_id),
        "document_id": str(reference.document_id),
        "version_id": str(reference.version_id),
    }
    response = StructuredRetrievalResponse(
        contract_version="mnemo.structured/v2",
        schema_version="mnemo.structured/v2",
        operation="describe",
        request_id=uuid4(),
        snapshot_identity="a" * 64,
        scope={},
        representations_requested=[],
        representations_searched=[],
        completeness="complete",
        coverage={},
        items=[
            {"dataset_id": str(uuid4()), "provenance": dict(identity)},
            {"values": {"price": {"provenance": [dict(identity)]}}},
        ],
        next_cursor=None,
        limits={},
        omissions=[],
        recommended_next_actions=[],
        structured={},
    )
    result = await StructuredRetrievalApplicationService(
        engine,
        ServerConfig(),  # type: ignore[arg-type]
    )._with_source_metadata(response, PrincipalContextV1(uuid4(), True))
    first = result.items[0]["provenance"]["source_metadata"]
    second = result.items[1]["values"]["price"]["provenance"][0]["source_metadata"]
    assert first == second
    assert first["source_id"] == str(reference.source_id)
    assert first["original_filename"] == "table.csv"
