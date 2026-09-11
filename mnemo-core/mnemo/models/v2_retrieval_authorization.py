"""Immutable V2-only retrieval authorization bindings.

These objects are additive.  They carry the server-issued result of base
authorization; they do not derive a principal or establish notebook ownership.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from ._shared import require_non_empty, require_sha256
from .advanced_retrieval import PositionalScopeV2, RetrievalScopeV2

V2_RETRIEVAL_AUTHORIZATION_DECISION_SCHEMA = "mnemo.v2-retrieval-authorization-decision/1"
V2_RETRIEVAL_OPERATION = "retrieve"


@dataclass(frozen=True, slots=True, kw_only=True)
class V2ActiveRuntimeBindingV1:
    """Server-resolved active V2 runtime identities; callers cannot override them."""

    alias_set_digest: str
    generation_ids: tuple[UUID, ...]
    profile_fingerprint: str
    vector_space_identity: str
    database_identity: str
    build_run_id: UUID
    admission_policy_identity: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.alias_set_digest, "alias_set_digest"),
            (self.profile_fingerprint, "profile_fingerprint"),
            (self.vector_space_identity, "vector_space_identity"),
            (self.database_identity, "database_identity"),
        ):
            require_sha256(value, name)
        if len(self.generation_ids) != 4 or len(set(self.generation_ids)) != 4:
            raise ValueError("V2 runtime binding requires exactly four distinct generations")
        require_non_empty(self.admission_policy_identity, "admission_policy_identity")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2RetrievalAuthorizationDecisionV1:
    """Non-expandable allow decision issued before V2 source enumeration."""

    decision_id: UUID
    principal_actor_id: UUID
    operation: str
    retrieval_scope: RetrievalScopeV2
    positional_scope: PositionalScopeV2
    runtime_binding: V2ActiveRuntimeBindingV1
    authorization_policy_identity: str
    authorization_policy_revision: str
    request_fingerprint: str
    issued_at: str
    required_provenance_evidence: tuple[str, ...]
    schema_version: str = V2_RETRIEVAL_AUTHORIZATION_DECISION_SCHEMA

    def __post_init__(self) -> None:
        if self.operation != V2_RETRIEVAL_OPERATION:
            raise ValueError("V2 authorization decision permits only the retrieval operation")
        require_non_empty(self.authorization_policy_identity, "authorization_policy_identity")
        require_non_empty(self.authorization_policy_revision, "authorization_policy_revision")
        require_non_empty(self.issued_at, "issued_at")
        require_sha256(self.request_fingerprint, "request_fingerprint")
        if not self.required_provenance_evidence or any(
            not value.strip() for value in self.required_provenance_evidence
        ):
            raise ValueError("V2 authorization decision requires provenance obligations")
        if len(set(self.required_provenance_evidence)) != len(self.required_provenance_evidence):
            raise ValueError("V2 authorization provenance obligations must be unique")

    @property
    def decision_fingerprint(self) -> str:
        """Canonical identity makes mutation/stale-binding comparison deterministic."""

        payload = {
            "schema_version": self.schema_version,
            "decision_id": str(self.decision_id),
            "principal_actor_id": str(self.principal_actor_id),
            "operation": self.operation,
            "retrieval_scope": self.retrieval_scope.model_dump(mode="json"),
            "positional_scope": self.positional_scope.model_dump(mode="json"),
            "runtime_binding": {
                "alias_set_digest": self.runtime_binding.alias_set_digest,
                "generation_ids": [str(value) for value in self.runtime_binding.generation_ids],
                "profile_fingerprint": self.runtime_binding.profile_fingerprint,
                "vector_space_identity": self.runtime_binding.vector_space_identity,
                "database_identity": self.runtime_binding.database_identity,
                "build_run_id": str(self.runtime_binding.build_run_id),
                "admission_policy_identity": self.runtime_binding.admission_policy_identity,
            },
            "authorization_policy_identity": self.authorization_policy_identity,
            "authorization_policy_revision": self.authorization_policy_revision,
            "request_fingerprint": self.request_fingerprint,
            "issued_at": self.issued_at,
            "required_provenance_evidence": list(self.required_provenance_evidence),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def permits(
        self,
        *,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        runtime_binding: V2ActiveRuntimeBindingV1,
    ) -> None:
        """Reject any downstream broadening or substitution before enumeration."""

        if scope != self.retrieval_scope or position != self.positional_scope:
            raise PermissionError("V2 authorization decision scope mismatch")
        if runtime_binding != self.runtime_binding:
            raise PermissionError("V2 authorization decision runtime binding mismatch")
