"""WP-14 additive scope resolver and evidence-chain security tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mnemo.interfaces import (
    ContractValidationError,
    NotFoundError,
    PrincipalContextV1,
    StorageInterfaceV1,
)
from mnemo.models import Source
from mnemo.retrieval import StorageDocumentScopeResolverV1


def _source(notebook_id, document_id):  # type: ignore[no-untyped-def]
    return Source(
        source_id=uuid4(),
        notebook_id=notebook_id,
        document_id=document_id,
        created_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_scope_resolver_explicit_unique_ambiguous_and_version_mismatch() -> None:
    notebook_a, notebook_b, document_id, version_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    storage = SimpleNamespace(
        get_document=AsyncMock(
            return_value=SimpleNamespace(versions=(SimpleNamespace(version_id=version_id),))
        )
    )
    associations = SimpleNamespace(
        list_sources_for_document=AsyncMock(
            return_value=(_source(notebook_a, document_id), _source(notebook_b, document_id))
        )
    )
    resolver = StorageDocumentScopeResolverV1(storage, associations)  # type: ignore[arg-type]
    principal = PrincipalContextV1(uuid4(), True)

    explicit = await resolver.resolve_document_scope(principal, document_id, version_id, notebook_a)
    assert explicit.notebook_id == notebook_a
    with pytest.raises(ContractValidationError, match=r"ambiguous|multiple"):
        await resolver.resolve_document_scope(principal, document_id, version_id, None)
    with pytest.raises(NotFoundError, match="authorized resource"):
        await resolver.resolve_document_scope(principal, document_id, uuid4(), notebook_a)

    associations.list_sources_for_document.return_value = (_source(notebook_a, document_id),)
    unique = await resolver.resolve_document_scope(principal, document_id, version_id, None)
    assert unique.notebook_id == notebook_a


@pytest.mark.anyio
async def test_scope_resolver_non_enumerating_cross_notebook_and_missing() -> None:
    notebook_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    storage = SimpleNamespace(
        get_document=AsyncMock(
            return_value=SimpleNamespace(versions=(SimpleNamespace(version_id=version_id),))
        )
    )
    associations = SimpleNamespace(
        list_sources_for_document=AsyncMock(return_value=(_source(notebook_id, document_id),))
    )
    resolver = StorageDocumentScopeResolverV1(storage, associations)  # type: ignore[arg-type]
    principal = PrincipalContextV1(uuid4(), True)

    with pytest.raises(NotFoundError) as cross_scope:
        await resolver.resolve_document_scope(principal, document_id, version_id, uuid4())
    associations.list_sources_for_document.return_value = ()
    with pytest.raises(NotFoundError) as missing:
        await resolver.resolve_document_scope(principal, document_id, version_id, None)
    assert "notebook" not in str(cross_scope.value).lower()
    assert type(cross_scope.value) is type(missing.value)
    assert str(cross_scope.value) == str(missing.value)


def test_frozen_storage_protocol_no_longer_contains_adr_0072_method() -> None:
    assert "list_sources_for_document" not in StorageInterfaceV1.__dict__
