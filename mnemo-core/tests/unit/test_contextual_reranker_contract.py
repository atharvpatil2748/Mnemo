"""Unit tests for Governed V2 Contextual Reranker Contract & Invariants."""

import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest
from mnemo.models.multilingual import (
    LanguageEvidenceKindV3,
    LanguageEvidenceReferenceV3,
)
from mnemo.models.multilingual_reranking import (
    RERANKER_PAIR_POLICY_ID,
    RERANKER_PAIR_POLICY_V2_ID,
    AuthorizedRerankerEvidenceV1,
    CandidateProvenanceV1,
    MultilingualRerankCandidateV3,
    RerankerInputAuditV2,
    RerankerPairPolicyV1,
    RerankerPairPolicyV2,
    render_contextual_provider_text,
)
from mnemo.models.text_representations import (
    RepresentationAuthority,
    TextRepresentationReferenceV1,
    TextRepresentationType,
    text_representation_reference_id,
)


def _make_source_reference(
    text: str = "Exact canonical chunk text.",
) -> LanguageEvidenceReferenceV3:
    return LanguageEvidenceReferenceV3(
        notebook_id=uuid4(),
        source_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        kind=LanguageEvidenceKindV3.CANONICAL_CHUNK,
        evidence_id="chunk:sample-1",
        chunk_id="chunk:sample-1",
        source_content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _make_representation_reference(text: str) -> TextRepresentationReferenceV1:
    source = _make_source_reference(text)
    observation_id = uuid4()
    c_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ref_id = text_representation_reference_id(
        evidence_reference_digest=source.identity_digest,
        representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT,
        authority=RepresentationAuthority.ORIGINAL,
        content_hash=c_hash,
        observation_id=observation_id,
        derivation_id=None,
        source_generation_ids=(),
    )
    return TextRepresentationReferenceV1(
        reference_id=ref_id,
        evidence_reference=source,
        representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT,
        representation_authority=RepresentationAuthority.ORIGINAL,
        content_hash=c_hash,
        representation_observation_id=observation_id,
        representation_derivation_id=None,
        source_generation_ids=(),
        language_observation_references=(),
        script_observation_references=(),
    )


def _make_audit_v2(
    *,
    semantic_text: str,
    title: str | None = None,
    heading_path: tuple[str, ...] = (),
    corrupt_contextual_hash: bool = False,
    corrupt_rendered_hash: bool = False,
) -> RerankerInputAuditV2:
    policy = RerankerPairPolicyV2()
    contextual_doc = render_contextual_provider_text(
        title=title,
        heading_path=heading_path,
        semantic_text=semantic_text,
    )
    contextual_hash = hashlib.sha256(contextual_doc.encode("utf-8")).hexdigest()
    if corrupt_contextual_hash:
        contextual_hash = "f" * 64
    rendered_hash = "a" * 64
    if corrupt_rendered_hash:
        rendered_hash = "0" * 64

    return RerankerInputAuditV2(
        builder_revision="test-rev",
        provider_id="bge-m3-reranker",
        model_id="BAAI/bge-reranker-v2-m3",
        model_revision="main",
        provider_configuration_digest="b" * 64,
        query_preprocessing_identity="bge-m3-query-v1",
        document_preprocessing_identity="bge-m3-doc-v1",
        tokenizer_identity="xlm-roberta-bge-m3",
        tokenizer_revision="main",
        tokenizer_configuration_digest="c" * 64,
        query_hash="d" * 64,
        preprocessed_query_hash="d" * 64,
        semantic_text_hash=hashlib.sha256(semantic_text.encode("utf-8")).hexdigest(),
        contextual_text_hash=contextual_hash,
        preprocessed_document_hash="e" * 64,
        query_token_count=10,
        document_token_count=20,
        special_token_count=4,
        available_content_token_count=252,
        retained_query_token_count=10,
        retained_document_token_count=20,
        retained_token_count=34,
        query_truncated=False,
        document_truncated=False,
        retained_query_hash="f" * 64,
        retained_document_hash="f" * 64,
        rendered_input_hash=rendered_hash,
        retained_input_hash="a" * 64,
        pair_identity="a" * 64,
        pair_policy=policy,
    )


def test_canonical_content_hash_unaffected_by_contextual_rendering():
    """Verify that auxiliary contextual rendering never alters canonical content hash."""
    canonical_text = "शेतकऱ्यांची दैन्यावस्था आणि दुष्काळातील महसूल वसुली."
    canonical_hash = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

    contextual_text = render_contextual_provider_text(
        title="Shetkaryacha Asud",
        heading_path=("Pan 2",),
        semantic_text=canonical_text,
    )

    assert contextual_text.startswith("[Shetkaryacha Asud | Pan 2] ")
    assert hashlib.sha256(canonical_text.encode("utf-8")).hexdigest() == canonical_hash
    assert canonical_hash != hashlib.sha256(contextual_text.encode("utf-8")).hexdigest()


def test_deterministic_rendering():
    """Verify that contextual rendering is 100% deterministic regardless of extra whitespace."""
    text = "Important policy excerpt on finance."
    r1 = render_contextual_provider_text(
        title="  RBI   Report  2024  ",
        heading_path=("  Chapter  1  ", "  Section A  "),
        semantic_text=text,
    )
    r2 = render_contextual_provider_text(
        title="RBI Report 2024",
        heading_path=("Chapter 1", "Section A"),
        semantic_text=text,
    )
    assert (
        r1 == r2 == "[RBI Report 2024 | Chapter 1 > Section A] Important policy excerpt on finance."
    )


def test_candidate_with_title_and_heading_path():
    """Verify title and hierarchical heading formatting."""
    rendered = render_contextual_provider_text(
        title="Maharashtra Economic Survey",
        heading_path=("Macroeconomic Overview", "GSDP Growth"),
        semantic_text="The nominal GSDP expanded steadily.",
    )
    expected = (
        "[Maharashtra Economic Survey | Macroeconomic Overview > GSDP Growth] "
        "The nominal GSDP expanded steadily."
    )
    assert rendered == expected


def test_candidate_with_no_heading_path():
    """Verify graceful rendering when heading_path is empty."""
    text = "Machine learning gradient descent optimization."
    rendered = render_contextual_provider_text(
        title="Linear Regression",
        heading_path=(),
        semantic_text=text,
    )
    assert rendered == "[Linear Regression] Machine learning gradient descent optimization."


def test_candidate_with_empty_or_none_title():
    """Verify graceful rendering when title is None or blank string."""
    text = "Section content without document title."
    rendered_none = render_contextual_provider_text(
        title=None,
        heading_path=("Methods", "Data Collection"),
        semantic_text=text,
    )
    assert rendered_none == "[Methods > Data Collection] Section content without document title."

    rendered_empty = render_contextual_provider_text(
        title="   ",
        heading_path=(),
        semantic_text=text,
    )
    assert rendered_empty == text


def test_adjacent_marathi_pages_identical_book_title():
    """Verify identical book titles are disambiguated by section/heading."""
    text_p1 = "विद्येविना मती गेली..."
    text_p2 = "सावकारांनी शेत जमिनी जप्त केल्या..."

    p1_rendered = render_contextual_provider_text(
        title="Shetkaryacha Asud",
        heading_path=("Pan 1 - Prastavana",),
        semantic_text=text_p1,
    )
    p2_rendered = render_contextual_provider_text(
        title="Shetkaryacha Asud",
        heading_path=("Pan 2 - Dushkal",),
        semantic_text=text_p2,
    )

    assert "[Shetkaryacha Asud | Pan 1 - Prastavana]" in p1_rendered
    assert "[Shetkaryacha Asud | Pan 2 - Dushkal]" in p2_rendered
    assert p1_rendered != p2_rendered


def test_en_to_mr_bilingual_topical_collision():
    """Verify contextual anchors provide distinct language/report identities."""
    mr_text = "महाराष्ट्र आर्थिक पाहणीनुसार कृषी विकास दर..."
    en_text = "According to Maharashtra Economic Survey, agriculture growth rate..."

    mr_rendered = render_contextual_provider_text(
        title="Maharashtra Economic Survey Marathi",
        heading_path=("ठळक वैशिष्ट्ये",),
        semantic_text=mr_text,
    )
    en_rendered = render_contextual_provider_text(
        title="Maharashtra Economic Survey English",
        heading_path=("Highlights",),
        semantic_text=en_text,
    )

    assert "Maharashtra Economic Survey Marathi" in mr_rendered
    assert "Maharashtra Economic Survey English" in en_rendered


def test_contextual_hash_mismatch_fails_closed():
    """Candidate construction fails closed if contextual hash does not match rendered context."""
    text = "Exact canonical chunk text."
    source = _make_source_reference()
    repr_ref = _make_representation_reference(text)
    provenance = CandidateProvenanceV1(
        source_reference_digest=source.identity_digest,
        representation_reference_id=repr_ref.reference_id,
        authorization_scope_digest="a" * 64,
        retrieval_snapshot_identity="b" * 64,
        retrieval_paths_digest="c" * 64,
        fusion_policy_id="test-fusion",
        fusion_rank=1,
        source_generation_ids=(uuid4(),),
    )

    corrupt_audit = _make_audit_v2(
        semantic_text=text,
        title="Test Title",
        heading_path=("Heading 1",),
        corrupt_contextual_hash=True,
    )

    with pytest.raises(ValueError, match="candidate contextual rendering conflicts with audit"):
        MultilingualRerankCandidateV3(
            candidate_id=uuid4(),
            input_ordinal=0,
            source_reference=source,
            representation_reference=repr_ref,
            semantic_text=text,
            semantic_text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            title_metadata="Test Title",
            heading_path=("Heading 1",),
            language_observation_references=(),
            script_observation_references=(),
            provenance=provenance,
            input_audit=corrupt_audit,
        )


def test_canonical_semantic_hash_mismatch_fails_closed():
    """Candidate construction fails closed if semantic text hash does not match semantic text."""
    text = "Exact canonical chunk text."
    source = _make_source_reference()
    repr_ref = _make_representation_reference(text)
    provenance = CandidateProvenanceV1(
        source_reference_digest=source.identity_digest,
        representation_reference_id=repr_ref.reference_id,
        authorization_scope_digest="a" * 64,
        retrieval_snapshot_identity="b" * 64,
        retrieval_paths_digest="c" * 64,
        fusion_policy_id="test-fusion",
        fusion_rank=1,
        source_generation_ids=(uuid4(),),
    )

    audit = _make_audit_v2(
        semantic_text=text,
        title="Test Title",
        heading_path=(),
    )

    with pytest.raises(
        ValueError, match="reranker semantic text hash conflicts with representation"
    ):
        # Alter semantic text so it mismatches representation ref
        altered_repr = _make_representation_reference("Different text")
        MultilingualRerankCandidateV3(
            candidate_id=uuid4(),
            input_ordinal=0,
            source_reference=source,
            representation_reference=altered_repr,
            semantic_text=text,
            semantic_text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            title_metadata="Test Title",
            heading_path=(),
            language_observation_references=(),
            script_observation_references=(),
            provenance=provenance,
            input_audit=audit,
        )


def test_reranker_pair_policy_v1_frozen_invariants():
    """Test that the frozen V1 pair policy forbids title metadata in provider input."""
    policy = RerankerPairPolicyV1()
    assert policy.policy_id == RERANKER_PAIR_POLICY_ID
    assert policy.title_metadata_policy == "exclude_from_provider_input"

    with pytest.raises(
        ValueError, match="reranker pair policy differs from the governed V2 policy"
    ):
        RerankerPairPolicyV1(title_metadata_policy="include_in_provider_input")


def test_reranker_pair_policy_v2_invariants():
    """Test that V2 contextual pair policy enforces title and heading context inclusion."""
    policy = RerankerPairPolicyV2()
    assert policy.policy_id == RERANKER_PAIR_POLICY_V2_ID
    assert policy.title_metadata_policy == "include_in_provider_input_with_heading_path"
    assert policy.rendering_policy == "bracket_title_heading_prefix_token_id_pair"

    with pytest.raises(
        ValueError, match="reranker pair policy differs from governed V2 contextual policy"
    ):
        RerankerPairPolicyV2(pair_max_tokens=512)


def test_authorized_reranker_evidence_heading_path_validation():
    """Test that AuthorizedRerankerEvidenceV1 accepts and validates heading_path."""
    text = "Authorized semantic chunk."
    source = _make_source_reference()
    repr_ref = _make_representation_reference(text)
    provenance = CandidateProvenanceV1(
        source_reference_digest=source.identity_digest,
        representation_reference_id=repr_ref.reference_id,
        authorization_scope_digest="a" * 64,
        retrieval_snapshot_identity="b" * 64,
        retrieval_paths_digest="c" * 64,
        fusion_policy_id="test-fusion",
        fusion_rank=1,
        source_generation_ids=(uuid4(),),
    )

    # Valid heading path
    evidence = AuthorizedRerankerEvidenceV1(
        candidate_id=uuid4(),
        source_reference=source,
        representation_reference=repr_ref,
        semantic_text=text,
        title_metadata="Book Title",
        language_observation_references=(),
        script_observation_references=(),
        provenance=provenance,
        heading_path=("Chapter 1", "Section 2"),
    )
    assert evidence.heading_path == ("Chapter 1", "Section 2")

    # Blank entry in heading path raises ValueError
    with pytest.raises(ValueError, match="heading_path entries must not be blank"):
        AuthorizedRerankerEvidenceV1(
            candidate_id=uuid4(),
            source_reference=source,
            representation_reference=repr_ref,
            semantic_text=text,
            title_metadata="Book Title",
            language_observation_references=(),
            script_observation_references=(),
            provenance=provenance,
            heading_path=("Chapter 1", "   "),
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"builder_id": "wrong"}, "builder identity"),
        ({"title_metadata_included": False}, "requires title_metadata"),
        ({"provider_id": ""}, "provider_id"),
        ({"query_hash": "bad"}, "query_hash"),
        ({"query_token_count": 0}, "must each contain tokens"),
        ({"document_token_count": 0}, "must each contain tokens"),
        ({"special_token_count": 0}, "special-token count"),
        ({"special_token_count": 256}, "special-token count"),
        ({"available_content_token_count": 251}, "content token count"),
        ({"retained_query_token_count": 0}, "query token count"),
        ({"retained_query_token_count": 97}, "query token count"),
        ({"retained_document_token_count": 0}, "retain document"),
        ({"retained_token_count": 33}, "token accounting"),
        (
            {
                "retained_query_token_count": 96,
                "retained_document_token_count": 157,
                "retained_token_count": 257,
            },
            "token accounting",
        ),
        ({"query_truncated": True}, "query truncation flag"),
        ({"document_truncated": True}, "document truncation flag"),
    ),
)
def test_contextual_audit_rejects_each_invalid_contract_branch(
    changes,
    message,  # type: ignore[no-untyped-def]
):
    audit = _make_audit_v2(semantic_text="exact")
    with pytest.raises(ValueError, match=message):
        replace(audit, **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"fusion_rank": 0}, "fusion_rank"),
        ({"fusion_rank": 1001}, "governed bound"),
        ({"fusion_policy_id": ""}, "fusion_policy_id"),
        ({"source_reference_digest": "bad"}, "source_reference_digest"),
    ),
)
def test_candidate_provenance_rejects_invalid_security_bindings(
    changes,
    message,  # type: ignore[no-untyped-def]
):
    generation = uuid4()
    valid = CandidateProvenanceV1(
        source_reference_digest="a" * 64,
        representation_reference_id=uuid4(),
        authorization_scope_digest="b" * 64,
        retrieval_snapshot_identity="c" * 64,
        retrieval_paths_digest="d" * 64,
        fusion_policy_id="rrf-v1",
        fusion_rank=1,
        source_generation_ids=(generation,),
    )
    with pytest.raises(ValueError, match=message):
        replace(valid, **changes)
    with pytest.raises(ValueError, match="must be unique"):
        replace(valid, source_generation_ids=(generation, generation))
