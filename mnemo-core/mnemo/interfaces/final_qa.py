"""Additive final-QA orchestration contract."""

from typing import Protocol, runtime_checkable

from mnemo.models.final_qa import FinalQARequest, FinalQAResult


@runtime_checkable
class FinalQAInterfaceV1(Protocol):  # pragma: no cover
    async def execute(self, request: FinalQARequest) -> FinalQAResult: ...


FinalQAInterface = FinalQAInterfaceV1
