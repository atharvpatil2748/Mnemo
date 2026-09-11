"""Bounded, provenance-preserving Phase 8.5.6 retrieval orchestration."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

from mnemo.cursors import CursorCodecV2, CursorInvalidError, CursorSigningKeyV2
from mnemo.interfaces.advanced_retrieval import (
    AdvancedCandidateRerankerV1,
    AdvancedRetrievalSourceV1,
    AdvancedSourcePage,
    PrincipalAwareAdvancedRetrievalSourceV2,
)
from mnemo.interfaces.errors import ConflictError, ContractValidationError, IntegrityError
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    ExpansionPolicy,
    RepresentationReportV2,
    RepresentationSearchStatus,
    RetrievalCompleteness,
    RetrievalDiagnosticsV2,
    RetrievalPlanV2,
    RetrievalResultSetV1,
)

_CURSOR_DOMAIN = "mnemo-advanced-retrieval-cursor/v2"
_RRF_K = 60
_LOGGER = logging.getLogger(__name__)


class RetrievalCursorCodec:
    """Issue and verify opaque notebook-scoped, expiring continuation cursors."""

    def __init__(
        self,
        secret: bytes,
        *,
        ttl: timedelta = timedelta(minutes=15),
        key_id: str = "advanced-v2",
        verification_keys: tuple[tuple[str, bytes], ...] = (),
    ) -> None:
        if len(secret) < 32:
            raise ValueError("cursor signing secret must contain at least 32 bytes")
        if ttl <= timedelta(0) or ttl > timedelta(days=1):
            raise ValueError("cursor ttl must be positive and at most one day")
        self._codec = CursorCodecV2(
            CursorSigningKeyV2(key_id=key_id, secret=secret),
            verification_keys=tuple(
                CursorSigningKeyV2(key_id=item_key_id, secret=item_secret)
                for item_key_id, item_secret in verification_keys
            ),
            ttl=ttl,
        )

    def encode(
        self,
        *,
        plan: RetrievalPlanV2,
        representation_index: int,
        offset: int,
        snapshots: dict[str, str],
        now: datetime,
    ) -> str:
        if representation_index < 0 or representation_index >= len(plan.representations):
            raise ValueError("cursor representation index is outside the plan")
        if offset < 0:
            raise ValueError("cursor offset must be non-negative")
        if any(len(value) != 64 for value in snapshots.values()):
            raise ValueError("cursor snapshots must be SHA-256 identities")
        return self._codec.encode(
            domain=_CURSOR_DOMAIN,
            snapshot_identity=_combined_snapshot(snapshots),
            binding={
                "fingerprint": plan.fingerprint,
                "notebook_id": str(plan.scope.notebook_id),
            },
            position={
                "representation_index": representation_index,
                "offset": offset,
                "snapshots": snapshots,
            },
            limits=plan.budgets.model_dump(mode="json"),
            now=now,
        )

    def decode(self, token: str, *, plan: RetrievalPlanV2, now: datetime) -> dict[str, object]:
        try:
            state = self._codec.decode(
                token,
                expected_domain=_CURSOR_DOMAIN,
                expected_binding={
                    "fingerprint": plan.fingerprint,
                    "notebook_id": str(plan.scope.notebook_id),
                },
                expected_limits=plan.budgets.model_dump(mode="json"),
                now=now,
            )
        except CursorInvalidError as error:
            raise IntegrityError("advanced retrieval cursor is invalid") from error
        representation_index = state.position.get("representation_index")
        offset = state.position.get("offset")
        snapshots = state.position.get("snapshots")
        if (
            isinstance(representation_index, bool)
            or not isinstance(representation_index, int)
            or representation_index < 0
            or isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
            or not isinstance(snapshots, dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in snapshots.items())
        ):
            raise IntegrityError("advanced retrieval cursor payload is invalid")
        typed_snapshots = cast(dict[str, str], snapshots)
        if _combined_snapshot(typed_snapshots) != state.snapshot_identity:
            raise IntegrityError("advanced retrieval cursor snapshot state is invalid")
        return {
            "representation_index": representation_index,
            "offset": offset,
            "snapshots": typed_snapshots,
            "expires_at": int(state.expires_at.timestamp()),
        }

    def encode_partitioned(
        self,
        *,
        plan: RetrievalPlanV2,
        document_ids: tuple[str, ...],
        cursors: dict[str, str],
        snapshot_identity: str,
        now: datetime,
    ) -> str:
        """Encode one aggregate continuation using the shared CursorCodecV2 format."""
        return self._codec.encode(
            domain="mnemo-partitioned-retrieval/v1",
            snapshot_identity=snapshot_identity,
            binding={
                "fingerprint": plan.fingerprint,
                "notebook_id": str(plan.scope.notebook_id),
                "document_ids": list(document_ids),
            },
            position={"partition_cursors": cursors},
            limits=plan.budgets.model_dump(mode="json"),
            now=now,
        )

    def decode_partitioned(
        self, token: str, *, plan: RetrievalPlanV2, document_ids: tuple[str, ...], now: datetime
    ) -> dict[str, object]:
        """Verify an aggregate continuation and return opaque partition cursors."""
        try:
            state = self._codec.decode(
                token,
                expected_domain="mnemo-partitioned-retrieval/v1",
                expected_binding={
                    "fingerprint": plan.fingerprint,
                    "notebook_id": str(plan.scope.notebook_id),
                    "document_ids": list(document_ids),
                },
                expected_limits=plan.budgets.model_dump(mode="json"),
                now=now,
            )
        except (CursorInvalidError, ConflictError) as error:
            raise IntegrityError("partitioned retrieval cursor is invalid") from error
        cursors = state.position.get("partition_cursors")
        if not isinstance(cursors, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in cursors.items()
        ):
            raise IntegrityError("partitioned retrieval cursor payload is invalid")
        return {
            "cursors": cast(dict[str, str], cursors),
            "snapshot_identity": state.snapshot_identity,
        }


class AdvancedRetrievalService:
    """Orchestrate ranked or deterministic exhaustive retrieval without widening V1."""

    @property
    def profile_id(self) -> str:
        """Return the stable public identity required by the V1 service protocol."""
        return "advanced-retrieval-v1"

    def __init__(
        self,
        *,
        sources: tuple[AdvancedRetrievalSourceV1, ...],
        cursor_codec: RetrievalCursorCodec,
        reranker: AdvancedCandidateRerankerV1 | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        by_representation: dict[EvidenceRepresentation, AdvancedRetrievalSourceV1] = {}
        for source in sources:
            if not isinstance(source, AdvancedRetrievalSourceV1):
                raise TypeError("sources must implement AdvancedRetrievalSourceV1")
            if source.representation in by_representation:
                raise ValueError("only one source may own a representation")
            by_representation[source.representation] = source
        if reranker is not None and not isinstance(reranker, AdvancedCandidateRerankerV1):
            raise TypeError("reranker must implement AdvancedCandidateRerankerV1")
        self._sources = by_representation
        self._codec = cursor_codec
        self._reranker = reranker
        self._clock = clock

    async def execute(
        self, plan: RetrievalPlanV2, *, cursor: str | None = None
    ) -> RetrievalResultSetV1:
        if not isinstance(plan, RetrievalPlanV2):
            raise TypeError("plan must be RetrievalPlanV2")
        if cursor is not None and plan.mode is not AdvancedRetrievalMode.EXHAUSTIVE:
            raise ValueError("continuation cursors are only valid for exhaustive retrieval")
        started = time.perf_counter()
        if plan.mode is AdvancedRetrievalMode.RANKED:
            return await self._ranked(plan, started)
        return await self._exhaustive(plan, cursor, started)

    async def execute_authorized(
        self,
        *,
        principal: PrincipalContextV1,
        plan: RetrievalPlanV2,
        cursor: str | None = None,
    ) -> RetrievalResultSetV1:
        """Execute while preserving the server-owned principal to V2 sources."""
        if not principal.authenticated:
            raise PermissionError("server-derived authenticated principal is required")
        if cursor is not None and plan.mode is not AdvancedRetrievalMode.EXHAUSTIVE:
            raise ValueError("continuation cursors are only valid for exhaustive retrieval")
        started = time.perf_counter()
        if plan.mode is AdvancedRetrievalMode.RANKED:
            return await self._ranked(plan, started, principal=principal)
        return await self._exhaustive(plan, cursor, started, principal=principal)

    async def _ranked(
        self,
        plan: RetrievalPlanV2,
        started: float,
        *,
        principal: PrincipalContextV1 | None = None,
    ) -> RetrievalResultSetV1:
        pages: list[AdvancedSourcePage] = []
        reports: list[RepresentationReportV2] = []
        per_source_limit = max(1, plan.budgets.recall_limit // len(plan.representations))
        for representation in plan.representations:
            source = self._sources.get(representation)
            if source is None:
                reports.append(_unavailable_report(representation))
                continue
            try:
                page = await self._retrieve_source(
                    source, plan, offset=0, limit=per_source_limit, principal=principal
                )
                _validate_page(page, plan, source, per_source_limit)
            except Exception as error:
                if isinstance(error, (IntegrityError, ConflictError, TypeError, ValueError)):
                    raise
                _LOGGER.exception(
                    "advanced retrieval source failed: representation=%s",
                    representation.value,
                )
                reports.append(_failed_report(representation, type(error).__name__))
                continue
            pages.append(page)
            reports.append(_searched_report(page))

        recalled = tuple(candidate for page in pages for candidate in page.candidates)
        _validate_authorization(recalled, plan)
        expanded = await self._expand_ranked(plan, recalled)
        merged = _deduplicate((*recalled, *expanded))
        fused = _rank_fuse(merged)[: plan.budgets.fusion_limit]
        rerank_input = tuple(fused[: plan.budgets.rerank_limit])
        reranked = await self._rerank(plan, rerank_input)
        selected, truncated_reason = _apply_output_bounds(plan, reranked)
        unavailable = any(
            report.status is not RepresentationSearchStatus.SEARCHED for report in reports
        )
        all_failed = bool(reports) and all(
            report.status is RepresentationSearchStatus.FAILED for report in reports
        )
        completeness = (
            RetrievalCompleteness.UNKNOWN
            if all_failed
            else RetrievalCompleteness.EMPTY
            if not selected and not unavailable
            else RetrievalCompleteness.PARTIAL
            if unavailable
            else RetrievalCompleteness.UNKNOWN
        )
        snapshots = {page.representation.value: page.snapshot_identity for page in pages}
        return _result(
            plan=plan,
            snapshot_identity=_combined_snapshot(snapshots),
            completeness=completeness,
            selected=selected,
            examined=sum(page.examined for page in pages),
            cursor=None,
            recalled=len(recalled),
            expanded=len(expanded),
            deduplicated=len(recalled) + len(expanded) - len(merged),
            fused=len(fused),
            reranked=len(reranked),
            reports=tuple(reports),
            truncation_reason=truncated_reason,
            started=started,
        )

    async def _exhaustive(
        self,
        plan: RetrievalPlanV2,
        cursor: str | None,
        started: float,
        *,
        principal: PrincipalContextV1 | None = None,
    ) -> RetrievalResultSetV1:
        now = self._clock()
        index = 0
        offset = 0
        cursor_snapshots: dict[str, str] = {}
        if cursor is not None:
            state = self._codec.decode(cursor, plan=plan, now=now)
            index = cast(int, state["representation_index"])
            offset = cast(int, state["offset"])
            cursor_snapshots = cast(dict[str, str], state["snapshots"])
            await self._validate_prior_snapshots(plan, index, cursor_snapshots, principal=principal)
        reports: list[RepresentationReportV2] = [
            _unavailable_report(representation)
            for representation in plan.representations
            if representation not in self._sources
        ]
        selected: list[AdvancedRetrievalCandidate] = []
        examined = 0
        snapshots = dict(cursor_snapshots)
        next_index: int | None = None
        next_offset = 0
        unavailable = bool(reports)

        for representation_index in range(index, len(plan.representations)):
            representation = plan.representations[representation_index]
            source = self._sources.get(representation)
            if source is None:
                offset = 0
                continue
            remaining = plan.budgets.result_limit - len(selected)
            if remaining <= 0:
                next_index, next_offset = representation_index, offset
                break
            try:
                page = await self._retrieve_source(
                    source, plan, offset=offset, limit=remaining, principal=principal
                )
                _validate_page(page, plan, source, remaining)
            except Exception as error:
                if isinstance(error, (IntegrityError, ConflictError, TypeError, ValueError)):
                    raise
                unavailable = True
                reports.append(_failed_report(representation, type(error).__name__))
                offset = 0
                continue
            previous_snapshot = snapshots.get(representation.value)
            if previous_snapshot is not None and previous_snapshot != page.snapshot_identity:
                raise ConflictError("advanced retrieval snapshot changed during pagination")
            snapshots[representation.value] = page.snapshot_identity
            _validate_authorization(page.candidates, plan)
            selected_before_page = len(selected)
            bounded, bound_reason = _apply_output_bounds(plan, tuple((*selected, *page.candidates)))
            selected = list(bounded)
            examined += page.examined
            reports.append(_searched_report(page))
            if bound_reason is not None or not page.exhausted:
                next_index = representation_index
                next_offset = (
                    offset + len(selected) - selected_before_page
                    if bound_reason is not None
                    else cast(int, page.next_offset)
                )
                break
            offset = 0

        has_more = next_index is not None
        next_cursor = (
            self._codec.encode(
                plan=plan,
                representation_index=next_index,
                offset=next_offset,
                snapshots=snapshots,
                now=now,
            )
            if next_index is not None
            else None
        )
        completeness = (
            RetrievalCompleteness.TRUNCATED
            if has_more
            else RetrievalCompleteness.PARTIAL
            if unavailable
            else RetrievalCompleteness.EMPTY
            if not selected and cursor is None
            else RetrievalCompleteness.COMPLETE
        )
        return _result(
            plan=plan,
            snapshot_identity=_combined_snapshot(snapshots),
            completeness=completeness,
            selected=tuple(selected),
            examined=examined,
            cursor=next_cursor,
            recalled=len(selected),
            expanded=0,
            deduplicated=0,
            fused=len(selected),
            reranked=0,
            reports=tuple(reports),
            truncation_reason="result_limit" if has_more else None,
            started=started,
        )

    async def _validate_prior_snapshots(
        self,
        plan: RetrievalPlanV2,
        index: int,
        snapshots: dict[str, str],
        *,
        principal: PrincipalContextV1 | None,
    ) -> None:
        for representation in plan.representations[:index]:
            source = self._sources.get(representation)
            expected = snapshots.get(representation.value)
            if source is None or expected is None:
                continue
            page = await self._retrieve_source(source, plan, offset=0, limit=1, principal=principal)
            _validate_page(page, plan, source, 1)
            if page.snapshot_identity != expected:
                raise ConflictError("advanced retrieval snapshot changed during pagination")

    @staticmethod
    async def _retrieve_source(
        source: AdvancedRetrievalSourceV1,
        plan: RetrievalPlanV2,
        *,
        offset: int,
        limit: int,
        principal: PrincipalContextV1 | None,
    ) -> AdvancedSourcePage:
        if isinstance(source, PrincipalAwareAdvancedRetrievalSourceV2):
            if principal is None:
                raise PermissionError("governed V2 source requires a server principal")
            return await source.retrieve_authorized(
                principal=principal, plan=plan, offset=offset, limit=limit
            )
        return await source.retrieve(plan, offset=offset, limit=limit)

    async def _expand_ranked(
        self,
        plan: RetrievalPlanV2,
        seeds: tuple[AdvancedRetrievalCandidate, ...],
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        if plan.expansion_policy is ExpansionPolicy.NONE or plan.budgets.expansion_limit == 0:
            return ()
        expanded: list[AdvancedRetrievalCandidate] = []
        for representation in plan.representations:
            source = self._sources.get(representation)
            if source is None:
                continue
            remaining = plan.budgets.expansion_limit - len(expanded)
            if remaining <= 0:
                break
            values = await source.expand(plan, seeds, limit=remaining)
            if len(values) > remaining:
                raise IntegrityError("advanced retrieval source exceeded expansion budget")
            _validate_authorization(values, plan)
            expanded.extend(values)
        return tuple(expanded)

    async def _rerank(
        self,
        plan: RetrievalPlanV2,
        candidates: tuple[AdvancedRetrievalCandidate, ...],
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        if self._reranker is None or not candidates:
            return candidates
        output = await self._reranker.rerank(plan.query, candidates)
        if not isinstance(output, tuple) or len(output) != len(candidates):
            raise IntegrityError("advanced reranker must preserve candidate cardinality")
        if {item.candidate_id for item in output} != {item.candidate_id for item in candidates}:
            raise IntegrityError("advanced reranker changed candidate identities")
        original = {item.candidate_id: item for item in candidates}
        if any(
            _provenance_key(item) != _provenance_key(original[item.candidate_id]) for item in output
        ):
            raise IntegrityError("advanced reranker changed candidate provenance")
        output_order = {item.candidate_id: index for index, item in enumerate(output)}
        return tuple(
            sorted(
                output,
                key=lambda item: (-int(item.title_match), output_order[item.candidate_id]),
            )
        )


def _deduplicate(
    candidates: tuple[AdvancedRetrievalCandidate, ...],
) -> tuple[AdvancedRetrievalCandidate, ...]:
    merged: dict[object, AdvancedRetrievalCandidate] = {}
    for candidate in candidates:
        previous = merged.get(candidate.candidate_id)
        if previous is None:
            merged[candidate.candidate_id] = candidate
            continue
        if _authority_key(previous) != _authority_key(candidate):
            raise IntegrityError("candidate identity collided across distinct provenance")
        paths = tuple({item.path: item for item in (*previous.paths, *candidate.paths)}.values())
        merged[candidate.candidate_id] = replace(previous, paths=paths)
    return tuple(merged.values())


def _rank_fuse(
    candidates: tuple[AdvancedRetrievalCandidate, ...],
) -> tuple[AdvancedRetrievalCandidate, ...]:
    scored = tuple(
        replace(
            candidate,
            fused_score=sum(1.0 / (_RRF_K + path.source_rank) for path in candidate.paths),
        )
        for candidate in candidates
    )
    return tuple(
        sorted(
            scored,
            key=lambda item: (
                -int(item.title_match),
                -cast(float, item.fused_score),
                str(item.candidate_id),
            ),
        )
    )


def _apply_output_bounds(
    plan: RetrievalPlanV2,
    candidates: tuple[AdvancedRetrievalCandidate, ...],
) -> tuple[tuple[AdvancedRetrievalCandidate, ...], str | None]:
    selected: list[AdvancedRetrievalCandidate] = []
    total_bytes = 0
    total_characters = 0
    reason: str | None = None
    for candidate in candidates:
        content_characters = 0 if candidate.content is None else len(candidate.content)
        if len(selected) >= plan.budgets.result_limit:
            reason = "result_limit"
            break
        if total_bytes + candidate.serialized_size > plan.budgets.max_serialized_bytes:
            reason = "byte_limit"
            break
        if total_characters + content_characters > plan.budgets.max_content_characters:
            reason = "content_limit"
            break
        selected.append(candidate)
        total_bytes += candidate.serialized_size
        total_characters += content_characters
    if reason is not None and not selected and candidates:
        raise ContractValidationError(
            "advanced retrieval budgets cannot serialize one evidence item"
        )
    return tuple(replace(item, final_rank=index) for index, item in enumerate(selected, 1)), reason


def _result(
    *,
    plan: RetrievalPlanV2,
    snapshot_identity: str,
    completeness: RetrievalCompleteness,
    selected: tuple[AdvancedRetrievalCandidate, ...],
    examined: int,
    cursor: str | None,
    recalled: int,
    expanded: int,
    deduplicated: int,
    fused: int,
    reranked: int,
    reports: tuple[RepresentationReportV2, ...],
    truncation_reason: str | None,
    started: float,
) -> RetrievalResultSetV1:
    serialized = sum(item.serialized_size for item in selected)
    characters = sum(0 if item.content is None else len(item.content) for item in selected)
    diagnostics = RetrievalDiagnosticsV2(
        mode=plan.mode,
        recalled=recalled,
        expanded=expanded,
        deduplicated=deduplicated,
        fused=fused,
        reranked=reranked,
        returned=len(selected),
        serialized_bytes=serialized,
        content_characters=characters,
        truncated=truncation_reason is not None,
        truncation_reason=truncation_reason,
        elapsed_milliseconds=max(0, int((time.perf_counter() - started) * 1000)),
        representation_reports=reports,
    )
    return RetrievalResultSetV1(
        query_fingerprint=plan.fingerprint,
        snapshot_identity=snapshot_identity,
        ordering_policy=plan.ranking_policy,
        completeness=completeness,
        results=tuple(replace(item, final_rank=index) for index, item in enumerate(selected, 1)),
        examined_count=examined,
        returned_count=len(selected),
        next_cursor=cursor,
        diagnostics=diagnostics,
    )


def _validate_page(
    page: AdvancedSourcePage,
    plan: RetrievalPlanV2,
    source: AdvancedRetrievalSourceV1,
    limit: int,
) -> None:
    if not isinstance(page, AdvancedSourcePage) or page.representation is not source.representation:
        raise IntegrityError("advanced retrieval source returned an invalid page")
    if len(page.candidates) > limit or page.examined < len(page.candidates):
        raise IntegrityError("advanced retrieval source exceeded its page budget")
    if len({item.candidate_id for item in page.candidates}) != len(page.candidates):
        raise IntegrityError("advanced retrieval source returned duplicate candidates")
    if page.exhausted != (page.next_offset is None):
        raise IntegrityError("advanced retrieval source continuation is inconsistent")
    if len(page.snapshot_identity) != 64 or any(
        character not in "0123456789abcdef" for character in page.snapshot_identity
    ):
        raise IntegrityError("advanced retrieval source snapshot is invalid")
    _validate_authorization(page.candidates, plan)


def _validate_authorization(
    candidates: tuple[AdvancedRetrievalCandidate, ...], plan: RetrievalPlanV2
) -> None:
    for candidate in candidates:
        if candidate.notebook_id != plan.scope.notebook_id:
            raise IntegrityError("advanced retrieval source leaked another notebook")
        if plan.scope.source_ids and candidate.source_id not in plan.scope.source_ids:
            raise IntegrityError("advanced retrieval source violated source scope")
        if plan.scope.document_ids and candidate.document_id not in plan.scope.document_ids:
            raise IntegrityError("advanced retrieval source violated document scope")
        if plan.scope.version_ids and candidate.version_id not in plan.scope.version_ids:
            raise IntegrityError("advanced retrieval source violated version scope")
        if candidate.representation not in plan.representations:
            raise IntegrityError("advanced retrieval source returned an unrequested representation")


def _authority_key(candidate: AdvancedRetrievalCandidate) -> tuple[object, ...]:
    return (
        candidate.notebook_id,
        candidate.source_id,
        candidate.document_id,
        candidate.version_id,
        candidate.representation,
        None if candidate.chunk is None else candidate.chunk.id,
        candidate.occurrence_id,
        candidate.derivation_id,
        candidate.locator,
        candidate.document_title,
        candidate.content,
    )


def _provenance_key(candidate: AdvancedRetrievalCandidate) -> tuple[object, ...]:
    return (*_authority_key(candidate), candidate.paths, candidate.expansion_reason)


def _searched_report(page: AdvancedSourcePage) -> RepresentationReportV2:
    return RepresentationReportV2(
        representation=page.representation,
        status=RepresentationSearchStatus.SEARCHED,
        examined=page.examined,
        returned=len(page.candidates),
        exhausted=page.exhausted,
    )


def _unavailable_report(representation: EvidenceRepresentation) -> RepresentationReportV2:
    return RepresentationReportV2(
        representation=representation,
        status=RepresentationSearchStatus.UNAVAILABLE,
        examined=0,
        returned=0,
        exhausted=False,
        reason_code="representation_unavailable",
    )


def _failed_report(representation: EvidenceRepresentation, reason: str) -> RepresentationReportV2:
    return RepresentationReportV2(
        representation=representation,
        status=RepresentationSearchStatus.FAILED,
        examined=0,
        returned=0,
        exhausted=False,
        reason_code=f"source_failure:{reason}",
    )


def _combined_snapshot(snapshots: dict[str, str]) -> str:
    return hashlib.sha256(_canonical_json(snapshots)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
