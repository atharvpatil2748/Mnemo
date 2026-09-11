"""Deterministic bounded multi-document retrieval primitives for Phase 8.5 WP-11."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalInterfaceV1
from mnemo.models.advanced_retrieval import (
    RetrievalCompleteness,
    RetrievalPlanV2,
    RetrievalResultSetV1,
    RetrievalScopeV2,
)

from .advanced import RetrievalCursorCodec


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalPartitionV1:
    """One authorized document partition and its exact retrieval result."""

    document_id: UUID
    result: RetrievalResultSetV1


@dataclass(frozen=True, slots=True, kw_only=True)
class PartitionedRetrievalResultV1:
    """Stable, provenance-preserving result for an explicit document set."""

    query_fingerprint: str
    snapshot_identity: str
    partitions: tuple[RetrievalPartitionV1, ...]
    completeness: RetrievalCompleteness
    omissions: tuple[str, ...] = ()
    next_cursor: str | None = None

    @property
    def next_cursors(self) -> Mapping[UUID, str]:
        return {
            partition.document_id: partition.result.next_cursor
            for partition in self.partitions
            if partition.result.next_cursor is not None
        }


class PartitionedRetrievalServiceV1:
    """Compose independent authorized document traversals deterministically.

    This is deliberately a thin composition layer. It does not decompose natural
    language, infer joins, or replace the underlying ranked/exhaustive service.
    """

    def __init__(
        self,
        retrieval: AdvancedRetrievalInterfaceV1,
        cursor_codec: RetrievalCursorCodec | None = None,
    ) -> None:
        if not isinstance(retrieval, AdvancedRetrievalInterfaceV1):
            raise TypeError("retrieval must implement AdvancedRetrievalInterfaceV1")
        self._retrieval = retrieval
        self._cursor_codec = cursor_codec

    async def resolve_document_set(
        self, *, scope: RetrievalScopeV2, document_ids: tuple[UUID, ...]
    ) -> tuple[UUID, ...]:
        """Validate explicit partition identities without inferring unauthorized documents."""
        if not document_ids or len(document_ids) != len(set(document_ids)):
            raise ValueError("document_ids must be a non-empty unique set")
        if any(document_id not in scope.document_ids for document_id in document_ids):
            raise ValueError("document partition is outside the authorized scope")
        return tuple(sorted(document_ids, key=str))

    async def execute(
        self,
        plan: RetrievalPlanV2,
        *,
        document_ids: tuple[UUID, ...],
        cursors: Mapping[UUID, str] | None = None,
        cursor: str | None = None,
    ) -> PartitionedRetrievalResultV1:
        document_ids = await self.resolve_document_set(scope=plan.scope, document_ids=document_ids)
        expected_snapshot: object | None = None
        if cursor is not None and cursors:
            raise ValueError("provide one aggregate cursor or partition cursors, not both")
        if cursor is not None:
            if self._cursor_codec is None:
                raise RuntimeError("partitioned continuation requires a cursor codec")
            decoded = self._cursor_codec.decode_partitioned(
                cursor,
                plan=plan,
                document_ids=tuple(str(item) for item in document_ids),
                now=datetime.now(UTC),
            )
            expected_snapshot = decoded["snapshot_identity"]
            raw_cursors = decoded["cursors"]
            if not isinstance(raw_cursors, dict):
                raise ValueError("partitioned cursor state is invalid")
            cursors = {UUID(key): value for key, value in raw_cursors.items()}
        cursor_map: Mapping[UUID, str] = cursors or {}
        partitions: list[RetrievalPartitionV1] = []
        for document_id in document_ids:
            partition_plan = plan.model_copy(
                update={
                    "scope": RetrievalScopeV2(
                        notebook_id=plan.scope.notebook_id,
                        source_ids=plan.scope.source_ids,
                        document_ids=(document_id,),
                        version_ids=plan.scope.version_ids,
                    )
                }
            )
            result = await self._retrieval.execute(
                partition_plan, cursor=cursor_map.get(document_id)
            )
            partitions.append(RetrievalPartitionV1(document_id=document_id, result=result))
        completeness = _combine_completeness(partitions)
        snapshots = [partition.result.snapshot_identity for partition in partitions]
        snapshot_identity = _sha256(snapshots)
        if cursor is not None and expected_snapshot != snapshot_identity:
            raise ValueError("partitioned retrieval snapshot changed; restart the traversal")
        aggregate_cursor = None
        if any(partition.result.next_cursor is not None for partition in partitions):
            if self._cursor_codec is None:
                raise RuntimeError("partitioned continuation requires a cursor codec")
            encoded = {
                str(partition.document_id): partition.result.next_cursor
                for partition in partitions
                if partition.result.next_cursor is not None
            }
            aggregate_cursor = self._cursor_codec.encode_partitioned(
                plan=plan,
                document_ids=tuple(str(item) for item in document_ids),
                cursors=encoded,
                snapshot_identity=snapshot_identity,
                now=datetime.now(UTC),
            )
        return PartitionedRetrievalResultV1(
            query_fingerprint=_sha256(
                [plan.fingerprint, *[str(i) for i in sorted(document_ids, key=str)]]
            ),
            snapshot_identity=snapshot_identity,
            partitions=tuple(partitions),
            completeness=completeness,
            omissions=tuple(
                f"{partition.document_id}:continuation_required"
                for partition in partitions
                if partition.result.next_cursor is not None
            ),
            next_cursor=aggregate_cursor,
        )


def _combine_completeness(partitions: list[RetrievalPartitionV1]) -> RetrievalCompleteness:
    states = [partition.result.completeness for partition in partitions]
    if any(state is RetrievalCompleteness.TRUNCATED for state in states):
        return RetrievalCompleteness.TRUNCATED
    if any(
        state in {RetrievalCompleteness.PARTIAL, RetrievalCompleteness.UNKNOWN} for state in states
    ):
        return RetrievalCompleteness.PARTIAL
    if all(state is RetrievalCompleteness.EMPTY for state in states):
        return RetrievalCompleteness.EMPTY
    return RetrievalCompleteness.COMPLETE


def _sha256(values: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
