from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mnemo.retrieval.final_qa_authorization import StorageEvidenceAuthorizerV2
from mnemo.storage.sqlite import SQLiteStore


@pytest.mark.anyio
async def test_evidence_authorizer_fails_closed_at_each_canonical_boundary(tmp_path) -> None:  # type: ignore[no-untyped-def]
    actor, notebook, document, version, source = (uuid4() for _ in range(5))
    candidate = SimpleNamespace(
        notebook_id=notebook,
        document_id=document,
        version_id=version,
        source_id=source,
        occurrence_id=None,
        derivation_id=None,
        generation_id=None,
    )
    storage = SQLiteStore(tmp_path / "authorizer.db")
    authorizer = StorageEvidenceAuthorizerV2(storage)
    authorizer._resolver = SimpleNamespace(
        resolve_document_scope=AsyncMock(return_value=SimpleNamespace(source_id=source))
    )
    assert await authorizer.authorize_evidence(actor, notebook, candidate)
    assert not await authorizer.authorize_evidence(
        actor, notebook, SimpleNamespace(**{**vars(candidate), "notebook_id": uuid4()})
    )
    authorizer._resolver.resolve_document_scope.side_effect = RuntimeError("denied")
    assert not await authorizer.authorize_evidence(actor, notebook, candidate)
    authorizer._resolver.resolve_document_scope.side_effect = None
    authorizer._resolver.resolve_document_scope.return_value = SimpleNamespace(source_id=uuid4())
    assert not await authorizer.authorize_evidence(actor, notebook, candidate)
    derived = SimpleNamespace(**{**vars(candidate), "derivation_id": uuid4()})
    authorizer._resolver.resolve_document_scope.return_value = SimpleNamespace(source_id=source)
    assert await authorizer.generation_is_active(candidate)
    with_generation = SimpleNamespace(**{**vars(candidate), "generation_id": uuid4()})
    assert not await authorizer.generation_is_active(with_generation)

    asset_authorizer = StorageEvidenceAuthorizerV2(storage)
    asset_authorizer._resolver = SimpleNamespace(
        resolve_document_scope=AsyncMock(return_value=SimpleNamespace(source_id=source))
    )
    assert not await asset_authorizer.authorize_evidence(actor, notebook, derived)
    occurrence = uuid4()
    derivation = uuid4()
    candidate = SimpleNamespace(
        **{
            **vars(candidate),
            "occurrence_id": occurrence,
            "derivation_id": derivation,
        }
    )
    storage.get_authorized_asset_occurrence = AsyncMock(return_value=None)  # type: ignore[method-assign]
    storage.get_asset_derivation = AsyncMock(return_value=None)  # type: ignore[method-assign]
    assert not await asset_authorizer.authorize_evidence(actor, notebook, candidate)
    storage.get_authorized_asset_occurrence.return_value = SimpleNamespace(
        occurrence_id=occurrence,
        document_id=document,
        version_id=version,
    )
    assert not await asset_authorizer.authorize_evidence(actor, notebook, candidate)
    storage.get_asset_derivation.return_value = SimpleNamespace(occurrence_id=uuid4())
    assert not await asset_authorizer.authorize_evidence(actor, notebook, candidate)
    storage.get_asset_derivation.return_value = SimpleNamespace(occurrence_id=occurrence)
    assert await asset_authorizer.authorize_evidence(actor, notebook, candidate)


def test_evidence_authorizer_requires_storage_protocol() -> None:
    with pytest.raises(TypeError, match="StorageInterfaceV1"):
        StorageEvidenceAuthorizerV2(object())  # type: ignore[arg-type]
