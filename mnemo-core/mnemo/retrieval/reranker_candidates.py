"""Sole authorized Full Multilingual V2 reranker-candidate construction path."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mnemo.interfaces.multilingual import RerankerEvidenceResolverV1
from mnemo.models.multilingual import LanguageEvidenceReferenceV3
from mnemo.models.multilingual_reranking import (
    MultilingualRerankCandidateV3,
    RerankerInputAuditV1,
    RerankerInputAuditV2,
    RerankerPairPolicyV1,
    RerankerPairPolicyV2,
    V2TypedCandidateAuditV1,
    render_contextual_provider_text,
)
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1

RERANKER_BUILDER_REVISION = "1.0.0"


class V2TypedCandidateBuilderV1:
    """Build the shared authorized V2 candidate without selecting a reranker."""

    builder_id = "mnemo.v2-typed-candidate-builder/1"

    def __init__(self, *, resolver: RerankerEvidenceResolverV1) -> None:
        self._resolver = resolver

    async def build(
        self,
        *,
        query: str,
        source: LanguageEvidenceReferenceV3,
        decision: V2RetrievalAuthorizationDecisionV1,
        input_ordinal: int,
        retrieval_paths: tuple[str, ...],
    ) -> MultilingualRerankCandidateV3:
        if not query.strip():
            raise ValueError("query must not be blank")
        if not 0 <= input_ordinal <= 199:
            raise ValueError("input_ordinal must be in [0,199]")
        scope = decision.retrieval_scope
        if source.notebook_id != scope.notebook_id:
            raise PermissionError("V2 decision does not bind the evidence notebook")
        for permitted, actual, label in (
            (scope.source_ids, source.source_id, "source"),
            (scope.document_ids, source.document_id, "document"),
            (scope.version_ids, source.version_id, "version"),
        ):
            if permitted and actual not in permitted:
                raise PermissionError(f"V2 decision excludes evidence {label}")
        if not retrieval_paths or len(set(retrieval_paths)) != len(retrieval_paths):
            raise ValueError("retrieval_paths must be non-empty and unique")
        resolved = await self._resolver.resolve_reranker_evidence(
            source=source,
            decision=decision,
            retrieval_paths=retrieval_paths,
            fusion_rank=input_ordinal + 1,
        )
        if resolved.source_reference != source:
            raise ValueError("reranker resolver returned a different source reference")
        if resolved.provenance.authorization_scope_digest != decision.decision_fingerprint:
            raise ValueError("reranker resolver returned incompatible authorization provenance")
        semantic_text = resolved.semantic_text
        if not semantic_text.strip():
            raise ValueError("reranker semantic text cannot be blank")
        contextual = render_contextual_provider_text(
            title=resolved.title_metadata,
            heading_path=resolved.heading_path,
            semantic_text=semantic_text,
        )
        semantic_hash = _text_hash(semantic_text)
        audit = V2TypedCandidateAuditV1(
            query_hash=_text_hash(query),
            semantic_text_hash=semantic_hash,
            contextual_text_hash=_text_hash(contextual),
            authorization_decision_fingerprint=decision.decision_fingerprint,
        )
        return MultilingualRerankCandidateV3(
            candidate_id=resolved.candidate_id,
            input_ordinal=input_ordinal,
            source_reference=resolved.source_reference,
            representation_reference=resolved.representation_reference,
            semantic_text=semantic_text,
            semantic_text_hash=semantic_hash,
            title_metadata=resolved.title_metadata,
            heading_path=resolved.heading_path,
            language_observation_references=resolved.language_observation_references,
            script_observation_references=resolved.script_observation_references,
            provenance=resolved.provenance,
            input_audit=audit,
            runtime_security=resolved.runtime_security,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderedRerankerPairV1:
    input_ids: tuple[int, ...]
    attention_mask: tuple[int, ...] | None
    token_type_ids: tuple[int, ...] | None

    def __post_init__(self) -> None:
        if not self.input_ids or any(item < 0 for item in self.input_ids):
            raise ValueError("rendered reranker input IDs must be non-negative and non-empty")
        for values, name in (
            (self.attention_mask, "attention_mask"),
            (self.token_type_ids, "token_type_ids"),
        ):
            if values is not None and len(values) != len(self.input_ids):
                raise ValueError(f"{name} length must match input IDs")


class RerankerTokenizerV1(Protocol):  # pragma: no cover
    @property
    def identity(self) -> str: ...

    @property
    def revision(self) -> str: ...

    @property
    def configuration_digest(self) -> str: ...

    def encode_without_special_tokens(self, text: str) -> tuple[int, ...]: ...

    def build_pair(
        self, query_ids: tuple[int, ...], document_ids: tuple[int, ...]
    ) -> RenderedRerankerPairV1: ...


class RerankerCandidateBuilderV1:
    """Resolve authorized semantic evidence and freeze exact provider input audit."""

    def __init__(
        self,
        *,
        resolver: RerankerEvidenceResolverV1,
        tokenizer: RerankerTokenizerV1,
        provider_id: str,
        model_id: str,
        model_revision: str,
        provider_configuration_digest: str,
        query_preprocessing_identity: str,
        document_preprocessing_identity: str,
        preprocess_query: Callable[[str], str],
        preprocess_document: Callable[[str], str],
        policy: RerankerPairPolicyV1 | RerankerPairPolicyV2 | None = None,
    ) -> None:
        self._resolver = resolver
        self._tokenizer = tokenizer
        self._provider_id = _non_empty(provider_id, "provider_id")
        self._model_id = _non_empty(model_id, "model_id")
        self._model_revision = _non_empty(model_revision, "model_revision")
        self._provider_configuration_digest = _sha256(
            provider_configuration_digest, "provider_configuration_digest"
        )
        self._query_preprocessing_identity = _non_empty(
            query_preprocessing_identity, "query_preprocessing_identity"
        )
        self._document_preprocessing_identity = _non_empty(
            document_preprocessing_identity, "document_preprocessing_identity"
        )
        self._preprocess_query = preprocess_query
        self._preprocess_document = preprocess_document
        self._policy = policy if policy is not None else RerankerPairPolicyV1()

    async def build(
        self,
        *,
        query: str,
        source: LanguageEvidenceReferenceV3,
        decision: V2RetrievalAuthorizationDecisionV1,
        input_ordinal: int,
        retrieval_paths: tuple[str, ...],
    ) -> MultilingualRerankCandidateV3:
        if not 0 <= input_ordinal <= 199:
            raise ValueError("input_ordinal must be in [0,199]")
        scope = decision.retrieval_scope
        if source.notebook_id != scope.notebook_id:
            raise PermissionError("V2 decision does not bind the evidence notebook")
        for permitted, actual, label in (
            (scope.source_ids, source.source_id, "source"),
            (scope.document_ids, source.document_id, "document"),
            (scope.version_ids, source.version_id, "version"),
        ):
            if permitted and actual not in permitted:
                raise PermissionError(f"V2 decision excludes evidence {label}")
        if not retrieval_paths or len(set(retrieval_paths)) != len(retrieval_paths):
            raise ValueError("retrieval_paths must be non-empty and unique")
        resolved = await self._resolver.resolve_reranker_evidence(
            source=source,
            decision=decision,
            retrieval_paths=retrieval_paths,
            fusion_rank=input_ordinal + 1,
        )
        if resolved.source_reference != source:
            raise ValueError("reranker resolver returned a different source reference")
        if resolved.provenance.authorization_scope_digest != (decision.decision_fingerprint):
            raise ValueError("reranker resolver returned incompatible authorization provenance")
        semantic_text = resolved.semantic_text
        if not semantic_text.strip():
            raise ValueError("reranker semantic text cannot be blank")
        if resolved.title_metadata is not None and (
            semantic_text.strip() == resolved.title_metadata.strip()
        ):
            raise ValueError("title-only reranker evidence is forbidden")
        preprocessed_query = self._preprocess_query(query)
        audit: RerankerInputAuditV1 | RerankerInputAuditV2
        if isinstance(self._policy, RerankerPairPolicyV2):
            contextual_doc = render_contextual_provider_text(
                title=resolved.title_metadata,
                heading_path=resolved.heading_path,
                semantic_text=semantic_text,
            )
            preprocessed_document = self._preprocess_document(contextual_doc)
        else:
            contextual_doc = semantic_text
            preprocessed_document = self._preprocess_document(semantic_text)
        query_ids = self._tokenizer.encode_without_special_tokens(preprocessed_query)
        document_ids = self._tokenizer.encode_without_special_tokens(preprocessed_document)
        if not query_ids or not document_ids:
            raise ValueError("reranker query and document must retain semantic tokens")
        empty_pair = self._tokenizer.build_pair((), ())
        special_count = len(empty_pair.input_ids)
        if not 1 <= special_count <= 255:
            raise ValueError("frozen tokenizer produced invalid special-token count")
        content_budget = 256 - special_count
        if content_budget < 2:
            raise ValueError("frozen tokenizer leaves no query/document content budget")
        kept_query_count = min(len(query_ids), 96, content_budget - 1)
        kept_query = query_ids[:kept_query_count]
        document_budget = content_budget - kept_query_count
        kept_document = document_ids[:document_budget]
        if not kept_document:
            raise ValueError("reranker pair must retain document semantic tokens")
        rendered = self._tokenizer.build_pair(kept_query, kept_document)
        expected_total = len(kept_query) + len(kept_document) + special_count
        if len(rendered.input_ids) != expected_total or expected_total > 256:
            raise ValueError("frozen tokenizer pair rendering violates governed accounting")
        query_hash = _text_hash(query)
        preprocessed_query_hash = _text_hash(preprocessed_query)
        semantic_text_hash = _text_hash(semantic_text)
        preprocessed_document_hash = _text_hash(preprocessed_document)
        retained_query_hash = _canonical_hash(list(kept_query))
        retained_document_hash = _canonical_hash(list(kept_document))
        rendered_payload = {
            "input_ids": list(rendered.input_ids),
            "attention_mask": (
                None if rendered.attention_mask is None else list(rendered.attention_mask)
            ),
            "token_type_ids": (
                None if rendered.token_type_ids is None else list(rendered.token_type_ids)
            ),
        }
        rendered_input_hash = _canonical_hash(rendered_payload)
        retained_input_hash = _canonical_hash(
            {
                **rendered_payload,
                "tokenizer_identity": self._tokenizer.identity,
                "tokenizer_revision": self._tokenizer.revision,
                "tokenizer_configuration_digest": self._tokenizer.configuration_digest,
                "policy_id": self._policy.policy_id,
            }
        )
        pair_identity = _canonical_hash(
            {
                "candidate_id": str(resolved.candidate_id),
                "query_hash": query_hash,
                "retained_input_hash": retained_input_hash,
                "provider_id": self._provider_id,
                "model_id": self._model_id,
                "model_revision": self._model_revision,
                "query_preprocessing_identity": self._query_preprocessing_identity,
                "document_preprocessing_identity": self._document_preprocessing_identity,
            }
        )
        if isinstance(self._policy, RerankerPairPolicyV2):
            audit = RerankerInputAuditV2(
                builder_revision=RERANKER_BUILDER_REVISION,
                provider_id=self._provider_id,
                model_id=self._model_id,
                model_revision=self._model_revision,
                provider_configuration_digest=self._provider_configuration_digest,
                query_preprocessing_identity=self._query_preprocessing_identity,
                document_preprocessing_identity=self._document_preprocessing_identity,
                tokenizer_identity=self._tokenizer.identity,
                tokenizer_revision=self._tokenizer.revision,
                tokenizer_configuration_digest=self._tokenizer.configuration_digest,
                query_hash=query_hash,
                preprocessed_query_hash=preprocessed_query_hash,
                semantic_text_hash=semantic_text_hash,
                contextual_text_hash=_text_hash(contextual_doc),
                preprocessed_document_hash=preprocessed_document_hash,
                query_token_count=len(query_ids),
                document_token_count=len(document_ids),
                special_token_count=special_count,
                available_content_token_count=content_budget,
                retained_query_token_count=len(kept_query),
                retained_document_token_count=len(kept_document),
                retained_token_count=len(rendered.input_ids),
                query_truncated=len(kept_query) < len(query_ids),
                document_truncated=len(kept_document) < len(document_ids),
                retained_query_hash=retained_query_hash,
                retained_document_hash=retained_document_hash,
                rendered_input_hash=rendered_input_hash,
                retained_input_hash=retained_input_hash,
                pair_identity=pair_identity,
                pair_policy=self._policy,
            )
        else:
            audit = RerankerInputAuditV1(
                builder_revision=RERANKER_BUILDER_REVISION,
                provider_id=self._provider_id,
                model_id=self._model_id,
                model_revision=self._model_revision,
                provider_configuration_digest=self._provider_configuration_digest,
                query_preprocessing_identity=self._query_preprocessing_identity,
                document_preprocessing_identity=self._document_preprocessing_identity,
                tokenizer_identity=self._tokenizer.identity,
                tokenizer_revision=self._tokenizer.revision,
                tokenizer_configuration_digest=self._tokenizer.configuration_digest,
                query_hash=query_hash,
                preprocessed_query_hash=preprocessed_query_hash,
                semantic_text_hash=semantic_text_hash,
                preprocessed_document_hash=preprocessed_document_hash,
                query_token_count=len(query_ids),
                document_token_count=len(document_ids),
                special_token_count=special_count,
                available_content_token_count=content_budget,
                retained_query_token_count=len(kept_query),
                retained_document_token_count=len(kept_document),
                retained_token_count=len(rendered.input_ids),
                query_truncated=len(kept_query) < len(query_ids),
                document_truncated=len(kept_document) < len(document_ids),
                retained_query_hash=retained_query_hash,
                retained_document_hash=retained_document_hash,
                rendered_input_hash=rendered_input_hash,
                retained_input_hash=retained_input_hash,
                pair_identity=pair_identity,
                pair_policy=self._policy,
            )
        return MultilingualRerankCandidateV3(
            candidate_id=resolved.candidate_id,
            input_ordinal=input_ordinal,
            source_reference=resolved.source_reference,
            representation_reference=resolved.representation_reference,
            semantic_text=semantic_text,
            semantic_text_hash=semantic_text_hash,
            title_metadata=resolved.title_metadata,
            heading_path=resolved.heading_path,
            language_observation_references=resolved.language_observation_references,
            script_observation_references=resolved.script_observation_references,
            provenance=resolved.provenance,
            input_audit=audit,
            runtime_security=resolved.runtime_security,
        )


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _non_empty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value


def _sha256(value: str, name: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")
    return value
