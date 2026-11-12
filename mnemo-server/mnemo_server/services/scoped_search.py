"""Internal, bounded multi-notebook search over the existing shared V2 service.

No public route or MCP tool imports this command. Per-scope admission and
authorization are deliberately separate from the retained one-notebook V2 API.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from mnemo.cursors import CursorCodecV2, CursorConflictError, CursorInvalidError, CursorSigningKeyV2
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError, NotFoundError, OperationTimeoutError
from mnemo.models import AdvancedRetrievalMode, EvidenceRepresentation

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.retrieval_v2 import (
    EvidenceScopeRequest,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
)
from mnemo_server.schemas.scope_contract_review import ScopeRequestReview, SelectedNotebooks
from mnemo_server.services.authorization import ServerPrincipalV1
from mnemo_server.services.shared_search import (
    ScopedDocumentSelection,
    ScopedRepresentationAdmission,
    ScopedSearchAuthorization,
    SharedSearchApplicationService,
    SharedSearchKind,
    SharedSearchRequest,
    SharedSearchResult,
)

_AUTOMATIC_ORDER = (
    EvidenceRepresentation.CANONICAL_TEXT,
    EvidenceRepresentation.OCR_TEXT,
    EvidenceRepresentation.VISION_ANALYSIS,
    EvidenceRepresentation.MULTILINGUAL_TEXT,
    EvidenceRepresentation.VISUAL_VECTOR,
)
_CONCURRENCY = 4


@dataclass(frozen=True, slots=True)
class ScopedNotebookResult:
    notebook_id: UUID
    status: str
    sources: tuple[ScopedRepresentationAdmission, ...]
    response: SharedSearchResult | None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class ScopedRankedResult:
    """Internal aggregate, not an existing public response contract."""

    items: tuple[dict[str, object], ...]
    notebooks: tuple[ScopedNotebookResult, ...]
    completeness: str
    omissions: tuple[str, ...]
    requested_k: int
    candidate_budget: int
    byte_budget: int


@dataclass(frozen=True, slots=True)
class ScopedTraversalResult:
    items: tuple[dict[str, object], ...]
    completeness: str
    omissions: tuple[str, ...]
    snapshot_identity: str
    next_cursor: str | None
    requested_k: int


class ScopedSearchApplicationService:
    """Run each authorized partition through the existing shared application path."""

    def __init__(
        self,
        engine: KnowledgeEngine,
        config: ServerConfig,
        *,
        child_observer: Callable[[UUID, str, str, int | None, str | None], None] | None = None,
    ) -> None:
        self._engine = engine
        self._config = config
        self._child_observer = child_observer
        self._authorization = ScopedSearchAuthorization(engine)
        secret = config.delivery_cursor_secret.encode("utf-8")
        self._cursor = CursorCodecV2(
            CursorSigningKeyV2(
                "scoped-" + hashlib.sha256(config.delivery_cursor_key_id.encode()).hexdigest()[:20],
                hashlib.sha256(secret + b":scoped-search/v1").digest(),
            ),
            ttl=timedelta(seconds=config.delivery_cursor_ttl_seconds),
        )

    async def execute_ranked(
        self, request: ScopeRequestReview, principal: ServerPrincipalV1
    ) -> ScopedRankedResult:
        if request.mode != "ranked" or request.cursor is not None:
            raise ValueError("ranked fan-out cannot consume a continuation cursor")
        selected = (
            request.scope.notebook_ids if isinstance(request.scope, SelectedNotebooks) else None
        )
        documents = tuple(
            ScopedDocumentSelection(item.notebook_id, item.document_id, item.version_id)
            for item in request.documents
        )
        selection = await self._authorization.resolve(
            principal, selected_notebooks=selected, documents=documents
        )
        representations = (
            tuple(request.representations)
            if request.representations is not None
            else _AUTOMATIC_ORDER
        )
        admission = await self._authorization.inspect_active_sources(selection, representations)
        by_notebook = {
            scope.notebook_id: tuple(
                item for item in admission if item.notebook_id == scope.notebook_id
            )
            for scope in selection.notebooks
        }
        partition_specs = (
            tuple((item.notebook_id, item) for item in documents)
            if documents
            else tuple((item.notebook_id, None) for item in selection.notebooks)
        )
        notebook_count = len(partition_specs)
        candidate_budget = self._config.max_advanced_candidate_budget
        per_candidate = candidate_budget // notebook_count
        minimum_pool = (
            self._config.production_rerank_candidate_limit if self._config.production_mode else 1
        )
        if per_candidate < minimum_pool or per_candidate < len(representations):
            raise DependencyUnavailableError(
                "selected scope exceeds bounded source candidate budget", retryable=False
            )
        per_evidence = min(request.limit, per_candidate, self._config.max_advanced_evidence_budget)
        per_bytes = self._config.max_advanced_response_bytes // notebook_count
        if per_bytes < 256:
            raise DependencyUnavailableError(
                "selected scope exceeds bounded response budget", retryable=False
            )
        per_content = self._config.max_advanced_content_characters // notebook_count
        if per_content < 1:
            raise DependencyUnavailableError(
                "selected scope exceeds bounded content budget", retryable=False
            )
        policy = _admission_policy(
            admission, getattr(self._engine, "full_multilingual_v2_alias_digest", None)
        )
        semaphore = asyncio.Semaphore(_CONCURRENCY)
        shared = SharedSearchApplicationService(self._engine, self._config)

        async def _search_notebook(
            notebook_id: UUID, exact_document: ScopedDocumentSelection | None
        ) -> ScopedNotebookResult:
            sources = by_notebook[notebook_id]
            selected_representations = tuple(
                item.representation for item in sources if item.status == "active"
            )
            if not selected_representations:
                not_applicable = all(item.status == "not_applicable" for item in sources)
                return ScopedNotebookResult(
                    notebook_id,
                    "not_applicable" if not_applicable else "unavailable",
                    sources,
                    None,
                    None if not_applicable else "no_admitted_source",
                )
            body = EvidenceSearchRequest(
                query=request.query,
                mode=AdvancedRetrievalMode.RANKED,
                scope=EvidenceScopeRequest(
                    notebook_id=notebook_id,
                    document_ids=(exact_document.document_id,) if exact_document else (),
                    version_ids=(exact_document.version_id,) if exact_document else (),
                ),
                representations=selected_representations,
                candidate_budget=per_candidate,
                evidence_budget=per_evidence,
                max_serialized_bytes=per_bytes,
                max_content_characters=per_content,
            )
            async with semaphore:
                if self._child_observer is not None:
                    self._child_observer(notebook_id, "shared_evidence", "started", None, None)
                try:
                    result = await shared.execute(
                        SharedSearchRequest(SharedSearchKind.EVIDENCE, body),
                        principal,
                        automatic_policy_version=policy,
                    )
                except BaseException as error:
                    if self._child_observer is not None:
                        self._child_observer(
                            notebook_id,
                            "shared_evidence",
                            "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                            None,
                            type(error).__name__,
                        )
                    if not isinstance(error, (DependencyUnavailableError, OperationTimeoutError)):
                        raise
                    return ScopedNotebookResult(
                        notebook_id, "failed", sources, None, "partition_execution_failed"
                    )
                if self._child_observer is not None:
                    self._child_observer(
                        notebook_id,
                        "shared_evidence",
                        "completed",
                        len(result.response.items)
                        if isinstance(result.response, EvidenceSearchResponse)
                        else None,
                        None,
                    )
            if not isinstance(result.response, EvidenceSearchResponse):
                raise TypeError("scoped evidence service returned another operation")
            if any(
                UUID(str(item["notebook_id"])) != notebook_id
                or (
                    exact_document is not None
                    and (
                        UUID(str(item["document_id"])),
                        UUID(str(item["version_id"])),
                    )
                    != (exact_document.document_id, exact_document.version_id)
                )
                for item in result.response.items
            ):
                raise NotFoundError("authorized resource was not found")
            return ScopedNotebookResult(notebook_id, "searched", sources, result)

        async def search_notebook(
            notebook_id: UUID, exact_document: ScopedDocumentSelection | None
        ) -> ScopedNotebookResult:
            if self._child_observer is not None:
                self._child_observer(notebook_id, "child", "started", None, None)
            try:
                partition = await _search_notebook(notebook_id, exact_document)
            except BaseException as error:
                if self._child_observer is not None:
                    self._child_observer(
                        notebook_id,
                        "child",
                        "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                        None,
                        type(error).__name__,
                    )
                raise
            if self._child_observer is not None:
                self._child_observer(
                    notebook_id,
                    "child",
                    "completed",
                    len(partition.response.response.items)
                    if partition.response is not None
                    and isinstance(partition.response.response, EvidenceSearchResponse)
                    else 0,
                    None,
                )
            return partition

        try:
            async with asyncio.timeout(self._config.max_advanced_elapsed_milliseconds / 1000):
                async with asyncio.TaskGroup() as group:
                    tasks = [
                        group.create_task(search_notebook(notebook_id, exact_document))
                        for notebook_id, exact_document in partition_specs
                    ]
                partitions = tuple(task.result() for task in tasks)
                await self._authorization.revalidate(selection)
                current = await self._authorization.inspect_active_sources(
                    selection, representations
                )
                if current != admission:
                    raise NotFoundError("authorized resource was not found")
        except TimeoutError as error:
            raise OperationTimeoutError("scoped search deadline expired") from error
        except ExceptionGroup as error:
            first = error.exceptions[0]
            if isinstance(first, (NotFoundError, PermissionError)):
                raise NotFoundError("authorized resource was not found") from first
            raise first from error

        searched = tuple(item for item in partitions if item.response is not None)
        if not searched or not any(
            source.status == "searched"
            for partition in searched
            if partition.response is not None
            for source in partition.response.envelope.sources
        ):
            raise DependencyUnavailableError("no applicable authorized source was searched")
        if documents:
            excluded = tuple(
                ScopedNotebookResult(
                    scope.notebook_id,
                    "not_applicable",
                    by_notebook[scope.notebook_id],
                    None,
                    "document_filter_excludes_scope",
                )
                for scope in selection.notebooks
                if all(item.notebook_id != scope.notebook_id for item in documents)
            )
            partitions += excluded
        pools: dict[UUID, deque[list[dict[str, object]]]] = {
            scope.notebook_id: deque() for scope in selection.notebooks
        }
        for partition in searched:
            assert partition.response is not None
            if not isinstance(partition.response.response, EvidenceSearchResponse):
                raise TypeError("scoped evidence service returned another operation")
            pools[partition.notebook_id].append(list(partition.response.response.items))
        ordered: list[dict[str, object]] = []
        while any(any(pool for pool in notebook_pools) for notebook_pools in pools.values()):
            for scope in selection.notebooks:
                notebook_pools = pools[scope.notebook_id]
                for _ in range(len(notebook_pools)):
                    pool = notebook_pools.popleft()
                    if pool:
                        ordered.append(pool.pop(0))
                        if pool:
                            notebook_pools.append(pool)
                        break
        items: list[dict[str, object]] = []
        bytes_used = 0
        truncated = False
        for item in ordered:
            if len(items) >= request.limit:
                truncated = True
                break
            size = len(json.dumps(item, sort_keys=True, default=str).encode("utf-8"))
            if bytes_used + size > self._config.max_advanced_response_bytes:
                truncated = True
                break
            items.append(item)
            bytes_used += size
        if ordered and not items:
            raise DependencyUnavailableError("bounded response cannot contain one evidence item")
        omissions = (
            tuple(
                f"{item.notebook_id}:{item.reason_code}"
                for item in partitions
                if item.reason_code is not None
            )
            + tuple(
                f"{item.notebook_id}:{source.representation.value}:{source.reason_code}"
                for item in partitions
                for source in item.sources
                if source.status not in {"active", "not_applicable"}
            )
            + tuple(
                f"{item.notebook_id}:{source.representation}:{source.reason_code}"
                for item in searched
                if item.response is not None
                for source in item.response.envelope.sources
                if source.status != "searched"
            )
            + (("global_result_budget",) if truncated else ())
        )
        partial = bool(omissions) or any(
            item.response is not None and item.response.completeness == "partial"
            for item in partitions
        )
        completeness = "partial" if partial else "empty" if not items else "unknown"
        return ScopedRankedResult(
            tuple(items),
            partitions,
            completeness,
            omissions,
            request.limit,
            candidate_budget,
            self._config.max_advanced_response_bytes,
        )

    async def execute_traversal(
        self, request: ScopeRequestReview, principal: ServerPrincipalV1
    ) -> ScopedTraversalResult:
        """Traverse signed notebook partitions without changing child cursor formats."""
        if request.mode != "traversal":
            raise ValueError("aggregate continuation requires traversal mode")
        selected = (
            request.scope.notebook_ids if isinstance(request.scope, SelectedNotebooks) else None
        )
        documents = tuple(
            ScopedDocumentSelection(item.notebook_id, item.document_id, item.version_id)
            for item in request.documents
        )
        selection = await self._authorization.resolve(
            principal, selected_notebooks=selected, documents=documents
        )
        notebooks = tuple(sorted(selection.notebooks, key=lambda item: str(item.notebook_id)))
        by_scope = {item.notebook_id: item for item in notebooks}
        partitions = (
            tuple(
                (by_scope[item.notebook_id], item)
                for item in sorted(
                    documents,
                    key=lambda value: (
                        str(value.notebook_id),
                        str(value.document_id),
                        str(value.version_id),
                    ),
                )
            )
            if documents
            else tuple((item, None) for item in notebooks)
        )
        if len(partitions) > 16:
            raise DependencyUnavailableError(
                "aggregate traversal exceeds bounded cursor partition count", retryable=False
            )
        per_partition_bytes = self._config.max_advanced_response_bytes // len(partitions)
        per_partition_content = self._config.max_advanced_content_characters // len(partitions)
        if per_partition_bytes < 256 or per_partition_content < 1:
            raise DependencyUnavailableError("aggregate traversal exceeds bounded byte budget")
        representations = (
            tuple(request.representations)
            if request.representations is not None
            else _AUTOMATIC_ORDER
        )
        admission = await self._authorization.inspect_active_sources(selection, representations)
        by_notebook = {
            scope.notebook_id: tuple(
                item for item in admission if item.notebook_id == scope.notebook_id
            )
            for scope in notebooks
        }
        policy = _admission_policy(
            admission, getattr(self._engine, "full_multilingual_v2_alias_digest", None)
        )
        per_call_candidate = (
            self._config.production_rerank_candidate_limit if self._config.production_mode else 1
        )
        max_calls = self._config.max_advanced_candidate_budget // per_call_candidate
        if max_calls < len(partitions):
            raise DependencyUnavailableError("aggregate traversal candidate budget is too small")
        binding: dict[str, object] = {
            "actor_id": str(principal.actor_id),
            "scope_kind": request.scope.kind,
            "membership": [[str(item.notebook_id), item.membership_revision] for item in notebooks],
            "documents": sorted(
                [str(item.notebook_id), str(item.document_id), str(item.version_id)]
                for item in documents
            ),
            "query": request.query,
            "representations": [item.value for item in representations],
            "automatic": request.representations is None,
            "policy": policy,
        }
        limits: dict[str, object] = {
            "requested_k": request.limit,
            "candidate_budget": self._config.max_advanced_candidate_budget,
            "byte_budget": self._config.max_advanced_response_bytes,
            "content_budget": self._config.max_advanced_content_characters,
            "deadline_ms": self._config.max_advanced_elapsed_milliseconds,
            "per_call_candidate": per_call_candidate,
        }
        keys = tuple(_partition_key(scope.notebook_id, exact) for scope, exact in partitions)
        states: dict[str, dict[str, object]] = {}
        next_index = 0
        prior_omissions: tuple[str, ...] = ()
        if request.cursor is not None:
            decoded = self._cursor.decode(
                request.cursor,
                expected_domain="mnemo-scoped-search-cursor/v1",
                expected_binding=binding,
                expected_limits=limits,
            )
            position = decoded.position
            next_index = position.get("next_index")  # type: ignore[assignment]
            raw_states = position.get("states")
            raw_omissions = position.get("omissions")
            if (
                not isinstance(next_index, int)
                or isinstance(next_index, bool)
                or not 0 <= next_index < len(partitions)
                or not isinstance(raw_states, dict)
                or set(raw_states) != set(keys)
                or not isinstance(raw_omissions, list)
                or not all(isinstance(item, str) for item in raw_omissions)
            ):
                raise CursorInvalidError("aggregate cursor position is invalid")
            for state in raw_states.values():
                if not isinstance(state, dict) or not isinstance(state.get("done"), bool):
                    raise CursorInvalidError("aggregate partition state is invalid")
                if state.get("excluded") is True:
                    if state != {"excluded": True, "done": True}:
                        raise CursorInvalidError("aggregate excluded state is invalid")
                    continue
                if (
                    not isinstance(state.get("snapshot"), str)
                    or not isinstance(state.get("status_digest"), str)
                    or (state.get("cursor") is not None and not isinstance(state["cursor"], str))
                    or (
                        state.get("last_cursor") is not None
                        and not isinstance(state["last_cursor"], str)
                    )
                    or (state["done"] and state.get("cursor") is not None)
                    or (not state["done"] and state.get("last_cursor") is not None)
                ):
                    raise CursorInvalidError("aggregate partition cursor is invalid")
            states = raw_states
            prior_omissions = tuple(raw_omissions)
        shared = SharedSearchApplicationService(self._engine, self._config)
        items: list[dict[str, object]] = []
        omissions = list(prior_omissions)
        calls = 0
        bytes_used = 0
        fetched_bytes = 0

        async def retrieve_one(
            notebook_id: UUID,
            exact_document: ScopedDocumentSelection | None,
            cursor: str | None,
        ) -> SharedSearchResult:
            nonlocal fetched_bytes
            active = tuple(
                item.representation for item in by_notebook[notebook_id] if item.status == "active"
            )
            if not active:
                raise DependencyUnavailableError("no active representation for traversal")
            response = await shared.execute(
                SharedSearchRequest(
                    SharedSearchKind.EVIDENCE,
                    EvidenceSearchRequest(
                        query=request.query,
                        mode=AdvancedRetrievalMode.EXHAUSTIVE,
                        scope=EvidenceScopeRequest(
                            notebook_id=notebook_id,
                            document_ids=(exact_document.document_id,) if exact_document else (),
                            version_ids=(exact_document.version_id,) if exact_document else (),
                        ),
                        representations=active,
                        cursor=cursor,
                        candidate_budget=1,
                        evidence_budget=1,
                        max_serialized_bytes=per_partition_bytes,
                        max_content_characters=per_partition_content,
                    ),
                ),
                principal,
                automatic_policy_version=policy,
            )
            if not isinstance(response.response, EvidenceSearchResponse):
                raise TypeError("scoped traversal returned another operation")
            fetched_bytes += len(response.response.model_dump_json().encode("utf-8"))
            if fetched_bytes > self._config.max_advanced_response_bytes:
                raise DependencyUnavailableError("aggregate traversal byte budget exhausted")
            return response

        def snapshot(result: SharedSearchResult) -> tuple[str, str]:
            if not isinstance(result.response, EvidenceSearchResponse):
                raise TypeError("scoped traversal returned another operation")
            value = result.response.coverage.get("snapshot_identity")
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise CursorInvalidError("source snapshot is invalid")
            statuses = hashlib.sha256(
                json.dumps(
                    result.response.coverage.get("representations", []),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            return value, statuses

        try:
            async with asyncio.timeout(self._config.max_advanced_elapsed_milliseconds / 1000):
                prefetched: dict[str, SharedSearchResult] = {}
                # Validate every partition before emitting from any partition.
                for index, (scope, exact_document) in enumerate(partitions):
                    notebook_id = scope.notebook_id
                    key = keys[index]
                    state = states.get(key)
                    if not any(item.status == "active" for item in by_notebook[notebook_id]):
                        if state is not None and state.get("excluded") is not True:
                            raise CursorConflictError("aggregate admission changed")
                        states[key] = {"excluded": True, "done": True}
                        omission = f"{key}:no_admitted_source"
                        if omission not in omissions:
                            omissions.append(omission)
                        continue
                    if state is not None and state.get("excluded") is True:
                        raise CursorConflictError("aggregate admission changed")
                    if calls >= max_calls:
                        raise DependencyUnavailableError("aggregate validation budget exhausted")
                    cursor_value = (
                        state.get("last_cursor")
                        if state is not None and state.get("done") is True
                        else state.get("cursor")
                        if state is not None
                        else None
                    )
                    if cursor_value is not None and not isinstance(cursor_value, str):
                        raise CursorInvalidError("aggregate child cursor is invalid")
                    child = await retrieve_one(notebook_id, exact_document, cursor_value)
                    calls += 1
                    source_snapshot, status_digest = snapshot(child)
                    if state is not None and (source_snapshot, status_digest) != (
                        state.get("snapshot"),
                        state.get("status_digest"),
                    ):
                        raise CursorConflictError("aggregate source snapshot or status changed")
                    if state is not None and state.get("done") is True:
                        if child.next_cursor is not None:
                            raise CursorConflictError("completed aggregate partition changed")
                    else:
                        states[key] = {
                            "cursor": cursor_value,
                            "snapshot": source_snapshot,
                            "status_digest": status_digest,
                            "done": False,
                        }
                        prefetched[key] = child
                    for value in child.omissions:
                        omission = f"{key}:{value}"
                        if omission not in omissions:
                            omissions.append(omission)

                remaining = sum(state.get("done") is not True for state in states.values())
                while len(items) < request.limit and remaining:
                    index = next_index
                    next_index = (next_index + 1) % len(partitions)
                    state = states[keys[index]]
                    if state.get("done") is True:
                        continue
                    scope, exact_document = partitions[index]
                    previous_cursor = state.get("cursor")
                    if previous_cursor is not None and not isinstance(previous_cursor, str):
                        raise CursorInvalidError("aggregate child cursor is invalid")
                    page = prefetched.pop(keys[index]) if keys[index] in prefetched else None
                    if page is None:
                        if calls >= max_calls:
                            break
                        page = await retrieve_one(
                            scope.notebook_id, exact_document, previous_cursor
                        )
                        calls += 1
                    if snapshot(page) != (state.get("snapshot"), state.get("status_digest")):
                        raise CursorConflictError("aggregate source snapshot or status changed")
                    assert isinstance(page.response, EvidenceSearchResponse)
                    if len(page.response.items) > 1:
                        raise CursorConflictError("aggregate child exceeded one-item budget")
                    for item in page.response.items:
                        if UUID(str(item["notebook_id"])) != scope.notebook_id or (
                            exact_document is not None
                            and (
                                UUID(str(item["document_id"])),
                                UUID(str(item["version_id"])),
                            )
                            != (exact_document.document_id, exact_document.version_id)
                        ):
                            raise NotFoundError("authorized resource was not found")
                        size = len(json.dumps(item, sort_keys=True, default=str).encode())
                        if bytes_used + size > self._config.max_advanced_response_bytes:
                            raise DependencyUnavailableError(
                                "aggregate response byte budget exhausted"
                            )
                        items.append(item)
                        bytes_used += size
                    if page.next_cursor is not None:
                        if page.next_cursor == previous_cursor:
                            raise CursorConflictError("aggregate continuation did not advance")
                        state["cursor"] = page.next_cursor
                    else:
                        state["cursor"] = None
                        state["last_cursor"] = previous_cursor
                        state["done"] = True
                        remaining -= 1
                await self._authorization.revalidate(selection)
                if (
                    await self._authorization.inspect_active_sources(selection, representations)
                    != admission
                ):
                    raise CursorConflictError("aggregate generation admission changed")
        except TimeoutError as error:
            raise OperationTimeoutError("aggregate traversal deadline expired") from error
        snapshot_identity = hashlib.sha256(
            json.dumps(
                {"states": states, "next_index": next_index},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        next_cursor = None
        if remaining:
            next_cursor = self._cursor.encode(
                domain="mnemo-scoped-search-cursor/v1",
                snapshot_identity=snapshot_identity,
                binding=binding,
                position={
                    "next_index": next_index,
                    "states": states,
                    "omissions": omissions,
                },
                limits=limits,
            )
            if len(next_cursor) > 8192:
                raise DependencyUnavailableError("aggregate cursor exceeds bounded contract")
        return ScopedTraversalResult(
            tuple(items),
            "truncated"
            if next_cursor
            else "partial"
            if omissions
            else "empty"
            if not items and request.cursor is None
            else "complete",
            tuple(omissions),
            snapshot_identity,
            next_cursor,
            request.limit,
        )


def _admission_policy(
    admission: tuple[ScopedRepresentationAdmission, ...], full_alias: str | None
) -> str:
    return (
        "scoped-automatic/v1:"
        + hashlib.sha256(
            json.dumps(
                {
                    "full_alias": full_alias,
                    "sources": [
                        [
                            str(item.notebook_id),
                            item.representation.value,
                            item.status,
                            item.generation_alias,
                        ]
                        for item in admission
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )


def _partition_key(notebook_id: UUID, exact: ScopedDocumentSelection | None) -> str:
    if exact is None:
        return str(notebook_id)
    return f"{notebook_id}:{exact.document_id}:{exact.version_id}"
