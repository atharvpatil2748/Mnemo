"""Deterministic multi-source retrieval orchestration and RRF fusion."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, fields, replace

from mnemo.interfaces import (
    DependencyUnavailableError,
    EmbeddingProviderV1,
    EmbeddingVector,
    IntegrityError,
    MnemoInterfaceError,
    ParentPromotionInterfaceV1,
    PluginError,
    RetrieverInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    Chunk,
    FrozenMetadata,
    FusedChunkResult,
    FusionEvidence,
    RetrievalFusionResult,
    RetrievalInvocationTrace,
    RetrievalMode,
    RetrievalPlan,
    ScoredChunk,
    SubQuery,
)
from mnemo.registry import PluginRegistry, RegistryState

RRF_K = 60
DEFAULT_MAX_CONCURRENCY = 4
MAX_RETRIEVAL_CONCURRENCY = 32
MAX_GLOBAL_RESULTS = 100
_RUNTIME_RETRIEVAL_METADATA = frozenset({"document_title", "retrieval_title_match"})
_EFFECTIVE_MODE_ORDER = {
    RetrievalMode.DENSE: 0,
    RetrievalMode.SPARSE: 1,
}


@dataclass(frozen=True, slots=True)
class _Invocation:
    """One deterministic source-local execution unit."""

    subquery_index: int
    subquery: SubQuery
    effective_mode: RetrievalMode
    retriever: RetrieverInterfaceV1

    @property
    def invocation_id(self) -> str:
        return f"sq-{self.subquery_index}:{self.effective_mode.value}"

    @property
    def order_key(self) -> tuple[int, int]:
        return self.subquery_index, _EFFECTIVE_MODE_ORDER[self.effective_mode]


class MultiSourceRetriever:
    """Execute a bounded plan and retain every source-local rank contribution."""

    def __init__(
        self,
        registry: PluginRegistry,
        embedding_provider: EmbeddingProviderV1,
        *,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        """Bind frozen capabilities and one execution-time embedding provider."""
        if not isinstance(registry, PluginRegistry):
            raise TypeError("registry must be PluginRegistry")
        if registry.state is not RegistryState.FROZEN:
            raise ValueError("registry must be frozen before orchestration")
        if not isinstance(embedding_provider, EmbeddingProviderV1):
            raise TypeError("embedding_provider must implement EmbeddingProviderV1")
        _validate_bounded_integer(
            max_concurrency,
            "max_concurrency",
            maximum=MAX_RETRIEVAL_CONCURRENCY,
        )
        self._registry = registry
        self._embedding_provider = embedding_provider
        self._max_concurrency = max_concurrency

    async def execute(
        self,
        plan: RetrievalPlan,
        *,
        global_limit: int,
    ) -> RetrievalFusionResult:
        """Execute, promote, deduplicate, and fuse one validated retrieval plan."""
        if not isinstance(plan, RetrievalPlan):
            raise TypeError("plan must be RetrievalPlan")
        _validate_bounded_integer(global_limit, "global_limit", maximum=MAX_GLOBAL_RESULTS)

        invocations, promoter = self._preflight(plan)
        limiter = asyncio.Semaphore(self._max_concurrency)
        traces = await self._run_fail_fast(invocations, promoter, limiter)
        return RetrievalFusionResult(
            plan=plan,
            invocations=traces,
            results=_fuse(traces, global_limit),
        )

    def _preflight(
        self,
        plan: RetrievalPlan,
    ) -> tuple[tuple[_Invocation, ...], ParentPromotionInterfaceV1]:
        required_modes: set[RetrievalMode] = set()
        expanded: list[tuple[int, SubQuery, RetrievalMode]] = []
        for index, subquery in enumerate(plan.sub_queries, start=1):
            if subquery.retrieval_mode is RetrievalMode.GRAPH:
                raise UnsupportedError("graph retrieval is unavailable in Module 6.5 V1")
            if subquery.retrieval_mode is RetrievalMode.PARENT:
                raise UnsupportedError("parent is a promotion capability, not a retriever")
            effective_modes = (
                (RetrievalMode.DENSE, RetrievalMode.SPARSE)
                if subquery.retrieval_mode is RetrievalMode.HYBRID
                else (subquery.retrieval_mode,)
            )
            for mode in effective_modes:
                required_modes.add(mode)
                expanded.append((index, subquery, mode))

        resolved: dict[RetrievalMode, RetrieverInterfaceV1] = {}
        for mode in sorted(required_modes, key=lambda item: _EFFECTIVE_MODE_ORDER[item]):
            retriever = self._registry.resolve_retriever(mode.value)
            if retriever is None:
                raise DependencyUnavailableError(
                    f"retriever capability is unavailable: {mode.value}"
                )
            if not isinstance(retriever, RetrieverInterfaceV1):
                raise IntegrityError(f"registered {mode.value} retriever violates its contract")
            if retriever.retrieval_mode != mode.value:
                raise IntegrityError(f"registered {mode.value} retriever reports the wrong mode")
            resolved[mode] = retriever

        promoter = self._registry.resolve_parent_promoter("default")
        if promoter is None:
            raise DependencyUnavailableError("parent_promotion/default capability is unavailable")
        if not isinstance(promoter, ParentPromotionInterfaceV1):
            raise IntegrityError("registered parent promoter violates its contract")

        invocations = tuple(
            _Invocation(index, subquery, mode, resolved[mode]) for index, subquery, mode in expanded
        )
        return invocations, promoter

    async def _run_fail_fast(
        self,
        invocations: tuple[_Invocation, ...],
        promoter: ParentPromotionInterfaceV1,
        limiter: asyncio.Semaphore,
    ) -> tuple[RetrievalInvocationTrace, ...]:
        tasks = tuple(
            asyncio.create_task(
                self._execute_invocation(invocation, promoter, limiter),
                name=invocation.invocation_id,
            )
            for invocation in invocations
        )
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            failures = [task for task in done if not task.cancelled() and task.exception()]
            if failures:
                for task in pending:
                    task.cancel()
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                raise _deterministic_failure(invocations, outcomes)
            if pending:
                await asyncio.gather(*pending)
            return tuple(task.result() for task in tasks)
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _execute_invocation(
        self,
        invocation: _Invocation,
        promoter: ParentPromotionInterfaceV1,
        limiter: asyncio.Semaphore,
    ) -> RetrievalInvocationTrace:
        async with limiter:
            embedding: EmbeddingVector | None = None
            if invocation.effective_mode is RetrievalMode.DENSE:
                embedding = await self._embedding_provider.embed(invocation.subquery.query_text)
                _validate_embedding(embedding, self._embedding_provider.dimensions)

            try:
                raw = await invocation.retriever.retrieve(
                    invocation.subquery.query_text,
                    embedding,
                    invocation.subquery.filters,
                    invocation.subquery.max_results,
                )
            except (MnemoInterfaceError, TypeError, ValueError):
                raise
            except Exception as error:
                raise _plugin_error(invocation, "retriever", error) from error
            _validate_stream(
                raw,
                invocation.effective_mode,
                invocation.subquery.max_results,
                "retriever",
            )

            try:
                promoted = await promoter.promote(raw)
            except (MnemoInterfaceError, TypeError, ValueError):
                raise
            except Exception as error:
                raise _plugin_error(invocation, "parent promoter", error) from error
            _validate_stream(
                promoted,
                invocation.effective_mode,
                invocation.subquery.max_results,
                "parent promoter",
            )
            if len(promoted) > len(raw):
                raise IntegrityError("parent promotion must not expand a source-local stream")

            return RetrievalInvocationTrace(
                invocation_id=invocation.invocation_id,
                subquery_index=invocation.subquery_index,
                declared_mode=invocation.subquery.retrieval_mode,
                effective_mode=invocation.effective_mode,
                query_text=invocation.subquery.query_text,
                filters=invocation.subquery.filters,
                requested_top_k=invocation.subquery.max_results,
                raw_results=raw,
                promoted_results=promoted,
            )


def _validate_bounded_integer(value: int, field_name: str, *, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1 or value > maximum:
        raise ValueError(f"{field_name} must be from 1 through {maximum}")


def _validate_embedding(embedding: EmbeddingVector, dimensions: int) -> None:
    if not isinstance(embedding, tuple):
        raise IntegrityError("embedding provider returned a non-tuple vector")
    if len(embedding) != dimensions:
        raise IntegrityError("embedding dimensions do not match the provider")
    if not embedding or any(
        isinstance(component, bool)
        or not isinstance(component, (int, float))
        or not math.isfinite(component)
        for component in embedding
    ):
        raise IntegrityError("embedding provider returned invalid components")


def _validate_stream(
    results: object,
    effective_mode: RetrievalMode,
    top_k: int,
    stage: str,
) -> None:
    if not isinstance(results, tuple):
        raise IntegrityError(f"{stage} returned a non-tuple stream")
    if len(results) > top_k:
        raise IntegrityError(f"{stage} returned more than the requested top_k")
    if any(not isinstance(item, ScoredChunk) for item in results):
        raise IntegrityError(f"{stage} returned an invalid result")
    identities = tuple(item.chunk.id for item in results)
    if len(set(identities)) != len(identities):
        raise IntegrityError(f"{stage} returned duplicate chunk identities")
    if any(item.source != effective_mode.value for item in results):
        raise IntegrityError(f"{stage} returned the wrong source-local domain")
    if tuple(item.rank for item in results) != tuple(range(1, len(results) + 1)):
        raise IntegrityError(f"{stage} ranks must be contiguous and match tuple order")
    expected = tuple(sorted(results, key=lambda item: (-item.score, item.chunk.id)))
    if results != expected:
        raise IntegrityError(f"{stage} stream ordering is not deterministic")


def _plugin_error(invocation: _Invocation, component: str, error: Exception) -> PluginError:
    from mnemo.models import FrozenMetadata

    return PluginError(
        f"{component} invocation failed: {invocation.invocation_id}",
        details=FrozenMetadata(
            {
                "retrieval.invocation_id": invocation.invocation_id,
                "retrieval.error.type": type(error).__name__,
            }
        ),
    )


def _deterministic_failure(
    invocations: tuple[_Invocation, ...],
    outcomes: list[RetrievalInvocationTrace | BaseException],
) -> BaseException:
    failures = tuple(
        (invocation.order_key, outcome)
        for invocation, outcome in zip(invocations, outcomes, strict=True)
        if isinstance(outcome, BaseException) and not isinstance(outcome, asyncio.CancelledError)
    )
    if not failures:
        return asyncio.CancelledError()
    return min(failures, key=lambda item: item[0])[1]


def _fuse(
    traces: tuple[RetrievalInvocationTrace, ...],
    global_limit: int,
) -> tuple[FusedChunkResult, ...]:
    chunks: dict[str, Chunk] = {}
    evidence_by_chunk: dict[str, list[FusionEvidence]] = {}
    for trace in traces:
        raw_ids = {result.chunk.id for result in trace.raw_results}
        for result in trace.promoted_results:
            existing = chunks.get(result.chunk.id)
            if existing is not None and not _same_chunk_snapshot(existing, result.chunk):
                raise IntegrityError("equal chunk IDs contain conflicting canonical snapshots")
            chunks[result.chunk.id] = (
                result.chunk
                if existing is None
                else _merge_runtime_retrieval_metadata(existing, result.chunk)
            )
            evidence_by_chunk.setdefault(result.chunk.id, []).append(
                FusionEvidence(
                    invocation_id=trace.invocation_id,
                    subquery_index=trace.subquery_index,
                    declared_mode=trace.declared_mode,
                    effective_mode=trace.effective_mode,
                    result=result,
                    identity_introduced_by_parent_promotion=result.chunk.id not in raw_ids,
                )
            )

    scored = tuple(
        (
            chunks[chunk_id],
            math.fsum(1.0 / (RRF_K + item.result.rank) for item in evidence),
            tuple(evidence),
        )
        for chunk_id, evidence in evidence_by_chunk.items()
    )
    ordered = sorted(scored, key=lambda item: (-item[1], item[0].id))[:global_limit]
    return tuple(
        FusedChunkResult(
            chunk=chunk,
            rrf_score=rrf_score,
            global_rank=rank,
            evidence=evidence,
        )
        for rank, (chunk, rrf_score, evidence) in enumerate(ordered, start=1)
    )


def _same_chunk_snapshot(left: Chunk, right: Chunk) -> bool:
    if any(
        getattr(left, field.name) != getattr(right, field.name)
        for field in fields(Chunk)
        if field.name != "metadata"
    ):
        return False
    left_metadata = {
        key: value for key, value in left.metadata.items() if key not in _RUNTIME_RETRIEVAL_METADATA
    }
    right_metadata = {
        key: value
        for key, value in right.metadata.items()
        if key not in _RUNTIME_RETRIEVAL_METADATA
    }
    if left_metadata != right_metadata:
        return False
    left_title = left.metadata.get("document_title")
    right_title = right.metadata.get("document_title")
    return left_title is None or right_title is None or left_title == right_title


def _merge_runtime_retrieval_metadata(left: Chunk, right: Chunk) -> Chunk:
    """Merge transient retrieval evidence without mutating the canonical snapshot."""
    metadata = dict(left.metadata)
    right_title = right.metadata.get("document_title")
    if "document_title" not in metadata and right_title is not None:
        metadata["document_title"] = right_title
    if bool(left.metadata.get("retrieval_title_match", False)) or bool(
        right.metadata.get("retrieval_title_match", False)
    ):
        metadata["retrieval_title_match"] = True
    elif "retrieval_title_match" in left.metadata or "retrieval_title_match" in right.metadata:
        metadata["retrieval_title_match"] = False
    return replace(left, metadata=FrozenMetadata(metadata))
