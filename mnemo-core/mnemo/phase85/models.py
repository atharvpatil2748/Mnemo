"""Immutable Phase 8.5 runtime lifecycle and readiness models."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class CapabilityLifecycleStage(StrEnum):
    """Ordered activation stages frozen by ADR-0074."""

    DECLARED = "declared"
    CONFIGURED = "configured"
    BUILDABLE = "buildable"
    READY = "ready"
    ACTIVE = "active"
    EXPOSED = "exposed"
    VERIFIED = "verified"
    CERTIFIED = "certified"


_CAPABILITY_STAGES = tuple(CapabilityLifecycleStage)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityState:
    """Explicit capability lifecycle without inferring verification or certification."""

    declared: bool = True
    configured: bool = False
    buildable: bool = False
    ready: bool = False
    active: bool = False
    exposed: bool = False
    behaviorally_verified: bool = False
    security_verified: bool = False
    certified: bool = False

    def __post_init__(self) -> None:
        implications = (
            (self.configured, self.declared, "configured requires declared"),
            (self.buildable, self.configured, "buildable requires configured"),
            (self.ready, self.buildable, "ready requires buildable"),
            (self.active, self.ready, "active requires ready"),
            (self.exposed, self.active, "exposed requires active"),
            (
                self.behaviorally_verified,
                self.exposed,
                "behavioral verification requires exposure",
            ),
            (
                self.certified,
                self.behaviorally_verified and self.security_verified,
                "certification requires behavioral and security verification",
            ),
        )
        for enabled, prerequisite, message in implications:
            if enabled and not prerequisite:
                raise ValueError(message)

    @property
    def stage(self) -> CapabilityLifecycleStage:
        """Return the highest sequential lifecycle stage reached."""
        if self.certified:
            return CapabilityLifecycleStage.CERTIFIED
        if self.behaviorally_verified:
            return CapabilityLifecycleStage.VERIFIED
        if self.exposed:
            return CapabilityLifecycleStage.EXPOSED
        if self.active:
            return CapabilityLifecycleStage.ACTIVE
        if self.ready:
            return CapabilityLifecycleStage.READY
        if self.buildable:
            return CapabilityLifecycleStage.BUILDABLE
        if self.configured:
            return CapabilityLifecycleStage.CONFIGURED
        return CapabilityLifecycleStage.DECLARED

    def advance(self, target: CapabilityLifecycleStage) -> CapabilityState:
        """Advance monotonically to one stage; certification needs security evidence."""
        if not isinstance(target, CapabilityLifecycleStage):
            raise TypeError("target must be CapabilityLifecycleStage")
        current_index = _CAPABILITY_STAGES.index(self.stage)
        target_index = _CAPABILITY_STAGES.index(target)
        if target_index < current_index:
            raise ValueError("capability lifecycle cannot move backwards")
        values = {
            "declared": True,
            "configured": target_index >= 1,
            "buildable": target_index >= 2,
            "ready": target_index >= 3,
            "active": target_index >= 4,
            "exposed": target_index >= 5,
            "behaviorally_verified": target_index >= 6,
            "security_verified": self.security_verified,
            "certified": target_index >= 7,
        }
        return CapabilityState(**values)

    def with_security_verification(self, verified: bool = True) -> CapabilityState:
        """Return a snapshot with independent security verification evidence."""
        return replace(self, security_verified=verified)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityStatus:
    """Runtime status for one governance-defined capability."""

    capability_id: str
    owner: str
    state: CapabilityState
    dependencies: tuple[str, ...] = ()
    profile_ids: tuple[str, ...] = ()
    generation_id: str | None = None
    generation_active: bool = False
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not self.capability_id or not self.capability_id.strip():
            raise ValueError("capability_id must be non-empty")
        if not self.owner or not self.owner.strip():
            raise ValueError("owner must be non-empty")
        if (
            self.state.active
            and self.generation_id is None
            and self.capability_id
            in {
                "ocr",
                "vision",
                "visual_vector_retrieval",
                "structured_retrieval",
                "multilingual_retrieval",
                "multilingual_retrieval_v2",
                "multilingual_ocr",
                "multilingual_vision",
                "multimodal_retrieval",
            }
        ):
            raise ValueError("generation-backed capability cannot be active without generation_id")
        if self.generation_active and self.generation_id is None:
            raise ValueError("active generation requires generation_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelProfileState:
    """Model availability stages, kept separate from capability activation."""

    declared: bool = True
    configured: bool = False
    available_locally: bool = False
    loadable: bool = False
    initialized: bool = False
    active: bool = False

    def __post_init__(self) -> None:
        implications = (
            (self.configured, self.declared, "configured model requires declaration"),
            (self.available_locally, self.configured, "available model requires configuration"),
            (self.loadable, self.available_locally, "loadable model requires availability"),
            (self.initialized, self.loadable, "initialized model requires loadability"),
            (self.active, self.initialized, "active model requires initialization"),
        )
        for enabled, prerequisite, message in implications:
            if enabled and not prerequisite:
                raise ValueError(message)


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelProfileStatus:
    """Resolved provider/model identity and its actual runtime state."""

    profile_id: str
    operation: str
    provider: str | None
    model: str | None
    revision: str | None
    dimensions: int | None
    state: ModelProfileState
    reason_code: str | None = None
    trust_class: str = "local_trusted"
    certification: str = "non_certified_default"

    def __post_init__(self) -> None:
        if not self.profile_id or not self.profile_id.strip():
            raise ValueError("profile_id must be non-empty")
        if not self.operation or not self.operation.strip():
            raise ValueError("operation must be non-empty")
        if self.state.configured and (not self.provider or not self.model):
            raise ValueError("configured profile requires provider and model")
        if self.dimensions is not None and self.dimensions <= 0:
            raise ValueError("dimensions must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderReadinessResult:
    """Safe result returned by an actual provider readiness probe."""

    available_locally: bool
    loadable: bool
    initialized: bool
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.loadable and not self.available_locally:
            raise ValueError("loadable provider requires local availability")
        if self.initialized and not self.loadable:
            raise ValueError("initialized provider requires loadability")


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeReadiness:
    """Separate process/engine readiness from optional capability readiness."""

    process_alive: bool
    engine_ready: bool
    runtime_ready: bool
    required_capabilities: tuple[str, ...]
    unavailable_required: tuple[str, ...]
    unavailable_optional: tuple[str, ...]
