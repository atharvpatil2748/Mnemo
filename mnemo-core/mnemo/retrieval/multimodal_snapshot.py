"""Typed immutable serialization for Final-QA V2 validated/published snapshots."""

from __future__ import annotations

from mnemo.interfaces.errors import IntegrityError
from mnemo.models.multimodal import (
    FinalQAResultV2,
    MultimodalContextBuildResultV1,
    MultimodalGenerationResultV1,
)

from .final_qa_snapshot import _decode, _encode


def encode_validated_v2_snapshot(
    answer: MultimodalGenerationResultV1 | None,
    context: MultimodalContextBuildResultV1,
    retry_count: int,
) -> str:
    return _encode(
        {"kind": "validated_v2", "answer": answer, "context": context, "retry": retry_count}
    )


def decode_validated_v2_snapshot(
    payload: str,
) -> tuple[MultimodalGenerationResultV1 | None, MultimodalContextBuildResultV1, int]:
    decoded = _decode(payload)
    if not isinstance(decoded, dict) or decoded.get("kind") != "validated_v2":
        raise IntegrityError("invalid Final-QA V2 validated snapshot")
    answer = decoded.get("answer")
    context = decoded.get("context")
    retry = decoded.get("retry")
    if answer is not None and not isinstance(answer, MultimodalGenerationResultV1):
        raise IntegrityError("invalid Final-QA V2 generated answer snapshot")
    if not isinstance(context, MultimodalContextBuildResultV1):
        raise IntegrityError("invalid Final-QA V2 context snapshot")
    if isinstance(retry, bool) or not isinstance(retry, int) or retry not in {0, 1}:
        raise IntegrityError("invalid Final-QA V2 retry snapshot")
    return answer, context, retry


def encode_published_v2_snapshot(result: FinalQAResultV2) -> str:
    return _encode({"kind": "published_v2", "result": result})


def decode_published_v2_snapshot(payload: str) -> FinalQAResultV2:
    decoded = _decode(payload)
    if not isinstance(decoded, dict) or decoded.get("kind") != "published_v2":
        raise IntegrityError("invalid Final-QA V2 published snapshot")
    result = decoded.get("result")
    if not isinstance(result, FinalQAResultV2):
        raise IntegrityError("published snapshot does not retain FinalQAResultV2")
    return result
