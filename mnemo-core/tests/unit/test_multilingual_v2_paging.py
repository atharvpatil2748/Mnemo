"""Authorized V2 scoring must traverse every bounded evidence page."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from mnemo.models.advanced_retrieval import PositionalScopeV2, RetrievalScopeV2
from mnemo.models.multilingual import LanguageCode
from mnemo.models.v2_retrieval_authorization import (
    V2ActiveRuntimeBindingV1,
    V2RetrievalAuthorizationDecisionV1,
)
from mnemo.retrieval import multilingual_dense_v2, multilingual_sparse_v2
from mnemo.retrieval.multilingual_dense_v2 import AuthorizedMultilingualDenseRetrievalV2
from mnemo.retrieval.multilingual_sparse_v2 import AuthorizedMultilingualSparseRetrievalV2


def _decision() -> V2RetrievalAuthorizationDecisionV1:
    notebook = UUID(int=1)
    return V2RetrievalAuthorizationDecisionV1(
        decision_id=UUID(int=2),
        principal_actor_id=UUID(int=3),
        operation="retrieve",
        retrieval_scope=RetrievalScopeV2(notebook_id=notebook),
        positional_scope=PositionalScopeV2(),
        runtime_binding=V2ActiveRuntimeBindingV1(
            alias_set_digest="0" * 64,
            generation_ids=(UUID(int=4), UUID(int=5), UUID(int=6), UUID(int=7)),
            profile_fingerprint="0" * 64,
            vector_space_identity="0" * 64,
            database_identity="0" * 64,
            build_run_id=UUID(int=8),
            admission_policy_identity="fixture/1",
        ),
        authorization_policy_identity="fixture/1",
        authorization_policy_revision="1",
        request_fingerprint="0" * 64,
        issued_at="fixture",
        required_provenance_evidence=("language-evidence-reference-v3",),
    )


class _PagedEnumerator:
    def __init__(self) -> None:
        self.sources = tuple(
            SimpleNamespace(notebook_id=UUID(int=1), identity_digest=str(index))
            for index in range(3)
        )
        self.offsets: list[int] = []

    async def enumerate_authorized_multilingual_sources(self, **_: object) -> tuple[object, ...]:
        raise AssertionError("paged runtime must not use legacy 10k enumeration")

    async def enumerate_authorized_multilingual_sources_page(
        self, *, offset: int, limit: int, **_: object
    ) -> tuple[object, ...]:
        self.offsets.append(offset)
        return self.sources[offset : offset + limit]


class _EmbeddingStore:
    async def list_authorized_multilingual_embeddings_v3(
        self, *, authorized_sources: tuple[object, ...], **_: object
    ) -> tuple[object, ...]:
        return tuple(
            SimpleNamespace(
                source=source,
                vector=(1.0, 0.0) if source.identity_digest == "2" else (0.0, 1.0),
                embedding_id=UUID(int=int(source.identity_digest) + 10),
            )
            for source in authorized_sources
        )


class _Embedder:
    async def embed_query(self, **_: object) -> object:
        return SimpleNamespace(profile=SimpleNamespace(vector_space="space"), vector=(1.0, 0.0))


def test_dense_v2_pages_beyond_first_authorized_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(multilingual_dense_v2, "MULTILINGUAL_V2_PAGE_SIZE", 2)
    enumerator = _PagedEnumerator()
    service = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=enumerator,
        store=_EmbeddingStore(),
        query_embedder=_Embedder(),
        generation_id=UUID(int=5),
        vector_space="space",
    )
    result = asyncio.run(
        service.retrieve(
            decision=_decision(),
            query="ordinary question",
            query_language=LanguageCode("en"),
            limit=1,
        )
    )
    assert enumerator.offsets == [0, 2]
    assert result[0].embedding.source.identity_digest == "2"


class _SparseStore:
    async def search_authorized_multilingual_text_v2(
        self, *, authorized_sources: tuple[object, ...], **_: object
    ) -> tuple[tuple[object, float], ...]:
        return tuple(
            (SimpleNamespace(source=source), 10.0 if source.identity_digest == "2" else 1.0)
            for source in authorized_sources
        )


def test_sparse_v2_pages_and_ranks_globally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(multilingual_sparse_v2, "MULTILINGUAL_V2_PAGE_SIZE", 2)
    enumerator = _PagedEnumerator()
    service = AuthorizedMultilingualSparseRetrievalV2(
        source_enumerator=enumerator,
        store=_SparseStore(),
        generation_id=UUID(int=5),
    )
    plan = SimpleNamespace(query="ordinary question", position=PositionalScopeV2())
    result = asyncio.run(
        service.retrieve_authorized_multilingual_sparse(decision=_decision(), plan=plan, limit=1)
    )
    assert enumerator.offsets == [0, 2]
    assert result[0].source.identity_digest == "2"
