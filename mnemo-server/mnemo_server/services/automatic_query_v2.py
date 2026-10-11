"""Shared server-owned automatic evidence planner for MCP and HTTP V2."""

from __future__ import annotations

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError, DependencyUnavailableError
from mnemo.models import EvidenceRepresentation
from mnemo.retrieval.advanced import AdvancedRetrievalService

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.automatic_query_v2 import (
    AutomaticQueryV2Request,
    AutomaticQueryV2Response,
    AutomaticRepresentationStatus,
    RepresentationDecisionV2,
)
from mnemo_server.schemas.retrieval_v2 import EvidenceScopeRequest, EvidenceSearchRequest
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
    ServerPrincipalV1,
)
from mnemo_server.services.retrieval_v2 import EvidenceRetrievalApplicationService

_ORDER = (
    EvidenceRepresentation.CANONICAL_TEXT,
    EvidenceRepresentation.OCR_TEXT,
    EvidenceRepresentation.VISION_ANALYSIS,
    EvidenceRepresentation.MULTILINGUAL_TEXT,
    EvidenceRepresentation.VISUAL_VECTOR,
)


class AutomaticEvidencePlanner:
    """Select only composed V2 sources after the authorized scope is resolved."""

    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def plan(
        self, principal: ServerPrincipalV1
    ) -> tuple[
        EvidenceScopeRequest, tuple[EvidenceRepresentation, ...], list[RepresentationDecisionV2]
    ]:
        if not principal.authenticated:
            raise PermissionError("authenticated principal is required")
        # No persisted actor-to-notebook membership authority exists yet. Do not
        # guess a scope or leak per-notebook generation state in a multi-notebook store.
        page = await self._engine.storage.list_notebooks(limit=2, cursor=None)
        if len(page.items) != 1 or page.next_cursor is not None:
            raise DependencyUnavailableError(
                "automatic query requires one unambiguous authorized notebook scope",
                retryable=False,
            )
        notebook_id = page.items[0].notebook_id
        await CentralAuthorizationServiceV1(self._engine).authorize_notebook(
            principal, notebook_id, AuthorizationOperationV1.QUERY
        )
        retrieval = self._engine.advanced_retrieval
        if not isinstance(retrieval, AdvancedRetrievalService):
            raise DependencyUnavailableError(
                "automatic query requires the governed V2 retrieval service", retryable=False
            )
        active = set(retrieval.active_representations)
        if EvidenceRepresentation.CANONICAL_TEXT not in active:
            raise DependencyUnavailableError("canonical retrieval is unavailable", retryable=False)
        selected = tuple(item for item in _ORDER if item in active)
        decisions = [
            RepresentationDecisionV2(
                representation=item.value,
                status=(
                    AutomaticRepresentationStatus.SEARCHED
                    if item in active
                    else AutomaticRepresentationStatus.UNAVAILABLE
                ),
                reason="active_governed_source" if item in active else "no_ready_active_source",
            )
            for item in _ORDER
        ]
        return EvidenceScopeRequest(notebook_id=notebook_id), selected, decisions


class AutomaticQueryV2ApplicationService:
    def __init__(self, engine: KnowledgeEngine, config: ServerConfig) -> None:
        self._engine = engine
        self._config = config

    async def execute(
        self, request: AutomaticQueryV2Request, principal: ServerPrincipalV1
    ) -> AutomaticQueryV2Response:
        if request.cursor is not None and request.mode.value != "exhaustive":
            raise ContractValidationError("continuation requires exhaustive mode")
        scope, representations, decisions = await AutomaticEvidencePlanner(self._engine).plan(
            principal
        )
        if request.candidate_budget < len(representations):
            raise ContractValidationError(
                "candidate_budget is too small for the active representation set"
            )
        serving_alias = getattr(self._engine, "full_multilingual_v2_alias_digest", None)
        evidence = await EvidenceRetrievalApplicationService(self._engine, self._config).execute(
            EvidenceSearchRequest(
                query=request.query,
                mode=request.mode,
                scope=scope,
                representations=representations,
                cursor=request.cursor,
                candidate_budget=request.candidate_budget,
                evidence_budget=request.evidence_budget,
                max_serialized_bytes=request.max_serialized_bytes,
                max_content_characters=request.max_content_characters,
            ),
            principal,
            automatic_policy_version=(
                "automatic-evidence-plan/v1"
                if serving_alias is None
                else "automatic-evidence-plan/v1:" + serving_alias
            ),
            force_authorized=True,
        )
        actual = {
            item.get("representation"): item
            for item in evidence.coverage.get("representations", [])
        }
        status_map = {
            "searched": AutomaticRepresentationStatus.SEARCHED,
            "unavailable": AutomaticRepresentationStatus.UNAVAILABLE,
            "failed": AutomaticRepresentationStatus.FAILED,
            "omitted": AutomaticRepresentationStatus.OMITTED_BY_BUDGET,
        }
        decisions = [
            decision.model_copy(
                update={
                    "status": status_map.get(
                        actual[decision.representation].get("status", "failed"),
                        AutomaticRepresentationStatus.FAILED,
                    ),
                    "reason": (
                        "active_governed_source"
                        if actual[decision.representation].get("status") == "searched"
                        else str(
                            actual[decision.representation].get("reason_code") or "source_failed"
                        )
                    ),
                }
            )
            if decision.representation in actual
            else decision
            for decision in decisions
        ]
        return AutomaticQueryV2Response(
            request_id=evidence.request_id,
            notebook_id=scope.notebook_id,
            representation_decisions=decisions,
            evidence=evidence,
        )
