"""Runtime-derived Phase 8.5 capability discovery application service."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError
from mnemo.phase85 import CapabilityStatus

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.capabilities_v2 import (
    ActiveModelProfileResponse,
    CapabilityDependencyResponse,
    CapabilityDiscoveryRequest,
    CapabilityDocument,
    CapabilityGenerationResponse,
    CapabilityLifecycleResponse,
    CapabilityNextActionResponse,
    CapabilityProfileResponse,
    CapabilityResponse,
    CapabilityRuntimeResponse,
    CapabilityTaskGuidanceResponse,
    CapabilityTransportResponse,
)


@dataclass(frozen=True, slots=True)
class _PublicSemantics:
    category: str
    representations: tuple[str, ...] = ()
    modalities: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    retrieval_modes: tuple[str, ...] = ()
    continuation: bool = False
    http: tuple[str, ...] = ()
    mcp: tuple[str, ...] = ()


_GENERATION_BACKED: Final = frozenset(
    {
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
)

_SEMANTICS: Final[dict[str, _PublicSemantics]] = {
    "v1_retrieval": _PublicSemantics(
        "retrieval",
        ("canonical_text",),
        retrieval_modes=("ranked",),
        http=("/v1/search", "/v1/query"),
        mcp=("search_all_notebooks", "query_notebook"),
    ),
    "exact_retrieval": _PublicSemantics(
        "retrieval",
        ("canonical_text", "original_document"),
        continuation=True,
        http=("/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}",),
        mcp=("get_document", "get_document_chunk"),
    ),
    "positional_retrieval": _PublicSemantics(
        "retrieval",
        ("canonical_text", "positional_metadata"),
        continuation=True,
        http=("/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/expand",),
        mcp=("get_document",),
    ),
    "document_delivery": _PublicSemantics(
        "delivery",
        ("canonical_text", "original_document"),
        continuation=True,
        http=("/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}",),
        mcp=("get_document", "get_document_chunk"),
    ),
    "exhaustive_retrieval": _PublicSemantics(
        "retrieval",
        ("canonical_text", "title_metadata"),
        retrieval_modes=("ranked", "exhaustive"),
        continuation=True,
        http=("/v2/retrieval/evidence",),
        mcp=("search_evidence",),
    ),
    "structured_retrieval": _PublicSemantics(
        "structured",
        ("structured_rows", "structured_cells"),
        retrieval_modes=("exact",),
        continuation=True,
        http=("/v2/retrieval/structured",),
        mcp=("query_structured",),
    ),
    "asset_discovery": _PublicSemantics(
        "asset",
        ("asset_occurrence", "asset_metadata"),
        modalities=("image",),
        continuation=True,
        mcp=("get_asset",),
    ),
    "asset_delivery": _PublicSemantics(
        "delivery",
        ("original_asset",),
        modalities=("image",),
        continuation=True,
        mcp=("get_asset",),
    ),
    "ocr": _PublicSemantics(
        "derived", ("ocr_text",), modalities=("ocr",), mcp=("get_image_analysis",)
    ),
    "vision": _PublicSemantics(
        "derived", ("vision_analysis",), modalities=("vision",), mcp=("get_image_analysis",)
    ),
    "visual_vector_retrieval": _PublicSemantics(
        "retrieval",
        ("visual_vector",),
        modalities=("image",),
        retrieval_modes=("ranked",),
        http=("/v2/retrieval/evidence",),
        mcp=("search_evidence",),
    ),
    "multimodal_retrieval": _PublicSemantics(
        "retrieval",
        ("canonical_text", "ocr_text", "vision_analysis", "visual_vector"),
        modalities=("text", "image", "ocr", "vision"),
        retrieval_modes=("ranked", "exhaustive"),
        continuation=True,
        http=("/v2/retrieval/evidence",),
        mcp=("search_evidence",),
    ),
    "multilingual_retrieval": _PublicSemantics(
        "retrieval",
        ("canonical_text", "language_text"),
        modalities=("text",),
        languages=("en", "hi", "mr"),
        retrieval_modes=("ranked", "exhaustive", "cross_language"),
        continuation=True,
        http=("/v2/retrieval/evidence",),
        mcp=("search_evidence",),
    ),
    "multilingual_retrieval_v2": _PublicSemantics(
        "retrieval",
        ("canonical_text", "multilingual_text"),
        modalities=("text",),
        retrieval_modes=("ranked", "exhaustive", "cross_language"),
        continuation=True,
        http=("/v2/retrieval/evidence",),
        mcp=("search_evidence",),
    ),
    "final_qa_v2": _PublicSemantics(
        "final_qa",
        ("typed_evidence",),
        modalities=("text", "image", "ocr", "vision"),
        http=("/v2/notebooks/{notebook_id}/final-qa",),
        mcp=("run_final_qa_v2",),
    ),
    "capability_discovery": _PublicSemantics(
        "discovery",
        ("runtime_capability_metadata",),
        http=("/v2/capabilities",),
        mcp=("get_capabilities",),
    ),
}

_TASKS: Final = (
    (
        "ranked_semantic_search",
        "exhaustive_retrieval",
        "search_evidence",
        "Relevant ranked evidence",
        "Exact positions or every match",
    ),
    (
        "exhaustive_lookup",
        "exhaustive_retrieval",
        "search_evidence",
        "Every matching evidence item",
        "Top-k relevance only",
    ),
    (
        "exact_document_traversal",
        "exact_retrieval",
        "get_document",
        "Exact page/range/first/last/full content",
        "Semantic ranking",
    ),
    (
        "structured_query",
        "structured_retrieval",
        "query_structured",
        "Numeric filters, counts, groups, aggregates",
        "Free-text relevance or arbitrary SQL",
    ),
    (
        "original_asset",
        "asset_delivery",
        "get_asset",
        "Original image bytes or occurrence inventory",
        "Semantic image description",
    ),
    (
        "image_analysis",
        "vision",
        "get_image_analysis",
        "Existing OCR or Vision derivations",
        "Original image delivery",
    ),
    (
        "multimodal_search",
        "multimodal_retrieval",
        "search_evidence",
        "Semantic image/derived evidence discovery",
        "Original binary delivery",
    ),
    (
        "multilingual_search",
        "multilingual_retrieval",
        "search_evidence",
        "Same- or cross-language evidence retrieval",
        "English-only assumptions",
    ),
    (
        "final_qa",
        "final_qa_v2",
        "run_final_qa_v2",
        "Persisted cited answer over typed evidence",
        "Evidence discovery or exact traversal",
    ),
    (
        "capability_discovery",
        "capability_discovery",
        "get_capabilities",
        "Select a supported governed path",
        "Authorization or data retrieval",
    ),
)


class CapabilityDiscoveryService:
    """Project the single Phase85RuntimeV1 state into a redacted public document."""

    def __init__(self, engine: KnowledgeEngine, config: ServerConfig) -> None:
        self._engine = engine
        self._config = config

    def document(self, request: CapabilityDiscoveryRequest | None = None) -> CapabilityDocument:
        query = request or CapabilityDiscoveryRequest()
        runtime = self._engine.phase85
        selected = set(query.capability_ids)
        statuses = runtime.capabilities()
        unknown = selected - set(statuses)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ContractValidationError(f"unknown Phase 8.5 capabilities: {names}")
        items = tuple(
            self._capability(status)
            for capability_id, status in sorted(statuses.items())
            if not selected or capability_id in selected
        )
        readiness = runtime.readiness()
        active_profile = runtime.active_profile
        task_guidance = tuple(self._task(item, statuses) for item in _TASKS)
        base = CapabilityDocument(
            snapshot_identity="0" * 64,
            # WP-14 owns actor/notebook policy qualification. Accept the frozen optional
            # scope input, but never imply that global runtime metadata was authorized per scope.
            scope_qualified=False,
            runtime=CapabilityRuntimeResponse(
                engine_ready=readiness.engine_ready,
                runtime_ready=readiness.runtime_ready,
                required_capabilities=readiness.required_capabilities,
                unavailable_required=readiness.unavailable_required,
                unavailable_optional=readiness.unavailable_optional,
                configuration_fingerprint=runtime.configuration_fingerprint,
                active_profile=ActiveModelProfileResponse(
                    schema_version=active_profile.schema_version,
                    profile_id=active_profile.profile_id,
                    version=active_profile.version,
                    mode=active_profile.mode.value,
                    enabled=active_profile.enabled,
                    trust_class=active_profile.trust_class.value,
                    certification=active_profile.certification.value,
                    fingerprint=active_profile.fingerprint,
                    http_enabled=active_profile.http_enabled,
                    mcp_enabled=active_profile.mcp_enabled,
                ),
            ),
            capabilities=items,
            task_guidance=task_guidance,
            limitations=(
                "Capability metadata does not grant authorization.",
                "Exposed does not imply behaviorally verified or certified.",
                "Notebook scope is opaque until WP-14 authorization policy evaluation.",
            ),
        )
        canonical = base.model_dump(mode="json", exclude={"snapshot_identity"})
        identity = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return base.model_copy(update={"snapshot_identity": identity})

    def _capability(self, status: CapabilityStatus) -> CapabilityResponse:
        semantics = _SEMANTICS.get(status.capability_id, _PublicSemantics("runtime"))
        runtime = self._engine.phase85
        dependencies = tuple(
            CapabilityDependencyResponse(
                capability_id=dependency,
                stage=(
                    runtime.capability_status(dependency).state.stage.value
                    if dependency in runtime.capabilities()
                    else None
                ),
                active=(
                    runtime.capability_status(dependency).state.active
                    if dependency in runtime.capabilities()
                    else None
                ),
                reason=(
                    runtime.capability_status(dependency).reason_code
                    if dependency in runtime.capabilities()
                    else "external_dependency"
                ),
            )
            for dependency in status.dependencies
        )
        profiles = tuple(
            CapabilityProfileResponse(
                profile_id=profile.profile_id,
                operation=profile.operation,
                provider=profile.provider,
                model=profile.model,
                revision=profile.revision,
                dimensions=profile.dimensions,
                trust_class=profile.trust_class,
                certification=profile.certification,
                configured=profile.state.configured,
                available=profile.state.available_locally,
                loadable=profile.state.loadable,
                initialized=profile.state.initialized,
                active=profile.state.active,
                reason=profile.reason_code,
            )
            for profile_id in status.profile_ids
            for profile in (runtime.profile_status(profile_id),)
        )
        state = status.state
        tools = semantics.mcp if runtime.active_profile.mcp_enabled else ()
        next_actions = (
            tuple(
                CapabilityNextActionResponse(
                    action="invoke",
                    tool=tool,
                    reason="Capability is exposed by the active runtime.",
                )
                for tool in tools
            )
            if state.exposed
            else (
                CapabilityNextActionResponse(
                    action="inspect_dependencies",
                    tool="get_capabilities",
                    reason=status.reason_code or "Capability is not active and exposed.",
                ),
            )
        )
        return CapabilityResponse(
            capability_id=status.capability_id,
            description=status.owner,
            category=semantics.category,
            lifecycle=CapabilityLifecycleResponse(
                stage=state.stage.value,
                declared=state.declared,
                configured=state.configured,
                buildable=state.buildable,
                ready=state.ready,
                active=state.active,
                exposed=state.exposed,
                behaviorally_verified=state.behaviorally_verified,
                security_verified=state.security_verified,
                certified=state.certified,
            ),
            dependencies=dependencies,
            profiles=profiles,
            generation=CapabilityGenerationResponse(
                required=status.capability_id in _GENERATION_BACKED,
                generation_id=status.generation_id,
                present=status.generation_id is not None,
                active=status.generation_active,
            ),
            transports=CapabilityTransportResponse(
                http=semantics.http if runtime.active_profile.http_enabled else (),
                mcp=semantics.mcp if runtime.active_profile.mcp_enabled else (),
                callable=state.exposed
                and bool(
                    (semantics.http if runtime.active_profile.http_enabled else ())
                    or (semantics.mcp if runtime.active_profile.mcp_enabled else ())
                ),
            ),
            supported_representations=semantics.representations if state.active else (),
            supported_modalities=semantics.modalities if state.active else (),
            supported_languages=self._supported_languages(status, semantics),
            retrieval_modes=semantics.retrieval_modes,
            continuation=semantics.continuation,
            limits=self._limits(status.capability_id),
            recommended_tools=tools,
            next_actions=next_actions,
            unavailable_reason=None if state.active else status.reason_code or "not_active",
        )

    def _supported_languages(
        self, status: CapabilityStatus, semantics: _PublicSemantics
    ) -> tuple[str, ...]:
        if not status.state.active:
            return ()
        if status.capability_id != "multilingual_retrieval_v2":
            return semantics.languages
        records = self._engine.language_capability_records
        return tuple(
            sorted(
                {
                    item.input.language.value
                    for item in records
                    if item.effective_state
                    in {"active", "exposed", "evaluated", "verified", "certified"}
                    and item.availability_state == "available"
                }
            )
        )

    def _limits(self, capability_id: str) -> dict[str, int | str | bool]:
        if capability_id in {
            "exhaustive_retrieval",
            "multimodal_retrieval",
            "multilingual_retrieval",
            "multilingual_retrieval_v2",
            "visual_vector_retrieval",
        }:
            return {
                "max_candidates": self._config.max_advanced_candidate_budget,
                "max_evidence": self._config.max_advanced_evidence_budget,
                "max_response_bytes": self._config.max_advanced_response_bytes,
                "max_elapsed_milliseconds": self._config.max_advanced_elapsed_milliseconds,
            }
        if capability_id == "structured_retrieval":
            return {
                "max_rows_scanned": self._config.max_structured_rows_scanned,
                "max_rows_returned": self._config.max_structured_rows_returned,
                "max_groups": self._config.max_structured_groups,
                "max_page_size": self._config.max_structured_page_size,
            }
        if capability_id in {"document_delivery", "exact_retrieval", "positional_retrieval"}:
            return {
                "max_document_bytes": self._config.max_delivery_document_bytes,
                "max_response_bytes": self._config.max_delivery_response_bytes,
                "cursor_ttl_seconds": self._config.delivery_cursor_ttl_seconds,
                "selector_families": "full,page,slide,sheet,block,chunk,section,from_end,adjacent",
            }
        if capability_id in {"asset_discovery", "asset_delivery", "ocr", "vision"}:
            return {
                "max_asset_bytes": self._config.max_delivery_asset_bytes,
                "max_assets": self._config.max_delivery_assets,
            }
        return {}

    @staticmethod
    def _task(
        item: tuple[str, str, str, str, str], statuses: Mapping[str, CapabilityStatus]
    ) -> CapabilityTaskGuidanceResponse:
        task, capability_id, tool, use_when, do_not_use_when = item
        status = statuses.get(capability_id)
        return CapabilityTaskGuidanceResponse(
            task=task,
            capability_id=capability_id,
            tool=tool,
            use_when=use_when,
            do_not_use_when=do_not_use_when,
            available=bool(status and status.state.exposed),
        )
