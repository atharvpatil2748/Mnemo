"""Production, fail-closed adapters for the active Full Multilingual V2 runtime."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid5

from mnemo.models._shared import FrozenMetadata
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    EvidenceRepresentation,
    RetrievalPathEvidenceV2,
    advanced_candidate_id,
)
from mnemo.models.multilingual import LanguageEvidenceReferenceV3
from mnemo.models.multilingual_reranking import (
    AuthorizedRerankerEvidenceV1,
    CandidateProvenanceV1,
)
from mnemo.models.text_representations import RepresentationAuthority
from mnemo.models.v2_evidence_resolution import (
    AuthorizedV2EvidenceResolutionV1,
    V2AuthorizedEvidenceHandleV1,
    V2CandidateRuntimeSecurityBindingV1,
    V2GenerationSetBindingV1,
    V2RepresentationResolutionState,
    V2SemanticEvidenceRecordV1,
    V2TransformationLineageV1,
)
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1
from mnemo.phase85.v2_database_identity import GovernedV2DatabaseIdentityVerifier
from mnemo.phase85.v2_evaluation_runtime import V2RuntimeIdentityV1
from mnemo.phase85.v2_readiness import V2GenerationCapability, V2GenerationEvidence
from mnemo.retrieval.full_multilingual_v2 import MultilingualV2RetrievalCandidate
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore

_RESOLUTION_NAMESPACE = UUID("5a5df9f3-8e13-54c0-9008-e4193ac5d8e0")
_CANDIDATE_NAMESPACE = UUID("7bc24f65-22ee-5c8b-a4d8-722017f20606")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class GovernedActiveV2GenerationInspector:
    """Reconcile the dynamic active alias with immutable build evidence."""

    def __init__(
        self,
        *,
        store: SQLiteV2ReadOnlyRuntimeStore,
        verifier: GovernedV2DatabaseIdentityVerifier,
        identity: V2RuntimeIdentityV1,
    ) -> None:
        self._store = store
        self._verifier = verifier
        self._identity = identity

    async def inspect_active_v2_generations(
        self, generation_ids: tuple[UUID, ...]
    ) -> tuple[V2GenerationEvidence, ...]:
        active = await self._store.resolve_active_multilingual_v2_generation_set()
        alias_digest = await self._store.resolve_active_multilingual_v2_alias_digest()
        if (
            active is None
            or active != generation_ids
            or alias_digest != self._identity.alias_set_digest
        ):
            raise RuntimeError("ACTIVE_GENERATION_MISMATCH")
        self._verifier.verify(expected_database_identity=self._identity.database_identity)
        evidence = await self._store.inspect_active_v2_generations(generation_ids)
        binding = self._verifier.resolve_vector_embedding_generation(
            active_generation_ids=generation_ids,
            expected_database_identity=self._identity.database_identity,
        )
        by_capability = {item.capability: item for item in evidence}
        if (
            binding.embedding_generation_id
            != by_capability[V2GenerationCapability.MULTILINGUAL_EMBEDDING].generation_id
            or binding.vector_generation_id
            != by_capability[V2GenerationCapability.MULTILINGUAL_VECTOR].generation_id
            or binding.build_run_id != self._identity.build_run_id
            or binding.vector_space_identity != self._identity.vector_space_identity
        ):
            raise RuntimeError("ACTIVE_GENERATION_DEPENDENCY_MISMATCH")
        return evidence


class AuthorizedV2SourceStorageEnumerator:
    """Enumerate semantic identities only inside one immutable V2 decision."""

    def __init__(
        self,
        *,
        store: SQLiteV2ReadOnlyRuntimeStore,
        generations: V2GenerationSetBindingV1,
        identity: V2RuntimeIdentityV1,
        model_identity: str,
    ) -> None:
        self._store = store
        self._generations = generations
        self._identity = identity
        self._model_identity = model_identity
        self._handles: dict[tuple[str, str], V2AuthorizedEvidenceHandleV1] = {}

    def runtime_security(
        self, decision: V2RetrievalAuthorizationDecisionV1
    ) -> V2CandidateRuntimeSecurityBindingV1:
        runtime = decision.runtime_binding
        expected = (
            self._identity.alias_set_digest,
            self._generations.ordered_ids,
            self._identity.profile_fingerprint,
            self._identity.vector_space_identity,
            self._identity.database_identity,
            self._identity.build_run_id,
        )
        actual = (
            runtime.alias_set_digest,
            runtime.generation_ids,
            runtime.profile_fingerprint,
            runtime.vector_space_identity,
            runtime.database_identity,
            runtime.build_run_id,
        )
        if actual != expected:
            raise PermissionError("AUTHORIZATION_RUNTIME_MISMATCH")
        return V2CandidateRuntimeSecurityBindingV1(
            authorization_decision=decision,
            generations=self._generations,
            profile_id=self._identity.profile_id,
            model_identity=self._model_identity,
        )

    async def enumerate_authorized_v2_evidence(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        generations: V2GenerationSetBindingV1,
        limit: int,
    ) -> tuple[V2AuthorizedEvidenceHandleV1, ...]:
        if generations != self._generations:
            raise PermissionError("GENERATION_MISMATCH")
        security = self.runtime_security(decision)
        rows = await self._store.list_authorized_v2_semantic_rows(
            decision=decision,
            generation_id=generations.language_text_generation_id,
            limit=limit,
        )
        handles = tuple(
            V2AuthorizedEvidenceHandleV1(
                source_reference=row.source,
                representation_reference=row.representation,
                language_observation_references=row.language_observation_references,
                script_observation_references=row.script_observation_references,
                semantic_generation_id=row.generation_id,
                runtime_security=security,
            )
            for row in rows
        )
        for handle in handles:
            key = decision.decision_fingerprint, handle.source_reference.identity_digest
            self._handles[key] = handle
        return handles

    async def enumerate_authorized_multilingual_sources(
        self, *, decision: V2RetrievalAuthorizationDecisionV1, limit: int
    ) -> tuple[LanguageEvidenceReferenceV3, ...]:
        handles = await self.enumerate_authorized_v2_evidence(
            decision=decision, generations=self._generations, limit=limit
        )
        by_digest = {
            item.source_reference.identity_digest: item.source_reference for item in handles
        }
        return tuple(by_digest[key] for key in sorted(by_digest))

    async def resolve_handle(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        source: LanguageEvidenceReferenceV3,
    ) -> V2AuthorizedEvidenceHandleV1:
        self.runtime_security(decision)
        key = (decision.decision_fingerprint, source.identity_digest)
        handle = self._handles.get(key)
        if handle is None:
            await self.enumerate_authorized_v2_evidence(
                decision=decision, generations=self._generations, limit=10_000
            )
            handle = self._handles.get(key)
        if handle is None or handle.source_reference != source:
            raise PermissionError("EVIDENCE_UNAUTHORIZED")
        return handle


class AuthorizedV2EvidenceResolver:
    """Resolve exact semantic text and lineage through governed storage reads."""

    def __init__(self, *, store: SQLiteV2ReadOnlyRuntimeStore) -> None:
        self._store = store

    async def resolve_v2_evidence(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        handle: V2AuthorizedEvidenceHandleV1,
    ) -> AuthorizedV2EvidenceResolutionV1:
        if handle.runtime_security.authorization_decision_fingerprint != (
            decision.decision_fingerprint
        ):
            raise PermissionError("AUTHORIZATION_SCOPE_MISMATCH")
        row = await self._store.get_authorized_v2_semantic_row(
            decision=decision,
            generation_id=handle.semantic_generation_id,
            evidence_reference_digest=handle.source_reference.identity_digest,
            representation_reference_id=handle.representation_reference.reference_id,
        )
        if (
            row is None
            or row.source != handle.source_reference
            or row.representation != (handle.representation_reference)
        ):
            raise LookupError("SEMANTIC_TEXT_MISSING")
        lineage = None
        state = V2RepresentationResolutionState.CANONICAL
        if row.representation.representation_authority is (
            RepresentationAuthority.REPRESENTATION_DERIVED
        ):
            transformation = await self._store.get_authorized_v2_transformation(
                decision=decision,
                output_reference_id=row.representation.reference_id,
            )
            if transformation is None:
                raise LookupError("EVIDENCE_LINEAGE_INVALID")
            state = V2RepresentationResolutionState.DERIVED
            lineage = V2TransformationLineageV1(
                transformation_profile_identity=transformation.transformation_profile.profile_id,
                transformation_version=transformation.transformation_profile.provider_revision,
                transformation_digest=transformation.provenance.profile_configuration_digest,
                source_representation=transformation.source_representation.representation_type,
                target_representation=transformation.target_representation_type,
                transformation_derivation_identity=transformation.transformation_id,
                source_reference_digest=(
                    transformation.source_representation.evidence_reference.identity_digest
                ),
                source_generation_ids=transformation.source_generation_ids,
            )
        record = V2SemanticEvidenceRecordV1(
            handle=handle,
            semantic_text=row.text,
            semantic_text_content_hash=row.text_hash,
            representation_state=state,
            representation_observation_reference=(row.representation.representation_observation_id),
            transformation_lineage=lineage,
            position=row.position,
        )
        request = _digest(
            {
                "authorization": decision.decision_fingerprint,
                "source": handle.source_reference.identity_digest,
                "representation": str(handle.representation_reference.reference_id),
            }
        )
        return AuthorizedV2EvidenceResolutionV1.create(
            resolution_identity=uuid5(_RESOLUTION_NAMESPACE, request),
            request_fingerprint=request,
            record=record,
        )


class GovernedV2CandidateProjector:
    """Single V2 bridge into the shared reranker and advanced-candidate contracts."""

    def __init__(
        self,
        *,
        enumerator: AuthorizedV2SourceStorageEnumerator,
        resolver: AuthorizedV2EvidenceResolver,
        store: SQLiteV2ReadOnlyRuntimeStore,
    ) -> None:
        self._enumerator = enumerator
        self._resolver = resolver
        self._store = store

    async def resolve_reranker_evidence(
        self,
        *,
        source: LanguageEvidenceReferenceV3,
        decision: V2RetrievalAuthorizationDecisionV1,
        retrieval_paths: tuple[str, ...],
        fusion_rank: int,
    ) -> AuthorizedRerankerEvidenceV1:
        handle = await self._enumerator.resolve_handle(decision=decision, source=source)
        resolution = await self._resolver.resolve_v2_evidence(decision=decision, handle=handle)
        return await self.project_authorized_v2_evidence(
            resolution=resolution,
            retrieval_paths=retrieval_paths,
            fusion_rank=fusion_rank,
        )

    async def project_authorized_v2_evidence(
        self,
        *,
        resolution: AuthorizedV2EvidenceResolutionV1,
        retrieval_paths: tuple[str, ...] = ("governed_v2",),
        fusion_rank: int = 1,
    ) -> AuthorizedRerankerEvidenceV1:
        security = resolution.runtime_security
        if not retrieval_paths or len(set(retrieval_paths)) != len(retrieval_paths):
            raise ValueError("CANDIDATE_INVALID")
        provenance = CandidateProvenanceV1(
            source_reference_digest=resolution.source_reference.identity_digest,
            representation_reference_id=resolution.representation_reference.reference_id,
            authorization_scope_digest=security.authorization_decision_fingerprint,
            retrieval_snapshot_identity=resolution.resolution_fingerprint,
            retrieval_paths_digest=_digest(sorted(retrieval_paths)),
            fusion_policy_id="reciprocal-rank-fusion-k60-v2",
            fusion_rank=fusion_rank,
            source_generation_ids=security.generations.ordered_ids,
        )
        candidate_key = _digest(
            {"resolution": resolution.resolution_fingerprint, "rank": fusion_rank}
        )
        heading_path: tuple[str, ...] = ()
        if resolution.position is not None:
            heading_path = tuple(resolution.position.heading_path)
        return AuthorizedRerankerEvidenceV1(
            candidate_id=uuid5(_CANDIDATE_NAMESPACE, candidate_key),
            source_reference=resolution.source_reference,
            representation_reference=resolution.representation_reference,
            semantic_text=resolution.semantic_text,
            title_metadata=resolution.title_metadata,
            language_observation_references=(
                resolution.record.handle.language_observation_references
            ),
            script_observation_references=(resolution.record.handle.script_observation_references),
            provenance=provenance,
            runtime_security=security,
            heading_path=heading_path,
        )

    async def project_advanced_candidate(
        self,
        *,
        value: MultilingualV2RetrievalCandidate,
        decision: V2RetrievalAuthorizationDecisionV1,
    ) -> AdvancedRetrievalCandidate:
        candidate = value.candidate
        security = candidate.runtime_security
        if security is None or security.authorization_decision_fingerprint != (
            decision.decision_fingerprint
        ):
            raise PermissionError("CANDIDATE_INVALID")
        source = candidate.source_reference
        chunk = None
        if source.chunk_id is not None:
            chunk = await self._store.get_authorized_v2_chunk(
                decision=decision, chunk_id=source.chunk_id
            )
            if chunk is None:
                raise LookupError("EVIDENCE_LINEAGE_INVALID")
        locator = FrozenMetadata(
            {
                "evidence_reference_digest": source.identity_digest,
                "representation_reference_id": str(candidate.representation_reference.reference_id),
                "authorization_decision_fingerprint": decision.decision_fingerprint,
                "active_alias_set_identity": security.active_alias_set_identity,
                "database_identity": security.database_identity,
                "vector_space_identity": security.vector_space_identity,
                "generation_ids": [str(item) for item in security.generations.ordered_ids],
            }
        )
        return AdvancedRetrievalCandidate(
            candidate_id=advanced_candidate_id(
                representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
                document_id=source.document_id,
                version_id=source.version_id,
                chunk_id=None if chunk is None else chunk.id,
                occurrence_id=source.occurrence_id,
                derivation_id=source.derivation_id,
            ),
            notebook_id=source.notebook_id,
            source_id=source.source_id,
            document_id=source.document_id,
            version_id=source.version_id,
            representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
            chunk=chunk,
            occurrence_id=source.occurrence_id,
            derivation_id=source.derivation_id,
            locator=locator,
            document_title=None,
            content=candidate.semantic_text,
            paths=tuple(
                RetrievalPathEvidenceV2(path=path, source_rank=value.final_rank, source_score=None)
                for path in value.source_paths
            ),
            fused_score=value.fused_score,
            final_rank=value.final_rank,
        )
