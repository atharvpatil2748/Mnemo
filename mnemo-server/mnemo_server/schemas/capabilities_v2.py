"""Strict machine-readable Phase 8.5 capability discovery DTOs."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CapabilityDiscoveryRequest(BaseModel):
    """Optional deterministic filter shared by HTTP and MCP."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    notebook_id: UUID | None = None
    capability_ids: tuple[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")], ...] = ()


class CapabilityLifecycleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: Literal[
        "declared",
        "configured",
        "buildable",
        "ready",
        "active",
        "exposed",
        "verified",
        "certified",
    ]
    declared: bool
    configured: bool
    buildable: bool
    ready: bool
    active: bool
    exposed: bool
    behaviorally_verified: bool
    security_verified: bool
    certified: bool


class CapabilityDependencyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    stage: str | None
    active: bool | None
    reason: str | None = None


class CapabilityProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    operation: str
    provider: str | None
    model: str | None
    revision: str | None
    dimensions: int | None
    trust_class: str
    certification: str
    configured: bool
    available: bool
    loadable: bool
    initialized: bool
    active: bool
    reason: str | None = None


class CapabilityGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required: bool
    generation_id: str | None
    present: bool
    active: bool


class CapabilityTransportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    http: tuple[str, ...] = ()
    mcp: tuple[str, ...] = ()
    callable: bool


class CapabilityNextActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str
    tool: str | None = None
    reason: str


class CapabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    description: str
    category: str
    lifecycle: CapabilityLifecycleResponse
    dependencies: tuple[CapabilityDependencyResponse, ...]
    profiles: tuple[CapabilityProfileResponse, ...]
    generation: CapabilityGenerationResponse
    transports: CapabilityTransportResponse
    supported_representations: tuple[str, ...] = ()
    supported_modalities: tuple[str, ...] = ()
    supported_languages: tuple[str, ...] = ()
    retrieval_modes: tuple[str, ...] = ()
    continuation: bool = False
    limits: dict[str, int | str | bool]
    recommended_tools: tuple[str, ...] = ()
    next_actions: tuple[CapabilityNextActionResponse, ...]
    unavailable_reason: str | None = None


class CapabilityTaskGuidanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task: str
    capability_id: str
    tool: str
    use_when: str
    do_not_use_when: str
    available: bool


class ActiveModelProfileResponse(BaseModel):
    """Redacted selected production profile identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    profile_id: str
    version: str
    mode: str
    enabled: bool
    trust_class: str
    certification: str
    fingerprint: str = Field(min_length=64, max_length=64)
    http_enabled: bool
    mcp_enabled: bool


class CapabilityRuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_ready: bool
    runtime_ready: bool
    required_capabilities: tuple[str, ...]
    unavailable_required: tuple[str, ...]
    unavailable_optional: tuple[str, ...]
    configuration_fingerprint: str
    active_profile: ActiveModelProfileResponse


class CapabilityDocument(BaseModel):
    """One deterministic document serialized identically by HTTP and MCP."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["mnemo.capabilities/1"] = "mnemo.capabilities/1"
    snapshot_identity: str = Field(min_length=64, max_length=64)
    scope_qualified: bool
    runtime: CapabilityRuntimeResponse
    capabilities: tuple[CapabilityResponse, ...]
    task_guidance: tuple[CapabilityTaskGuidanceResponse, ...]
    limitations: tuple[str, ...]
