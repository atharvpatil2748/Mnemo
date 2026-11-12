"""Internal V2 search boundary shared by the retained HTTP and MCP adapters.

This module does not register an operation or interpret client authority fields.
The existing services remain the owners of retrieval plans, provider readiness,
generation selection, cursor validation, and public response serialization.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol, cast, runtime_checkable
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError, NotFoundError, OperationTimeoutError
from mnemo.interfaces.advanced_retrieval import PrincipalAwareAdvancedRetrievalInterfaceV2
from mnemo.models import (
    AssetOccurrence,
    EvidenceRepresentation,
    IndexGeneration,
    MultimodalRetrievalResultV2,
    RetrievalResultSetV1,
)
from mnemo.phase85.projections import ProjectionCompleteness, ProjectionCoverage
from mnemo.retrieval.advanced import AdvancedRetrievalService
from mnemo.retrieval.scope import StorageDocumentScopeResolverV1, StorageSourceAssociationReaderV1
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.automatic_query_v2 import (
    AutomaticQueryV2Request,
    AutomaticQueryV2Response,
)
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest, EvidenceSearchResponse
from mnemo_server.schemas.structured_v2 import (
    StructuredRetrievalRequest,
    StructuredRetrievalResponse,
)
from mnemo_server.services.authorization import ServerPrincipalV1
from mnemo_server.services.authorized_scope import (
    AuthorizedNotebookScope,
    AuthorizedNotebookScopeResolver,
)
from mnemo_server.services.automatic_query_v2 import AutomaticQueryV2ApplicationService
from mnemo_server.services.retrieval_v2 import EvidenceRetrievalApplicationService
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.structured_v2 import StructuredRetrievalApplicationService
from mnemo_server.typed_errors import ErrorCategory


class SharedSearchKind(StrEnum):
    AUTOMATIC = "automatic"
    EVIDENCE = "evidence"
    STRUCTURED = "structured"


type SearchRequestBody = (
    AutomaticQueryV2Request | EvidenceSearchRequest | StructuredRetrievalRequest
)
type SearchResponseBody = (
    AutomaticQueryV2Response | EvidenceSearchResponse | StructuredRetrievalResponse
)


@dataclass(frozen=True, slots=True)
class SharedSearchRequest:
    """A validated internal command; public request models remain unchanged."""

    kind: SharedSearchKind
    body: SearchRequestBody

    def __post_init__(self) -> None:
        expected = {
            SharedSearchKind.AUTOMATIC: AutomaticQueryV2Request,
            SharedSearchKind.EVIDENCE: EvidenceSearchRequest,
            SharedSearchKind.STRUCTURED: StructuredRetrievalRequest,
        }
        if not isinstance(self.body, expected[self.kind]):
            raise TypeError("shared search operation and request type disagree")


@dataclass(frozen=True, slots=True)
class SharedSearchPlan:
    """Server-resolved authority context, not a client-provided plan."""

    kind: SharedSearchKind
    actor_id: UUID
    notebook_id: UUID
    membership_revision: int | None


class SharedEvidenceReference(BaseModel):
    """Internal typed ancestry; public V2 payloads remain byte-for-byte shaped as before."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["canonical", "derived", "dataset", "row", "group"]
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_id: str | None = None
    occurrence_id: UUID | None = None
    derivation_id: UUID | None = None
    dataset_id: UUID | None = None
    row_id: str | None = None

    @model_validator(mode="after")
    def identity_is_typed(self) -> SharedEvidenceReference:
        if self.kind == "canonical" and self.chunk_id is None:
            raise ValueError("canonical evidence requires a chunk identity")
        if self.kind == "derived" and self.occurrence_id is None and self.derivation_id is None:
            raise ValueError("derived evidence requires an occurrence or derivation identity")
        if self.kind in {"dataset", "row", "group"} and self.dataset_id is None:
            raise ValueError("structured evidence requires a dataset identity")
        if self.kind in {"row", "group"} and self.row_id is None:
            raise ValueError("structured result requires a row or group identity")
        return self


class SharedSourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    representation: str
    status: str
    matched: int | None = Field(default=None, ge=0)
    reason_code: str | None = None


class SharedSearchEnvelope(BaseModel):
    """Internal result contract; never serialised directly by a public adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["mnemo.shared-search-internal/1"] = "mnemo.shared-search-internal/1"
    actor_id: UUID
    notebook_id: UUID
    membership_revision: int | None
    evidence: tuple[SharedEvidenceReference, ...]
    sources: tuple[SharedSourceStatus, ...]
    completeness: str
    omissions: tuple[str, ...]
    next_cursor: str | None


class SharedSearchSafeError(BaseModel):
    """Safe internal error shape; adapters retain their existing wire mappings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ErrorCategory
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class SharedSearchResult:
    plan: SharedSearchPlan
    envelope: SharedSearchEnvelope
    response: SearchResponseBody
    completeness: str
    next_cursor: str | None
    omissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuthorizedEvidenceSnapshot:
    """FinalQA input bound to the actor, ACL revision and evidence ancestry."""

    actor_id: UUID
    notebook_id: UUID
    membership_revision: int | None
    result: MultimodalRetrievalResultV2


@dataclass(frozen=True, slots=True)
class ScopedDocumentSelection:
    """An exact notebook/document/version tuple, never an access grant."""

    notebook_id: UUID
    document_id: UUID
    version_id: UUID


@dataclass(frozen=True, slots=True)
class AuthorizedSearchSelection:
    """Resolved authority for internal fan-out; no public operation uses this yet."""

    principal: ServerPrincipalV1
    notebooks: tuple[AuthorizedNotebookScope, ...]
    documents: tuple[ScopedDocumentSelection, ...]


@dataclass(frozen=True, slots=True)
class ScopedRepresentationAdmission:
    notebook_id: UUID
    representation: EvidenceRepresentation
    status: Literal["active", "not_applicable", "unavailable", "incomplete", "incompatible"]
    generation_alias: str | None
    reason_code: str | None


_SCOPED_CAPABILITY = {
    EvidenceRepresentation.OCR_TEXT: "ocr_text",
    EvidenceRepresentation.VISION_ANALYSIS: "vision_text",
    EvidenceRepresentation.VISUAL_VECTOR: "visual_vector",
    EvidenceRepresentation.MULTILINGUAL_TEXT: "language_text_v2",
}


@runtime_checkable
class _GenerationInspectionStore(Protocol):
    async def list_active_index_generations(
        self, capability: str
    ) -> tuple[IndexGeneration, ...]: ...

    async def get_index_generation_coverage(
        self, generation_id: UUID
    ) -> ProjectionCoverage | None: ...

    async def get_index_generation_sources(
        self, generation_id: UUID
    ) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]: ...


@runtime_checkable
class _AssetOccurrenceInspectionStore(Protocol):
    async def list_asset_occurrences(self, version_id: UUID) -> tuple[AssetOccurrence, ...]: ...


@runtime_checkable
class _FullV2AliasInspectionStore(_GenerationInspectionStore, Protocol):
    async def resolve_active_multilingual_v2_alias_digest(self) -> str | None: ...

    async def resolve_active_multilingual_v2_generation_set(self) -> tuple[UUID, ...] | None: ...

    async def get_index_generation(self, generation_id: UUID) -> IndexGeneration | None: ...


async def _inspect_full_v2_alias(
    storage: _GenerationInspectionStore,
    *,
    expected_alias: str | None,
    needed: set[UUID],
) -> tuple[
    Literal["active", "not_applicable", "unavailable", "incomplete", "incompatible"],
    str | None,
    str | None,
]:
    """Admit the atomic Full V2 alias, not legacy per-capability active pointers."""
    if not needed:
        return "not_applicable", None, "scope_has_no_versions"
    if expected_alias is None or not isinstance(storage, _FullV2AliasInspectionStore):
        return "unavailable", None, "governed_multilingual_alias_missing"
    actual_alias = await storage.resolve_active_multilingual_v2_alias_digest()
    if actual_alias != expected_alias:
        return "incompatible", None, "active_alias_changed"
    generation_ids = await storage.resolve_active_multilingual_v2_generation_set()
    if generation_ids is None or len(generation_ids) != 4 or len(set(generation_ids)) != 4:
        return "incomplete", None, "active_generation_set_missing"
    capabilities = (
        "representation_derivation_v2",
        "language_text_v2",
        "multilingual_embedding_v2",
        "multilingual_vector_v2",
    )
    generations = [await storage.get_index_generation(identifier) for identifier in generation_ids]
    if any(item is None for item in generations):
        return "incomplete", None, "active_generation_missing"
    present = cast(list[IndexGeneration], generations)
    if tuple(item.capability for item in present) != capabilities:
        return "incompatible", None, "active_generation_capability_mismatch"
    if len({item.profile for item in present}) != 1 or (
        present[2].model_identity,
        present[2].dimensions,
    ) != (present[3].model_identity, present[3].dimensions):
        return "incompatible", None, "active_generation_profile_mismatch"
    for generation in present:
        coverage = await storage.get_index_generation_coverage(generation.generation_id)
        if (
            generation.state.value != "ready"
            or coverage is None
            or coverage.completeness is not ProjectionCompleteness.COMPLETE
            or coverage.failed_count != 0
            or generation.checksum != coverage.checksum
        ):
            return "incomplete", None, "active_generation_coverage_invalid"
        _, source_versions = await storage.get_index_generation_sources(generation.generation_id)
        if not needed.issubset(source_versions):
            return "incomplete", None, "scope_coverage_unproven"
    return "active", actual_alias, None


class ScopedSearchAuthorization:
    """Authorize all partitions and exact versions before provider inspection."""

    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def resolve(
        self,
        principal: ServerPrincipalV1,
        *,
        selected_notebooks: tuple[UUID, ...] | None,
        documents: tuple[ScopedDocumentSelection, ...] = (),
    ) -> AuthorizedSearchSelection:
        authority = getattr(self._engine, "server_scope_authority", None)
        if not isinstance(authority, SQLiteNotebookScopeAuthority):
            raise DependencyUnavailableError("trusted membership authority is unavailable")
        resolver = AuthorizedNotebookScopeResolver(self._engine.storage, authority)
        scopes = await resolver.resolve(principal, selected_notebooks)
        if not scopes:
            raise NotFoundError("authorized resource was not found")
        if len(set(documents)) != len(documents):
            raise ValueError("document selections must be unique")
        authorized_ids = {scope.notebook_id for scope in scopes}
        if any(item.notebook_id not in authorized_ids for item in documents):
            raise NotFoundError("authorized resource was not found")
        if documents:
            document_resolver = StorageDocumentScopeResolverV1(
                self._engine.storage, StorageSourceAssociationReaderV1(self._engine.storage)
            )
            for item in documents:
                await document_resolver.resolve_document_scope(
                    principal, item.document_id, item.version_id, item.notebook_id
                )
        await resolver.revalidate(principal, scopes)
        return AuthorizedSearchSelection(principal, scopes, documents)

    async def revalidate(self, selection: AuthorizedSearchSelection) -> None:
        authority = getattr(self._engine, "server_scope_authority", None)
        if not isinstance(authority, SQLiteNotebookScopeAuthority):
            raise DependencyUnavailableError("trusted membership authority is unavailable")
        resolver = AuthorizedNotebookScopeResolver(self._engine.storage, authority)
        await resolver.revalidate(selection.principal, selection.notebooks)
        if selection.documents:
            document_resolver = StorageDocumentScopeResolverV1(
                self._engine.storage, StorageSourceAssociationReaderV1(self._engine.storage)
            )
            for item in selection.documents:
                await document_resolver.resolve_document_scope(
                    selection.principal, item.document_id, item.version_id, item.notebook_id
                )
        await resolver.revalidate(selection.principal, selection.notebooks)

    async def inspect_active_sources(
        self,
        selection: AuthorizedSearchSelection,
        representations: tuple[EvidenceRepresentation, ...],
    ) -> tuple[ScopedRepresentationAdmission, ...]:
        """Admit only source generations covering each exact authorized version set.

        This is a read-only admission check. It cannot promote an index or
        substitute for the source's own snapshot/authorization checks.
        """
        await self.revalidate(selection)
        retrieval = self._engine.advanced_retrieval
        if not isinstance(retrieval, AdvancedRetrievalService):
            raise DependencyUnavailableError("governed V2 retrieval is unavailable")
        active = set(retrieval.active_representations)
        storage = self._engine.storage
        if not isinstance(storage, _GenerationInspectionStore):
            raise DependencyUnavailableError("generation inspection is unavailable")
        versions = await self._version_universe(selection)
        asset_versions: dict[UUID, set[UUID]] = {}
        if any(
            representation in active
            and representation
            in {
                EvidenceRepresentation.OCR_TEXT,
                EvidenceRepresentation.VISION_ANALYSIS,
                EvidenceRepresentation.VISUAL_VECTOR,
            }
            for representation in representations
        ):
            if not isinstance(storage, _AssetOccurrenceInspectionStore):
                raise DependencyUnavailableError("asset occurrence inspection is unavailable")
            for notebook_id, scope_versions in versions.items():
                applicable: set[UUID] = set()
                for version_id in scope_versions:
                    occurrences = await storage.list_asset_occurrences(version_id)
                    if any(item.version_id != version_id for item in occurrences):
                        raise NotFoundError("authorized resource was not found")
                    if occurrences:
                        applicable.add(version_id)
                asset_versions[notebook_id] = applicable
        output: list[ScopedRepresentationAdmission] = []
        for scope in selection.notebooks:
            for representation in representations:
                status: Literal[
                    "active", "not_applicable", "unavailable", "incomplete", "incompatible"
                ]
                alias: str | None = None
                reason: str | None = None
                if representation not in active:
                    status, reason = "unavailable", "source_not_composed"
                elif representation is EvidenceRepresentation.CANONICAL_TEXT:
                    status = "active"
                elif representation is EvidenceRepresentation.MULTILINGUAL_TEXT:
                    status, alias, reason = await _inspect_full_v2_alias(
                        storage,
                        expected_alias=getattr(
                            self._engine, "full_multilingual_v2_alias_digest", None
                        ),
                        needed=versions[scope.notebook_id],
                    )
                elif representation in _SCOPED_CAPABILITY:
                    capability = _SCOPED_CAPABILITY[representation]
                    needed = asset_versions[scope.notebook_id]
                    if not needed:
                        status, reason = "not_applicable", "scope_has_no_asset_occurrences"
                    else:
                        generations = await storage.list_active_index_generations(capability)
                        if not generations:
                            status, reason = "unavailable", "active_generation_missing"
                        elif (
                            len({(item.profile, item.model_identity) for item in generations}) != 1
                        ):
                            status, reason = "incompatible", "multiple_active_profiles"
                        else:
                            covered: set[UUID] = set()
                            valid = True
                            for generation in generations:
                                coverage = await storage.get_index_generation_coverage(
                                    generation.generation_id
                                )
                                if (
                                    generation.state.value != "ready"
                                    or coverage is None
                                    or coverage.completeness is not ProjectionCompleteness.COMPLETE
                                    or coverage.failed_count != 0
                                    or generation.checksum != coverage.checksum
                                ):
                                    valid = False
                                    break
                                _, source_versions = await storage.get_index_generation_sources(
                                    generation.generation_id
                                )
                                covered.update(source_versions)
                            if not valid or not needed.issubset(covered):
                                status, reason = "incomplete", "scope_coverage_unproven"
                            else:
                                status = "active"
                                alias = hashlib.sha256(
                                    json.dumps(
                                        sorted(str(item.generation_id) for item in generations),
                                        separators=(",", ":"),
                                    ).encode()
                                ).hexdigest()
                else:
                    status, reason = "unavailable", "representation_not_admitted"
                output.append(
                    ScopedRepresentationAdmission(
                        scope.notebook_id, representation, status, alias, reason
                    )
                )
        await self.revalidate(selection)
        return tuple(output)

    async def _version_universe(
        self, selection: AuthorizedSearchSelection
    ) -> dict[UUID, set[UUID]]:
        versions: dict[UUID, set[UUID]] = {
            scope.notebook_id: set() for scope in selection.notebooks
        }
        if selection.documents:
            for item in selection.documents:
                versions[item.notebook_id].add(item.version_id)
            return versions
        storage = self._engine.storage
        for scope in selection.notebooks:
            cursor: str | None = None
            seen: set[str] = set()
            count = 0
            while True:
                page = await storage.list_sources(scope.notebook_id, limit=100, cursor=cursor)
                for source in page.items:
                    if source.notebook_id != scope.notebook_id:
                        raise NotFoundError("authorized resource was not found")
                    document = await storage.get_document(source.document_id)
                    if document is None:
                        raise NotFoundError("authorized resource was not found")
                    versions[scope.notebook_id].update(
                        version.version_id for version in document.versions
                    )
                count += len(page.items)
                if count > 10_000:
                    raise DependencyUnavailableError("scope source inventory exceeds bound")
                cursor = page.next_cursor
                if cursor is None:
                    break
                if cursor in seen or not page.items:
                    raise DependencyUnavailableError("scope source inventory did not advance")
                seen.add(cursor)
        return versions


class SharedSearchApplicationService:
    """Compose the retained V2 services without creating another retrieval stack."""

    def __init__(self, engine: KnowledgeEngine, config: ServerConfig) -> None:
        self._engine = engine
        self._config = config

    async def retrieve_for_answer(
        self,
        request: EvidenceSearchRequest,
        principal: ServerPrincipalV1,
        *,
        membership_revision: int | None,
        authorized: bool,
    ) -> RetrievalResultSetV1:
        """Use the existing advanced retriever and server ceilings for FinalQA."""
        if authorized and not principal.authenticated:
            raise PermissionError("production FinalQA requires authentication")
        retrieval = self._engine.advanced_retrieval
        if authorized and not isinstance(retrieval, PrincipalAwareAdvancedRetrievalInterfaceV2):
            raise DependencyUnavailableError(
                "production retrieval lacks the principal-aware V2 entry point"
            )
        authority = getattr(self._engine, "server_scope_authority", None)
        resolver = None
        scopes: tuple[AuthorizedNotebookScope, ...] = ()
        if authority is not None:
            if not isinstance(authority, SQLiteNotebookScopeAuthority):
                raise PermissionError("trusted membership authority is unavailable")
            resolver = AuthorizedNotebookScopeResolver(self._engine.storage, authority)
            scopes = await resolver.resolve(principal, (request.scope.notebook_id,))
            if membership_revision != scopes[0].membership_revision:
                raise NotFoundError("authorized resource was not found")
            authorized = True
        elif self._config.production_mode and not authorized:
            raise DependencyUnavailableError("principal-aware retrieval is required")
        plan = request.to_plan(
            max_candidate_budget=self._config.max_advanced_candidate_budget,
            max_evidence_budget=self._config.max_advanced_evidence_budget,
            max_response_bytes=self._config.max_advanced_response_bytes,
            max_content_characters=self._config.max_advanced_content_characters,
            max_rerank_candidates=self._config.production_rerank_candidate_limit,
            production_candidate_pool_k=(
                self._config.production_rerank_candidate_limit
                if self._config.production_mode or authorized
                else None
            ),
            security_scope_identity=(
                str(principal.actor_id) if membership_revision is not None else None
            ),
        )
        if membership_revision is not None:
            plan = plan.model_copy(update={"membership_revision": membership_revision})
        try:
            async with asyncio.timeout(self._config.max_advanced_elapsed_milliseconds / 1000):
                if authorized:
                    result = await cast(
                        PrincipalAwareAdvancedRetrievalInterfaceV2, retrieval
                    ).execute_authorized(principal=principal, plan=plan, cursor=request.cursor)
                else:
                    result = await retrieval.execute(plan, cursor=request.cursor)
        except TimeoutError as error:
            raise OperationTimeoutError("Final-QA evidence retrieval exceeded deadline") from error
        if resolver is not None:
            await resolver.revalidate(principal, scopes)
        return result

    async def bind_answer_snapshot(
        self,
        result: MultimodalRetrievalResultV2,
        principal: ServerPrincipalV1,
        notebook_id: UUID,
        membership_revision: int | None,
    ) -> AuthorizedEvidenceSnapshot:
        """Reject cross-scope or stale evidence before FinalQA can publish it."""
        authority = getattr(self._engine, "server_scope_authority", None)
        resolver = None
        scopes: tuple[AuthorizedNotebookScope, ...] = ()
        if authority is not None:
            if not isinstance(authority, SQLiteNotebookScopeAuthority):
                raise PermissionError("trusted membership authority is unavailable")
            resolver = AuthorizedNotebookScopeResolver(self._engine.storage, authority)
            scopes = await resolver.resolve(principal, (notebook_id,))
            if membership_revision != scopes[0].membership_revision:
                raise NotFoundError("authorized resource was not found")
        document_resolver = (
            StorageDocumentScopeResolverV1(
                self._engine.storage, StorageSourceAssociationReaderV1(self._engine.storage)
            )
            if resolver is not None
            else None
        )
        for candidate in result.candidates:
            if candidate.notebook_id != notebook_id:
                raise NotFoundError("authorized resource was not found")
            if document_resolver is not None:
                source = await document_resolver.resolve_document_scope(
                    principal, candidate.document_id, candidate.version_id, notebook_id
                )
                if source.source_id != candidate.source_id:
                    raise NotFoundError("authorized resource was not found")
        if resolver is not None:
            await resolver.revalidate(principal, scopes)
        return AuthorizedEvidenceSnapshot(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            membership_revision=membership_revision,
            result=result,
        )

    async def execute(
        self,
        request: SharedSearchRequest,
        principal: ServerPrincipalV1,
        *,
        automatic_policy_version: str | None = None,
    ) -> SharedSearchResult:
        authority = getattr(self._engine, "server_scope_authority", None)
        if authority is not None and not isinstance(authority, SQLiteNotebookScopeAuthority):
            raise PermissionError("trusted membership authority is unavailable")
        resolver = (
            AuthorizedNotebookScopeResolver(self._engine.storage, authority)
            if isinstance(authority, SQLiteNotebookScopeAuthority)
            else None
        )
        notebook_id = (
            None
            if isinstance(request.body, AutomaticQueryV2Request)
            else request.body.scope.notebook_id
        )
        membership: tuple[AuthorizedNotebookScope, ...] = ()
        if resolver is not None:
            membership = await resolver.resolve(
                principal, None if notebook_id is None else (notebook_id,)
            )
            if notebook_id is None:
                if len(membership) != 1:
                    raise DependencyUnavailableError(
                        "automatic query requires one unambiguous authorized notebook scope",
                        retryable=False,
                    )
                notebook_id = membership[0].notebook_id

        if isinstance(request.body, AutomaticQueryV2Request):
            automatic = await AutomaticQueryV2ApplicationService(
                self._engine, self._config
            ).execute(request.body, principal)
            response: SearchResponseBody = automatic
            if notebook_id is not None and automatic.notebook_id != notebook_id:
                raise NotFoundError("authorized resource was not found")
            notebook_id = automatic.notebook_id
            evidence = automatic.evidence
            completeness = evidence.completeness
            next_cursor = evidence.next_cursor
            omissions = tuple(evidence.omissions)
            references = _evidence_references(evidence)
            statuses = _evidence_statuses(evidence)
        elif isinstance(request.body, EvidenceSearchRequest):
            evidence_service = EvidenceRetrievalApplicationService(self._engine, self._config)
            evidence = (
                await evidence_service.execute(request.body, principal)
                if automatic_policy_version is None
                else await evidence_service.execute(
                    request.body,
                    principal,
                    automatic_policy_version=automatic_policy_version,
                )
            )
            response = evidence
            completeness = evidence.completeness
            next_cursor = evidence.next_cursor
            omissions = tuple(evidence.omissions)
            references = _evidence_references(evidence)
            statuses = _evidence_statuses(evidence)
        else:
            structured, catalog = await StructuredRetrievalApplicationService(
                self._engine, self._config
            ).execute_with_catalog(request.body, principal)
            response = structured
            completeness = structured.completeness
            next_cursor = structured.next_cursor
            omissions = tuple(structured.omissions)
            references = _structured_references(structured, catalog.datasets)
            statuses = (
                SharedSourceStatus(
                    representation="structured_table",
                    status=("searched" if structured.representations_searched else "unavailable"),
                    matched=(
                        int(structured.structured["matched_count"])
                        if structured.representations_searched
                        else None
                    ),
                ),
            )

        if notebook_id is None:
            raise NotFoundError("authorized resource was not found")
        if any(item.notebook_id != notebook_id for item in references):
            raise NotFoundError("authorized resource was not found")
        if resolver is not None:
            await resolver.revalidate(principal, membership)
        plan = SharedSearchPlan(
            kind=request.kind,
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            membership_revision=(membership[0].membership_revision if membership else None),
        )
        return SharedSearchResult(
            plan=plan,
            envelope=SharedSearchEnvelope(
                actor_id=plan.actor_id,
                notebook_id=plan.notebook_id,
                membership_revision=plan.membership_revision,
                evidence=references,
                sources=statuses,
                completeness=completeness,
                omissions=omissions,
                next_cursor=next_cursor,
            ),
            response=response,
            completeness=completeness,
            next_cursor=next_cursor,
            omissions=omissions,
        )


def _evidence_references(response: EvidenceSearchResponse) -> tuple[SharedEvidenceReference, ...]:
    references = []
    for item in response.items:
        kind: Literal["canonical", "derived"] = (
            "canonical" if item["chunk_id"] is not None else "derived"
        )
        references.append(
            SharedEvidenceReference(
                kind=kind,
                notebook_id=item["notebook_id"],
                source_id=item["source_id"],
                document_id=item["document_id"],
                version_id=item["version_id"],
                chunk_id=item["chunk_id"],
                occurrence_id=item["occurrence_id"],
                derivation_id=item["derivation_id"],
            )
        )
    return tuple(references)


def _evidence_statuses(response: EvidenceSearchResponse) -> tuple[SharedSourceStatus, ...]:
    return tuple(
        SharedSourceStatus(
            representation=item["representation"],
            status=item["status"],
            matched=(item["returned"] if item["status"] == "searched" else None),
            reason_code=item.get("reason_code"),
        )
        for item in response.coverage.get("representations", ())
    )


def _structured_references(
    response: StructuredRetrievalResponse, datasets: tuple[Any, ...]
) -> tuple[SharedEvidenceReference, ...]:
    by_candidate = {str(item.candidate.candidate_id): item for item in datasets}
    references: list[SharedEvidenceReference] = []

    def collect(node: dict[str, Any], row_id: str | None = None) -> None:
        candidate_id = node.get("candidate_id")
        if candidate_id is not None:
            dataset = by_candidate.get(candidate_id)
            if dataset is None:
                raise NotFoundError("authorized resource was not found")
            for field, expected in (
                ("notebook_id", dataset.notebook_id),
                ("source_id", dataset.source_id),
                ("document_id", dataset.document_id),
                ("version_id", dataset.version_id),
            ):
                if node.get(field) != str(expected):
                    raise NotFoundError("authorized resource was not found")
            references.append(
                SharedEvidenceReference(
                    kind="row" if row_id is not None else "dataset",
                    notebook_id=dataset.notebook_id,
                    source_id=dataset.source_id,
                    document_id=dataset.document_id,
                    version_id=dataset.version_id,
                    dataset_id=dataset.dataset_id,
                    row_id=row_id,
                    chunk_id=node.get("chunk_id"),
                )
            )
        for child in node.get("provenance", ()):
            if isinstance(child, dict):
                collect(child, row_id)

    for item in response.items:
        if "dataset_id" in item:
            dataset = next(
                (dataset for dataset in datasets if str(dataset.dataset_id) == item["dataset_id"]),
                None,
            )
            if (
                dataset is None
                or any(
                    item.get(field) != str(expected)
                    for field, expected in (
                        ("source_id", dataset.source_id),
                        ("document_id", dataset.document_id),
                        ("version_id", dataset.version_id),
                    )
                )
                or item.get("provenance", {}).get("notebook_id") != str(dataset.notebook_id)
            ):
                raise NotFoundError("authorized resource was not found")
            references.append(
                SharedEvidenceReference(
                    kind="dataset",
                    notebook_id=item["provenance"]["notebook_id"],
                    source_id=item["source_id"],
                    document_id=item["document_id"],
                    version_id=item["version_id"],
                    dataset_id=item["dataset_id"],
                )
            )
            continue
        row_id = item.get("record_id") or item.get("group_id")
        for side in ("left", "right"):
            if isinstance(item.get(side), dict):
                collect(item[side], item[side].get("record_id"))
        collect(item, row_id)
        for field in ("values", "aggregates"):
            for value in item.get(field, {}).values():
                for child in value.get("provenance", ()):
                    collect(child, row_id)
    return tuple(references)
