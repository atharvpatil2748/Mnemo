"""Authorized V2 scoring must traverse every bounded evidence page."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
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
from mnemo.storage.sqlite import SQLiteStore


def test_multilingual_cosine_rejects_invalid_vectors_and_scores_exactly() -> None:
    cosine = multilingual_dense_v2._cosine
    assert cosine((1.0, 0.0), (1.0, 1.0)) == pytest.approx(2**-0.5)
    with pytest.raises(ValueError, match="incompatible multilingual vector dimensions"):
        cosine((1.0,), (1.0, 0.0))
    with pytest.raises(ValueError, match="incompatible multilingual vector dimensions"):
        cosine((), ())
    with pytest.raises(ValueError, match="zero-norm multilingual vector"):
        cosine((0.0, 0.0), (1.0, 0.0))
    with pytest.raises(ValueError, match="zero-norm multilingual vector"):
        cosine((1.0, 0.0), (0.0, 0.0))


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


class _LegacyEnumerator:
    """Pre-paging source adapter retained for bounded small-corpus compatibility."""

    def __init__(self, count: int = 3) -> None:
        self.sources = tuple(
            SimpleNamespace(notebook_id=UUID(int=1), identity_digest=str(index))
            for index in range(count)
        )
        self.calls: list[int] = []

    async def enumerate_authorized_multilingual_sources(
        self, *, decision: V2RetrievalAuthorizationDecisionV1, limit: int
    ) -> tuple[object, ...]:
        assert decision.retrieval_scope.notebook_id == UUID(int=1)
        self.calls.append(limit)
        return self.sources[:limit]


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


def test_dense_stage_observer_is_optional_and_preserves_ranked_results() -> None:
    decision = _decision()
    baseline = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=_LegacyEnumerator(),
        store=_EmbeddingStore(),
        query_embedder=_Embedder(),
        generation_id=UUID(int=5),
        vector_space="space",
    )
    events: list[tuple[UUID, str, str, float | None, int | None, int | None, str | None]] = []
    observed = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=_LegacyEnumerator(),
        store=_EmbeddingStore(),
        query_embedder=_Embedder(),
        generation_id=UUID(int=5),
        vector_space="space",
        stage_observer=lambda *event: events.append(event),
    )

    async def retrieve(service: AuthorizedMultilingualDenseRetrievalV2) -> tuple[object, ...]:
        return await service.retrieve(
            decision=decision,
            query="same frozen query",
            query_language=LanguageCode("en"),
            limit=3,
        )

    baseline_result = asyncio.run(retrieve(baseline))
    observed_result = asyncio.run(retrieve(observed))
    assert observed_result == baseline_result
    assert [item.embedding.embedding_id for item in observed_result] == [
        item.embedding.embedding_id for item in baseline_result
    ]
    for stage in ("dense_cosine_scoring", "dense_candidate_merge_sort"):
        stage_events = [event for event in events if event[1] == stage]
        assert [event[2] for event in stage_events] == ["started", "completed"]
        assert stage_events[-1][3] is not None and stage_events[-1][3] >= 0
        assert stage_events[-1][4] == 3
        assert stage_events[-1][5] == 3
        assert stage_events[-1][6] is None


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


def test_dense_and_sparse_share_only_one_authorized_request_census(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mnemo.retrieval.multilingual_dense_v2 import RequestScopedAuthorizedSourcePagesV2

    monkeypatch.setattr(multilingual_dense_v2, "MULTILINGUAL_V2_PAGE_SIZE", 2)
    monkeypatch.setattr(multilingual_sparse_v2, "MULTILINGUAL_V2_PAGE_SIZE", 2)
    enumerator = _PagedEnumerator()
    dense = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=enumerator,
        store=_EmbeddingStore(),
        query_embedder=_Embedder(),
        generation_id=UUID(int=5),
        vector_space="space",
    )
    sparse = AuthorizedMultilingualSparseRetrievalV2(
        source_enumerator=enumerator, store=_SparseStore(), generation_id=UUID(int=5)
    )
    decision = _decision()
    pages = RequestScopedAuthorizedSourcePagesV2(enumerator=enumerator, decision=decision)

    async def scenario() -> None:
        dense_result = await dense.retrieve(
            decision=decision,
            query="ordinary question",
            query_language=LanguageCode("en"),
            limit=1,
            source_pages=pages,
        )
        sparse_result = await sparse.retrieve_authorized_multilingual_sparse(
            decision=decision,
            plan=SimpleNamespace(query="ordinary question", position=PositionalScopeV2()),
            limit=1,
            source_pages=pages,
        )
        assert dense_result[0].embedding.source.identity_digest == "2"
        assert sparse_result[0].source.identity_digest == "2"

    asyncio.run(scenario())
    assert enumerator.offsets == [0, 2]
    with pytest.raises(PermissionError):
        asyncio.run(
            pages.page(decision=replace(decision, decision_id=UUID(int=99)), offset=0, limit=2)
        )
    foreign = AuthorizedMultilingualSparseRetrievalV2(
        source_enumerator=_PagedEnumerator(), store=_SparseStore(), generation_id=UUID(int=5)
    )
    with pytest.raises(PermissionError):
        asyncio.run(
            foreign.retrieve_authorized_multilingual_sparse(
                decision=decision,
                plan=SimpleNamespace(query="ordinary question", position=PositionalScopeV2()),
                limit=1,
                source_pages=pages,
            )
        )


def test_request_census_rejects_foreign_and_duplicate_sources() -> None:
    from mnemo.retrieval.multilingual_dense_v2 import RequestScopedAuthorizedSourcePagesV2

    decision = _decision()
    enumerator = _PagedEnumerator()
    pages = RequestScopedAuthorizedSourcePagesV2(enumerator=enumerator, decision=decision)
    enumerator.sources = (SimpleNamespace(notebook_id=UUID(int=99), identity_digest="foreign"),)
    with pytest.raises(PermissionError, match="notebook scope"):
        asyncio.run(pages.page(decision=decision, offset=0, limit=2))

    enumerator.sources = (
        SimpleNamespace(notebook_id=UUID(int=1), identity_digest="duplicate"),
        SimpleNamespace(notebook_id=UUID(int=1), identity_digest="duplicate"),
    )
    with pytest.raises(ValueError, match="duplicate identities"):
        asyncio.run(pages.page(decision=decision, offset=0, limit=2))


def test_request_census_is_bounded_and_legacy_read_checks_decision() -> None:
    from mnemo.retrieval.multilingual_dense_v2 import RequestScopedAuthorizedSourcePagesV2

    decision = _decision()
    enumerator = _PagedEnumerator()
    pages = RequestScopedAuthorizedSourcePagesV2(enumerator=enumerator, decision=decision)
    for offset in range(9):
        asyncio.run(pages.page(decision=decision, offset=offset, limit=1))
    assert len(pages._pages) == 8
    assert (0, 1) not in pages._pages
    asyncio.run(pages.page(decision=decision, offset=0, limit=1))
    assert enumerator.offsets.count(0) == 2
    with pytest.raises(PermissionError):
        asyncio.run(pages.all(decision=replace(decision, decision_id=UUID(int=99)), limit=1))


def test_request_census_supports_legacy_enumerator_but_rejects_page_access() -> None:
    from mnemo.retrieval.multilingual_dense_v2 import RequestScopedAuthorizedSourcePagesV2

    decision = _decision()
    enumerator = _LegacyEnumerator()
    pages = RequestScopedAuthorizedSourcePagesV2(enumerator=enumerator, decision=decision)

    values = asyncio.run(pages.all(decision=decision, limit=10))

    assert values == enumerator.sources
    assert enumerator.calls == [10]
    with pytest.raises(TypeError, match="not paged"):
        asyncio.run(pages.page(decision=decision, offset=0, limit=2))


def test_dense_legacy_enumerator_retains_bounded_small_corpus_path() -> None:
    enumerator = _LegacyEnumerator()
    service = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=enumerator,  # type: ignore[arg-type]
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
            limit=2,
        )
    )

    assert enumerator.calls == [10_001]
    assert [item.embedding.source.identity_digest for item in result] == ["2", "0"]


def test_dense_legacy_enumerator_rejects_population_over_limit() -> None:
    enumerator = _LegacyEnumerator(count=10_001)
    service = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=enumerator,  # type: ignore[arg-type]
        store=_EmbeddingStore(),
        query_embedder=_Embedder(),
        generation_id=UUID(int=5),
        vector_space="space",
    )

    with pytest.raises(ValueError, match="exceeds 10000"):
        asyncio.run(
            service.retrieve(
                decision=_decision(),
                query="ordinary question",
                query_language=LanguageCode("en"),
                limit=2,
            )
        )
    assert enumerator.calls == [10_001]


def test_sparse_rejects_overlapping_authorized_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(multilingual_sparse_v2, "MULTILINGUAL_V2_PAGE_SIZE", 2)
    enumerator = _PagedEnumerator()

    async def repeated_page(*, offset: int, **_: object) -> tuple[object, ...]:
        return enumerator.sources[:2] if offset in (0, 2) else ()

    enumerator.enumerate_authorized_multilingual_sources_page = repeated_page  # type: ignore[method-assign]
    service = AuthorizedMultilingualSparseRetrievalV2(
        source_enumerator=enumerator, store=_SparseStore(), generation_id=UUID(int=5)
    )
    with pytest.raises(ValueError, match="overlap"):
        asyncio.run(
            service.retrieve_authorized_multilingual_sparse(
                decision=_decision(),
                plan=SimpleNamespace(query="ordinary question", position=PositionalScopeV2()),
                limit=2,
            )
        )


def test_sparse_rejects_store_evidence_outside_authorized_page() -> None:
    class ForeignSparseStore:
        async def search_authorized_multilingual_text_v2(
            self, **_: object
        ) -> tuple[tuple[object, float], ...]:
            foreign = SimpleNamespace(identity_digest="foreign")
            return ((SimpleNamespace(source=foreign), 1.0),)

    service = AuthorizedMultilingualSparseRetrievalV2(
        source_enumerator=_PagedEnumerator(),
        store=ForeignSparseStore(),
        generation_id=UUID(int=5),
    )
    with pytest.raises(PermissionError, match="unauthorized evidence"):
        asyncio.run(
            service.retrieve_authorized_multilingual_sparse(
                decision=_decision(),
                plan=SimpleNamespace(query="ordinary question", position=PositionalScopeV2()),
                limit=2,
            )
        )


def test_dense_rejects_foreign_notebook_on_later_page_before_vector_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multilingual_dense_v2, "MULTILINGUAL_V2_PAGE_SIZE", 2)
    enumerator = _PagedEnumerator()
    cast(Any, enumerator.sources[2]).notebook_id = UUID(int=99)

    class RecordingEmbeddingStore:
        def __init__(self) -> None:
            self.authorized_pages: list[tuple[str, ...]] = []

        async def list_authorized_multilingual_embeddings_v3(
            self, *, authorized_sources: tuple[object, ...], **kwargs: object
        ) -> tuple[object, ...]:
            self.authorized_pages.append(
                tuple(str(cast(Any, source).identity_digest) for source in authorized_sources)
            )
            return await _EmbeddingStore().list_authorized_multilingual_embeddings_v3(
                authorized_sources=authorized_sources, **kwargs
            )

    store = RecordingEmbeddingStore()
    service = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=cast(Any, enumerator),
        store=cast(Any, store),
        query_embedder=cast(Any, _Embedder()),
        generation_id=UUID(int=5),
        vector_space="space",
    )

    with pytest.raises(PermissionError, match="crossed notebook scope"):
        asyncio.run(
            service.retrieve(
                decision=_decision(),
                query="ordinary question",
                query_language=LanguageCode("en"),
                limit=2,
            )
        )

    assert store.authorized_pages == [("0", "1")]


@pytest.mark.parametrize("limit", [0, 1001])
def test_sparse_rejects_result_limits_outside_governed_bounds(limit: int) -> None:
    service = AuthorizedMultilingualSparseRetrievalV2(
        source_enumerator=_PagedEnumerator(), store=_SparseStore(), generation_id=UUID(int=5)
    )
    with pytest.raises(ValueError, match="governed bounds"):
        asyncio.run(
            service.retrieve_authorized_multilingual_sparse(
                decision=_decision(),
                plan=SimpleNamespace(query="ordinary question", position=PositionalScopeV2()),
                limit=limit,
            )
        )


def test_v2_semantic_page_index_is_migrated_for_existing_store(tmp_path: Path) -> None:
    database = tmp_path / "index-migration.db"

    async def open_store() -> None:
        store = SQLiteStore(database)
        await store.open()
        await store.close()

    asyncio.run(open_store())
    with sqlite3.connect(database) as db:
        db.execute("DROP INDEX idx_language_text_projection_v2_page")
        db.execute("INSERT OR IGNORE INTO schema_versions VALUES (16, 'fixture')")
        db.execute("DELETE FROM schema_versions WHERE version>16")
        db.commit()
    asyncio.run(open_store())
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (17,)
        indexes = {
            row[1] for row in db.execute("PRAGMA index_list(language_text_projection_rows_v2)")
        }
        assert "idx_language_text_projection_v2_page" in indexes
        plan = tuple(
            row[3]
            for row in db.execute(
                "EXPLAIN QUERY PLAN SELECT payload,payload_hash "
                "FROM language_text_projection_rows_v2 "
                "WHERE notebook_id=? AND generation_id=? "
                "ORDER BY evidence_reference_digest,representation_reference_id LIMIT ? OFFSET ?",
                ("notebook", "generation", 2000, 0),
            )
        )
        assert not any("TEMP B-TREE FOR ORDER BY" in step for step in plan)
