"""Additive Phase 8.5 model-profile registry contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mnemo.phase85.profiles import ActiveModelProfileSnapshot, ModelProfileComponent


@runtime_checkable
class ModelProfileRegistryV1(Protocol):  # pragma: no cover
    """Expose one selected immutable profile without paths or secret material."""

    @property
    def active(self) -> ActiveModelProfileSnapshot: ...

    def component(self, component_id: str) -> ModelProfileComponent | None: ...
