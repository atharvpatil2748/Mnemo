"""Production adapters for Phase 8.5.6 representation-local retrieval."""

from __future__ import annotations

from dataclasses import replace

from mnemo.interfaces import RerankerInterfaceV1, RetrieverInterfaceV1
from mnemo.interfaces.advanced_retrieval import (
    AdvancedCanonicalStoreV1,
    AdvancedSourcePage,
    CanonicalEvidenceRecord,
)
from mnemo.models import FrozenMetadata, MetadataFilter, ScoredChunk
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    ExpansionPolicy,
    RetrievalPathEvidenceV2,
    RetrievalPlanV2,
    advanced_candidate_id,
)


class CanonicalTextAdvancedSource:
    """Adapt canonical V1 ranked retrieval and deterministic SQLite enumeration."""

    def __init__(
        self,
        *,
        store: AdvancedCanonicalStoreV1,
        ranked_retriever: RetrieverInterfaceV1,
    ) -> None:
        if not isinstance(store, AdvancedCanonicalStoreV1):
            raise TypeError("store must implement AdvancedCanonicalStoreV1")
        if not isinstance(ranked_retriever, RetrieverInterfaceV1):
            raise TypeError("ranked_retriever must implement RetrieverInterfaceV1")
        if ranked_retriever.retrieval_mode != "sparse":
            raise ValueError("canonical ranked adapter requires a sparse V1 retriever")
        self._store = store
        self._ranked = ranked_retriever

    @property
    def representation(self) -> EvidenceRepresentation:
        return EvidenceRepresentation.CANONICAL_TEXT

    async def retrieve(
        self, plan: RetrievalPlanV2, *, offset: int, limit: int
    ) -> AdvancedSourcePage:
        snapshot = await self._store.advanced_canonical_snapshot(
            scope=plan.scope, position=plan.position, query=plan.query
        )
        if plan.mode is AdvancedRetrievalMode.RANKED:
            if offset != 0:
                raise ValueError("ranked canonical retrieval does not support offsets")
            scored = await self._ranked.retrieve(
                plan.query,
                None,
                MetadataFilter(
                    notebook_id=plan.scope.notebook_id,
                    source_ids=plan.scope.source_ids,
                ),
                limit,
            )
            records = await self._store.get_advanced_canonical_records(
                scope=plan.scope,
                position=plan.position,
                chunk_ids=tuple(item.chunk.id for item in scored),
            )
            by_chunk = {record.chunk.id: record for record in records}
            candidates: list[AdvancedRetrievalCandidate] = []
            for item in scored:
                record = by_chunk.get(item.chunk.id)
                if record is None:
                    continue
                chunk = item.chunk
                candidates.append(
                    _canonical_candidate(
                        record=replace(record, chunk=chunk),
                        path=item.source,
                        rank=item.rank,
                        score=item.score,
                        title_match=record.title_match
                        or bool(chunk.metadata.get("retrieval_title_match", False)),
                    )
                )
            return AdvancedSourcePage(
                representation=self.representation,
                snapshot_identity=snapshot,
                candidates=tuple(candidates),
                examined=len(scored),
                next_offset=None,
                exhausted=True,
            )

        records = await self._store.enumerate_advanced_canonical(
            scope=plan.scope,
            position=plan.position,
            query=plan.query,
            offset=offset,
            limit=limit + 1,
        )
        has_more = len(records) > limit
        page_records = records[:limit]
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity=snapshot,
            candidates=tuple(
                _canonical_candidate(
                    record=record,
                    path="sqlite-canonical-enumeration",
                    rank=offset + index,
                    score=None,
                    title_match=record.title_match,
                )
                for index, record in enumerate(page_records, 1)
            ),
            examined=len(page_records),
            next_offset=offset + len(page_records) if has_more else None,
            exhausted=not has_more,
        )

    async def expand(
        self,
        plan: RetrievalPlanV2,
        seeds: tuple[AdvancedRetrievalCandidate, ...],
        *,
        limit: int,
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        if limit == 0 or plan.expansion_policy is ExpansionPolicy.NONE:
            return ()
        seed_ids = tuple(item.chunk.id for item in seeds if item.chunk is not None)
        records = await self._store.expand_advanced_canonical(
            scope=plan.scope,
            seed_chunk_ids=seed_ids,
            include_parents=plan.expansion_policy is ExpansionPolicy.PARENT_AND_ADJACENT,
            limit=limit,
        )
        return tuple(
            replace(
                _canonical_candidate(
                    record=record,
                    path="canonical-expansion",
                    rank=index,
                    score=None,
                    title_match=record.title_match,
                ),
                expansion_reason=plan.expansion_policy.value,
            )
            for index, record in enumerate(records, 1)
        )


class CanonicalAdvancedReranker:
    """Adapt the frozen V1 reranker without changing advanced provenance."""

    def __init__(self, reranker: RerankerInterfaceV1) -> None:
        if not isinstance(reranker, RerankerInterfaceV1):
            raise TypeError("reranker must implement RerankerInterfaceV1")
        self._reranker = reranker

    async def rerank(
        self,
        query: str,
        candidates: tuple[AdvancedRetrievalCandidate, ...],
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        canonical = tuple(candidate for candidate in candidates if candidate.chunk is not None)
        if len(canonical) != len(candidates):
            # A V1 text reranker cannot compare non-canonical representations.
            return candidates
        scored = tuple(
            ScoredChunk(
                chunk=candidate.chunk,
                score=candidate.fused_score or 0.0,
                source="advanced-source-rank-fusion",
                rank=index,
            )
            for index, candidate in enumerate(canonical, 1)
            if candidate.chunk is not None
        )
        reranked = await self._reranker.rerank(query, scored, len(scored))
        by_chunk = {
            candidate.chunk.id: candidate for candidate in canonical if candidate.chunk is not None
        }
        return tuple(by_chunk[item.chunk.id] for item in reranked)


def _canonical_candidate(
    *,
    record: CanonicalEvidenceRecord,
    path: str,
    rank: int,
    score: float | None,
    title_match: bool,
) -> AdvancedRetrievalCandidate:
    chunk = record.chunk
    title = record.document_title
    locator = FrozenMetadata(
        {
            "page_number": chunk.position.page_number,
            "section_index": chunk.position.section_index,
            "chunk_index": chunk.position.chunk_index_in_section,
            "start_offset": chunk.position.start_offset,
            "end_offset": chunk.position.end_offset,
            "heading_path": list(chunk.heading_path),
        }
    )
    return AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            chunk_id=chunk.id,
            occurrence_id=None,
            derivation_id=None,
        ),
        notebook_id=record.notebook_id,
        source_id=record.source_id,
        document_id=chunk.document_id,
        version_id=chunk.version_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        chunk=chunk,
        occurrence_id=None,
        derivation_id=None,
        locator=locator,
        document_title=title,
        content=chunk.text,
        paths=(
            RetrievalPathEvidenceV2(
                path=path,
                source_rank=rank,
                source_score=score,
                title_match=title_match,
                parent_promoted=bool(chunk.metadata.get("retrieval_parent_promoted", False)),
            ),
        ),
    )
