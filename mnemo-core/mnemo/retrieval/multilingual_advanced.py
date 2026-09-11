"""Adapter from governed multilingual retrieval to the shared HTTP/MCP evidence path."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalSourceV1, AdvancedSourcePage
from mnemo.models import FrozenMetadata
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    RetrievalPathEvidenceV2,
    RetrievalPlanV2,
    advanced_candidate_id,
)
from mnemo.models.multilingual import (
    LanguageCode,
    LanguageProviderProfile,
    MultilingualCandidate,
)
from mnemo.retrieval.multilingual import MultilingualRetrievalPlanner, MultilingualRetrievalService


class MultilingualAdvancedSourceV2:
    """Expose multilingual ranked retrieval only behind an active generation gate."""

    def __init__(
        self,
        *,
        planner: MultilingualRetrievalPlanner,
        service: MultilingualRetrievalService,
        dense_profile: LanguageProviderProfile,
        target_languages: tuple[LanguageCode, ...],
        exhaustive_fallback: AdvancedRetrievalSourceV1,
    ) -> None:
        if not target_languages or len(set(target_languages)) != len(target_languages):
            raise ValueError("target_languages must be non-empty and unique")
        if exhaustive_fallback.representation is not EvidenceRepresentation.MULTILINGUAL_TEXT:
            raise ValueError("multilingual exhaustive fallback owns the wrong representation")
        self._planner = planner
        self._service = service
        self._dense_profile = dense_profile
        self._target_languages = target_languages
        self._exhaustive = exhaustive_fallback

    @property
    def representation(self) -> EvidenceRepresentation:
        return EvidenceRepresentation.MULTILINGUAL_TEXT

    async def retrieve(
        self, plan: RetrievalPlanV2, *, offset: int, limit: int
    ) -> AdvancedSourcePage:
        if plan.mode is AdvancedRetrievalMode.EXHAUSTIVE:
            return await self._exhaustive.retrieve(plan, offset=offset, limit=limit)
        if offset != 0:
            raise ValueError("ranked multilingual retrieval does not support offsets")
        multilingual_plan = await self._planner.plan(
            actor_id=_actor_from_plan(plan),
            notebook_id=plan.scope.notebook_id,
            query=plan.query,
            base_plan=plan,
            target_languages=self._target_languages,
            dense_profile=self._dense_profile,
            translation_profile=None,
            transliteration_enabled=True,
        )
        result = await self._service.execute(multilingual_plan)
        candidates = tuple(_advanced_candidate(item) for item in result.candidates[:limit])
        snapshot = hashlib.sha256(
            json.dumps(
                {
                    "plan": plan.fingerprint,
                    "profile": self._dense_profile.configuration_digest,
                    "candidates": [str(item.candidate_id) for item in candidates],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity=snapshot,
            candidates=candidates,
            examined=_metadata_int(result.diagnostics.get("recalled"), len(candidates)),
            next_offset=None,
            exhausted=True,
        )

    async def expand(
        self,
        plan: RetrievalPlanV2,
        seeds: tuple[AdvancedRetrievalCandidate, ...],
        *,
        limit: int,
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        del plan, seeds, limit
        return ()


def _actor_from_plan(plan: RetrievalPlanV2) -> UUID:
    if plan.security_scope_identity is None:
        raise ValueError("multilingual transport requires a server-owned security scope")
    return UUID(plan.security_scope_identity)


def _advanced_candidate(item: MultilingualCandidate) -> AdvancedRetrievalCandidate:
    source = item.candidate
    derived_identity = item.match_embedding_id or item.match_derivation_id or source.derivation_id
    if derived_identity is None:
        raise ValueError("multilingual candidate lacks derived match provenance")
    paths = tuple(
        RetrievalPathEvidenceV2(
            path=f"{selection.path.value}:{selection.target_language.value}",
            source_rank=_metadata_int(
                item.source_ranks[f"{selection.path.value}:{selection.target_language.value}"],
                1,
            ),
            source_score=item.fused_score,
        )
        for selection in item.paths
    )
    return AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
            document_id=source.document_id,
            version_id=source.version_id,
            chunk_id=None,
            occurrence_id=None,
            derivation_id=derived_identity,
        ),
        notebook_id=source.notebook_id,
        source_id=source.source_id,
        document_id=source.document_id,
        version_id=source.version_id,
        representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
        chunk=None,
        occurrence_id=None,
        derivation_id=derived_identity,
        locator=FrozenMetadata(
            {
                "authoritative_evidence_kind": source.kind.value,
                "authoritative_evidence_id": source.authoritative_id,
                "authoritative_chunk_id": source.chunk_id,
                "authoritative_occurrence_id": (
                    None if source.occurrence_id is None else str(source.occurrence_id)
                ),
                "source_derivation_id": (
                    None if source.derivation_id is None else str(source.derivation_id)
                ),
                "match_embedding_id": (
                    None if item.match_embedding_id is None else str(item.match_embedding_id)
                ),
                "match_derivation_id": (
                    None if item.match_derivation_id is None else str(item.match_derivation_id)
                ),
                "evidence_language": item.evidence_language.value,
                "evidence_script": item.evidence_script.value,
            }
        ),
        document_title=source.document_title,
        content=source.content,
        paths=paths,
        fused_score=item.fused_score,
    )


def _metadata_int(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value
