"""Single additive Phase 8.5 runtime composed by KnowledgeEngine."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from mnemo.config import DerivedModelProfileConfig, MnemoConfig
from mnemo.interfaces.phase85 import Phase85RuntimeV1, ProviderReadinessProbeV1
from mnemo.phase85.models import (
    CapabilityState,
    CapabilityStatus,
    ModelProfileState,
    ModelProfileStatus,
    ProviderReadinessResult,
    RuntimeReadiness,
)
from mnemo.phase85.profiles import ActiveModelProfileSnapshot, ModelProfileRegistry


@dataclass(frozen=True, slots=True)
class _CapabilityDefinition:
    owner: str
    dependencies: tuple[str, ...] = ()
    profile_ids: tuple[str, ...] = ()
    code_present: bool = True
    generation_backed: bool = False


_CAPABILITY_DEFINITIONS: Mapping[str, _CapabilityDefinition] = MappingProxyType(
    {
        "canonical_ingestion": _CapabilityDefinition("KnowledgeEngine ingestion pipeline"),
        "v1_retrieval": _CapabilityDefinition(
            "V1 retrieval/query services", profile_ids=("v1.embedding", "v1.reranker")
        ),
        "document_delivery": _CapabilityDefinition(
            "DocumentExpansionServiceV1", dependencies=("authorization", "provenance")
        ),
        "exact_retrieval": _CapabilityDefinition(
            "Exact retrieval service", dependencies=("authorization", "provenance")
        ),
        "positional_retrieval": _CapabilityDefinition(
            "Positional retrieval service",
            dependencies=("exact_retrieval", "cursor_continuation"),
        ),
        "exhaustive_retrieval": _CapabilityDefinition(
            "AdvancedRetrievalService", dependencies=("completeness", "cursor_continuation")
        ),
        "structured_retrieval": _CapabilityDefinition(
            "StructuredRetrievalService",
            dependencies=("exhaustive_retrieval", "completeness"),
            generation_backed=True,
        ),
        "multi_document_retrieval": _CapabilityDefinition(
            "Bounded document-set retrieval service",
            dependencies=("exhaustive_retrieval", "structured_retrieval"),
            code_present=False,
        ),
        "asset_discovery": _CapabilityDefinition(
            "Asset catalog and multimodal retrieval",
            dependencies=("authorization", "provenance"),
        ),
        "asset_delivery": _CapabilityDefinition(
            "DocumentExpansionServiceV1", dependencies=("authorization", "provenance")
        ),
        "ocr": _CapabilityDefinition(
            "OCR service/provider/store",
            dependencies=("processing_jobs", "authorization"),
            profile_ids=("ocr",),
            generation_backed=True,
        ),
        "vision": _CapabilityDefinition(
            "Vision service/provider/store",
            dependencies=("processing_jobs", "authorization"),
            profile_ids=("vision",),
            generation_backed=True,
        ),
        "visual_vector_retrieval": _CapabilityDefinition(
            "Visual embedding retrieval source",
            dependencies=("vision",),
            profile_ids=("visual_embedding",),
            generation_backed=True,
        ),
        "multimodal_retrieval": _CapabilityDefinition(
            "Multimodal retrieval/fusion service",
            dependencies=("exhaustive_retrieval", "asset_discovery"),
            generation_backed=True,
        ),
        "multilingual_retrieval": _CapabilityDefinition(
            "MultilingualRetrievalService",
            dependencies=("exhaustive_retrieval",),
            profile_ids=("multilingual_embedding", "multilingual_reranker"),
            generation_backed=True,
        ),
        "multilingual_retrieval_v2": _CapabilityDefinition(
            "Full Multilingual V2 shared application service",
            dependencies=("exhaustive_retrieval", "authorization", "provenance"),
            profile_ids=("multilingual_embedding", "multilingual_reranker"),
            generation_backed=True,
        ),
        "multilingual_ocr": _CapabilityDefinition(
            "Multilingual OCR projection",
            dependencies=("ocr", "multilingual_retrieval"),
            profile_ids=("ocr",),
            generation_backed=True,
        ),
        "multilingual_vision": _CapabilityDefinition(
            "Multilingual Vision projection",
            dependencies=("vision", "multilingual_retrieval"),
            profile_ids=("vision",),
            generation_backed=True,
        ),
        "cursor_continuation": _CapabilityDefinition("Cursor codecs"),
        "provenance": _CapabilityDefinition("Typed evidence and delivery envelopes"),
        "completeness": _CapabilityDefinition("Domain result-set completeness"),
        "authorization": _CapabilityDefinition("Notebook/version/occurrence authorizers"),
        "capability_discovery": _CapabilityDefinition("Phase85RuntimeV1 registry"),
        "final_qa_v2": _CapabilityDefinition(
            "FinalQAInterfaceV2",
            dependencies=("multimodal_retrieval", "authorization", "provenance"),
        ),
        "behavioral_verification": _CapabilityDefinition(
            "Blind-agent evaluation harness", code_present=False
        ),
        "security_verification": _CapabilityDefinition(
            "Phase 8.5 security gate", code_present=False
        ),
        "processing_jobs": _CapabilityDefinition("ProcessingJobStoreV1/ProcessingWorkerV1"),
        "phase_11_deterministic_primitives": _CapabilityDefinition(
            "Phase85RuntimeV1 public contracts", code_present=False
        ),
        "runtime_profile_activation": _CapabilityDefinition("Phase85RuntimeV1 registry"),
    }
)

PHASE85_CAPABILITY_IDS = frozenset(_CAPABILITY_DEFINITIONS)
PHASE85_REQUIRED_CAPABILITY_IDS = frozenset({"canonical_ingestion", "v1_retrieval"})


@dataclass(frozen=True, slots=True, kw_only=True)
class Phase85ProviderRegistration:
    """One exact profile and its provider-owned readiness probe."""

    profile_id: str
    probe: ProviderReadinessProbeV1
    activate_when_ready: bool = True

    def __post_init__(self) -> None:
        if not self.profile_id or not self.profile_id.strip():
            raise ValueError("profile_id must be non-empty")
        if not isinstance(self.probe, ProviderReadinessProbeV1):
            raise TypeError("probe must implement ProviderReadinessProbeV1")


@dataclass(frozen=True, slots=True, kw_only=True)
class Phase85ServiceRegistration:
    """Evidence that one capability service/generation is ready for activation."""

    capability_id: str
    service: object
    ready: bool
    activate: bool = False
    generation_id: str | None = None
    generation_active: bool = False
    profile_fingerprint: str | None = None
    exposed: bool = False
    behaviorally_verified: bool = False
    security_verified: bool = False
    certified: bool = False

    def __post_init__(self) -> None:
        if not self.capability_id or not self.capability_id.strip():
            raise ValueError("capability_id must be non-empty")
        if self.service is None:
            raise TypeError("service must not be None")
        if self.activate and not self.ready:
            raise ValueError("activation requires a ready service")
        if self.generation_active and self.generation_id is None:
            raise ValueError("active generation requires generation_id")
        if self.profile_fingerprint is not None and len(self.profile_fingerprint) != 64:
            raise ValueError("profile_fingerprint must be a SHA-256 identity")
        if self.exposed and not self.activate:
            raise ValueError("exposure requires activation")
        if self.behaviorally_verified and not self.exposed:
            raise ValueError("behavioral verification requires exposure")
        if self.certified and not (self.behaviorally_verified and self.security_verified):
            raise ValueError("certification requires behavioral and security verification")


class Phase85Runtime(Phase85RuntimeV1):
    """Resolve profiles and capabilities without creating a competing engine."""

    def __init__(
        self,
        config: MnemoConfig,
        *,
        engine_ready: bool,
        active_v1_profiles: frozenset[str] = frozenset(),
        core_active_capabilities: frozenset[str] = frozenset(),
        provider_registrations: tuple[Phase85ProviderRegistration, ...] = (),
        service_registrations: tuple[Phase85ServiceRegistration, ...] = (),
    ) -> None:
        if not isinstance(config, MnemoConfig):
            raise TypeError("config must be MnemoConfig")
        unknown_core = core_active_capabilities - PHASE85_CAPABILITY_IDS
        if unknown_core:
            raise ValueError(f"unknown core capabilities: {', '.join(sorted(unknown_core))}")
        self._config = config
        self._profile_registry = ModelProfileRegistry(config)
        self._engine_ready = engine_ready
        self._active_v1_profiles = active_v1_profiles
        self._provider_registrations = _unique_provider_registrations(provider_registrations)
        self._service_registrations = _unique_service_registrations(service_registrations)
        unknown_services = set(self._service_registrations) - PHASE85_CAPABILITY_IDS
        if unknown_services:
            raise ValueError(f"unknown service capabilities: {', '.join(sorted(unknown_services))}")
        self._core_active_capabilities = core_active_capabilities
        self._profiles = _profile_catalog(config, active_v1_profiles, self._profile_registry.active)
        unknown_profiles = set(self._provider_registrations) - set(self._profiles)
        if unknown_profiles:
            raise ValueError(f"unknown provider profiles: {', '.join(sorted(unknown_profiles))}")
        self._capabilities: Mapping[str, CapabilityStatus] = MappingProxyType({})
        self._initialized = False
        self._lock = asyncio.Lock()
        self._configuration_fingerprint = _configuration_fingerprint(
            config, self._profile_registry.active
        )
        self._refresh_capabilities()

    @property
    def configuration_fingerprint(self) -> str:
        return self._configuration_fingerprint

    @property
    def active_profile(self) -> ActiveModelProfileSnapshot:
        return self._profile_registry.active

    def capabilities(self) -> Mapping[str, CapabilityStatus]:
        return self._capabilities

    def capability_status(self, capability_id: str) -> CapabilityStatus:
        try:
            return self._capabilities[capability_id]
        except KeyError as error:
            raise KeyError(f"unknown Phase 8.5 capability: {capability_id}") from error

    def profiles(self) -> Mapping[str, ModelProfileStatus]:
        return self._profiles

    def profile_status(self, profile_id: str) -> ModelProfileStatus:
        try:
            return self._profiles[profile_id]
        except KeyError as error:
            raise KeyError(f"unknown Phase 8.5 model profile: {profile_id}") from error

    def readiness(self) -> RuntimeReadiness:
        unavailable_required = tuple(
            sorted(
                capability_id
                for capability_id in PHASE85_REQUIRED_CAPABILITY_IDS
                if not self._capabilities[capability_id].state.active
            )
        )
        unavailable_optional = tuple(
            sorted(
                capability_id
                for capability_id, status in self._capabilities.items()
                if capability_id not in PHASE85_REQUIRED_CAPABILITY_IDS and not status.state.active
            )
        )
        return RuntimeReadiness(
            process_alive=True,
            engine_ready=self._engine_ready,
            runtime_ready=self._engine_ready and not unavailable_required,
            required_capabilities=tuple(sorted(PHASE85_REQUIRED_CAPABILITY_IDS)),
            unavailable_required=unavailable_required,
            unavailable_optional=unavailable_optional,
        )

    def service(self, capability_id: str) -> object | None:
        if capability_id not in PHASE85_CAPABILITY_IDS:
            raise KeyError(f"unknown Phase 8.5 capability: {capability_id}")
        registration = self._service_registrations.get(capability_id)
        return None if registration is None else registration.service

    async def initialize(self) -> None:
        async with self._lock:
            if self._initialized:
                return
            resolved = dict(self._profiles)
            for profile_id, registration in self._provider_registrations.items():
                profile = resolved[profile_id]
                if not profile.state.configured:
                    continue
                try:
                    result = await registration.probe.probe(profile)
                    if not isinstance(result, ProviderReadinessResult):
                        raise TypeError("provider probe returned an invalid result")
                    state = ModelProfileState(
                        declared=True,
                        configured=profile.state.configured,
                        available_locally=result.available_locally,
                        loadable=result.loadable,
                        initialized=result.initialized,
                        active=result.initialized and registration.activate_when_ready,
                    )
                    resolved[profile_id] = replace(
                        profile,
                        state=state,
                        reason_code=result.reason_code,
                    )
                except Exception as error:  # optional failures are isolated by contract
                    resolved[profile_id] = replace(
                        profile,
                        state=ModelProfileState(
                            declared=True,
                            configured=profile.state.configured,
                        ),
                        reason_code=f"provider_probe_failed:{type(error).__name__}",
                    )
            self._profiles = MappingProxyType(resolved)
            self._initialized = True
            self._refresh_capabilities()

    async def shutdown(self) -> None:
        async with self._lock:
            # Provider probes may own a local executor/model lifetime.  The
            # original probe-only contract remains valid; close is optional so
            # legacy providers retain their existing shutdown semantics.
            for registration in self._provider_registrations.values():
                close = getattr(registration.probe, "close", None)
                if close is None:
                    continue
                result = close()
                if inspect.isawaitable(result):
                    await result
            self._initialized = False
            self._profiles = _profile_catalog(
                self._config,
                self._active_v1_profiles,
                self._profile_registry.active,
            )
            self._refresh_capabilities()

    def _refresh_capabilities(self) -> None:
        statuses: dict[str, CapabilityStatus] = {}
        for capability_id, definition in _CAPABILITY_DEFINITIONS.items():
            service = self._service_registrations.get(capability_id)
            profiles = tuple(self._profiles[profile_id] for profile_id in definition.profile_ids)
            enabled = _capability_enabled(self._config, capability_id)
            core_selected = capability_id in self._core_active_capabilities and enabled
            core_active = self._initialized and core_selected
            configured = (
                enabled
                and definition.code_present
                and (
                    core_selected
                    or service is not None
                    or (bool(profiles) and all(profile.state.configured for profile in profiles))
                )
            )
            providers_ready = not profiles or all(profile.state.initialized for profile in profiles)
            buildable = configured and (core_active or (service is not None and providers_ready))
            profile_binding_required = definition.generation_backed and bool(definition.profile_ids)
            profile_compatible = service is None or service.profile_fingerprint in {
                None,
                self._profile_registry.active.fingerprint,
            }
            if profile_binding_required:
                profile_compatible = bool(
                    service
                    and service.profile_fingerprint == self._profile_registry.active.fingerprint
                )
            generation_ready = not definition.generation_backed or (
                service is not None
                and service.generation_id is not None
                and service.generation_active
                and profile_compatible
            )
            ready = buildable and (
                core_active or (service is not None and service.ready and generation_ready)
            )
            active = ready and (core_active or bool(service and service.activate))
            exposed = (
                active
                and bool(service and service.exposed)
                and (self._config.phase85.features.http or self._config.phase85.features.mcp)
            )
            verified = exposed and bool(service and service.behaviorally_verified)
            security_verified = bool(service and service.security_verified)
            certified = verified and security_verified and bool(service and service.certified)
            state = CapabilityState(
                declared=True,
                configured=configured,
                buildable=buildable,
                ready=ready,
                active=active,
                exposed=exposed,
                behaviorally_verified=verified,
                security_verified=security_verified,
                certified=certified,
            )
            statuses[capability_id] = CapabilityStatus(
                capability_id=capability_id,
                owner=definition.owner,
                dependencies=definition.dependencies,
                profile_ids=definition.profile_ids,
                generation_id=None if service is None else service.generation_id,
                generation_active=bool(service and service.generation_active),
                state=state,
                reason_code=_capability_reason(
                    definition=definition,
                    enabled=enabled,
                    active_profile_fingerprint=self._profile_registry.active.fingerprint,
                    core_active=core_active,
                    core_selected=core_selected,
                    service=service,
                    profiles=profiles,
                    state=state,
                ),
            )
        changed = True
        while changed:
            changed = False
            for capability_id, status in tuple(statuses.items()):
                unavailable = tuple(
                    dependency
                    for dependency in status.dependencies
                    if dependency in statuses and not statuses[dependency].state.active
                )
                if not unavailable or not status.state.ready:
                    continue
                statuses[capability_id] = replace(
                    status,
                    state=CapabilityState(
                        declared=status.state.declared,
                        configured=status.state.configured,
                        buildable=status.state.buildable,
                        security_verified=status.state.security_verified,
                    ),
                    reason_code=f"dependency_unavailable:{unavailable[0]}",
                )
                changed = True
        self._capabilities = MappingProxyType(statuses)


def _profile_catalog(
    config: MnemoConfig,
    active_v1_profiles: frozenset[str],
    active_profile: ActiveModelProfileSnapshot,
) -> Mapping[str, ModelProfileStatus]:
    profiles: dict[str, ModelProfileStatus] = {
        "v1.embedding": _configured_profile(
            "v1.embedding",
            "canonical_text_embedding",
            config.embedding.provider,
            config.embedding.model,
            dimensions=config.embedding.dimensions,
            active="v1.embedding" in active_v1_profiles,
        ),
        "v1.reranker": _configured_profile(
            "v1.reranker",
            "canonical_text_reranking",
            config.reranker.provider,
            config.reranker.model,
            active="v1.reranker" in active_v1_profiles,
        ),
    }
    for role in ("planner", "synthesizer", "extractor", "classifier"):
        value = getattr(config.llm, role)
        profile_id = f"llm.{role}"
        profiles[profile_id] = _configured_profile(
            profile_id,
            f"llm_{role}",
            value.provider,
            value.model,
            active=profile_id in active_v1_profiles,
        )
    for profile_id, operation, value in (
        ("vision", "vision_analysis", config.models.vision),
        (
            "multilingual_embedding",
            "multilingual_text_embedding",
            config.models.multilingual_embedding,
        ),
        (
            "multilingual_reranker",
            "multilingual_text_reranking",
            config.models.multilingual_reranker,
        ),
        ("visual_embedding", "visual_embedding", config.models.visual_embedding),
    ):
        profiles[profile_id] = _derived_profile(
            profile_id,
            operation,
            value,
            enabled=config.phase85.enabled,
            trust_class=active_profile.trust_class.value,
            certification=active_profile.certification.value,
        )
    profiles["ocr"] = ModelProfileStatus(
        profile_id="ocr",
        operation="ocr",
        provider=None,
        model=None,
        revision=None,
        dimensions=None,
        state=ModelProfileState(declared=True, configured=False),
        reason_code="profile_not_configured",
        trust_class=active_profile.trust_class.value,
        certification=active_profile.certification.value,
    )
    return MappingProxyType(profiles)


def _configured_profile(
    profile_id: str,
    operation: str,
    provider: str,
    model: str,
    *,
    dimensions: int | None = None,
    active: bool,
) -> ModelProfileStatus:
    state = ModelProfileState(
        declared=True,
        configured=True,
        available_locally=active,
        loadable=active,
        initialized=active,
        active=active,
    )
    return ModelProfileStatus(
        profile_id=profile_id,
        operation=operation,
        provider=provider,
        model=model,
        revision=None,
        dimensions=dimensions,
        state=state,
        reason_code=None if active else "provider_not_initialized",
    )


def _derived_profile(
    profile_id: str,
    operation: str,
    value: DerivedModelProfileConfig,
    *,
    enabled: bool,
    trust_class: str,
    certification: str,
) -> ModelProfileStatus:
    configured = enabled and value.enabled
    return ModelProfileStatus(
        profile_id=profile_id,
        operation=operation,
        provider=value.provider if configured else None,
        model=value.model if configured else None,
        revision=value.revision,
        dimensions=value.dimensions,
        state=ModelProfileState(declared=True, configured=configured),
        reason_code="provider_not_registered" if configured else "profile_not_configured",
        trust_class=trust_class,
        certification=certification,
    )


def _unique_provider_registrations(
    values: tuple[Phase85ProviderRegistration, ...],
) -> Mapping[str, Phase85ProviderRegistration]:
    result: dict[str, Phase85ProviderRegistration] = {}
    for value in values:
        if value.profile_id in result:
            raise ValueError(f"duplicate provider profile registration: {value.profile_id}")
        result[value.profile_id] = value
    return MappingProxyType(result)


def _unique_service_registrations(
    values: tuple[Phase85ServiceRegistration, ...],
) -> Mapping[str, Phase85ServiceRegistration]:
    result: dict[str, Phase85ServiceRegistration] = {}
    for value in values:
        if value.capability_id in result:
            raise ValueError(f"duplicate capability service registration: {value.capability_id}")
        result[value.capability_id] = value
    return MappingProxyType(result)


def _configuration_fingerprint(
    config: MnemoConfig, active_profile: ActiveModelProfileSnapshot
) -> str:
    profiles = _profile_catalog(config, frozenset(), active_profile)
    payload = {
        "active_profile_fingerprint": active_profile.fingerprint,
        "features": config.phase85.features.model_dump(mode="json"),
        "profiles": {
            profile_id: {
                "operation": value.operation,
                "provider": value.provider,
                "model": value.model,
                "revision": value.revision,
                "dimensions": value.dimensions,
            }
            for profile_id, value in sorted(profiles.items())
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _capability_reason(
    *,
    definition: _CapabilityDefinition,
    enabled: bool,
    active_profile_fingerprint: str,
    core_active: bool,
    core_selected: bool,
    service: Phase85ServiceRegistration | None,
    profiles: tuple[ModelProfileStatus, ...],
    state: CapabilityState,
) -> str | None:
    if state.active:
        return None
    if not enabled:
        return "profile_disabled"
    if not definition.code_present:
        return "implementation_pending"
    if profiles and not all(profile.state.configured for profile in profiles):
        return "profile_not_configured"
    if profiles and not all(profile.state.initialized for profile in profiles):
        return "provider_not_ready"
    if core_active:
        return "engine_not_ready"
    if core_selected:
        return "runtime_not_initialized"
    if service is None:
        return "service_not_registered"
    if (
        definition.generation_backed
        and definition.profile_ids
        and service.profile_fingerprint is None
    ):
        return "profile_generation_unbound"
    if (
        service.profile_fingerprint is not None
        and service.profile_fingerprint != active_profile_fingerprint
    ):
        return "profile_generation_mismatch"
    if definition.generation_backed and not service.generation_active:
        return "active_generation_unavailable"
    if not service.ready:
        return "service_not_ready"
    if not service.activate:
        return "activation_not_selected"
    return "capability_unavailable"


def _capability_enabled(config: MnemoConfig, capability_id: str) -> bool:
    if capability_id in PHASE85_REQUIRED_CAPABILITY_IDS:
        return True
    if not config.phase85.enabled:
        return False
    features = config.phase85.features
    feature_map = {
        "exhaustive_retrieval": features.advanced_retrieval,
        "structured_retrieval": features.structured_retrieval,
        "ocr": features.ocr,
        "multilingual_ocr": features.ocr and features.multilingual,
        "vision": features.vision,
        "multilingual_vision": features.vision and features.multilingual,
        "visual_vector_retrieval": features.visual_vector,
        "multilingual_retrieval": features.multilingual,
        "multilingual_retrieval_v2": features.multilingual,
        "multimodal_retrieval": features.multimodal,
        "final_qa_v2": features.final_qa_v2,
    }
    return feature_map.get(capability_id, True)
