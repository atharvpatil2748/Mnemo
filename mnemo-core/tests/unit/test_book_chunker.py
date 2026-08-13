"""Acceptance and invariant tests for Phase 4 Module 4.3 BookChunker."""

import re
import socket
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from mnemo.chunkers import BookChunker, ChunkerDispatcher
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
from mnemo.registry import PluginRegistry


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


@dataclass(slots=True)
class Plugin:
    name: str
    callback: Callable[[PluginRegistry], None]
    version: str = "1.0.0"
    core_version_range: str = ">=0.1.0,<1.0.0"

    def capabilities(self) -> tuple[str, ...]:
        return ("chunker",)

    def register(self, registry: PluginRegistry) -> None:
        self.callback(registry)


def _words(count: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def _document(
    *blocks: Block,
    doc_type: DocType = DocType.BOOK,
    title: str | None = "A Source Book",
) -> ParsedDocument:
    return ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(content_hash="b" * 64, title=title),
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


def _registry(chunker: BookChunker) -> PluginRegistry:
    registry = PluginRegistry(core_version="0.15.0")

    def register(current: PluginRegistry) -> None:
        current.register_chunker_v2(DocType.BOOK, chunker, priority=10, plugin_name="book-test")

    registry.load_plugin(Plugin("book-test", register))
    registry.freeze()
    return registry


def test_v2_contract_capabilities_and_registry_slot() -> None:
    chunker = BookChunker()
    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.BOOK,)
    capabilities = chunker.capabilities()
    assert capabilities.supported_doc_types == (DocType.BOOK,)
    assert capabilities.preserves_semantic_boundaries
    assert not capabilities.supports_parent_child
    assert not capabilities.supports_overlap

    registry = _registry(chunker)
    assert registry.resolve_chunker_v2(DocType.BOOK) is chunker
    assert registry.resolve_chunker(DocType.BOOK) is None


def test_simple_chapters_never_merge_even_with_large_target() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter One", level=1),
        TextBlock(ordinal=1, text=_words(8, "first")),
        TextBlock(ordinal=2, text=_words(5, "tail")),
        HeadingBlock(ordinal=3, text="Chapter Two", level=1),
        TextBlock(ordinal=4, text=_words(8, "second")),
    )
    drafts = BookChunker().chunk(
        document, _context(document, target=100, maximum=200), WordCounter()
    )
    assert len(drafts) == 2
    assert drafts[0].source_span == BlockSpan(start_ordinal=1, end_ordinal=2)
    assert drafts[1].source_span == BlockSpan(start_ordinal=4, end_ordinal=4)
    assert "second0" not in drafts[0].text
    assert "tail0" not in drafts[1].text


def test_part_chapter_section_subsection_heading_hierarchy() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="PART I", level=1),
        HeadingBlock(ordinal=1, text="CHAPTER 1", level=1),
        HeadingBlock(ordinal=2, text="1.1 Foundations", level=1),
        HeadingBlock(ordinal=3, text="1.1.1 First Principle", level=1),
        TextBlock(ordinal=4, text=_words(20)),
    )
    draft = BookChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.heading_path == (
        "A Source Book",
        "PART I",
        "CHAPTER 1",
        "1.1 Foundations",
        "1.1.1 First Principle",
    )
    assert draft.position.section_index == 4


def test_canonical_heading_levels_drive_unnumbered_books() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="The First Principle", level=1),
        HeadingBlock(ordinal=1, text="An Observation", level=2),
        TextBlock(ordinal=2, text=_words(15)),
    )
    draft = BookChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.heading_path == (
        "A Source Book",
        "The First Principle",
        "An Observation",
    )


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("Part IV", ("Part IV",)),
        ("Chapter IX", ("Chapter IX",)),
        ("Appendix A", ("Appendix A",)),
        ("Preface", ("Preface",)),
        ("Bibliography", ("Bibliography",)),
    ],
)
def test_roman_numbering_front_and_back_matter(heading: str, expected: tuple[str, ...]) -> None:
    document = _document(
        HeadingBlock(ordinal=0, text=heading, level=1),
        TextBlock(ordinal=1, text=_words(15)),
    )
    draft = BookChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.heading_path[1:] == expected


def test_valid_toc_with_page_numbers_is_extracted_and_excluded() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Contents", level=1),
        TextBlock(
            ordinal=1,
            text="Part I ........ 1\nChapter 1 ........ 3\n1.1 Foundations ........ 5",
        ),
        HeadingBlock(ordinal=2, text="Part I", level=1),
        HeadingBlock(ordinal=3, text="Chapter 1", level=1),
        HeadingBlock(ordinal=4, text="1.1 Foundations", level=1),
        TextBlock(ordinal=5, text=_words(20, "body")),
    )
    draft = BookChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.source_span == BlockSpan(start_ordinal=5, end_ordinal=5)
    assert draft.heading_path[1:] == ("Part I", "Chapter 1", "1.1 Foundations")
    assert draft.metadata["chunker.book.hierarchy_source"] == "toc"
    assert "Contents" not in draft.text


def test_pdf_clickable_toc_and_word_numbered_chapter_title_are_preserved() -> None:
    document = _document(
        HeadingBlock(
            ordinal=0,
            text="Table of Contents with clickable chapter links:",
            level=1,
        ),
        TextBlock(
            ordinal=1,
            text="CHAPTER ONE!40\nCHAPTER ELEVEN!577\nCHAPTER EIGHTEEN!827",
        ),
        HeadingBlock(ordinal=2, text="CHAPTER ELEVEN", level=1, page_number=577),
        ImageBlock(ordinal=3, asset_id=uuid4(), page_number=577),
        HeadingBlock(ordinal=4, text="The Universal Form", level=1, page_number=577),
        HeadingBlock(ordinal=5, text="Revealed", level=1, page_number=577),
        TextBlock(ordinal=6, text=_words(20, "body"), page_number=577),
    )
    draft = BookChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.source_span == BlockSpan(start_ordinal=6, end_ordinal=6)
    assert draft.heading_path[1:] == (
        "CHAPTER ELEVEN",
        "The Universal Form Revealed",
    )
    assert draft.metadata["chunker.book.hierarchy_source"] == "toc"


def test_word_numbered_chapter_does_not_keep_front_matter_as_parent() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Introduction", level=1),
        TextBlock(ordinal=1, text=_words(15, "intro")),
        HeadingBlock(ordinal=2, text="CHAPTER EIGHTEEN", level=1, page_number=10),
        HeadingBlock(ordinal=3, text="Conclusion", level=1, page_number=10),
        TextBlock(ordinal=4, text=_words(15, "body"), page_number=10),
    )
    drafts = BookChunker().chunk(document, _context(document), WordCounter())
    assert drafts[-1].heading_path[1:] == ("CHAPTER EIGHTEEN", "Conclusion")


def test_valid_toc_without_page_numbers_in_one_block_is_excluded() -> None:
    document = _document(
        TextBlock(
            ordinal=0,
            text="Contents\nChapter One\nChapter Two\nChapter Three\nAppendix",
        ),
        HeadingBlock(ordinal=1, text="Chapter One", level=1),
        TextBlock(ordinal=2, text=_words(20)),
    )
    draft = BookChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.source_span.start_ordinal == 2
    assert draft.metadata["chunker.book.hierarchy_source"] == "toc"


def test_false_positive_contents_heading_preserves_following_prose() -> None:
    prose = "Contents matter to readers because structure improves comprehension and recall."
    document = _document(
        HeadingBlock(ordinal=0, text="Contents", level=1),
        TextBlock(ordinal=1, text=prose),
    )
    drafts = BookChunker().chunk(document, _context(document), WordCounter())
    assert drafts[0].text == prose
    assert drafts[0].metadata["chunker.book.hierarchy_source"] == "headings"


def test_no_toc_uses_heading_inference_deterministically() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter 1", level=1),
        HeadingBlock(ordinal=1, text="1.1 Topic", level=1),
        TextBlock(ordinal=2, text=_words(20)),
    )
    first = BookChunker().chunk(document, _context(document), WordCounter())
    second = BookChunker().chunk(document, _context(document), WordCounter())
    assert first == second
    assert first[0].heading_path[1:] == ("Chapter 1", "1.1 Topic")


def test_informative_canonical_levels_take_precedence_over_text_patterns() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter 1", level=1),
        HeadingBlock(ordinal=1, text="Part IV", level=2),
        TextBlock(ordinal=2, text=_words(20)),
    )
    draft = BookChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.heading_path[1:] == ("Chapter 1", "Part IV")


def test_source_authored_summary_and_metadata_marked_verbatim() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter 1", level=1),
        HeadingBlock(ordinal=1, text="Chapter Summary", level=2),
        TextBlock(ordinal=2, text=_words(18, "summary")),
        HeadingBlock(ordinal=3, text="Definitions", level=2),
        TextBlock(
            ordinal=4,
            text=_words(35, "definition"),
            metadata=FrozenMetadata({"parser.block_role": "definition"}),
        ),
        HeadingBlock(ordinal=5, text="Discussion", level=2),
        TextBlock(ordinal=6, text=_words(20, "passage")),
    )
    drafts = BookChunker().chunk(
        document, _context(document, target=200, maximum=400), WordCounter()
    )
    assert tuple(draft.chunk_type for draft in drafts) == (
        ChunkType.SUMMARY,
        ChunkType.VERBATIM,
        ChunkType.PASSAGE,
    )
    assert all(draft.text for draft in drafts)
    assert all(draft.parent_index is None for draft in drafts)


def test_no_labeled_summary_or_verbatim_evidence_fabricates_neither() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter 1", level=1),
        TextBlock(ordinal=1, text=_words(30)),
    )
    drafts = BookChunker().chunk(document, _context(document), WordCounter())
    assert {draft.chunk_type for draft in drafts} == {ChunkType.PASSAGE}


def test_passages_pack_near_configured_book_target() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter 1", level=1),
        TextBlock(ordinal=1, text=_words(100, "a")),
        TextBlock(ordinal=2, text=_words(100, "b")),
        TextBlock(ordinal=3, text=_words(100, "c")),
    )
    counter = WordCounter()
    drafts = BookChunker().chunk(document, _context(document, target=200, maximum=500), counter)
    assert tuple(counter.count(draft.text) for draft in drafts) == (200, 100)
    assert drafts[0].source_span == BlockSpan(start_ordinal=1, end_ordinal=2)


def test_oversized_paragraph_uses_sentence_then_word_boundaries_without_truncation() -> None:
    text = " ".join(f"{_words(12, str(index))}." for index in range(6))
    document = _document(TextBlock(ordinal=0, text=text))
    counter = WordCounter()
    drafts = BookChunker().chunk(document, _context(document, target=20, maximum=40), counter)
    assert all(counter.count(draft.text) <= 40 for draft in drafts)
    assert " ".join(draft.text for draft in drafts).replace("  ", " ") == text
    assert len({draft.source_span for draft in drafts}) == 1

    one_sentence = _words(90) + "."
    one = _document(TextBlock(ordinal=0, text=one_sentence))
    split = BookChunker().chunk(one, _context(one, target=20, maximum=40), counter)
    assert all(counter.count(draft.text) <= 40 for draft in split)
    assert " ".join(draft.text for draft in split) == one_sentence


def test_oversized_word_and_atomic_special_blocks_fail_closed() -> None:
    for document in (
        _document(TextBlock(ordinal=0, text="x" * 31)),
        _document(TableBlock(ordinal=0, rows=(("x" * 31,),))),
        _document(EquationBlock(ordinal=0, latex="x" * 31)),
        _document(CodeBlock(ordinal=0, code="x" * 31)),
    ):
        with pytest.raises(UnsupportedError):
            BookChunker().chunk(
                document,
                _context(document, target=15, maximum=30),
                CharacterCounter(),
            )


def test_special_blocks_remain_inside_their_chapter_and_preserve_types() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter One", level=1),
        TableBlock(ordinal=1, rows=(("term", "value"),)),
        EquationBlock(ordinal=2, latex="x^2 + y^2 = z^2"),
        CodeBlock(ordinal=3, code="value = value + 1", code_language="python"),
        CaptionBlock(ordinal=4, text="A source caption", target_ordinal=1),
        ImageBlock(ordinal=5, asset_id=uuid4(), alt_text="A source image description"),
        HeadingBlock(ordinal=6, text="Chapter Two", level=1),
        TextBlock(ordinal=7, text=_words(20)),
    )
    drafts = BookChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.chunk_type for draft in drafts[:4]) == (
        ChunkType.PASSAGE,
        ChunkType.EQUATION,
        ChunkType.CODE,
        ChunkType.CAPTION,
    )
    assert all(draft.source_span.end_ordinal <= 5 for draft in drafts[:-1])
    assert drafts[-1].source_span == BlockSpan(start_ordinal=7, end_ordinal=7)


@pytest.mark.parametrize(
    "text",
    [
        "नमस्ते दुनिया। यह पुस्तक का एक अध्याय है।",
        "第一章 思考。これは本の章です。",
        "café cafe\u0301 👨\u200d👩\u200d👧\u200d👦",
    ],
)
def test_multilingual_unicode_content_and_headings_are_deterministic(text: str) -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="अध्याय 一", level=1),
        TextBlock(ordinal=1, text=text),
    )
    chunker = BookChunker()
    assert chunker.chunk(document, _context(document), WordCounter()) == chunker.chunk(
        document, _context(document), WordCounter()
    )


def test_supplied_counter_dependency_failure_and_no_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(TextBlock(ordinal=0, text=_words(20)))
    counter = WordCounter()
    before = document

    def reject_network(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", reject_network)
    drafts = BookChunker().chunk(document, _context(document), counter)
    assert counter.calls
    assert document is before
    with pytest.raises(FrozenInstanceError):
        drafts[0].text = "changed"  # type: ignore[misc]
    with pytest.raises(DependencyUnavailableError):
        BookChunker().chunk(document, _context(document), MissingCounter())


def test_dispatcher_finalizes_book_drafts_without_fabricated_relationships() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter 1", level=1),
        TextBlock(ordinal=1, text=_words(20)),
    )
    context = _context(document)
    registry = _registry(BookChunker())
    chunks = ChunkerDispatcher(registry, WordCounter()).dispatch(document, context)
    assert len(chunks) == 1
    assert chunks[0].parent_chunk_id is None
    assert chunks[0].sibling_ids == ()
    assert chunks[0].source_span == BlockSpan(start_ordinal=1, end_ordinal=1)


def test_empty_irrelevant_and_non_book_inputs() -> None:
    empty = _document()
    assert BookChunker().chunk(empty, _context(empty), WordCounter()) == ()
    irrelevant = _document(
        HeadingBlock(ordinal=0, text="Chapter 1", level=1),
        ImageBlock(ordinal=1, asset_id=uuid4()),
    )
    assert BookChunker().chunk(irrelevant, _context(irrelevant), WordCounter()) == ()
    generic = _document(TextBlock(ordinal=0, text="text"), doc_type=DocType.GENERIC)
    with pytest.raises(UnsupportedError):
        BookChunker().chunk(generic, _context(generic), WordCounter())


def test_all_output_invariants_and_no_disjoint_provenance() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Chapter 1", level=1),
        TextBlock(ordinal=1, text=_words(8, "a")),
        ImageBlock(ordinal=2, asset_id=uuid4()),
        TextBlock(ordinal=3, text=_words(8, "b")),
    )
    drafts = BookChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.source_span for draft in drafts) == (
        BlockSpan(start_ordinal=1, end_ordinal=1),
        BlockSpan(start_ordinal=3, end_ordinal=3),
    )
    assert all(draft.text and draft.parent_index is None for draft in drafts)
    assert all(draft.source_span.end_ordinal < len(document.blocks) for draft in drafts)
