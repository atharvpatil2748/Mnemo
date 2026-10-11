"""Full V2 exhaustive traversal reads authorized typed projection rows."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from mnemo.models.advanced_retrieval import EvidenceRepresentation
from mnemo.retrieval.full_multilingual_advanced_v2 import (
    FullMultilingualAdvancedSourceV2,
    RegistryQueryLanguageResolverV2,
)


@pytest.mark.anyio
async def test_exhaustive_full_v2_preserves_distinct_derived_rows_and_terminal_page() -> None:
    notebook, source_id, document, version, occurrence, derivation = (uuid4() for _ in range(6))
    generation = uuid4()
    evidence_ids = (uuid4(), uuid4())
    rows = [
        SimpleNamespace(
            source=SimpleNamespace(
                notebook_id=notebook,
                source_id=source_id,
                document_id=document,
                version_id=version,
                chunk_id=None,
                occurrence_id=occurrence,
                derivation_id=derivation,
                evidence_id=evidence_id,
                kind=SimpleNamespace(value="ocr_region"),
            ),
            representation=SimpleNamespace(reference_id=uuid4()),
            text=text,
        )
        for evidence_id, text in zip(evidence_ids, ("Chip thickness", "Rake face"), strict=True)
    ]
    decision = SimpleNamespace(runtime_binding=SimpleNamespace(database_identity="d" * 64))

    class Application:
        async def authorize_only(self, *, principal: object, plan: object) -> object:
            assert principal is not None and plan is not None
            return decision

    class Store:
        async def list_authorized_v2_semantic_rows(self, **kwargs: object) -> object:
            assert kwargs["decision"] is decision
            assert kwargs["generation_id"] == generation
            assert kwargs["limit"] == 2
            return rows[kwargs["offset"] : kwargs["offset"] + kwargs["limit"]]

        async def get_authorized_v2_chunk(self, **kwargs: object) -> None:
            assert kwargs["decision"] is decision
            return None

    instance = object.__new__(FullMultilingualAdvancedSourceV2)
    instance._application = Application()
    instance._exhaustive_store = Store()
    instance._language_text_generation_id = generation
    instance.alias_set_digest = "a" * 64
    plan = SimpleNamespace(fingerprint="b" * 64)
    first = await instance._retrieve_exhaustive_authorized(
        principal=SimpleNamespace(), plan=plan, offset=0, limit=1
    )
    second = await instance._retrieve_exhaustive_authorized(
        principal=SimpleNamespace(), plan=plan, offset=1, limit=1
    )
    assert first.representation is EvidenceRepresentation.MULTILINGUAL_TEXT
    assert first.next_offset == 1 and not first.exhausted
    assert second.next_offset is None and second.exhausted
    assert first.snapshot_identity == second.snapshot_identity
    assert [page.candidates[0].content for page in (first, second)] == [
        "Chip thickness",
        "Rake face",
    ]
    assert first.candidates[0].candidate_id != second.candidates[0].candidate_id
    assert first.candidates[0].chunk is None
    assert first.candidates[0].locator["active_alias_set_identity"] == "a" * 64
    assert first.candidates[0].locator["evidence_id"] == str(evidence_ids[0])
    assert await instance.expand(plan, first.candidates, limit=1) == ()

    with pytest.raises(RuntimeError, match="not composed"):
        instance._language_text_generation_id = None
        await instance._retrieve_exhaustive_authorized(
            principal=SimpleNamespace(), plan=plan, offset=0, limit=1
        )
    instance._language_text_generation_id = generation
    rows[0].source.chunk_id = uuid4()
    with pytest.raises(LookupError, match="lineage"):
        await instance._retrieve_exhaustive_authorized(
            principal=SimpleNamespace(), plan=plan, offset=0, limit=1
        )


@pytest.mark.anyio
async def test_full_v2_source_requires_principal_and_resolves_language_conservatively() -> None:
    from mnemo.models.advanced_retrieval import AdvancedRetrievalMode

    source = object.__new__(FullMultilingualAdvancedSourceV2)
    source._exhaustive_store = object()
    plan = SimpleNamespace(mode=AdvancedRetrievalMode.EXHAUSTIVE)
    with pytest.raises(PermissionError, match="principal"):
        await source.retrieve(plan, offset=0, limit=1)
    source._exhaustive_store = None

    class Fallback:
        async def retrieve(self, plan: object, *, offset: int, limit: int) -> object:
            assert offset == 2 and limit == 1
            return "fallback-page"

    source._exhaustive_fallback = Fallback()
    assert await source.retrieve(plan, offset=2, limit=1) == "fallback-page"
    assert (
        await source.retrieve_authorized(principal=SimpleNamespace(), plan=plan, offset=2, limit=1)
        == "fallback-page"
    )
    with pytest.raises(PermissionError, match="server-owned principal"):
        await source.retrieve(SimpleNamespace(mode=AdvancedRetrievalMode.RANKED), offset=0, limit=1)

    class Registry:
        mixed = False

        async def detect(self, **kwargs: object) -> object:
            assert kwargs["text"] == "formula"
            return SimpleNamespace(
                mixed_language=self.mixed,
                hypotheses=(SimpleNamespace(language=SimpleNamespace(value="en")),),
            )

    registry = Registry()
    resolver = RegistryQueryLanguageResolverV2(registry)
    principal = SimpleNamespace(actor_id=uuid4())
    assert (
        await resolver.resolve_query_language(
            principal=principal, notebook_id=uuid4(), query="formula"
        )
    ).value == "en"
    registry.mixed = True
    assert (
        await resolver.resolve_query_language(
            principal=principal, notebook_id=uuid4(), query="formula"
        )
    ).value == "und"
