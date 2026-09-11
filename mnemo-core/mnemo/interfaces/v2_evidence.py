"""Ports for bounded Full Multilingual V2 evidence enumeration and resolution."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mnemo.models.advanced_retrieval import AdvancedRetrievalCandidate
from mnemo.models.v2_evidence_resolution import (
    AuthorizedV2EvidenceResolutionV1,
    V2AuthorizedEvidenceHandleV1,
    V2GenerationSetBindingV1,
    V2SemanticEvidenceRecordV1,
)
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1


@runtime_checkable
class V2AuthorizedEvidenceStoreV1(Protocol):  # pragma: no cover
    """Storage-owned exact reads; callers never receive database implementation details."""

    async def enumerate_authorized_v2_evidence(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        generations: V2GenerationSetBindingV1,
        limit: int,
    ) -> tuple[V2AuthorizedEvidenceHandleV1, ...]: ...

    async def resolve_authorized_v2_semantic_evidence(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        handle: V2AuthorizedEvidenceHandleV1,
    ) -> V2SemanticEvidenceRecordV1 | None: ...


@runtime_checkable
class AuthorizedV2EvidenceResolverV1(Protocol):  # pragma: no cover
    """Application adapter that revalidates an exact storage record under one decision."""

    async def resolve_v2_evidence(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        handle: V2AuthorizedEvidenceHandleV1,
    ) -> AuthorizedV2EvidenceResolutionV1: ...


@runtime_checkable
class GovernedV2CandidateProjectorV1(Protocol):  # pragma: no cover
    """Project only a complete authorized resolution; never reconstruct authorization."""

    async def project_authorized_v2_evidence(
        self,
        *,
        resolution: AuthorizedV2EvidenceResolutionV1,
    ) -> AdvancedRetrievalCandidate: ...
