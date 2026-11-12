"""Disposable-only typed retrieval probe; never builds or promotes generations.

This is an operational path check, not a semantic relevance benchmark. Results
contain identities and provider status only, never source or query content.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mnemo.engine import KnowledgeEngine  # noqa: E402
from mnemo.interfaces import NotFoundError, OperationTimeoutError, PrincipalContextV1  # noqa: E402
from mnemo.interfaces.advanced_retrieval import (  # noqa: E402
    AdvancedRetrievalSourceV1,
    AdvancedSourcePage,
    PrincipalAwareAdvancedRetrievalSourceV2,
)
from mnemo.models.advanced_retrieval import (  # noqa: E402
    AdvancedRetrievalCandidate,
    EvidenceRepresentation,
    RetrievalPlanV2,
)
from mnemo.retrieval import advanced as advanced_retrieval_module  # noqa: E402
from mnemo.retrieval.advanced import AdvancedRetrievalService, RetrievalCursorCodec  # noqa: E402
from mnemo.retrieval.advanced_sources import CanonicalTextAdvancedSource  # noqa: E402
from mnemo.retrieval.clip_text_query import LocalCLIPTextQueryProvider  # noqa: E402
from mnemo.retrieval.multimodal_sources import ProjectedMultimodalAdvancedSource  # noqa: E402
from mnemo.retrieval.sparse import SparseRetriever  # noqa: E402
from mnemo_server.config import ServerConfig  # noqa: E402
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchResponse  # noqa: E402
from mnemo_server.schemas.scope_contract_review import (  # noqa: E402
    ScopeRequestReview,
    SelectedNotebooks,
)
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority  # noqa: E402
from mnemo_server.services.scoped_search import ScopedSearchApplicationService  # noqa: E402
from mnemo_server.services.shared_search import ScopedSearchAuthorization  # noqa: E402

from scripts.evaluate_phase86_four_notebooks import (  # noqa: E402
    EvaluationProgress,
    ReadOnlyEvaluationStore,
    _ranked_identity,
    _target_key,
    attach_full_v2,
    load_qrels,
    metrics,
)
from scripts.phase86_identity_qrels import BOUND_NAME  # noqa: E402
from scripts.run_phase86_four_notebooks import notebook_ids, preflight, run_paths  # noqa: E402

COPY = ROOT / "scratch/module_894_multimodal/eval-20261109-01"
CLIP = (
    Path("D:/Mnemo/phase8.5.11-models/huggingface/hub")
    / "models--openai--clip-vit-large-patch14/snapshots"
    / "32bd64288804d66eefd0ccbe215aa642df71cc41"
)
_REPRESENTATIONS = (
    EvidenceRepresentation.OCR_TEXT,
    EvidenceRepresentation.VISION_ANALYSIS,
    EvidenceRepresentation.VISUAL_VECTOR,
)


def _visual_candidate_key(candidate: AdvancedRetrievalCandidate) -> tuple[str, ...]:
    evidence = candidate.evidence_id
    if evidence is None and candidate.chunk is not None:
        evidence = candidate.chunk.id
    if evidence is None and candidate.derivation_id is not None:
        evidence = str(candidate.derivation_id)
    return (
        str(candidate.notebook_id),
        str(candidate.source_id),
        str(candidate.document_id),
        str(candidate.version_id),
        "" if evidence is None else str(evidence),
    )


def _visual_candidate_record(candidate: AdvancedRetrievalCandidate) -> dict[str, object]:
    content_digest = (
        None
        if candidate.content is None
        else hashlib.sha256(candidate.content.encode("utf-8")).hexdigest()
    )
    locator_digest = hashlib.sha256(
        json.dumps(
            dict(candidate.locator), sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()
    return {
        "candidate_id": str(candidate.candidate_id),
        "notebook_id": str(candidate.notebook_id),
        "source_id": str(candidate.source_id),
        "document_id": str(candidate.document_id),
        "version_id": str(candidate.version_id),
        "representation": candidate.representation.value,
        "chunk_id": None if candidate.chunk is None else candidate.chunk.id,
        "occurrence_id": (
            None if candidate.occurrence_id is None else str(candidate.occurrence_id)
        ),
        "derivation_id": (
            None if candidate.derivation_id is None else str(candidate.derivation_id)
        ),
        "evidence_id": candidate.evidence_id,
        "content_sha256": content_digest,
        "locator_sha256": locator_digest,
        "locator_keys": sorted(dict(candidate.locator)),
        "fused_score": candidate.fused_score,
        "source_ranks": [{"path": item.path, "rank": item.source_rank} for item in candidate.paths],
    }


async def probe(
    *,
    with_bge: bool,
    frozen_qrels: bool,
    trace_children: bool = False,
    trace_sources: bool = False,
    case_id_filter: str | None = None,
    visual_qrels: bool = False,
    unified_visual: bool = False,
    single_notebook_only: bool = False,
) -> dict[str, object]:
    plan, records = preflight()
    _base_runtime, _run_id, logs = run_paths(plan)
    if not COPY.resolve(strict=True).is_relative_to((ROOT / "scratch").resolve(strict=True)):
        raise ValueError("probe must use the isolated scratch copy")
    expected = (
        UUID(str(plan["existing_notebook"]["id"])),
        *notebook_ids(plan).values(),
    )
    owner = UUID(str(plan["disposable_actor_id"]))
    authority = SQLiteNotebookScopeAuthority(COPY / "acl.db")
    if any(not authority.permits(owner, notebook) for notebook in expected):
        raise PermissionError("disposable owner lacks exact four-notebook scope")
    store = ReadOnlyEvaluationStore(COPY / "mnemo.db")
    async with AsyncExitStack() as stack:
        await store.open()
        stack.push_async_callback(store.close)
        canonical = CanonicalTextAdvancedSource(
            store=store, ranked_retriever=SparseRetriever(store)
        )
        sources: list[AdvancedRetrievalSourceV1] = [canonical]
        if not frozen_qrels:
            for representation in _REPRESENTATIONS[:2]:
                sources.append(
                    ProjectedMultimodalAdvancedSource(store=store, representation=representation)
                )
            provider = LocalCLIPTextQueryProvider(
                snapshot=CLIP,
                profile_id="clip-vit-large-patch14/recertification-v2",
                shared_space_id="openai/clip-vit-large-patch14@32bd64288804d66eefd0ccbe215aa642df71cc41",
                dimensions=768,
            )
            if not await provider.ready():
                raise RuntimeError("CLIP query tower unavailable")
            sources.append(
                ProjectedMultimodalAdvancedSource(
                    store=store,
                    representation=EvidenceRepresentation.VISUAL_VECTOR,
                    visual_query_provider=provider,
                )
            )
        harness = SimpleNamespace(
            storage=store,
            server_scope_authority=authority,
            advanced_retrieval=AdvancedRetrievalService(
                sources=tuple(sources),
                cursor_codec=RetrievalCursorCodec(b"disposable-multimodal-probe-only"),
            ),
            full_multilingual_v2_alias_digest=None,
            config=SimpleNamespace(
                storage=SimpleNamespace(sqlite=SimpleNamespace(path=COPY / "mnemo.db"))
            ),
        )
        if with_bge:
            await attach_full_v2(COPY, logs, plan, store, harness, canonical, stack)
            if not frozen_qrels:
                harness.advanced_retrieval = AdvancedRetrievalService(
                    sources=(
                        *sources,
                        harness.advanced_retrieval._sources[
                            EvidenceRepresentation.MULTILINGUAL_TEXT
                        ],
                    ),
                    cursor_codec=RetrievalCursorCodec(b"disposable-multimodal-probe-only"),
                )
        authorization = ScopedSearchAuthorization(cast(KnowledgeEngine, harness))
        principal = PrincipalContextV1(owner, True)
        selection = await authorization.resolve(principal, selected_notebooks=expected)
        service = ScopedSearchApplicationService(cast(KnowledgeEngine, harness), ServerConfig())
        results: dict[str, object] = {}
        if visual_qrels:
            if unified_visual and not with_bge:
                raise ValueError("unified visual evaluation requires the verified BGE source")
            qrel_path = ROOT / "evaluation/module_894_mvea/visual-identity.v1.json"
            qrel_digest = hashlib.sha256(qrel_path.read_bytes()).hexdigest()
            if qrel_digest != "621cc19d102c3ec79942659755bcfa9347071dcba82ea48df3b25ed408ec3e63":
                raise ValueError("frozen visual QREL identity changed")
            visual_cases = json.loads(qrel_path.read_text(encoding="utf-8"))["cases"]
            if len(visual_cases) != 20:
                raise ValueError("visual QREL cohort is incomplete")
            progress_path = COPY / f"visual-evaluation-progress-{uuid4().hex}.jsonl"
            rows: list[dict[str, object]] = []
            visual_progress_stream = progress_path.open("x", encoding="utf-8")
            stack.callback(visual_progress_stream.close)
            with nullcontext(visual_progress_stream):
                child_started: dict[tuple[str, str], tuple[str, float]] = {}

                def append_progress(value: dict[str, object]) -> None:
                    visual_progress_stream.write(json.dumps(value, sort_keys=True) + "\n")
                    visual_progress_stream.flush()
                    os.fsync(visual_progress_stream.fileno())

                def observe_child(
                    notebook_id: UUID,
                    stage: str,
                    outcome: str,
                    result_count: int | None,
                    error_category: str | None,
                ) -> None:
                    key = (str(notebook_id), stage)
                    now = datetime.now(UTC).isoformat()
                    monotonic = time.perf_counter()
                    if outcome == "started":
                        child_started[key] = (now, monotonic)
                        append_progress(
                            {
                                "event": "child_started",
                                "notebook_id": str(notebook_id),
                                "stage": stage,
                                "started_at": now,
                            }
                        )
                        return
                    initial = child_started.pop(key, None)
                    append_progress(
                        {
                            "event": "child_terminal",
                            "notebook_id": str(notebook_id),
                            "stage": stage,
                            "outcome": outcome,
                            "started_at": None if initial is None else initial[0],
                            "completed_at": now,
                            "elapsed_seconds": (
                                None if initial is None else monotonic - initial[1]
                            ),
                            "result_count": result_count,
                            "exception_class": error_category,
                        }
                    )

                traced_service = ScopedSearchApplicationService(
                    cast(KnowledgeEngine, harness),
                    ServerConfig(),
                    child_observer=observe_child,
                )
            visual_trace_stream = None
            visual_trace_state: dict[str, object] = {
                "case_id": "",
                "notebook_id": "",
                "targets": set(),
            }

            def trace_started(stage: str, representation: str | None = None) -> tuple[str, float]:
                started_at = datetime.now(UTC).isoformat()
                started = time.perf_counter()
                if visual_trace_stream is not None:
                    append_progress(
                        {
                            "event": "pipeline_stage_started",
                            "case_id": visual_trace_state["case_id"],
                            "notebook_id": visual_trace_state["notebook_id"],
                            "stage": stage,
                            "representation": representation,
                            "started_at": started_at,
                        }
                    )
                return started_at, started

            def trace_completed(
                stage: str,
                timing: tuple[str, float],
                *,
                outcome: str,
                inputs: tuple[AdvancedRetrievalCandidate, ...] | None = None,
                outputs: tuple[AdvancedRetrievalCandidate, ...] | None = None,
                representation: str | None = None,
                error: BaseException | None = None,
            ) -> None:
                if visual_trace_stream is None:
                    return
                target_keys = visual_trace_state["targets"]
                assert isinstance(target_keys, set)
                output_records = (
                    [] if outputs is None else [_visual_candidate_record(item) for item in outputs]
                )
                target_ranks = (
                    []
                    if outputs is None
                    else [
                        index
                        for index, item in enumerate(outputs, 1)
                        if _visual_candidate_key(item) in target_keys
                    ]
                )
                unique_evidence = (
                    set()
                    if outputs is None
                    else {
                        (
                            str(item.notebook_id),
                            str(item.source_id),
                            str(item.document_id),
                            str(item.version_id),
                            "chunk",
                            item.chunk.id,
                        )
                        if item.chunk is not None
                        else (
                            str(item.notebook_id),
                            str(item.source_id),
                            str(item.document_id),
                            str(item.version_id),
                            "occurrence",
                            str(item.occurrence_id),
                        )
                        if item.occurrence_id is not None
                        else _visual_candidate_key(item)
                        for item in outputs
                    }
                )
                append_progress(
                    {
                        "event": "pipeline_stage_terminal",
                        "case_id": visual_trace_state["case_id"],
                        "notebook_id": visual_trace_state["notebook_id"],
                        "stage": stage,
                        "representation": representation,
                        "started_at": timing[0],
                        "completed_at": datetime.now(UTC).isoformat(),
                        "elapsed_seconds": time.perf_counter() - timing[1],
                        "outcome": outcome,
                        "exception_class": None if error is None else type(error).__name__,
                        "input_count": None if inputs is None else len(inputs),
                        "output_count": None if outputs is None else len(outputs),
                        "unique_evidence_count": len(unique_evidence),
                        "target_ranks": target_ranks,
                        "candidates": output_records,
                    }
                )

            if trace_sources or visual_qrels:
                visual_source_trace_path = COPY / f"visual-source-trace-{uuid4().hex}.jsonl"
                visual_trace_stream = stack.enter_context(
                    visual_source_trace_path.open("x", encoding="utf-8")
                )
                results["source_trace_artifact"] = str(visual_source_trace_path)

                for advanced_source in harness.advanced_retrieval._sources.values():
                    source_representation = advanced_source.representation.value
                    if isinstance(advanced_source, PrincipalAwareAdvancedRetrievalSourceV2):
                        original_authorized = advanced_source.retrieve_authorized

                        async def traced_source_authorized(
                            *,
                            principal: PrincipalContextV1,
                            plan: RetrievalPlanV2,
                            offset: int,
                            limit: int,
                            method: Callable[
                                ..., Awaitable[AdvancedSourcePage]
                            ] = original_authorized,
                            representation_name: str = source_representation,
                        ) -> AdvancedSourcePage:
                            timing = trace_started("provider_output", representation_name)
                            try:
                                page = await method(
                                    principal=principal, plan=plan, offset=offset, limit=limit
                                )
                            except BaseException as error:
                                trace_completed(
                                    "provider_output",
                                    timing,
                                    outcome=(
                                        "cancelled"
                                        if isinstance(error, asyncio.CancelledError)
                                        else "failed"
                                    ),
                                    representation=representation_name,
                                    error=error,
                                )
                                raise
                            trace_completed(
                                "provider_output",
                                timing,
                                outcome="completed",
                                outputs=page.candidates,
                                representation=representation_name,
                            )
                            return page

                        stack.enter_context(
                            patch.object(
                                advanced_source, "retrieve_authorized", traced_source_authorized
                            )
                        )
                    else:
                        original_retrieve = advanced_source.retrieve

                        async def traced_source_retrieve(
                            plan: RetrievalPlanV2,
                            *,
                            offset: int,
                            limit: int,
                            method: Callable[
                                ..., Awaitable[AdvancedSourcePage]
                            ] = original_retrieve,
                            representation_name: str = source_representation,
                        ) -> AdvancedSourcePage:
                            timing = trace_started("provider_output", representation_name)
                            try:
                                page = await method(plan, offset=offset, limit=limit)
                            except BaseException as error:
                                trace_completed(
                                    "provider_output",
                                    timing,
                                    outcome=(
                                        "cancelled"
                                        if isinstance(error, asyncio.CancelledError)
                                        else "failed"
                                    ),
                                    representation=representation_name,
                                    error=error,
                                )
                                raise
                            trace_completed(
                                "provider_output",
                                timing,
                                outcome="completed",
                                outputs=page.candidates,
                                representation=representation_name,
                            )
                            return page

                        stack.enter_context(
                            patch.object(advanced_source, "retrieve", traced_source_retrieve)
                        )

                original_deduplicate = advanced_retrieval_module._deduplicate

                def traced_deduplicate(
                    candidates: tuple[AdvancedRetrievalCandidate, ...],
                ) -> tuple[AdvancedRetrievalCandidate, ...]:
                    timing = trace_started("candidate_deduplication")
                    values = original_deduplicate(candidates)
                    trace_completed(
                        "candidate_deduplication",
                        timing,
                        outcome="completed",
                        inputs=candidates,
                        outputs=values,
                    )
                    return values

                original_rank_fuse = advanced_retrieval_module._rank_fuse

                def traced_rank_fuse(
                    candidates: tuple[AdvancedRetrievalCandidate, ...],
                    *,
                    source_rank_first: bool = False,
                ) -> tuple[AdvancedRetrievalCandidate, ...]:
                    timing = trace_started("fusion")
                    values = original_rank_fuse(candidates, source_rank_first=source_rank_first)
                    trace_completed(
                        "fusion", timing, outcome="completed", inputs=candidates, outputs=values
                    )
                    return values

                original_diversify = advanced_retrieval_module._diversify_occurrences

                def traced_diversify(
                    candidates: tuple[AdvancedRetrievalCandidate, ...],
                ) -> tuple[AdvancedRetrievalCandidate, ...]:
                    timing = trace_started("advanced_selection")
                    values = original_diversify(candidates)
                    trace_completed(
                        "advanced_selection",
                        timing,
                        outcome="completed",
                        inputs=candidates,
                        outputs=values,
                    )
                    return values

                original_bounds = advanced_retrieval_module._apply_output_bounds

                def traced_bounds(
                    plan: RetrievalPlanV2,
                    candidates: tuple[AdvancedRetrievalCandidate, ...],
                ) -> tuple[tuple[AdvancedRetrievalCandidate, ...], str | None]:
                    timing = trace_started("result_truncation")
                    values, reason = original_bounds(plan, candidates)
                    trace_completed(
                        "result_truncation",
                        timing,
                        outcome="completed",
                        inputs=candidates,
                        outputs=values,
                    )
                    if visual_trace_stream is not None and reason is not None:
                        append_progress(
                            {
                                "event": "truncation_reason",
                                "case_id": visual_trace_state["case_id"],
                                "notebook_id": visual_trace_state["notebook_id"],
                                "reason": reason,
                            }
                        )
                    return values, reason

                original_rerank = AdvancedRetrievalService._rerank

                async def traced_rerank(
                    instance: AdvancedRetrievalService,
                    plan: RetrievalPlanV2,
                    candidates: tuple[AdvancedRetrievalCandidate, ...],
                ) -> tuple[AdvancedRetrievalCandidate, ...]:
                    timing = trace_started("reranking")
                    try:
                        values = await original_rerank(instance, plan, candidates)
                    except BaseException as error:
                        trace_completed(
                            "reranking",
                            timing,
                            outcome=(
                                "cancelled"
                                if isinstance(error, asyncio.CancelledError)
                                else "failed"
                            ),
                            inputs=candidates,
                            error=error,
                        )
                        raise
                    trace_completed(
                        "reranking",
                        timing,
                        outcome="completed",
                        inputs=candidates,
                        outputs=values,
                    )
                    return values

                stack.enter_context(
                    patch.object(advanced_retrieval_module, "_deduplicate", traced_deduplicate)
                )
                stack.enter_context(
                    patch.object(advanced_retrieval_module, "_rank_fuse", traced_rank_fuse)
                )
                stack.enter_context(
                    patch.object(
                        advanced_retrieval_module, "_diversify_occurrences", traced_diversify
                    )
                )
                stack.enter_context(
                    patch.object(advanced_retrieval_module, "_apply_output_bounds", traced_bounds)
                )
                stack.enter_context(
                    patch.object(AdvancedRetrievalService, "_rerank", traced_rerank)
                )

                for case in visual_cases:
                    if case_id_filter and case["case_id"] != case_id_filter:
                        continue
                    if single_notebook_only and len(case["selected_notebooks"]) != 1:
                        continue
                    label = str(case["case_id"])
                    selected = tuple(UUID(value) for value in case["selected_notebooks"])
                    representation = (
                        EvidenceRepresentation.VISION_ANALYSIS
                        if case["representation"] == "vision_text"
                        else EvidenceRepresentation.VISUAL_VECTOR
                    )
                    visual_trace_state["case_id"] = label
                    visual_trace_state["notebook_id"] = (
                        str(selected[0]) if len(selected) == 1 else "multi_notebook"
                    )
                    visual_trace_state["targets"] = {
                        (
                            str(target["notebook_id"]),
                            str(target["source_id"]),
                            str(target["document_id"]),
                            str(target["version_id"]),
                            str(target["evidence_id"]),
                        )
                        for target in case["targets"]
                    }
                    request = ScopeRequestReview(
                        query=case["query"],
                        mode="ranked",
                        limit=10,
                        scope=SelectedNotebooks(kind="selected", notebook_ids=selected),
                        representations=(
                            (
                                EvidenceRepresentation.CANONICAL_TEXT,
                                EvidenceRepresentation.MULTILINGUAL_TEXT,
                                *_REPRESENTATIONS,
                            )
                            if unified_visual
                            else (representation,)
                        ),
                    )
                    visual_progress_stream.write(
                        json.dumps({"case_id": label, "event": "started"}) + "\n"
                    )
                    visual_progress_stream.flush()
                    os.fsync(visual_progress_stream.fileno())
                    try:
                        visual_ranked = await traced_service.execute_ranked(request, principal)
                    except BaseException as error:
                        append_progress(
                            {"case_id": label, "event": "failed", "error": type(error).__name__}
                        )
                        raise
                    visual_target_keys = {
                        (
                            target["notebook_id"],
                            target["source_id"],
                            target["document_id"],
                            target["version_id"],
                            target["evidence_id"],
                        )
                        for target in case["targets"]
                    }
                    identities = [
                        (
                            str(item["notebook_id"]),
                            str(item["source_id"]),
                            str(item["document_id"]),
                            str(item["version_id"]),
                            str(item.get("derivation_id")),
                        )
                        for item in visual_ranked.items
                    ]
                    ranks = [
                        index + 1
                        for index, identity in enumerate(identities)
                        if identity in visual_target_keys
                    ]
                    child_ranked: list[dict[str, object]] = []
                    provider_statuses: list[dict[str, object]] = []
                    for partition in visual_ranked.notebooks:
                        provider_statuses.extend(
                            {
                                "notebook_id": str(partition.notebook_id),
                                "representation": source.representation.value,
                                "status": source.status,
                                "reason_code": source.reason_code,
                            }
                            for source in partition.sources
                        )
                        if partition.response is None or not isinstance(
                            partition.response.response, EvidenceSearchResponse
                        ):
                            continue
                        for rank, item in enumerate(partition.response.response.items, 1):
                            child_ranked.append(
                                {
                                    "notebook_id": str(partition.notebook_id),
                                    "rank": rank,
                                    **{
                                        key: item.get(key)
                                        for key in (
                                            "representation",
                                            "source_id",
                                            "document_id",
                                            "version_id",
                                            "evidence_id",
                                            "chunk_id",
                                            "occurrence_id",
                                            "derivation_id",
                                            "asset_id",
                                        )
                                    },
                                }
                            )
                    row = {
                        "case_id": label,
                        "representation": case["representation"],
                        "retrieval_mode": (
                            "unified_all_five" if unified_visual else "typed_provider_only"
                        ),
                        "selected_notebooks": case["selected_notebooks"],
                        "target_count": len(visual_target_keys),
                        "target_ranks": ranks,
                        "returned_count": len(identities),
                        "ranked_identities": identities,
                        "ranked_representations": [
                            {
                                "notebook_id": str(item.get("notebook_id")),
                                "representation": str(item.get("representation")),
                                "source_id": str(item.get("source_id")),
                                "document_id": str(item.get("document_id")),
                                "version_id": str(item.get("version_id")),
                                "evidence_id": str(item.get("evidence_id")),
                                "occurrence_id": (
                                    None
                                    if item.get("occurrence_id") is None
                                    else str(item.get("occurrence_id"))
                                ),
                                "derivation_id": (
                                    None
                                    if item.get("derivation_id") is None
                                    else str(item.get("derivation_id"))
                                ),
                                "asset_id": (
                                    None
                                    if item.get("asset_id") is None
                                    else str(item.get("asset_id"))
                                ),
                            }
                            for item in visual_ranked.items
                        ],
                        "child_ranked": child_ranked,
                        "provider_statuses": provider_statuses,
                        "completeness": visual_ranked.completeness,
                        "omissions": visual_ranked.omissions,
                    }
                    rows.append(row)
                    append_progress({"case_id": label, "event": "completed", "result": row})
            if case_id_filter and not rows:
                raise ValueError(f"unknown frozen visual case: {case_id_filter}")
            if single_notebook_only and len(rows) != 10:
                raise ValueError(
                    "single-notebook visual slice must contain exactly ten frozen cases"
                )
            return {
                "qrel_digest": qrel_digest,
                "progress": str(progress_path),
                "cases": rows,
                "evaluated_count": len(rows),
            }
        if frozen_qrels:
            if not with_bge:
                raise ValueError("frozen QREL comparison requires Full V2 composition")
            qrel_path = logs / BOUND_NAME
            qrel_digest = hashlib.sha256(qrel_path.read_bytes()).hexdigest()
            if qrel_digest != "e910c921900b2f65daf58d5a4a92bce32f980194930f1e0a511f7500100c835d":
                raise ValueError("frozen QREL digest changed")
            manifest = load_qrels(
                qrel_path,
                COPY / "mnemo.db",
                set(expected),
                {row["sha256"] for row in records.values()},
            )
            cases: list[dict[str, object]] = []
            source_traces: dict[str, dict[str, object]] = {}
            source_trace_path: Path | None = None
            source_trace_stream = None
            current_case = ""
            target_keys: set[tuple[str, ...]] = set()
            if trace_sources:
                source_trace_path = COPY / f"source-trace-{uuid4().hex}.jsonl"
                source_trace_stream = stack.enter_context(
                    source_trace_path.open("x", encoding="utf-8")
                )
                for source in harness.advanced_retrieval._sources.values():
                    original_retrieve = source.retrieve
                    representation = source.representation

                    def record_event(
                        plan: RetrievalPlanV2,
                        named: EvidenceRepresentation,
                        page: AdvancedSourcePage | None,
                        error: BaseException | None,
                    ) -> None:
                        assert source_trace_stream is not None
                        observation: dict[str, object] = {
                            "case_id": current_case,
                            "notebook_id": str(plan.scope.notebook_id),
                            "representation": named.value,
                            "outcome": (
                                "cancelled"
                                if isinstance(error, asyncio.CancelledError)
                                else "failed"
                                if error is not None
                                else "completed"
                            ),
                        }
                        if error is not None:
                            observation["exception_class"] = type(error).__name__
                        else:
                            assert page is not None
                            matches: list[int] = []
                            for rank, candidate in enumerate(page.candidates, 1):
                                evidence = candidate.evidence_id or (
                                    candidate.chunk.id if candidate.chunk is not None else None
                                )
                                if evidence is None and candidate.derivation_id is not None:
                                    evidence = str(candidate.derivation_id)
                                identity = (
                                    str(candidate.notebook_id),
                                    str(candidate.source_id),
                                    str(candidate.document_id),
                                    str(candidate.version_id),
                                    str(evidence),
                                )
                                if identity in target_keys:
                                    matches.append(rank)
                            observation.update(
                                {"returned": len(page.candidates), "target_ranks": matches}
                            )
                            source_traces.setdefault(current_case, {})[
                                f"{plan.scope.notebook_id}:{named.value}"
                            ] = {
                                "returned": len(page.candidates),
                                "target_ranks": matches,
                            }
                        source_trace_stream.write(json.dumps(observation, sort_keys=True) + "\n")
                        source_trace_stream.flush()
                        os.fsync(source_trace_stream.fileno())

                    async def observed_retrieve(
                        plan: RetrievalPlanV2,
                        *,
                        offset: int,
                        limit: int,
                        method: Callable[..., Awaitable[AdvancedSourcePage]] = original_retrieve,
                        named: EvidenceRepresentation = representation,
                    ) -> AdvancedSourcePage:
                        try:
                            page = await method(plan, offset=offset, limit=limit)
                        except BaseException as error:
                            record_event(plan, named, None, error)
                            raise
                        record_event(plan, named, page, None)
                        return page

                    if isinstance(source, PrincipalAwareAdvancedRetrievalSourceV2):
                        original_authorized = source.retrieve_authorized

                        async def observed_authorized(
                            *,
                            principal: PrincipalContextV1,
                            plan: RetrievalPlanV2,
                            offset: int,
                            limit: int,
                            method: Callable[
                                ..., Awaitable[AdvancedSourcePage]
                            ] = original_authorized,
                            named: EvidenceRepresentation = representation,
                        ) -> AdvancedSourcePage:
                            try:
                                page = await method(
                                    principal=principal, plan=plan, offset=offset, limit=limit
                                )
                            except BaseException as error:
                                record_event(plan, named, None, error)
                                raise
                            record_event(plan, named, page, None)
                            return page

                        stack.enter_context(
                            patch.object(source, "retrieve_authorized", observed_authorized)
                        )
                    else:
                        stack.enter_context(patch.object(source, "retrieve", observed_retrieve))
            progress = EvaluationProgress(COPY, COPY.name)
            stack.callback(progress.close)
            for case in manifest["cases"]:
                current_case = str(case["case_id"])
                if case_id_filter is not None and current_case != case_id_filter:
                    continue
                target_keys = {_target_key(value) for value in case["targets"]}
                selected = tuple(UUID(value) for value in case["selected_notebooks"])
                request = ScopeRequestReview(
                    query=case["query"],
                    mode="ranked",
                    limit=10,
                    scope=SelectedNotebooks(kind="selected", notebook_ids=selected),
                    representations=(
                        EvidenceRepresentation.CANONICAL_TEXT,
                        EvidenceRepresentation.MULTILINGUAL_TEXT,
                    ),
                )
                case_id = str(case["case_id"])
                result = await progress.execute(
                    service,
                    request,
                    principal,
                    case_id=case_id,
                    mode="canonical_sparse_plus_bge_m3_full_v2",
                    selected=selected,
                )
                ranked = [_ranked_identity(item) for item in result.items]
                cases.append(
                    {
                        "case_id": case_id,
                        "ranked_identity": [
                            {
                                key: str(item[key])
                                for key in (
                                    "notebook_id",
                                    "source_id",
                                    "document_id",
                                    "version_id",
                                    "evidence_id",
                                    "representation",
                                )
                            }
                            for item in ranked
                        ],
                        "metrics": metrics(
                            ranked, {_target_key(value) for value in case["targets"]}, 10
                        ),
                        "completeness": result.completeness,
                        "omissions": result.omissions,
                        "provider_statuses": [
                            {
                                "notebook_id": str(partition.notebook_id),
                                "representation": source.representation,
                                "status": source.status,
                                "reason": source.reason_code,
                            }
                            for partition in result.notebooks
                            if partition.response is not None
                            for source in partition.response.envelope.sources
                        ],
                        "child_target_ranks": {
                            str(partition.notebook_id): [
                                rank
                                for rank, item in enumerate(partition.response.response.items, 1)
                                if _target_key(_ranked_identity(item)) in target_keys
                            ]
                            for partition in result.notebooks
                            if partition.response is not None
                            and isinstance(partition.response.response, EvidenceSearchResponse)
                        },
                        **(
                            {"source_trace": source_traces.get(case_id, {})}
                            if trace_sources
                            else {}
                        ),
                    }
                )
            if not cases:
                raise ValueError("selected frozen QREL case was not found")
            output = COPY / f"frozen-qrel-evaluation-{uuid4().hex}.json"
            with output.open("x", encoding="utf-8") as stream:
                json.dump({"qrels_sha256": qrel_digest, "cases": cases}, stream, sort_keys=True)
            return {
                "frozen_qrels": {
                    "artifact": str(output),
                    "progress": str(progress.path),
                    "source_trace": None if source_trace_path is None else str(source_trace_path),
                    "case_count": len(cases),
                }
            }
        admission = await authorization.inspect_active_sources(selection, _REPRESENTATIONS)
        trace_stream = None
        current_probe = ""
        if trace_sources:
            trace_path = COPY / f"multimodal-source-trace-{uuid4().hex}.jsonl"
            trace_stream = stack.enter_context(trace_path.open("x", encoding="utf-8"))
            results["source_trace_artifact"] = str(trace_path)
            for source in harness.advanced_retrieval._sources.values():
                representation = source.representation

                def emit_page(
                    plan: RetrievalPlanV2,
                    named: EvidenceRepresentation,
                    page: AdvancedSourcePage | None,
                    error: BaseException | None,
                ) -> None:
                    assert trace_stream is not None
                    observation: dict[str, object] = {
                        "probe": current_probe,
                        "notebook_id": str(plan.scope.notebook_id),
                        "representation": named.value,
                        "outcome": (
                            "cancelled"
                            if isinstance(error, asyncio.CancelledError)
                            else "failed"
                            if error is not None
                            else "completed"
                        ),
                    }
                    if error is not None:
                        observation["exception_class"] = type(error).__name__
                    else:
                        assert page is not None
                        observation["returned"] = len(page.candidates)
                        observation["identities"] = [
                            {
                                "notebook_id": str(candidate.notebook_id),
                                "source_id": str(candidate.source_id),
                                "document_id": str(candidate.document_id),
                                "version_id": str(candidate.version_id),
                                "evidence_id": str(
                                    candidate.evidence_id
                                    or (
                                        candidate.chunk.id
                                        if candidate.chunk is not None
                                        else candidate.derivation_id
                                    )
                                ),
                            }
                            for candidate in page.candidates
                        ]
                    trace_stream.write(json.dumps(observation, sort_keys=True) + "\n")
                    trace_stream.flush()
                    os.fsync(trace_stream.fileno())

                if isinstance(source, PrincipalAwareAdvancedRetrievalSourceV2):
                    original_authorized = source.retrieve_authorized

                    async def observed_authorized(
                        *,
                        principal: PrincipalContextV1,
                        plan: RetrievalPlanV2,
                        offset: int,
                        limit: int,
                        method: Callable[..., Awaitable[AdvancedSourcePage]] = original_authorized,
                        named: EvidenceRepresentation = representation,
                    ) -> AdvancedSourcePage:
                        try:
                            page = await method(
                                principal=principal, plan=plan, offset=offset, limit=limit
                            )
                        except BaseException as error:
                            emit_page(plan, named, None, error)
                            raise
                        emit_page(plan, named, page, None)
                        return page

                    stack.enter_context(
                        patch.object(source, "retrieve_authorized", observed_authorized)
                    )
                else:
                    original_retrieve = source.retrieve

                    async def observed_retrieve(
                        plan: RetrievalPlanV2,
                        *,
                        offset: int,
                        limit: int,
                        method: Callable[..., Awaitable[AdvancedSourcePage]] = original_retrieve,
                        named: EvidenceRepresentation = representation,
                    ) -> AdvancedSourcePage:
                        try:
                            page = await method(plan, offset=offset, limit=limit)
                        except BaseException as error:
                            emit_page(plan, named, None, error)
                            raise
                        emit_page(plan, named, page, None)
                        return page

                    stack.enter_context(patch.object(source, "retrieve", observed_retrieve))
        for representation in _REPRESENTATIONS:
            current_probe = f"typed_{representation.value}"
            query = (
                "DECSISION"
                if representation is EvidenceRepresentation.OCR_TEXT
                else "agricultural production chart"
            )
            request = ScopeRequestReview(
                query=query,
                mode="ranked",
                limit=10,
                scope=SelectedNotebooks(kind="selected", notebook_ids=expected),
                representations=(representation,),
            )
            result = await service.execute_ranked(request, principal)
            for item in result.items:
                if not (item.get("chunk_id") or item.get("derivation_id")):
                    raise ValueError(
                        f"{representation.value} lacks evidence ID: keys={sorted(item)} "
                        f"locator_type={type(item.get('locator')).__name__}"
                    )
            results[representation.value] = {
                "completeness": result.completeness,
                "omissions": result.omissions,
                "identities": [
                    {
                        key: str(
                            item.get("chunk_id") or item.get("derivation_id")
                            if key == "evidence_id"
                            else item[key]
                        )
                        for key in (
                            "notebook_id",
                            "source_id",
                            "document_id",
                            "version_id",
                            "evidence_id",
                            "representation",
                        )
                    }
                    for item in result.items
                ],
            }
        if with_bge:
            current_probe = "combined"
            request = ScopeRequestReview(
                query="agricultural production chart",
                mode="ranked",
                limit=10,
                scope=SelectedNotebooks(kind="selected", notebook_ids=expected),
                representations=(
                    EvidenceRepresentation.CANONICAL_TEXT,
                    EvidenceRepresentation.MULTILINGUAL_TEXT,
                    *_REPRESENTATIONS,
                ),
            )
            try:
                combined = await service.execute_ranked(request, principal)
            except OperationTimeoutError:
                results["combined"] = {"outcome": "timed_out_under_existing_deadline"}
            else:
                results["combined"] = {
                    "outcome": "completed",
                    "completeness": combined.completeness,
                    "omissions": combined.omissions,
                    "representations": [str(item["representation"]) for item in combined.items],
                    "identities": [
                        {
                            key: str(item[key])
                            for key in ("notebook_id", "source_id", "document_id", "version_id")
                        }
                        for item in combined.items
                    ],
                }
            if trace_children:
                children: dict[str, object] = {}
                for notebook_id in (expected[0], expected[2]):
                    current_probe = f"combined_child_{notebook_id}"
                    child_request = request.model_copy(
                        update={
                            "scope": SelectedNotebooks(kind="selected", notebook_ids=(notebook_id,))
                        }
                    )
                    child = await service.execute_ranked(child_request, principal)
                    children[str(notebook_id)] = [
                        {
                            "representation": str(item["representation"]),
                            "source_id": str(item["source_id"]),
                            "evidence_id": str(item.get("chunk_id") or item.get("derivation_id")),
                        }
                        for item in child.items
                    ]
                results["combined_children"] = children
            try:
                await service.execute_ranked(request, PrincipalContextV1(uuid4(), True))
            except NotFoundError:
                results["ungranted_principal"] = "denied"
            else:
                raise PermissionError("ungranted principal received scoped results")
        return {
            "scope": [str(value) for value in expected],
            "admission": [
                {
                    "notebook_id": str(item.notebook_id),
                    "representation": item.representation.value,
                    "status": item.status,
                    "reason": item.reason_code,
                }
                for item in admission
            ],
            "results": results,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-bge", action="store_true")
    parser.add_argument("--frozen-qrels", action="store_true")
    parser.add_argument("--trace-children", action="store_true")
    parser.add_argument("--trace-sources", action="store_true")
    parser.add_argument("--case-id")
    parser.add_argument("--visual-qrels", action="store_true")
    parser.add_argument("--unified-visual", action="store_true")
    parser.add_argument("--single-notebook-only", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(
        probe(
            with_bge=args.with_bge,
            frozen_qrels=args.frozen_qrels,
            trace_children=args.trace_children,
            trace_sources=args.trace_sources,
            case_id_filter=args.case_id,
            visual_qrels=args.visual_qrels,
            unified_visual=args.unified_visual,
            single_notebook_only=args.single_notebook_only,
        )
    )
    if not args.frozen_qrels:
        artifact = COPY / f"multimodal-probe-{uuid4().hex}.json"
        with artifact.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, sort_keys=True)
        result = {**result, "artifact": str(artifact)}
    print(
        json.dumps(
            result,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
