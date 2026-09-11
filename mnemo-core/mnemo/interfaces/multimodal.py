"""Provider-neutral Phase 8.5.8 multimodal and Final-QA V2 interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models import FrozenMetadata
from mnemo.models.final_qa_execution import (
    FinalQAExecutionSnapshotPhase,
    FinalQAExecutionState,
)
from mnemo.models.multimodal import (
    EvidenceCandidateV2,
    EvidenceCitationV2,
    FinalQAExecutionSnapshotV2,
    FinalQAExecutionV2,
    FinalQARequestV2,
    FinalQAResultV2,
    MultimodalGenerationRequestV1,
    MultimodalGenerationResultV1,
    MultimodalProviderCapabilitiesV1,
)


@runtime_checkable
class EvidenceAuthorizerV2(Protocol):  # pragma: no cover
    async def authorize_evidence(
        self, actor_id: UUID, notebook_id: UUID, candidate: EvidenceCandidateV2
    ) -> bool: ...

    async def generation_is_active(self, candidate: EvidenceCandidateV2) -> bool: ...


@runtime_checkable
class MultimodalCandidateRerankerV1(Protocol):  # pragma: no cover
    async def score(
        self, query: str, candidates: tuple[EvidenceCandidateV2, ...]
    ) -> FrozenMetadata: ...


@runtime_checkable
class MultimodalProviderV1(Protocol):  # pragma: no cover
    def capabilities(self) -> MultimodalProviderCapabilitiesV1: ...

    async def complete(
        self, request: MultimodalGenerationRequestV1
    ) -> MultimodalGenerationResultV1: ...


@runtime_checkable
class FinalQAExecutionStoreV2(Protocol):  # pragma: no cover
    async def create_final_qa_v2_execution(self, execution: FinalQAExecutionV2) -> bool: ...

    async def get_final_qa_v2_execution(
        self, assistant_turn_id: UUID
    ) -> FinalQAExecutionV2 | None: ...

    async def put_final_qa_v2_snapshot(self, snapshot: FinalQAExecutionSnapshotV2) -> None: ...

    async def get_final_qa_v2_snapshot(
        self, execution_id: UUID, phase: FinalQAExecutionSnapshotPhase
    ) -> FinalQAExecutionSnapshotV2 | None: ...

    async def transition_final_qa_v2_execution(
        self,
        execution_id: UUID,
        expected: FinalQAExecutionState,
        target: FinalQAExecutionState,
        *,
        retry_count: int | None = None,
        failure_classification: str | None = None,
    ) -> bool: ...

    async def put_final_qa_v2_citations(
        self, citations: tuple[EvidenceCitationV2, ...]
    ) -> None: ...


@runtime_checkable
class FinalQAInterfaceV2(Protocol):  # pragma: no cover
    async def execute(self, request: FinalQARequestV2) -> FinalQAResultV2: ...
