"""Thin, transport-independent runtime composition for Mnemo core."""

from __future__ import annotations

import asyncio
import importlib
import logging
import warnings
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

from mnemo._version import __version__
from mnemo.config import MnemoConfig
from mnemo.interfaces import (
    AdvancedCanonicalStoreV1,
    AdvancedRetrievalInterfaceV1,
    AssetCatalogStoreV1,
    AssetRecordStoreV1,
    DependencyUnavailableError,
    DocumentScopeResolverV1,
    EmbeddingCapabilities,
    EmbeddingProviderV1,
    FinalQAExecutionStoreV1,
    FinalQAExecutionStoreV2,
    FinalQAInterfaceV1,
    FinalQAInterfaceV2,
    LifecycleError,
    LLMCapabilities,
    LLMInterfaceV1,
    MnemoInterfaceError,
    MultilingualAdvancedStoreV1,
    MultimodalAdvancedStoreV1,
    OCRStoreV1,
    ProcessingJobStoreV1,
    RerankerCapabilities,
    RerankerInterfaceV1,
    StorageCapabilities,
    StorageInterfaceV1,
    StructuredDatasetCatalogV1,
    TokenCounterInterfaceV1,
    VisionStoreV1,
    VisualQueryEmbeddingProviderV1,
)
from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalSourceV1
from mnemo.models.advanced_retrieval import EvidenceRepresentation
from mnemo.models.retrieval import ScoredChunk
from mnemo.phase85 import (
    Phase85ProviderRegistration,
    Phase85Runtime,
    Phase85ServiceRegistration,
)
from mnemo.phase85.language_capabilities import LanguageCapabilityRecordV3
from mnemo.phase85.v2_readiness import V2ReadinessSnapshot
from mnemo.registry import PluginInterfaceV1, PluginLoadResult, PluginRegistry
from mnemo.retrieval import (
    DeterministicComparisonServiceV1,
    PartitionedRetrievalServiceV1,
    RetrievalCursorCodec,
    StorageDocumentScopeResolverV1,
    StorageSourceAssociationReaderV1,
    StructuredDatasetRuntimeService,
)

_LOGGER = logging.getLogger(__name__)
_PRIMARY_SLOT = "primary"
_LLM_ROLES = ("planner", "synthesizer", "extractor", "classifier")
_REQUIRED_CAPABILITIES = frozenset({"storage", "embedding_provider", "reranker", "llm"})
type _LLMRole = Literal["planner", "synthesizer", "extractor", "classifier"]
type _ProviderCapability = (
    StorageCapabilities | EmbeddingCapabilities | RerankerCapabilities | LLMCapabilities
)


class EngineState(StrEnum):
    """Lifecycle states of one KnowledgeEngine runtime instance."""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class KnowledgeEngineError(MnemoInterfaceError):
    """Base exception for KnowledgeEngine composition failures."""

    code = "engine.error"


class EngineLifecycleError(KnowledgeEngineError, LifecycleError):
    """An operation is invalid for the engine's current lifecycle state."""

    code = "engine.lifecycle"


class EngineInitializationError(KnowledgeEngineError, DependencyUnavailableError):
    """Runtime discovery, resolution, or structural validation failed."""

    code = "engine.initialization"


class _V2OwnedOuterPassThroughReranker:
    """Satisfy the legacy core slot without loading a second production reranker."""

    def capabilities(self) -> RerankerCapabilities:
        return RerankerCapabilities(
            supports_cross_encoder=False,
            supports_batch=False,
            preserves_raw_scores=True,
        )

    async def rerank(
        self,
        query: str,
        candidates: tuple[ScoredChunk, ...],
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if not isinstance(candidates, tuple) or any(
            not isinstance(candidate, ScoredChunk) for candidate in candidates
        ):
            raise TypeError("candidates must be a tuple of ScoredChunk")
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        return candidates[:top_k]


class _V2OwnedOuterPassThroughRerankerPlugin:
    """Register the inert outer slot used by the certified V2-owned reranker path."""

    name = "mnemo-v2-owned-outer-pass-through-reranker"
    version = __version__
    core_version_range = ">=0.0.0"

    def capabilities(self) -> tuple[str, ...]:
        return ("reranker",)

    def register(self, registry: PluginRegistry) -> None:
        registry.register_reranker(
            _PRIMARY_SLOT,
            _V2OwnedOuterPassThroughReranker(),
            priority=0,
        )


@dataclass(frozen=True, slots=True)
class _ResolvedProviders:
    storage: StorageInterfaceV1
    embedding: EmbeddingProviderV1
    reranker: RerankerInterfaceV1
    planner: LLMInterfaceV1
    synthesizer: LLMInterfaceV1
    extractor: LLMInterfaceV1
    classifier: LLMInterfaceV1
    capabilities: Mapping[str, _ProviderCapability]


@dataclass(frozen=True, slots=True)
class FinalQAComponents:
    """Explicit local resources required to compose ADR-0046."""

    token_counter: TokenCounterInterfaceV1
    clock: Callable[[], datetime]
    operational_store_v2: FinalQAExecutionStoreV2 | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must implement TokenCounterInterfaceV1")
        if not callable(self.clock):
            raise TypeError("clock must be callable")
        if self.operational_store_v2 is not None and not isinstance(
            self.operational_store_v2, FinalQAExecutionStoreV2
        ):
            raise TypeError("operational_store_v2 must implement FinalQAExecutionStoreV2")


class KnowledgeEngine:
    """Compose and validate one Mnemo core runtime from frozen configuration."""

    def __init__(
        self,
        config: MnemoConfig,
        *,
        final_qa_components: FinalQAComponents | None = None,
        phase85_provider_registrations: tuple[Phase85ProviderRegistration, ...] = (),
        phase85_service_registrations: tuple[Phase85ServiceRegistration, ...] = (),
        advanced_retrieval_cursor_codec: RetrievalCursorCodec | None = None,
        visual_query_embedding_provider: VisualQueryEmbeddingProviderV1 | None = None,
        multilingual_advanced_source: object | None = None,
        full_multilingual_v2_source: object | None = None,
        full_multilingual_v2_readiness: V2ReadinessSnapshot | None = None,
        language_capability_records: tuple[LanguageCapabilityRecordV3, ...] = (),
        final_qa_v2: FinalQAInterfaceV2 | None = None,
    ) -> None:
        """Create an uninitialized runtime without performing discovery or I/O."""
        if not isinstance(config, MnemoConfig):
            raise TypeError("config must be MnemoConfig")
        if final_qa_components is not None and not isinstance(
            final_qa_components, FinalQAComponents
        ):
            raise TypeError("final_qa_components must be FinalQAComponents or None")
        self._config = config
        self._final_qa_components = final_qa_components
        self._phase85_provider_registrations = phase85_provider_registrations
        self._phase85_service_registrations = phase85_service_registrations
        self._advanced_retrieval_cursor_codec = advanced_retrieval_cursor_codec
        self._visual_query_embedding_provider = visual_query_embedding_provider
        self._multilingual_advanced_source = multilingual_advanced_source
        self._full_multilingual_v2_source = full_multilingual_v2_source
        self._full_multilingual_v2_readiness = full_multilingual_v2_readiness
        self._language_capability_records = language_capability_records
        if final_qa_v2 is not None and not isinstance(final_qa_v2, FinalQAInterfaceV2):
            raise TypeError("final_qa_v2 must implement FinalQAInterfaceV2")
        self._final_qa_v2 = final_qa_v2
        self._final_qa: FinalQAInterfaceV1 | None = None
        self._phase85: Phase85Runtime | None = None
        self._advanced_retrieval: AdvancedRetrievalInterfaceV1 | None = None
        self._partitioned_retrieval: PartitionedRetrievalServiceV1 | None = None
        self._comparison: DeterministicComparisonServiceV1 | None = None
        self._structured_retrieval: StructuredDatasetRuntimeService | None = None
        self._registry = self._new_registry()
        self._state = EngineState.UNINITIALIZED
        self._providers: _ResolvedProviders | None = None
        self._lifecycle_lock = asyncio.Lock()

    @property
    def config(self) -> MnemoConfig:
        """Return the exact frozen runtime configuration."""
        return self._config

    @property
    def registry(self) -> PluginRegistry:
        """Return the current registry owned by this engine."""
        return self._registry

    async def install_exposed_full_multilingual_v2(
        self,
        *,
        source: object,
        readiness: V2ReadinessSnapshot,
    ) -> None:
        """Install the server-composed V2 source after all exposure gates pass.

        The server owns principal resolution and production registration, while
        core owns the shared retrieval graph.  Installation is deliberately
        impossible before READY and rejects activation-only readiness evidence.
        """
        async with self._lifecycle_lock:
            providers = self._require_ready()
            if not readiness.v2_exposed:
                raise EngineInitializationError(
                    "Full Multilingual V2 installation requires EXPOSED readiness"
                )
            if not isinstance(source, AdvancedRetrievalSourceV1):
                raise EngineInitializationError(
                    "Full Multilingual V2 source does not implement shared retrieval"
                )
            if source.representation is not EvidenceRepresentation.MULTILINGUAL_TEXT:
                raise EngineInitializationError("Full Multilingual V2 owns wrong representation")
            self._full_multilingual_v2_source = source
            self._full_multilingual_v2_readiness = readiness
            self._advanced_retrieval = await self._compose_advanced_retrieval(providers)

    @property
    def state(self) -> EngineState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def version(self) -> str:
        """Return the Mnemo package version."""
        return __version__

    @property
    def storage(self) -> StorageInterfaceV1:
        """Return the resolved primary storage façade while ready."""
        return self._require_ready().storage

    @property
    def asset_catalog(self) -> AssetCatalogStoreV1:
        """Return the additive Phase 8.5 asset catalog capability."""
        storage = self._require_ready().storage
        if not isinstance(storage, AssetCatalogStoreV1):
            raise DependencyUnavailableError("storage does not provide the asset catalog")
        return storage

    @property
    def asset_records(self) -> AssetRecordStoreV1:
        """Return safe asset metadata lookup without exposing physical paths."""
        storage = self._require_ready().storage
        if not isinstance(storage, AssetRecordStoreV1):
            raise DependencyUnavailableError("storage does not provide asset metadata lookup")
        return storage

    @property
    def processing_jobs(self) -> ProcessingJobStoreV1:
        """Return the additive durable processing capability while ready."""
        storage = self._require_ready().storage
        if not isinstance(storage, ProcessingJobStoreV1):
            raise DependencyUnavailableError("storage does not provide durable processing jobs")
        return storage

    @property
    def ocr_store(self) -> OCRStoreV1:
        """Return the additive derived OCR projection capability while ready."""
        storage = self._require_ready().storage
        if not isinstance(storage, OCRStoreV1):
            raise DependencyUnavailableError("storage does not provide OCR derivations")
        return storage

    @property
    def vision_store(self) -> VisionStoreV1:
        """Return additive vision and visual-vector derivation persistence."""
        storage = self._require_ready().storage
        if not isinstance(storage, VisionStoreV1):
            raise DependencyUnavailableError("storage does not provide vision derivations")
        return storage

    @property
    def embedding_provider(self) -> EmbeddingProviderV1:
        """Return the resolved primary embedding provider while ready."""
        return self._require_ready().embedding

    @property
    def reranker(self) -> RerankerInterfaceV1:
        """Return the resolved primary reranker while ready."""
        return self._require_ready().reranker

    @property
    def final_qa(self) -> FinalQAInterfaceV1:
        """Return the configured final-QA graph while ready."""
        self._require_ready()
        if self._final_qa is None:
            raise DependencyUnavailableError("final QA components were not supplied")
        return self._final_qa

    @property
    def final_qa_v2(self) -> FinalQAInterfaceV2:
        """Return the explicitly composed Final-QA V2 application interface."""
        self._require_ready()
        if self._final_qa_v2 is None:
            raise DependencyUnavailableError("Final-QA V2 is not composed")
        return self._final_qa_v2

    @property
    def final_qa_v2_execution_store(self) -> FinalQAExecutionStoreV2:
        """Return the mutable operational store, never an inferred corpus substitute."""
        providers = self._require_ready()
        components = self._final_qa_components
        if components is not None and components.operational_store_v2 is not None:
            return components.operational_store_v2
        if isinstance(providers.storage, FinalQAExecutionStoreV2):
            return providers.storage
        raise DependencyUnavailableError("Final-QA V2 operational persistence is unavailable")

    @property
    def phase85(self) -> Phase85Runtime:
        """Return the single additive Phase 8.5 runtime while the engine is ready."""
        self._require_ready()
        if self._phase85 is None:
            raise DependencyUnavailableError("Phase 8.5 runtime is unavailable")
        return self._phase85

    @property
    def language_capability_records(self) -> tuple[LanguageCapabilityRecordV3, ...]:
        """Return immutable runtime-derived V2 language capability projections."""
        self._require_ready()
        return self._language_capability_records

    @property
    def advanced_retrieval(self) -> AdvancedRetrievalInterfaceV1:
        """Return the composed additive ranked/exhaustive retrieval service."""
        self._require_ready()
        if self._advanced_retrieval is None:
            raise DependencyUnavailableError("advanced retrieval is not configured")
        return self._advanced_retrieval

    @property
    def partitioned_retrieval(self) -> PartitionedRetrievalServiceV1:
        """Return deterministic multi-document retrieval while ready."""
        self._require_ready()
        if self._partitioned_retrieval is None:
            raise DependencyUnavailableError("partitioned retrieval is not configured")
        return self._partitioned_retrieval

    @property
    def comparison(self) -> DeterministicComparisonServiceV1:
        """Return deterministic comparison primitives over typed evidence."""
        self._require_ready()
        if self._comparison is None:
            raise DependencyUnavailableError("comparison primitives are not configured")
        return self._comparison

    @property
    def structured_retrieval(self) -> StructuredDatasetRuntimeService:
        """Return the additive exact-version structured dataset runtime."""
        self._require_ready()
        if self._structured_retrieval is None:
            raise DependencyUnavailableError("structured retrieval is not configured")
        return self._structured_retrieval

    @property
    def document_scope_resolver(self) -> DocumentScopeResolverV1:
        """Return the additive fail-closed document scope resolver."""
        storage = self._require_ready().storage
        return StorageDocumentScopeResolverV1(storage, StorageSourceAssociationReaderV1(storage))

    def llm(self, role: _LLMRole) -> LLMInterfaceV1:
        """Return the resolved language model for one fixed role while ready."""
        providers = self._require_ready()
        match role:
            case "planner":
                return providers.planner
            case "synthesizer":
                return providers.synthesizer
            case "extractor":
                return providers.extractor
            case "classifier":
                return providers.classifier
            case _:
                raise ValueError(f"unknown LLM role: {role}")

    def capabilities(self) -> Mapping[str, _ProviderCapability]:
        """Return immutable capabilities advertised by resolved providers."""
        return self._require_ready().capabilities

    async def initialize(self) -> None:
        """Discover and atomically validate the configured runtime."""
        async with self._lifecycle_lock:
            if self._state is EngineState.READY:
                return
            if self._state is EngineState.FAILED:
                raise EngineLifecycleError("a failed KnowledgeEngine cannot be initialized")
            if self._state in (EngineState.INITIALIZING, EngineState.STOPPING):
                raise EngineLifecycleError(f"cannot initialize while engine is {self._state.value}")
            if self._state is EngineState.STOPPED:
                self._registry = self._new_registry()
            self._state = EngineState.INITIALIZING
            try:
                self._compose_runtime()
                await self._registry.execute_startup_hooks()
                self._registry.freeze()
                providers = self._resolve_providers()
                final_qa = self._compose_final_qa(providers)
                advanced_retrieval = await self._compose_advanced_retrieval(providers)
                partitioned_retrieval = (
                    None
                    if advanced_retrieval is None
                    else PartitionedRetrievalServiceV1(
                        advanced_retrieval, self._advanced_retrieval_cursor_codec
                    )
                )
                structured_retrieval = self._compose_structured_retrieval(providers)
                comparison = (
                    None if structured_retrieval is None else DeterministicComparisonServiceV1()
                )
                final_qa_v2 = self._compose_final_qa_v2(providers)
                structured_ready = (
                    False if structured_retrieval is None else await structured_retrieval.ready()
                )
                structured_generation_id = (
                    None
                    if not structured_ready or structured_retrieval is None
                    else await structured_retrieval.active_generation_identity()
                )
                phase85 = self._compose_phase85_runtime(
                    providers,
                    advanced_retrieval,
                    structured_retrieval,
                    structured_ready,
                    structured_generation_id,
                )
                await phase85.initialize()
                if not phase85.readiness().runtime_ready:
                    raise EngineInitializationError(
                        "required Phase 8.5 runtime capabilities are unavailable"
                    )
            except Exception as error:
                if "phase85" in locals():
                    with suppress(Exception):
                        await phase85.shutdown()
                with suppress(Exception):
                    await self._registry.execute_shutdown_hooks()
                self._providers = None
                self._final_qa = None
                self._final_qa_v2 = None
                self._phase85 = None
                self._advanced_retrieval = None
                self._partitioned_retrieval = None
                self._comparison = None
                self._structured_retrieval = None
                self._registry = self._new_registry()
                self._state = EngineState.FAILED
                if isinstance(error, EngineInitializationError):
                    raise
                raise EngineInitializationError(
                    "KnowledgeEngine initialization failed",
                ) from error
            self._providers = providers
            self._final_qa = final_qa
            self._final_qa_v2 = final_qa_v2
            self._phase85 = phase85
            self._advanced_retrieval = advanced_retrieval
            self._partitioned_retrieval = partitioned_retrieval
            self._comparison = comparison
            self._structured_retrieval = structured_retrieval
            self._state = EngineState.READY

    async def startup(self) -> None:
        """Deprecated alias for initialize()."""
        warnings.warn(
            "KnowledgeEngine.startup() is deprecated; use initialize()",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.initialize()

    async def shutdown(self) -> None:
        """Apply Phase 1 lifecycle shutdown without contacting providers."""
        async with self._lifecycle_lock:
            if self._state in (EngineState.UNINITIALIZED, EngineState.STOPPED):
                return
            if self._state is EngineState.FAILED:
                self._providers = None
                self._final_qa = None
                self._phase85 = None
                self._advanced_retrieval = None
                self._partitioned_retrieval = None
                self._comparison = None
                self._structured_retrieval = None
                return
            if self._state in (EngineState.INITIALIZING, EngineState.STOPPING):
                raise EngineLifecycleError(f"cannot shut down while engine is {self._state.value}")
            self._state = EngineState.STOPPING
            try:
                if self._phase85 is not None:
                    await self._phase85.shutdown()
                await self._registry.execute_shutdown_hooks()
            finally:
                self._providers = None
                self._final_qa = None
                self._phase85 = None
                self._advanced_retrieval = None
                self._partitioned_retrieval = None
                self._comparison = None
                self._structured_retrieval = None
                self._state = EngineState.STOPPED

    def _compose_phase85_runtime(
        self,
        providers: _ResolvedProviders,
        advanced_retrieval: AdvancedRetrievalInterfaceV1 | None,
        structured_retrieval: StructuredDatasetRuntimeService | None,
        structured_ready: bool,
        structured_generation_id: str | None,
    ) -> Phase85Runtime:
        """Compose ADR-0074 state from already-validated V1 providers and additive services."""
        service_registrations = list(self._phase85_service_registrations)
        if not any(item.capability_id == "capability_discovery" for item in service_registrations):
            service_registrations.append(
                Phase85ServiceRegistration(
                    capability_id="capability_discovery",
                    service=self,
                    ready=True,
                    activate=True,
                    exposed=True,
                    security_verified=True,
                )
            )
        if isinstance(providers.storage, AssetCatalogStoreV1) and not any(
            item.capability_id == "asset_discovery" for item in service_registrations
        ):
            service_registrations.append(
                Phase85ServiceRegistration(
                    capability_id="asset_discovery",
                    service=providers.storage,
                    ready=True,
                    activate=True,
                    security_verified=True,
                )
            )
        if advanced_retrieval is not None and not any(
            item.capability_id == "exhaustive_retrieval" for item in service_registrations
        ):
            service_registrations.append(
                Phase85ServiceRegistration(
                    capability_id="exhaustive_retrieval",
                    service=advanced_retrieval,
                    ready=True,
                    activate=True,
                    exposed=True,
                    security_verified=True,
                )
            )
        if (
            advanced_retrieval is not None
            and isinstance(providers.storage, MultimodalAdvancedStoreV1)
            and not any(
                item.capability_id == "multimodal_retrieval" for item in service_registrations
            )
        ):
            service_registrations.append(
                Phase85ServiceRegistration(
                    capability_id="multimodal_retrieval",
                    service=advanced_retrieval,
                    ready=True,
                    activate=True,
                    exposed=True,
                    security_verified=True,
                )
            )
        if structured_retrieval is not None and not any(
            item.capability_id == "structured_retrieval" for item in service_registrations
        ):
            service_registrations.append(
                Phase85ServiceRegistration(
                    capability_id="structured_retrieval",
                    service=structured_retrieval,
                    ready=structured_ready,
                    activate=structured_ready,
                    generation_id=structured_generation_id,
                    generation_active=structured_generation_id is not None,
                    exposed=structured_ready,
                    security_verified=True,
                )
            )
        if self._final_qa_v2 is not None and not any(
            item.capability_id == "final_qa_v2" for item in service_registrations
        ):
            service_registrations.append(
                Phase85ServiceRegistration(
                    capability_id="final_qa_v2",
                    service=self._final_qa_v2,
                    ready=True,
                    activate=True,
                    exposed=True,
                    security_verified=True,
                )
            )
        return Phase85Runtime(
            self._config,
            engine_ready=True,
            active_v1_profiles=frozenset(
                {
                    "v1.embedding",
                    "v1.reranker",
                    "llm.planner",
                    "llm.synthesizer",
                    "llm.extractor",
                    "llm.classifier",
                }
            ),
            core_active_capabilities=frozenset(
                {
                    "canonical_ingestion",
                    "v1_retrieval",
                    "authorization",
                    "completeness",
                    "cursor_continuation",
                    "provenance",
                    "capability_discovery",
                    "runtime_profile_activation",
                }
            ),
            provider_registrations=self._phase85_provider_registrations,
            service_registrations=tuple(service_registrations),
        )

    async def _compose_advanced_retrieval(
        self, providers: _ResolvedProviders
    ) -> AdvancedRetrievalInterfaceV1 | None:
        codec = self._advanced_retrieval_cursor_codec
        if codec is None or not isinstance(providers.storage, AdvancedCanonicalStoreV1):
            return None
        sparse = self._registry.resolve_retriever("sparse")
        if sparse is None:
            raise EngineInitializationError("advanced retrieval requires the sparse retriever")
        from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalSourceV1
        from mnemo.retrieval import (
            AdvancedRetrievalService,
            CanonicalAdvancedReranker,
            CanonicalTextAdvancedSource,
            ProjectedMultilingualAdvancedSource,
            ProjectedMultimodalAdvancedSource,
        )

        sources: list[AdvancedRetrievalSourceV1] = [
            CanonicalTextAdvancedSource(store=providers.storage, ranked_retriever=sparse)
        ]
        if isinstance(providers.storage, MultimodalAdvancedStoreV1):
            for representation in (
                EvidenceRepresentation.ASSET_METADATA,
                EvidenceRepresentation.OCR_TEXT,
                EvidenceRepresentation.VISION_ANALYSIS,
            ):
                generation = await providers.storage.active_multimodal_generation_identity(
                    representation
                )
                if generation is not None:
                    sources.append(
                        ProjectedMultimodalAdvancedSource(
                            store=providers.storage, representation=representation
                        )
                    )
            visual_provider = self._visual_query_embedding_provider
            if visual_provider is not None and await visual_provider.ready():
                generation = await providers.storage.active_multimodal_generation_identity(
                    EvidenceRepresentation.VISUAL_VECTOR,
                    profile_id=visual_provider.profile_id,
                )
                if generation is not None:
                    sources.append(
                        ProjectedMultimodalAdvancedSource(
                            store=providers.storage,
                            representation=EvidenceRepresentation.VISUAL_VECTOR,
                            visual_query_provider=visual_provider,
                        )
                    )
        v2_exposed = (
            self._full_multilingual_v2_readiness is not None
            and self._full_multilingual_v2_readiness.v2_exposed
        )
        if v2_exposed:
            multilingual_source = self._full_multilingual_v2_source
            if not isinstance(multilingual_source, AdvancedRetrievalSourceV1):
                raise EngineInitializationError(
                    "exposed Full Multilingual V2 source does not implement shared retrieval"
                )
            if multilingual_source.representation is not EvidenceRepresentation.MULTILINGUAL_TEXT:
                raise EngineInitializationError("Full Multilingual V2 owns wrong representation")
            sources.append(multilingual_source)
        elif isinstance(providers.storage, MultilingualAdvancedStoreV1) and (
            await providers.storage.active_multilingual_generation_identity() is not None
        ):
            projected_multilingual = ProjectedMultilingualAdvancedSource(providers.storage)
            if self._multilingual_advanced_source is None:
                sources.append(projected_multilingual)
            else:
                multilingual_source = self._multilingual_advanced_source
                if not isinstance(multilingual_source, AdvancedRetrievalSourceV1):
                    raise EngineInitializationError(
                        "multilingual advanced source does not implement the shared contract"
                    )
                if (
                    multilingual_source.representation
                    is not EvidenceRepresentation.MULTILINGUAL_TEXT
                ):
                    raise EngineInitializationError(
                        "multilingual advanced source owns the wrong representation"
                    )
                sources.append(multilingual_source)

        return cast(
            AdvancedRetrievalInterfaceV1,
            AdvancedRetrievalService(
                sources=tuple(sources),
                cursor_codec=codec,
                # Full Multilingual V2 has already applied the governed BGE
                # candidate contract.  Applying the legacy primary reranker a
                # second time would make the public path differ from V2.
                reranker=(None if v2_exposed else CanonicalAdvancedReranker(providers.reranker)),
            ),
        )

    @staticmethod
    def _compose_structured_retrieval(
        providers: _ResolvedProviders,
    ) -> StructuredDatasetRuntimeService | None:
        if not isinstance(providers.storage, StructuredDatasetCatalogV1):
            return None
        return StructuredDatasetRuntimeService(providers.storage)

    def _compose_runtime(self) -> None:
        results: list[PluginLoadResult] = []
        builtins = self._registry.load_plugins(_builtin_plugins(self._config))
        self._log_failures("built-in", builtins)
        results.extend(builtins)
        entry_points = self._registry.discover_and_load_entry_points()
        self._log_failures("entry-point", entry_points)
        results.extend(entry_points)
        candidates = _plugin_candidates(self._config.plugins.directory)
        paths = self._registry.discover_and_load_paths(candidates)
        self._log_failures("path", paths)
        results.extend(paths)
        _reject_required_plugin_failures(tuple(results))

    def _compose_final_qa(self, providers: _ResolvedProviders) -> FinalQAInterfaceV1 | None:
        components = self._final_qa_components
        if components is None:
            return None
        counter = components.token_counter
        tokenizer_id = importlib.import_module("mnemo.tokenizers").O200K_BASE_TOKENIZER_ID
        if counter.tokenizer_id != tokenizer_id or counter.count("") != 0:
            raise EngineInitializationError("canonical final-QA token counter is unavailable")
        for slot in ("dense", "sparse"):
            if self._registry.resolve_retriever(slot) is None:
                raise EngineInitializationError(f"required retriever '{slot}' is unavailable")
        if self._registry.resolve_parent_promoter("default") is None:
            raise EngineInitializationError("required parent promoter 'default' is unavailable")
        from mnemo.retrieval import (
            CitationEngine,
            ContextBuilder,
            FinalQAOrchestrator,
            GroundedAnswerGenerator,
            MultiSourceRetriever,
            QueryPlanner,
            RerankingModule,
        )

        planner = QueryPlanner(providers.planner, providers.embedding)
        fusion = MultiSourceRetriever(self._registry, providers.embedding)
        reranker = RerankingModule(self._registry)
        context = ContextBuilder(self._registry, counter)
        answer = GroundedAnswerGenerator(self._registry, counter)
        citation = CitationEngine(providers.storage, components.clock)
        return FinalQAOrchestrator(
            planner,
            fusion,
            reranker,
            context,
            answer,
            citation,
            providers.storage,
            components.clock,
            (providers.storage if isinstance(providers.storage, FinalQAExecutionStoreV1) else None),
        )

    def _compose_final_qa_v2(self, providers: _ResolvedProviders) -> FinalQAInterfaceV2 | None:
        """Compose V2 only when storage, tokenizer, and configured LLM are available."""
        if self._final_qa_components is None:
            return self._final_qa_v2
        operational_store = self._final_qa_components.operational_store_v2
        if operational_store is None:
            if not isinstance(providers.storage, FinalQAExecutionStoreV2):
                return self._final_qa_v2
            operational_store = providers.storage
        from mnemo.retrieval import (
            FinalQAV2Orchestrator,
            LLMFinalQAV2Provider,
            MultimodalContextBuilder,
            StorageEvidenceAuthorizerV2,
        )

        provider = LLMFinalQAV2Provider(providers.synthesizer)
        authorizer = StorageEvidenceAuthorizerV2(providers.storage)
        return FinalQAV2Orchestrator(
            store=operational_store,
            provider=provider,
            context_builder=MultimodalContextBuilder(
                authorizer, self._final_qa_components.token_counter
            ),
            token_counter=self._final_qa_components.token_counter,
            authorizer=authorizer,
        )

    def _resolve_providers(self) -> _ResolvedProviders:
        storage = self._registry.resolve_storage(_PRIMARY_SLOT)
        embedding = self._registry.resolve_embedding_provider(_PRIMARY_SLOT)
        reranker = self._registry.resolve_reranker(_PRIMARY_SLOT)
        llms = {role: self._registry.resolve_llm(role) for role in _LLM_ROLES}

        if storage is None:
            raise EngineInitializationError("required storage provider 'primary' is unavailable")
        if embedding is None:
            raise EngineInitializationError("required embedding provider 'primary' is unavailable")
        if reranker is None:
            raise EngineInitializationError("required reranker 'primary' is unavailable")
        missing_roles = tuple(role for role, provider in llms.items() if provider is None)
        if missing_roles:
            raise EngineInitializationError(
                f"required LLM providers are unavailable: {', '.join(missing_roles)}"
            )

        planner = _require_llm(llms["planner"], "planner")
        synthesizer = _require_llm(llms["synthesizer"], "synthesizer")
        extractor = _require_llm(llms["extractor"], "extractor")
        classifier = _require_llm(llms["classifier"], "classifier")
        capabilities: dict[str, _ProviderCapability] = {
            "storage": _storage_capabilities(storage),
            "embedding": _embedding_capabilities(
                embedding,
                expected_dimensions=self._config.embedding.dimensions,
            ),
            "reranker": _reranker_capabilities(reranker),
            "planner": _llm_capabilities(planner, "planner"),
            "synthesizer": _llm_capabilities(synthesizer, "synthesizer"),
            "extractor": _llm_capabilities(extractor, "extractor"),
            "classifier": _llm_capabilities(classifier, "classifier"),
        }
        return _ResolvedProviders(
            storage=storage,
            embedding=embedding,
            reranker=reranker,
            planner=planner,
            synthesizer=synthesizer,
            extractor=extractor,
            classifier=classifier,
            capabilities=MappingProxyType(capabilities),
        )

    def _require_ready(self) -> _ResolvedProviders:
        if self._state is not EngineState.READY or self._providers is None:
            raise EngineLifecycleError("resolved providers are available only while READY")
        return self._providers

    def _new_registry(self) -> PluginRegistry:
        return PluginRegistry(core_version=self.version)

    @staticmethod
    def _log_failures(source: str, results: tuple[PluginLoadResult, ...]) -> None:
        for result in results:
            if not result.loaded:
                _LOGGER.warning(
                    "%s plugin %s failed discovery: %s (%s)",
                    source,
                    result.descriptor.name,
                    result.error_message,
                    result.error_code,
                )


def _builtin_plugins(config: MnemoConfig) -> tuple[PluginInterfaceV1, ...]:
    """Return built-in candidates supplied by their designated roadmap modules."""
    primary_storage: StorageInterfaceV1 | None = None

    class CoreStoragePlugin:
        name = "mnemo-core-storage"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("storage",)

        def register(self, registry: PluginRegistry) -> None:
            nonlocal primary_storage
            from mnemo.storage import (
                CompositeStorage,
                FilesystemBlobStore,
                QdrantStore,
                SQLiteStore,
                SurrealDBStore,
            )

            filesystem = FilesystemBlobStore(config.storage.filesystem.root)
            sqlite = SQLiteStore(config.storage.sqlite.path)
            qdrant = QdrantStore(
                config.storage.qdrant,
                vector_dimensions=config.embedding.dimensions,
            )
            surrealdb = SurrealDBStore(config.storage.surrealdb)

            composite = CompositeStorage(
                filesystem=filesystem,
                sqlite=sqlite,
                qdrant=qdrant,
                surrealdb=surrealdb,
            )
            primary_storage = composite

            # Core priority permits an explicitly higher-priority provider override.
            registry.register_storage("primary", composite, priority=0)

            async def open_when_active() -> None:
                if registry.resolve_storage("primary") is composite:
                    await composite.open()

            async def close_when_active() -> None:
                if registry.resolve_storage("primary") is composite:
                    await composite.close()

            registry.register_startup_hook(open_when_active)
            registry.register_shutdown_hook(close_when_active)

    class CoreRetrievalPlugin:
        name = "mnemo-core-retrieval"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("retriever", "parent_promotion")

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.retrieval import DenseRetriever, ParentRetriever, SparseRetriever

            if primary_storage is None:
                raise EngineInitializationError("primary storage must register before retrieval")
            registry.register_retriever("dense", DenseRetriever(primary_storage), priority=0)
            registry.register_retriever("sparse", SparseRetriever(primary_storage), priority=0)
            registry.register_parent_promoter(
                "default", ParentRetriever(primary_storage), priority=0
            )

    class CoreParserPlugin:
        name = "mnemo-core-parsers"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("parser",)

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.parsers import (
                CSVParser,
                DOCXParser,
                HTMLParser,
                JSONParser,
                MarkdownParser,
                PDFParser,
                PlainTextParser,
                PPTXParser,
                StandaloneImageParser,
                XLSXParser,
            )

            plain_text_parser = PlainTextParser()
            parsers = (
                (PDFParser(), (".pdf", "application/pdf")),
                (
                    DOCXParser(),
                    (
                        ".docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                ),
                (
                    PPTXParser(),
                    (
                        ".pptx",
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    ),
                ),
                (MarkdownParser(), (".md", ".markdown", "text/markdown", "text/x-markdown")),
                (HTMLParser(), (".html", ".htm", "text/html")),
                (
                    StandaloneImageParser(),
                    (
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".gif",
                        ".webp",
                        ".tif",
                        ".tiff",
                        ".bmp",
                        ".svg",
                        "image/png",
                        "image/jpeg",
                        "image/gif",
                        "image/webp",
                        "image/tiff",
                        "image/bmp",
                        "image/svg+xml",
                    ),
                ),
                (
                    plain_text_parser,
                    (
                        ".txt",
                        ".log",
                        "text/plain",
                        # Code file extensions — parsed as RawCodeBlock by PlainTextParser
                        ".c",
                        ".cc",
                        ".cpp",
                        ".cxx",
                        ".go",
                        ".h",
                        ".hpp",
                        ".java",
                        ".js",
                        ".jsx",
                        ".py",
                        ".rs",
                        ".ts",
                        ".tsx",
                        # MIME types that mimetypes / libmagic detect for code files
                        "text/javascript",
                        "text/x-python",
                        "text/x-c",
                        "text/x-c++",
                        "text/x-java",
                        "text/x-go",
                        "text/x-rust",
                    ),
                ),
                (JSONParser(), (".json", "application/json")),
                (CSVParser(), (".csv", ".tsv", "text/csv", "text/tab-separated-values")),
                (
                    XLSXParser(),
                    (
                        ".xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
            )
            for parser, slots in parsers:
                for slot in slots:
                    registry.register_parser(slot, parser, priority=0)

    class CoreChunkerPlugin:
        name = "mnemo-core-chunkers"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("chunker",)

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.chunkers import (
                BookChunker,
                CodeChunker,
                DocumentationChunker,
                EmailChunker,
                GenericChunker,
                MarkdownChunker,
                PaperChunker,
                ResumeChunker,
                SlidesChunker,
            )
            from mnemo.models import DocType

            registry.register_chunker_v2(DocType.GENERIC, GenericChunker(), priority=0)
            registry.register_chunker_v2(DocType.BOOK, BookChunker(), priority=0)
            registry.register_chunker_v2(DocType.PAPER, PaperChunker(), priority=0)
            registry.register_chunker_v2(DocType.CODE, CodeChunker(), priority=0)
            registry.register_chunker_v2(DocType.MARKDOWN, MarkdownChunker(), priority=0)
            registry.register_chunker_v2(DocType.EMAIL, EmailChunker(), priority=0)
            registry.register_chunker_v2(DocType.RESUME, ResumeChunker(), priority=0)
            registry.register_chunker_v2(DocType.SLIDES, SlidesChunker(), priority=0)
            registry.register_chunker_v2(DocType.DOCUMENTATION, DocumentationChunker(), priority=0)

    class CoreEmbeddingPlugin:
        name = "mnemo-core-embedding"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("embedding",)

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.embeddings.cached import CachedEmbeddingProvider
            from mnemo.storage.cache import SQLiteEmbeddingCache

            cache = SQLiteEmbeddingCache(config.storage.sqlite.path.parent / "embedding-cache.db")
            provider: EmbeddingProviderV1
            if config.embedding.provider == "sentence-transformers":
                from mnemo.embeddings.sentence_transformers import SentenceTransformersEmbedder

                provider = SentenceTransformersEmbedder(config.embedding)
            elif config.embedding.provider == "ollama":
                from mnemo.embeddings.ollama import OllamaEmbedder

                provider = OllamaEmbedder(config.embedding)
            else:
                raise ValueError(f"Unsupported embedding provider: {config.embedding.provider}")

            cached = CachedEmbeddingProvider(provider, cache)
            registry.register_embedding_provider("primary", cached, priority=0)
            registry.register_startup_hook(cache.initialize)
            registry.register_startup_hook(provider.initialize)

    class CoreLLMPlugin:
        name = "mnemo-core-llm"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("llm",)

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.llms import OllamaLLM

            for role in _LLM_ROLES:
                role_config = getattr(config.llm, role)
                if role_config.provider != "ollama":
                    continue
                provider = OllamaLLM(role_config)
                registry.register_llm(role, provider, priority=0)
                registry.register_startup_hook(provider.initialize)
                registry.register_shutdown_hook(provider.close)

    plugins: list[PluginInterfaceV1] = [
        CoreStoragePlugin(),
        CoreRetrievalPlugin(),
        CoreParserPlugin(),
        CoreChunkerPlugin(),
        CoreEmbeddingPlugin(),
        CoreLLMPlugin(),
    ]
    if config.reranker.provider == "sentence-transformers":
        from mnemo.retrieval.reranker import CrossEncoderReranker, CrossEncoderRerankerPlugin

        plugins.append(CrossEncoderRerankerPlugin(CrossEncoderReranker(config.reranker)))
    elif config.reranker.provider == "v2-owned-pass-through":
        plugins.append(_V2OwnedOuterPassThroughRerankerPlugin())
    return tuple(plugins)


def _plugin_candidates(directory: Path) -> tuple[Path, ...]:
    """Return deterministic immediate Python plugin candidates."""
    if not directory.is_dir():
        raise EngineInitializationError(f"plugin directory is unavailable: {directory}")
    try:
        children = tuple(directory.iterdir())
    except OSError as error:
        raise EngineInitializationError(f"plugin directory cannot be read: {directory}") from error
    candidates = (
        child
        for child in children
        if not child.name.startswith(".")
        and (child.suffix == ".py" or (child.is_dir() and (child / "__init__.py").is_file()))
    )
    return tuple(sorted(candidates, key=lambda path: str(path)))


def _reject_required_plugin_failures(results: tuple[PluginLoadResult, ...]) -> None:
    """Reject failed plugins that advertise a Phase 1 required capability."""
    failed = tuple(
        result.descriptor.name
        for result in results
        if not result.loaded
        and not _REQUIRED_CAPABILITIES.isdisjoint(result.descriptor.capabilities)
    )
    if failed:
        raise EngineInitializationError(
            f"plugins providing required capabilities failed: {', '.join(failed)}"
        )


def _storage_capabilities(provider: StorageInterfaceV1) -> StorageCapabilities:
    if not isinstance(provider, StorageInterfaceV1):
        raise EngineInitializationError("primary storage does not implement StorageInterfaceV1")
    capabilities = provider.capabilities()
    if not isinstance(capabilities, StorageCapabilities):
        raise EngineInitializationError("primary storage returned invalid capabilities")
    return capabilities


def _embedding_capabilities(
    provider: EmbeddingProviderV1,
    *,
    expected_dimensions: int,
) -> EmbeddingCapabilities:
    if not isinstance(provider, EmbeddingProviderV1):
        raise EngineInitializationError(
            "primary embedding provider does not implement EmbeddingProviderV1"
        )
    capabilities = provider.capabilities()
    if not isinstance(capabilities, EmbeddingCapabilities):
        raise EngineInitializationError("primary embedding provider returned invalid capabilities")
    if provider.dimensions != expected_dimensions or capabilities.dimensions != expected_dimensions:
        raise EngineInitializationError("embedding dimensions do not match configuration")
    return capabilities


def _reranker_capabilities(provider: RerankerInterfaceV1) -> RerankerCapabilities:
    if not isinstance(provider, RerankerInterfaceV1):
        raise EngineInitializationError("primary reranker does not implement RerankerInterfaceV1")
    capabilities = provider.capabilities()
    if not isinstance(capabilities, RerankerCapabilities):
        raise EngineInitializationError("primary reranker returned invalid capabilities")
    return capabilities


def _require_llm(provider: LLMInterfaceV1 | None, role: str) -> LLMInterfaceV1:
    if provider is None or not isinstance(provider, LLMInterfaceV1):
        raise EngineInitializationError(f"{role} does not implement LLMInterfaceV1")
    if not isinstance(provider.provider, str) or not provider.provider.strip():
        raise EngineInitializationError(f"{role} LLM does not declare a provider")
    if not isinstance(provider.model, str) or not provider.model.strip():
        raise EngineInitializationError(f"{role} LLM does not declare a model")
    return provider


def _llm_capabilities(provider: LLMInterfaceV1, role: str) -> LLMCapabilities:
    capabilities = provider.capabilities()
    if not isinstance(capabilities, LLMCapabilities):
        raise EngineInitializationError(f"{role} LLM returned invalid capabilities")
    return capabilities
