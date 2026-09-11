"""Typed Full Multilingual V2 reranker candidate and input-audit contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from ._shared import require_non_empty, require_positive, require_sha256
from .multilingual import LanguageEvidenceReferenceV3
from .text_representations import ObservationReferenceV1, TextRepresentationReferenceV1
from .v2_evidence_resolution import V2CandidateRuntimeSecurityBindingV1

RERANKER_CANDIDATE_CONTRACT_V3 = "mnemo.multilingual-rerank-candidate/3"
RERANKER_INPUT_AUDIT_V1 = "mnemo.reranker-input-audit/1"
RERANKER_INPUT_AUDIT_V2 = "mnemo.reranker-input-audit/2"
RERANKER_BUILDER_ID = "mnemo.reranker-candidate-builder/1"
V2_TYPED_CANDIDATE_BUILDER_ID = "mnemo.v2-typed-candidate-builder/1"
RERANKER_PAIR_POLICY_ID = "bge-reranker-v2-m3-pair-256-v2"
RERANKER_PAIR_POLICY_V2_ID = "bge-reranker-v2-m3-pair-256-contextual-v1"


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankerPairPolicyV1:
    policy_id: str = RERANKER_PAIR_POLICY_ID
    pair_max_tokens: int = 256
    query_max_content_tokens: int = 96
    special_token_policy: str = "tokenizer_build_inputs_with_special_tokens_pair"
    query_truncation: str = "retain_head"
    document_truncation: str = "retain_head"
    unused_query_budget_policy: str = "assign_to_document_only"
    title_metadata_policy: str = "exclude_from_provider_input"
    rendering_policy: str = "token_id_pair_via_frozen_tokenizer"
    tie_breaking_policy: str = "score_desc_then_input_ordinal_then_candidate_id"

    def __post_init__(self) -> None:
        if (
            self.policy_id != RERANKER_PAIR_POLICY_ID
            or self.pair_max_tokens != 256
            or self.query_max_content_tokens != 96
            or self.special_token_policy != "tokenizer_build_inputs_with_special_tokens_pair"
            or self.query_truncation != "retain_head"
            or self.document_truncation != "retain_head"
            or self.unused_query_budget_policy != "assign_to_document_only"
            or self.title_metadata_policy != "exclude_from_provider_input"
            or self.rendering_policy != "token_id_pair_via_frozen_tokenizer"
            or self.tie_breaking_policy != "score_desc_then_input_ordinal_then_candidate_id"
        ):
            raise ValueError("reranker pair policy differs from the governed V2 policy")


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankerPairPolicyV2:
    policy_id: str = RERANKER_PAIR_POLICY_V2_ID
    pair_max_tokens: int = 256
    query_max_content_tokens: int = 96
    special_token_policy: str = "tokenizer_build_inputs_with_special_tokens_pair"
    query_truncation: str = "retain_head"
    document_truncation: str = "retain_head"
    unused_query_budget_policy: str = "assign_to_document_only"
    title_metadata_policy: str = "include_in_provider_input_with_heading_path"
    rendering_policy: str = "bracket_title_heading_prefix_token_id_pair"
    tie_breaking_policy: str = "score_desc_then_input_ordinal_then_candidate_id"

    def __post_init__(self) -> None:
        if (
            self.policy_id != RERANKER_PAIR_POLICY_V2_ID
            or self.pair_max_tokens != 256
            or self.query_max_content_tokens != 96
            or self.special_token_policy != "tokenizer_build_inputs_with_special_tokens_pair"
            or self.query_truncation != "retain_head"
            or self.document_truncation != "retain_head"
            or self.unused_query_budget_policy != "assign_to_document_only"
            or self.title_metadata_policy != "include_in_provider_input_with_heading_path"
            or self.rendering_policy != "bracket_title_heading_prefix_token_id_pair"
            or self.tie_breaking_policy != "score_desc_then_input_ordinal_then_candidate_id"
        ):
            raise ValueError("reranker pair policy differs from governed V2 contextual policy")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2TypedCandidateAuditV1:
    """Model-neutral audit created before a production reranker is selected.

    This binds authorized evidence and its contextual rendering without loading
    a tokenizer or claiming that any reranker has executed.
    """

    query_hash: str
    semantic_text_hash: str
    contextual_text_hash: str
    authorization_decision_fingerprint: str
    builder_id: str = V2_TYPED_CANDIDATE_BUILDER_ID
    schema_version: str = "mnemo.v2-typed-candidate-audit/1"

    def __post_init__(self) -> None:
        if self.builder_id != V2_TYPED_CANDIDATE_BUILDER_ID:
            raise ValueError("V2 typed candidate builder identity mismatch")
        for value, name in (
            (self.query_hash, "query_hash"),
            (self.semantic_text_hash, "semantic_text_hash"),
            (self.contextual_text_hash, "contextual_text_hash"),
            (self.authorization_decision_fingerprint, "authorization_decision_fingerprint"),
        ):
            require_sha256(value, name)


def render_contextual_provider_text(
    *,
    title: str | None,
    heading_path: tuple[str, ...],
    semantic_text: str,
) -> str:
    """Canonical deterministic renderer for provider-facing candidate input.

    Leaves canonical semantic text, stored chunk content, and content hashes
    100% untouched. Formats authorized hierarchical context as:
        [{clean_title} | {clean_headings}] {clean_semantic_text}
    """
    clean_title = " ".join((title or "").split()).strip()
    clean_headings = " > ".join(
        h_clean for h in heading_path if (h_clean := " ".join(h.split()).strip())
    )

    if clean_title and clean_headings:
        prefix = f"[{clean_title} | {clean_headings}] "
    elif clean_title:
        prefix = f"[{clean_title}] "
    elif clean_headings:
        prefix = f"[{clean_headings}] "
    else:
        prefix = ""

    return f"{prefix}{semantic_text}"


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateProvenanceV1:
    source_reference_digest: str
    representation_reference_id: UUID
    authorization_scope_digest: str
    retrieval_snapshot_identity: str
    retrieval_paths_digest: str
    fusion_policy_id: str
    fusion_rank: int
    source_generation_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.source_reference_digest, "source_reference_digest"),
            (self.authorization_scope_digest, "authorization_scope_digest"),
            (self.retrieval_snapshot_identity, "retrieval_snapshot_identity"),
            (self.retrieval_paths_digest, "retrieval_paths_digest"),
        ):
            require_sha256(value, name)
        require_non_empty(self.fusion_policy_id, "fusion_policy_id")
        require_positive(self.fusion_rank, "fusion_rank")
        if self.fusion_rank > 1000:
            raise ValueError("fusion rank exceeds governed bound")
        if len(set(self.source_generation_ids)) != len(self.source_generation_ids):
            raise ValueError("source generation identities must be unique")


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizedRerankerEvidenceV1:
    """Server-resolved semantic evidence supplied to the candidate builder."""

    candidate_id: UUID
    source_reference: LanguageEvidenceReferenceV3
    representation_reference: TextRepresentationReferenceV1
    semantic_text: str
    title_metadata: str | None
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]
    provenance: CandidateProvenanceV1
    runtime_security: V2CandidateRuntimeSecurityBindingV1 | None = None
    heading_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty(self.semantic_text, "semantic_text")
        if not self.semantic_text.strip():
            raise ValueError("authorized reranker semantic text cannot be blank")
        digest = hashlib.sha256(self.semantic_text.encode("utf-8")).hexdigest()
        if digest != self.representation_reference.content_hash:
            raise ValueError("resolved text conflicts with representation content hash")
        if self.provenance.source_reference_digest != self.source_reference.identity_digest:
            raise ValueError("resolved reranker provenance conflicts with source")
        if self.provenance.representation_reference_id != (
            self.representation_reference.reference_id
        ):
            raise ValueError("resolved reranker provenance conflicts with representation")
        if self.title_metadata is not None:
            require_non_empty(self.title_metadata, "title_metadata")
            if self.semantic_text.strip() == self.title_metadata.strip():
                raise ValueError("title-only authorized reranker evidence is forbidden")
        if any(not isinstance(h, str) or not h.strip() for h in self.heading_path):
            raise ValueError("heading_path entries must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankerInputAuditV1:
    builder_revision: str
    provider_id: str
    model_id: str
    model_revision: str
    provider_configuration_digest: str
    query_preprocessing_identity: str
    document_preprocessing_identity: str
    tokenizer_identity: str
    tokenizer_revision: str
    tokenizer_configuration_digest: str
    query_hash: str
    preprocessed_query_hash: str
    semantic_text_hash: str
    preprocessed_document_hash: str
    query_token_count: int
    document_token_count: int
    special_token_count: int
    available_content_token_count: int
    retained_query_token_count: int
    retained_document_token_count: int
    retained_token_count: int
    query_truncated: bool
    document_truncated: bool
    retained_query_hash: str
    retained_document_hash: str
    rendered_input_hash: str
    retained_input_hash: str
    pair_identity: str
    pair_policy: RerankerPairPolicyV1
    title_metadata_included: bool = False
    builder_id: str = RERANKER_BUILDER_ID

    def __post_init__(self) -> None:
        if self.builder_id != RERANKER_BUILDER_ID:
            raise ValueError("reranker audit builder identity mismatch")
        if self.title_metadata_included:
            raise ValueError("title metadata cannot be included in provider input")
        for value, name in (
            (self.builder_revision, "builder_revision"),
            (self.provider_id, "provider_id"),
            (self.model_id, "model_id"),
            (self.model_revision, "model_revision"),
            (self.query_preprocessing_identity, "query_preprocessing_identity"),
            (self.document_preprocessing_identity, "document_preprocessing_identity"),
            (self.tokenizer_identity, "tokenizer_identity"),
            (self.tokenizer_revision, "tokenizer_revision"),
        ):
            require_non_empty(value, name)
        for value, name in (
            (self.provider_configuration_digest, "provider_configuration_digest"),
            (self.tokenizer_configuration_digest, "tokenizer_configuration_digest"),
            (self.query_hash, "query_hash"),
            (self.preprocessed_query_hash, "preprocessed_query_hash"),
            (self.semantic_text_hash, "semantic_text_hash"),
            (self.preprocessed_document_hash, "preprocessed_document_hash"),
            (self.retained_query_hash, "retained_query_hash"),
            (self.retained_document_hash, "retained_document_hash"),
            (self.rendered_input_hash, "rendered_input_hash"),
            (self.retained_input_hash, "retained_input_hash"),
            (self.pair_identity, "pair_identity"),
        ):
            require_sha256(value, name)
        if self.query_token_count < 1 or self.document_token_count < 1:
            raise ValueError("reranker query and document must each contain tokens")
        if not 1 <= self.special_token_count <= 255:
            raise ValueError("invalid pair special-token count")
        if self.available_content_token_count != 256 - self.special_token_count:
            raise ValueError("available content token count mismatch")
        if not 1 <= self.retained_query_token_count <= 96:
            raise ValueError("retained query token count violates policy")
        if self.retained_document_token_count < 1:
            raise ValueError("reranker must retain document semantic content")
        expected_total = (
            self.retained_query_token_count
            + self.retained_document_token_count
            + self.special_token_count
        )
        if self.retained_token_count != expected_total or expected_total > 256:
            raise ValueError("retained pair token accounting mismatch")
        if self.query_truncated != (self.retained_query_token_count < self.query_token_count):
            raise ValueError("query truncation flag mismatch")
        if self.document_truncated != (
            self.retained_document_token_count < self.document_token_count
        ):
            raise ValueError("document truncation flag mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankerInputAuditV2:
    builder_revision: str
    provider_id: str
    model_id: str
    model_revision: str
    provider_configuration_digest: str
    query_preprocessing_identity: str
    document_preprocessing_identity: str
    tokenizer_identity: str
    tokenizer_revision: str
    tokenizer_configuration_digest: str
    query_hash: str
    preprocessed_query_hash: str
    semantic_text_hash: str
    contextual_text_hash: str
    preprocessed_document_hash: str
    query_token_count: int
    document_token_count: int
    special_token_count: int
    available_content_token_count: int
    retained_query_token_count: int
    retained_document_token_count: int
    retained_token_count: int
    query_truncated: bool
    document_truncated: bool
    retained_query_hash: str
    retained_document_hash: str
    rendered_input_hash: str
    retained_input_hash: str
    pair_identity: str
    pair_policy: RerankerPairPolicyV2
    title_metadata_included: bool = True
    builder_id: str = RERANKER_BUILDER_ID
    schema_version: str = RERANKER_INPUT_AUDIT_V2

    def __post_init__(self) -> None:
        if self.builder_id != RERANKER_BUILDER_ID:
            raise ValueError("reranker audit builder identity mismatch")
        if not self.title_metadata_included:
            raise ValueError("V2 contextual audit requires title_metadata_included=True")
        for value, name in (
            (self.builder_revision, "builder_revision"),
            (self.provider_id, "provider_id"),
            (self.model_id, "model_id"),
            (self.model_revision, "model_revision"),
            (self.query_preprocessing_identity, "query_preprocessing_identity"),
            (self.document_preprocessing_identity, "document_preprocessing_identity"),
            (self.tokenizer_identity, "tokenizer_identity"),
            (self.tokenizer_revision, "tokenizer_revision"),
        ):
            require_non_empty(value, name)
        for value, name in (
            (self.provider_configuration_digest, "provider_configuration_digest"),
            (self.tokenizer_configuration_digest, "tokenizer_configuration_digest"),
            (self.query_hash, "query_hash"),
            (self.preprocessed_query_hash, "preprocessed_query_hash"),
            (self.semantic_text_hash, "semantic_text_hash"),
            (self.contextual_text_hash, "contextual_text_hash"),
            (self.preprocessed_document_hash, "preprocessed_document_hash"),
            (self.retained_query_hash, "retained_query_hash"),
            (self.retained_document_hash, "retained_document_hash"),
            (self.rendered_input_hash, "rendered_input_hash"),
            (self.retained_input_hash, "retained_input_hash"),
            (self.pair_identity, "pair_identity"),
        ):
            require_sha256(value, name)
        if self.query_token_count < 1 or self.document_token_count < 1:
            raise ValueError("reranker query and document must each contain tokens")
        if not 1 <= self.special_token_count <= 255:
            raise ValueError("invalid pair special-token count")
        if self.available_content_token_count != 256 - self.special_token_count:
            raise ValueError("available content token count mismatch")
        if not 1 <= self.retained_query_token_count <= 96:
            raise ValueError("retained query token count violates policy")
        if self.retained_document_token_count < 1:
            raise ValueError("reranker must retain document semantic content")
        expected_total = (
            self.retained_query_token_count
            + self.retained_document_token_count
            + self.special_token_count
        )
        if self.retained_token_count != expected_total or expected_total > 256:
            raise ValueError("retained pair token accounting mismatch")
        if self.query_truncated != (self.retained_query_token_count < self.query_token_count):
            raise ValueError("query truncation flag mismatch")
        if self.document_truncated != (
            self.retained_document_token_count < self.document_token_count
        ):
            raise ValueError("document truncation flag mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualRerankCandidateV3:
    candidate_id: UUID
    input_ordinal: int
    source_reference: LanguageEvidenceReferenceV3
    representation_reference: TextRepresentationReferenceV1
    semantic_text: str
    semantic_text_hash: str
    title_metadata: str | None
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]
    provenance: CandidateProvenanceV1
    input_audit: RerankerInputAuditV1 | RerankerInputAuditV2 | V2TypedCandidateAuditV1
    runtime_security: V2CandidateRuntimeSecurityBindingV1 | None = None
    semantic_text_origin: str = "authorized_evidence_resolution"
    heading_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.input_ordinal <= 199:
            raise ValueError("reranker input ordinal exceeds governed candidate bound")
        require_non_empty(self.semantic_text, "semantic_text")
        if not self.semantic_text.strip():
            raise ValueError("reranker semantic text cannot be blank")
        require_sha256(self.semantic_text_hash, "semantic_text_hash")
        if hashlib.sha256(self.semantic_text.encode("utf-8")).hexdigest() != (
            self.semantic_text_hash
        ):
            raise ValueError("reranker semantic text hash does not match semantic text")
        if self.semantic_text_origin != "authorized_evidence_resolution":
            raise ValueError("reranker semantic text must come from authorized resolution")
        if self.semantic_text_hash != self.representation_reference.content_hash:
            raise ValueError("reranker semantic text hash conflicts with representation")
        if self.semantic_text_hash != self.input_audit.semantic_text_hash:
            raise ValueError("reranker semantic text hash conflicts with audit")
        if self.provenance.source_reference_digest != self.source_reference.identity_digest:
            raise ValueError("candidate provenance conflicts with source reference")
        if self.provenance.representation_reference_id != (
            self.representation_reference.reference_id
        ):
            raise ValueError("candidate provenance conflicts with representation reference")
        if self.title_metadata is not None:
            require_non_empty(self.title_metadata, "title_metadata")
        if self.title_metadata is not None and (
            self.semantic_text.strip() == self.title_metadata.strip()
        ):
            raise ValueError("title-only reranker candidate is forbidden")
        if any(not isinstance(h, str) or not h.strip() for h in self.heading_path):
            raise ValueError("heading_path entries must not be blank")
        if isinstance(self.input_audit, RerankerInputAuditV2):
            contextual_repr = render_contextual_provider_text(
                title=self.title_metadata,
                heading_path=self.heading_path,
                semantic_text=self.semantic_text,
            )
            if hashlib.sha256(contextual_repr.encode("utf-8")).hexdigest() != (
                self.input_audit.contextual_text_hash
            ):
                raise ValueError("candidate contextual rendering conflicts with audit")
        if isinstance(self.input_audit, V2TypedCandidateAuditV1):
            contextual_repr = render_contextual_provider_text(
                title=self.title_metadata,
                heading_path=self.heading_path,
                semantic_text=self.semantic_text,
            )
            if hashlib.sha256(contextual_repr.encode("utf-8")).hexdigest() != (
                self.input_audit.contextual_text_hash
            ):
                raise ValueError("typed candidate contextual rendering conflicts with audit")
            if self.provenance.authorization_scope_digest != (
                self.input_audit.authorization_decision_fingerprint
            ):
                raise ValueError("typed candidate authorization binding conflicts with provenance")
