"""Source-local parent candidate-promotion contract."""

from typing import Protocol, runtime_checkable

from mnemo.models import ScoredChunk

from .types import ParentPromotionCapabilities


@runtime_checkable
class ParentPromotionInterfaceV1(Protocol):  # pragma: no cover
    """Promote one bounded source-local retrieval stream to canonical parents."""

    @property
    def promotion_mode(self) -> str:
        """Return the stable promotion capability identifier."""
        ...

    def capabilities(self) -> ParentPromotionCapabilities:
        """Return immutable descriptive promotion capabilities."""
        ...

    async def promote(
        self,
        candidates: tuple[ScoredChunk, ...],
    ) -> tuple[ScoredChunk, ...]:
        """Return a deterministic single-pass promotion of one source stream."""
        ...


ParentPromotionInterface = ParentPromotionInterfaceV1
