"""Bounded, in-memory observation for the single-request offline DERE worker ONLY.

Never install these process-local probes in a server. No request flags, cursor
changes, extra retrieval calls, logging, model scoring, or disk writes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

from mnemo.retrieval import advanced
from mnemo.retrieval import full_multilingual_v2 as full


def identity(source: Any) -> dict[str, str]:
    return {
        key: str(getattr(source, key))
        for key in ("notebook_id", "source_id", "document_id", "version_id", "evidence_id")
    }


def advanced_row(candidate: Any) -> dict[str, Any]:
    evidence_id = candidate.evidence_id or (candidate.chunk.id if candidate.chunk else None)
    if not evidence_id:
        raise ValueError("unresolvable advanced evidence identity")
    return {
        **identity(candidate),
        "evidence_id": evidence_id,
        "candidate_id": str(candidate.candidate_id),
        "representation": candidate.representation.value,
        "score": candidate.fused_score,
        "occurrence_id": str(candidate.occurrence_id) if candidate.occurrence_id else None,
        "derivation_id": str(candidate.derivation_id) if candidate.derivation_id else None,
        "paths": [(v.path, v.source_rank, v.source_score) for v in candidate.paths],
    }


class RankTrace:
    """Hold bounded stage outputs, serializing allowlisted fields only after success."""

    def __init__(self) -> None:
        self.raw: dict[str, Any] = {}

    @contextmanager
    def observe(self, application: Any) -> Iterator[None]:
        with ExitStack() as stack:

            def wrap(obj: Any, name: str, stage: str, asynchronous: bool = False) -> None:
                original = getattr(obj, name)

                def sync(*args: Any, **kwargs: Any) -> Any:
                    value = original(*args, **kwargs)
                    self.raw[stage] = (args, kwargs, value)
                    return value

                async def run(*args: Any, **kwargs: Any) -> Any:
                    value = await original(*args, **kwargs)
                    self.raw[stage] = (args, kwargs, value)
                    return value

                stack.enter_context(patch.object(obj, name, run if asynchronous else sync))

            wrap(application._dense, "retrieve", "dense", True)
            wrap(application._sparse, "retrieve_authorized_multilingual_sparse", "sparse", True)
            wrap(full, "_merge_fused", "rrf")
            wrap(application._reranker, "score_candidates", "rerank", True)
            wrap(application, "retrieve", "v2", True)
            wrap(advanced, "_deduplicate", "dedup")
            wrap(advanced, "_rank_fuse", "combined")
            wrap(advanced, "_apply_output_bounds", "bounds")
            try:
                yield
            except BaseException:
                self.raw.clear()
                raise

    def snapshot(self, result: Any) -> dict[str, Any]:
        raw = self.raw
        dense = [
            {
                **identity(m.embedding.source),
                "rank": m.rank,
                "score": m.score,
                "digest": m.embedding.source.identity_digest,
            }
            for m in raw["dense"][2]
        ]
        sparse = [
            {
                **identity(m.source),
                "rank": m.rank,
                "score": m.score,
                "digest": m.source.identity_digest,
            }
            for m in raw["sparse"][2]
        ]
        # The dictionary was mutated by the REAL merge; reconstruct its deterministic
        # pre-slice order, retaining each independent contribution, not cosine + BM25.
        contributions: dict[str, dict[str, float]] = {}
        for path, rows in (("dense", dense), ("sparse", sparse)):
            for row in rows:
                contributions.setdefault(row["digest"], {})[path] = 1 / (
                    full.RRF_K_V2 + row["rank"]
                )
        fused = raw.get("rrf", (({},),))[0][0]
        rrf = [
            {
                **identity(source),
                "rank": i,
                "score": score,
                "contributions": contributions[source.identity_digest],
            }
            for i, (source, score, _) in enumerate(
                sorted(fused.values(), key=lambda v: (-v[1], v[0].identity_digest)), 1
            )
        ]
        plan = raw["v2"][1]["plan"]
        scored = raw.get("rerank", ((), {"candidates": ()}, ()))
        scores = {s.candidate_id: s.score for s in scored[2]}
        rerank = [
            {
                **identity(c.source_reference),
                "candidate_id": str(c.candidate_id),
                "input_position": c.input_ordinal + 1,
                "score": scores.get(c.candidate_id),
            }
            for c in scored[1]["candidates"]
        ]
        v2 = [
            {
                **identity(v.candidate.source_reference),
                "rank": v.final_rank,
                "fused_score": v.fused_score,
                "reranker_score": v.reranker_score,
            }
            for v in raw["v2"][2].candidates
        ]
        selected, reason = raw["bounds"][2]

        def output_row(item: Any) -> dict[str, Any]:
            return {
                **{
                    key: str(item[key])
                    for key in (
                        "candidate_id",
                        "notebook_id",
                        "source_id",
                        "document_id",
                        "version_id",
                        "representation",
                    )
                },
                "evidence_id": item.get("chunk_id")
                or item.get("evidence_id")
                or item.get("locator", {}).get("evidence_id"),
            }

        return {
            "score_semantics": {
                "dense": "L2 cosine",
                "sparse": "negative SQLite bm25",
                "rrf": "reciprocal ranks, k=60",
                "reranker": "pass-through",
            },
            "budgets": plan.budgets.model_dump(mode="json"),
            "dense": dense,
            "sparse": sparse,
            "full_v2_rrf_before_limits": rrf,
            "rerank_before_result_limit": rerank,
            "full_v2_selected": v2,
            "advanced_before_dedup": [advanced_row(c) for c in raw["dedup"][0][0]],
            "advanced_after_dedup": [advanced_row(c) for c in raw["dedup"][2]],
            "combined_before_fusion_limit": [advanced_row(c) for c in raw["combined"][2]],
            "advanced_before_output_bounds": [advanced_row(c) for c in raw["bounds"][0][1]],
            "advanced_selected": [advanced_row(c) for c in selected],
            "advanced_cut_reason": reason,
            "partitions": [
                {
                    "notebook_id": str(n.notebook_id),
                    "status": n.status,
                    "items": [output_row(i) for i in n.response.response.items]
                    if n.response
                    else [],
                }
                for n in result.notebooks
            ],
            "final": [output_row(i) for i in result.items],
            "omissions": result.omissions,
        }
