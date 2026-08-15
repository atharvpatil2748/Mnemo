"""Deterministic multi-source retrieval orchestration contract."""

from typing import Protocol, runtime_checkable

from mnemo.models import RetrievalFusionResult, RetrievalPlan


@runtime_checkable
class MultiSourceRetrievalInterfaceV1(Protocol):  # pragma: no cover
    """Execute, promote, and fuse one bounded retrieval plan."""

    async def execute(
        self,
        plan: RetrievalPlan,
        *,
        global_limit: int,
    ) -> RetrievalFusionResult:
        """Return deterministic globally ranked evidence for one plan."""
        ...


MultiSourceRetrievalInterface = MultiSourceRetrievalInterfaceV1
