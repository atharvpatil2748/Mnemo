"""Acceptance tests for Phase 4 Module 4.2 GenericChunker."""

import re
import socket
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from mnemo.chunkers import GenericChunker
from mnemo.interfaces import (
    ChunkerInterfaceV2,
    ChunkingContext,
    ChunkingOptions,
    DependencyUnavailableError,
    UnsupportedError,
)
from mnemo.models import (
    Block,
    BlockSpan,
    CaptionBlock,
    ChunkDraft,
    ChunkType,
    CodeBlock,
    DocType,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionStatus,
    EquationBlock,
    FrozenMetadata,
    HeadingBlock,
    ImageBlock,
    ParsedDocument,
    TableBlock,
    TextBlock,
)


class WordCounter:
    tokenizer_id = "tests/words;adapter=v1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def count(self, text: str) -> int:
        self.calls.append(text)
        return len(re.findall(r"\S+", text))


class CharacterCounter:
    tokenizer_id = "tests/characters;adapter=v1"

    def count(self, text: str) -> int:
        return len(text)


class MissingCounter:
    tokenizer_id = "tests/missing;adapter=v1"

    def count(self, text: str) -> int:
        raise DependencyUnavailableError("tokenizer unavailable", retryable=False)


def _document(*blocks: Block, doc_type: DocType = DocType.GENERIC) -> ParsedDocument:
    return ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="en",
        doc_type=doc_type,
    )


def _context(document: ParsedDocument, *, target: int = 20, maximum: int = 40) -> ChunkingContext:
    return ChunkingContext(
        document_version=DocumentVersion(
            version_id=uuid4(),
            document_id=uuid4(),
            content_hash=document.metadata.content_hash,
            metadata=document.metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        options=ChunkingOptions(target_tokens=target, max_tokens=maximum),
    )


def _words(count: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def test_v2_contract_capabilities_and_flat_hierarchy() -> None:
    chunker = GenericChunker()
    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.GENERIC,)
    capabilities = chunker.capabilities()
    assert capabilities.supported_doc_types == (DocType.GENERIC,)
    assert capabilities.preserves_semantic_boundaries
    assert not capabilities.supports_parent_child
    assert not capabilities.supports_overlap

    document = _document(TextBlock(ordinal=0, text=_words(20)))
    drafts = chunker.chunk(document, _context(document), WordCounter())
    assert all(draft.parent_index is None for draft in drafts)


def test_basic_paragraphs_pack_near_target_with_same_block_provenance() -> None:
    document = _document(TextBlock(ordinal=0, text=f"{_words(10, 'a')}\n\n{_words(10, 'b')}"))
    drafts = GenericChunker().chunk(document, _context(document), WordCounter())
    assert len(drafts) == 1
    assert drafts[0].source_span == BlockSpan(start_ordinal=0, end_ordinal=0)
    assert drafts[0].text == f"{_words(10, 'a')}\n\n{_words(10, 'b')}"
    assert drafts[0].chunk_type is ChunkType.PASSAGE


def test_adjacent_blocks_form_contiguous_multi_block_span() -> None:
    document = _document(
        TextBlock(ordinal=0, text=_words(8, "a"), page_number=1),
        TextBlock(ordinal=1, text=_words(8, "b"), page_number=2),
    )
    draft = GenericChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.source_span == BlockSpan(start_ordinal=0, end_ordinal=1)
    assert draft.position.page_number == 1
    assert draft.position.section_index == 0
    assert draft.position.chunk_index_in_section == 0


def test_skipped_image_prevents_disjoint_span() -> None:
    document = _document(
        TextBlock(ordinal=0, text=_words(8, "a")),
        ImageBlock(ordinal=1, asset_id=uuid4()),
        TextBlock(ordinal=2, text=_words(8, "b")),
    )
    drafts = GenericChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.source_span for draft in drafts) == (
        BlockSpan(start_ordinal=0, end_ordinal=0),
        BlockSpan(start_ordinal=2, end_ordinal=2),
    )


def test_heading_context_is_source_derived_and_isolates_sections() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter", level=1),
        TextBlock(ordinal=1, text=_words(15, "a")),
        HeadingBlock(ordinal=2, text="Topic", level=2),
        TextBlock(ordinal=3, text=_words(15, "b")),
        HeadingBlock(ordinal=4, text="Next", level=1),
        TextBlock(ordinal=5, text=_words(15, "c")),
    )
    drafts = GenericChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.heading_path for draft in drafts) == (
        ("Chapter",),
        ("Chapter", "Topic"),
        ("Next",),
    )
    assert tuple(draft.position.section_index for draft in drafts) == (1, 2, 3)


def test_sentence_then_word_fallback_never_exceeds_effective_maximum() -> None:
    sentences = " ".join(f"{_words(8, str(index))}." for index in range(4))
    document = _document(TextBlock(ordinal=0, text=sentences))
    counter = WordCounter()
    drafts = GenericChunker().chunk(document, _context(document, target=15, maximum=100), counter)
    assert drafts
    assert all(counter.count(draft.text) <= 30 for draft in drafts)
    assert all(counter.count(draft.text) >= 15 for draft in drafts)

    one_sentence = _words(70) + "."
    split_document = _document(TextBlock(ordinal=0, text=one_sentence))
    split = GenericChunker().chunk(
        split_document, _context(split_document, target=20, maximum=40), counter
    )
    assert len(split) == 3
    assert all(counter.count(draft.text) <= 40 for draft in split)
    assert len({draft.source_span for draft in split}) == 1


def test_oversized_word_and_atomic_blocks_fail_without_partial_output() -> None:
    word_document = _document(TextBlock(ordinal=0, text="x" * 31))
    with pytest.raises(UnsupportedError):
        GenericChunker().chunk(
            word_document,
            _context(word_document, target=15, maximum=30),
            CharacterCounter(),
        )

    table_document = _document(TableBlock(ordinal=0, rows=(("x" * 31,),)))
    with pytest.raises(UnsupportedError):
        GenericChunker().chunk(
            table_document,
            _context(table_document, target=15, maximum=30),
            CharacterCounter(),
        )

    equation_document = _document(EquationBlock(ordinal=0, latex="x" * 31))
    with pytest.raises(UnsupportedError):
        GenericChunker().chunk(
            equation_document,
            _context(equation_document, target=15, maximum=30),
            CharacterCounter(),
        )


def test_canonical_block_text_types_are_preserved() -> None:
    document = _document(
        TableBlock(ordinal=0, rows=(("Name", "Value"), ("alpha", "one"))),
        CodeBlock(ordinal=1, code="def f():\n    return 1", code_language="python"),
        CaptionBlock(ordinal=2, text="Figure caption", target_ordinal=0),
        ImageBlock(ordinal=3, asset_id=uuid4(), alt_text="Diagram alternative text"),
    )
    drafts = GenericChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.chunk_type for draft in drafts) == (
        ChunkType.PASSAGE,
        ChunkType.CODE,
        ChunkType.CAPTION,
    )
    assert drafts[0].text == "Name\tValue\nalpha\tone"
    assert drafts[1].text.startswith("def f()")
    assert "Figure caption" in drafts[2].text
    assert "Diagram alternative text" in drafts[2].text


def test_empty_and_irrelevant_documents_return_no_drafts() -> None:
    empty = _document()
    assert GenericChunker().chunk(empty, _context(empty), WordCounter()) == ()
    irrelevant = _document(
        HeadingBlock(ordinal=0, text="Only heading", level=1),
        ImageBlock(ordinal=1, asset_id=uuid4()),
        TableBlock(ordinal=2, rows=(("",),)),
    )
    assert GenericChunker().chunk(irrelevant, _context(irrelevant), WordCounter()) == ()


@pytest.mark.parametrize(
    "text",
    [
        "नमस्ते दुनिया। यह बहुभाषी पाठ है।",
        "你好\uff0c世界。これは多言語テキストです。",
        "café cafe\u0301 👨\u200d👩\u200d👧\u200d👦",
        "if (value >= 10) { return value * 2; }",
    ],
)
def test_unicode_multilingual_and_code_like_text_are_deterministic(text: str) -> None:
    document = _document(TextBlock(ordinal=0, text=text))
    chunker = GenericChunker()
    first = chunker.chunk(document, _context(document), WordCounter())
    second = chunker.chunk(document, _context(document), WordCounter())
    assert first == second
    assert first[0].text == text
    assert first[0].metadata == FrozenMetadata({"chunker.generic.strategy": "recursive"})


def test_supplied_counter_is_used_and_dependency_failure_propagates() -> None:
    document = _document(TextBlock(ordinal=0, text=_words(20)))
    counter = WordCounter()
    GenericChunker().chunk(document, _context(document), counter)
    assert counter.calls
    with pytest.raises(DependencyUnavailableError):
        GenericChunker().chunk(document, _context(document), MissingCounter())


def test_strategy_has_no_network_side_effect_and_does_not_mutate_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(TextBlock(ordinal=0, text=_words(20)))
    before = document

    def reject_network(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", reject_network)
    drafts = GenericChunker().chunk(document, _context(document), WordCounter())
    assert document is before
    assert drafts
    with pytest.raises(FrozenInstanceError):
        drafts[0].text = "changed"  # type: ignore[misc]


def test_non_generic_document_is_rejected() -> None:
    document = _document(TextBlock(ordinal=0, text="paper"), doc_type=DocType.PAPER)
    with pytest.raises(UnsupportedError):
        GenericChunker().chunk(document, _context(document), WordCounter())


def test_output_invariants_across_varied_documents() -> None:
    counter = WordCounter()
    documents = (
        _document(TextBlock(ordinal=0, text=_words(100))),
        _document(
            TextBlock(ordinal=0, text=f"{_words(5)}\n\n{_words(30)}"),
            TextBlock(ordinal=1, text=_words(12)),
        ),
    )
    for document in documents:
        drafts = GenericChunker().chunk(document, _context(document), counter)
        assert all(isinstance(draft, ChunkDraft) and draft.text for draft in drafts)
        assert all(draft.parent_index is None for draft in drafts)
        assert all(
            draft.source_span.start_ordinal <= draft.source_span.end_ordinal for draft in drafts
        )
        assert all(draft.source_span.end_ordinal < len(document.blocks) for draft in drafts)
        assert all(counter.count(draft.text) <= 40 for draft in drafts)
