"""Advanced-retrieval adapter over the shared Full Multilingual V2 application path."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalSourceV1, AdvancedSourcePage
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models._shared import FrozenMetadata
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    RetrievalPathEvidenceV2,
    RetrievalPlanV2,
    advanced_candidate_id,
)
from mnemo.models.multilingual import LanguageCode
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1
from mnemo.retrieval.full_multilingual_v2 import (
    FullMultilingualRetrievalApplicationV2,
    MultilingualV2RetrievalCandidate,
)
from mnemo.retrieval.language_detection import LanguageDetectorRegistryV2
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore


@runtime_checkable
class QueryLanguageResolverV2(Protocol):  # pragma: no cover
    async def resolve_query_language(
        self, *, principal: PrincipalContextV1, notebook_id: UUID, query: str
    ) -> LanguageCode: ...


@runtime_checkable
class V2AdvancedCandidateProjector(Protocol):  # pragma: no cover
    async def project_advanced_candidate(
        self,
        *,
        value: MultilingualV2RetrievalCandidate,
        decision: V2RetrievalAuthorizationDecisionV1,
    ) -> AdvancedRetrievalCandidate: ...


class RegistryQueryLanguageResolverV2:
    """Resolve a query language without converting script into a language claim."""

    def __init__(self, registry: LanguageDetectorRegistryV2) -> None:
        self._registry = registry

    async def resolve_query_language(
        self, *, principal: PrincipalContextV1, notebook_id: UUID, query: str
    ) -> LanguageCode:
        observation = await self._registry.detect(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            target_id=hashlib.sha256(query.encode("utf-8")).hexdigest(),
            text=query,
        )
        supported = tuple(item for item in observation.hypotheses if item.language.value != "und")
        if observation.mixed_language or len(supported) != 1:
            return LanguageCode("und")
        return supported[0].language


class FullMultilingualAdvancedSourceV2:
    """Expose V2 through stable contracts only after normal engine composition."""

    def __init__(
        self,
        *,
        application: FullMultilingualRetrievalApplicationV2,
        query_language_resolver: QueryLanguageResolverV2,
        projector: V2AdvancedCandidateProjector,
        exhaustive_fallback: AdvancedRetrievalSourceV1,
        alias_set_digest: str | None = None,
        exhaustive_store: SQLiteV2ReadOnlyRuntimeStore | None = None,
        language_text_generation_id: UUID | None = None,
    ) -> None:
        if not isinstance(query_language_resolver, QueryLanguageResolverV2):
            raise TypeError("query language resolver does not implement V2 contract")
        if not isinstance(projector, V2AdvancedCandidateProjector):
            raise TypeError("advanced candidate projector does not implement V2 contract")
        if exhaustive_fallback.representation is not EvidenceRepresentation.MULTILINGUAL_TEXT:
            raise ValueError("multilingual exhaustive fallback owns the wrong representation")
        self._application = application
        self._query_language_resolver = query_language_resolver
        self._projector = projector
        self._exhaustive_fallback = exhaustive_fallback
        self.alias_set_digest = alias_set_digest
        self._exhaustive_store = exhaustive_store
        self._language_text_generation_id = language_text_generation_id

    @property
    def representation(self) -> EvidenceRepresentation:
        return EvidenceRepresentation.MULTILINGUAL_TEXT

    async def retrieve(
        self, plan: RetrievalPlanV2, *, offset: int, limit: int
    ) -> AdvancedSourcePage:
        if plan.mode is AdvancedRetrievalMode.EXHAUSTIVE:
            if self._exhaustive_store is not None:
                raise PermissionError(
                    "Full V2 exhaustive traversal requires principal authorization"
                )
            return await self._exhaustive_fallback.retrieve(plan, offset=offset, limit=limit)
        raise PermissionError("V2 ranked retrieval requires the server-owned principal entry point")

    async def retrieve_authorized(
        self,
        *,
        principal: PrincipalContextV1,
        plan: RetrievalPlanV2,
        offset: int,
        limit: int,
    ) -> AdvancedSourcePage:
        if plan.mode is AdvancedRetrievalMode.EXHAUSTIVE:
            if self._exhaustive_store is not None:
                return await self._retrieve_exhaustive_authorized(
                    principal=principal, plan=plan, offset=offset, limit=limit
                )
            return await self._exhaustive_fallback.retrieve(plan, offset=offset, limit=limit)
        if offset != 0:
            raise ValueError("ranked Full Multilingual V2 retrieval does not support offsets")
        query_language = await self._query_language_resolver.resolve_query_language(
            principal=principal,
            notebook_id=plan.scope.notebook_id,
            query=plan.query,
        )
        result = await self._application.retrieve(
            principal=principal,
            plan=plan,
            query_language=query_language,
        )
        candidates = tuple(
            [await self._project_and_validate(item) for item in result.candidates[:limit]]
        )
        snapshot_identity = hashlib.sha256(
            json.dumps(
                {
                    "application_service_id": self._application.application_service_id,
                    "alias_set_digest": self.alias_set_digest,
                    "plan": plan.fingerprint,
                    "candidate_ids": [str(item.candidate_id) for item in candidates],
                    "omissions": result.omissions,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity=snapshot_identity,
            candidates=candidates,
            examined=result.dense_examined + result.sparse_examined,
            next_offset=None,
            exhausted=True,
        )

    async def _retrieve_exhaustive_authorized(
        self, *, principal: PrincipalContextV1, plan: RetrievalPlanV2, offset: int, limit: int
    ) -> AdvancedSourcePage:
        store = self._exhaustive_store
        generation_id = self._language_text_generation_id
        if store is None or generation_id is None or self.alias_set_digest is None:
            raise RuntimeError("Full V2 exhaustive source is not composed")
        decision = await self._application.authorize_only(principal=principal, plan=plan)
        rows = await store.list_authorized_v2_semantic_rows(
            decision=decision, generation_id=generation_id, offset=offset, limit=limit + 1
        )
        candidates: list[AdvancedRetrievalCandidate] = []
        for index, row in enumerate(rows[:limit], 1):
            source = row.source
            chunk = (
                None
                if source.chunk_id is None
                else await store.get_authorized_v2_chunk(
                    decision=decision, chunk_id=source.chunk_id
                )
            )
            if source.chunk_id is not None and chunk is None:
                raise LookupError("V2 canonical chunk lineage is unavailable")
            candidates.append(
                AdvancedRetrievalCandidate(
                    candidate_id=advanced_candidate_id(
                        representation=self.representation,
                        document_id=source.document_id,
                        version_id=source.version_id,
                        chunk_id=source.chunk_id,
                        occurrence_id=source.occurrence_id,
                        derivation_id=source.derivation_id,
                        evidence_id=source.evidence_id,
                    ),
                    notebook_id=source.notebook_id,
                    source_id=source.source_id,
                    document_id=source.document_id,
                    version_id=source.version_id,
                    representation=self.representation,
                    chunk=chunk,
                    occurrence_id=source.occurrence_id,
                    derivation_id=source.derivation_id,
                    evidence_id=source.evidence_id,
                    locator=FrozenMetadata(
                        {
                            "evidence_id": (
                                None if source.evidence_id is None else str(source.evidence_id)
                            ),
                            "evidence_kind": source.kind.value,
                            "representation_reference_id": str(row.representation.reference_id),
                            "generation_id": str(generation_id),
                            "active_alias_set_identity": self.alias_set_digest,
                            "database_identity": decision.runtime_binding.database_identity,
                        }
                    ),
                    document_title=None,
                    content=row.text,
                    paths=(
                        RetrievalPathEvidenceV2(
                            path="active-full-v2-semantic-projection",
                            source_rank=offset + index,
                            source_score=None,
                        ),
                    ),
                )
            )
        snapshot = hashlib.sha256(
            json.dumps(
                {
                    "alias": self.alias_set_digest,
                    "generation": str(generation_id),
                    "database": decision.runtime_binding.database_identity,
                    "plan": plan.fingerprint,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        has_more = len(rows) > limit
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity=snapshot,
            candidates=tuple(candidates),
            examined=len(rows),
            next_offset=offset + limit if has_more else None,
            exhausted=not has_more,
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

    async def _project_and_validate(
        self, value: MultilingualV2RetrievalCandidate
    ) -> AdvancedRetrievalCandidate:
        projected = await self._projector.project_advanced_candidate(
            value=value, decision=value.authorization_decision
        )
        if value.candidate.provenance.authorization_scope_digest != (
            value.authorization_decision.decision_fingerprint
        ):
            raise ValueError("V2 candidate lost its authorization decision binding")
        source = value.candidate.source_reference
        locator = dict(projected.locator)
        if (
            projected.notebook_id != source.notebook_id
            or projected.source_id != source.source_id
            or projected.document_id != source.document_id
            or projected.version_id != source.version_id
            or projected.representation is not EvidenceRepresentation.MULTILINGUAL_TEXT
            or projected.content != value.candidate.semantic_text
            or locator.get("evidence_reference_digest") != source.identity_digest
            or locator.get("representation_reference_id")
            != str(value.candidate.representation_reference.reference_id)
        ):
            raise ValueError("V2 advanced candidate projection lost identity or semantic text")
        return projected
