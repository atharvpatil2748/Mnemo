"""Additive ADR-0056 persisted Final-QA execution-store contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models.final_qa_execution import (
    FinalQAExecution,
    FinalQAExecutionSnapshot,
    FinalQAExecutionSnapshotPhase,
    FinalQAExecutionState,
)


@runtime_checkable
class FinalQAExecutionStoreV1(Protocol):
    async def create_final_qa_execution(self, execution: FinalQAExecution) -> bool: ...

    async def get_final_qa_execution(self, assistant_turn_id: UUID) -> FinalQAExecution | None: ...

    async def put_final_qa_execution_snapshot(self, snapshot: FinalQAExecutionSnapshot) -> None: ...

    async def get_final_qa_execution_snapshot(
        self, execution_id: UUID, phase: FinalQAExecutionSnapshotPhase
    ) -> FinalQAExecutionSnapshot | None: ...

    async def transition_final_qa_execution(
        self,
        execution_id: UUID,
        expected: FinalQAExecutionState,
        target: FinalQAExecutionState,
        *,
        retry_count: int | None = None,
        failure_classification: str | None = None,
    ) -> bool: ...
