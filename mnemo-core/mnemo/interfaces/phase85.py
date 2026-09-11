"""Additive Phase 8.5 runtime and provider-readiness contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mnemo.phase85.models import (
        CapabilityStatus,
        ModelProfileStatus,
        ProviderReadinessResult,
        RuntimeReadiness,
    )
    from mnemo.phase85.profiles import ActiveModelProfileSnapshot


@runtime_checkable
class ProviderReadinessProbeV1(Protocol):  # pragma: no cover
    """Perform provider-owned availability, loadability, and initialization checks."""

    async def probe(self, profile: ModelProfileStatus) -> ProviderReadinessResult: ...


@runtime_checkable
class Phase85RuntimeV1(Protocol):  # pragma: no cover
    """Expose one deterministic Phase 8.5 runtime snapshot and service registry."""

    @property
    def configuration_fingerprint(self) -> str: ...

    @property
    def active_profile(self) -> ActiveModelProfileSnapshot: ...

    def capabilities(self) -> Mapping[str, CapabilityStatus]: ...

    def capability_status(self, capability_id: str) -> CapabilityStatus: ...

    def profiles(self) -> Mapping[str, ModelProfileStatus]: ...

    def profile_status(self, profile_id: str) -> ModelProfileStatus: ...

    def readiness(self) -> RuntimeReadiness: ...

    def service(self, capability_id: str) -> object | None: ...

    async def initialize(self) -> None: ...

    async def shutdown(self) -> None: ...
