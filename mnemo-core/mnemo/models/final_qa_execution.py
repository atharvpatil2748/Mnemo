"""ADR-0056 immutable persisted Final-QA execution records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from .final_qa import FinalQARequest
from .notebook import Turn

_FINGERPRINT_DOMAIN = "mnemo.final_qa.request.v1"
_FINGERPRINT_SERIALIZATION_VERSION = 1
FINAL_QA_EXECUTION_CONTRACT_VERSION = "adr-0056/v1"
FINAL_QA_CITATION_CONTRACT_VERSION = "adr-0054/v1"
FINAL_QA_RETRY_POLICY_VERSION = "one-corrective-retry/v1"


class FinalQAExecutionState(StrEnum):
    RUNNING = "running"
    VALIDATED = "validated"
    ASSISTANT_PUBLISHED = "assistant_published"
    PUBLISHED = "published"
    REJECTED_CITATION_COMPLIANCE = "rejected_citation_compliance"


class FinalQAExecutionSnapshotPhase(StrEnum):
    VALIDATED = "validated"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalQAExecution:
    execution_id: UUID
    assistant_turn_id: UUID
    request_fingerprint: str
    notebook_id: UUID
    session_id: UUID
    user_turn_id: UUID
    contract_version: str
    payload_schema_version: int
    provider: str
    model: str
    model_configuration: str
    state: FinalQAExecutionState
    retry_count: int
    failure_classification: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalQAExecutionSnapshot:
    execution_id: UUID
    phase: FinalQAExecutionSnapshotPhase
    payload_schema_version: int
    payload: str
    created_at: datetime


def final_qa_request_fingerprint(
    request: FinalQARequest,
    *,
    notebook_id: UUID,
    user_turn: Turn,
    provider: str,
    model: str,
    model_configuration: dict[str, Any],
    tokenizer_id: str,
) -> str:
    """Return the ADR-0056 semantic-request digest, excluding publication slot."""
    material = {
        "domain": _FINGERPRINT_DOMAIN,
        "serialization_version": _FINGERPRINT_SERIALIZATION_VERSION,
        "notebook_id": str(notebook_id),
        "session_id": str(request.session_id),
        "user_turn_id": str(request.user_turn_id),
        "user_turn_content": user_turn.content,
        "query": request.query,
        "metadata_filter": _json_value(request.metadata_filter),
        "global_limit": request.global_limit,
        "context_budget": request.context_budget,
        "max_output_tokens": request.max_output_tokens,
        "table_of_contents": request.table_of_contents,
        "source_titles": request.source_titles,
        "document_labels": _json_value(request.document_labels),
        "system_prompt": {"id": "adr-0044/strict-final-qa/v1", "bytes": request.system_prompt},
        "tokenizer_id": tokenizer_id,
        "policy_versions": {
            "planner": "adr-0041/v1",
            "retrieval": "adr-0041/v1",
            "context": "adr-0043/v1",
            "citation": FINAL_QA_CITATION_CONTRACT_VERSION,
            "retry": FINAL_QA_RETRY_POLICY_VERSION,
        },
        "provider": provider,
        "model": model,
        "model_configuration": _json_value(model_configuration),
    }
    encoded = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_value(value: Any) -> Any:
    """Serialize deterministic simple model values used only in a fingerprint."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump())
    if hasattr(value, "__dataclass_fields__"):
        return {name: _json_value(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(_json_value(item) for item in value)
    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    return value
