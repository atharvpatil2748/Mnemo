"""Acceptance and invariant tests for Phase 4 Module 4.6 MarkdownChunker."""

import re
import socket
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from types import MappingProxyType
from uuid import uuid4

import pytest
from mnemo.chunkers import ChunkerDispatcher, MarkdownChunker
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion import DocumentCanonicalizer
from mnemo.interfaces import (
    ChunkerInterfaceV2,
    ChunkingContext,
    ChunkingOptions,
    DependencyUnavailableError,
    UnsupportedError,
)
from mnemo.interfaces.types import FileMetadata
from mnemo.models import (
    BlockSpan,
    ChunkType,
    DocType,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    ParsedDocument,
    TextBlock,
)
from mnemo.parsers import MarkdownParser
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
    version: str = "1.0.0"
    core_version_range: str = ">=0.1.0,<1.0.0"

    def capabilities(self) -> tuple[str, ...]:
        return ("chunker",)

    def register(self, registry: PluginRegistry) -> None:
        registry.register_chunker_v2(
            DocType.MARKDOWN,
            MarkdownChunker(),
            priority=10,
            plugin_name=self.name,
        )


def _document(markdown: str) -> ParsedDocument:
    data = markdown.encode()
    digest = sha256(data).hexdigest()
    parsed = MarkdownParser().parse(
        data,
        "test.md",
        FileMetadata(content_hash=digest, size_bytes=len(data), mime_type="text/markdown"),
    )
    cleaned = DocumentCleaner().clean(parsed)
    canonical = DocumentCanonicalizer().canonicalize(cleaned, MappingProxyType({}))
    return replace(canonical, doc_type=DocType.MARKDOWN)


def _context(
    document: ParsedDocument,
    *,
    target: int = 20,
    maximum: int = 40,
) -> ChunkingContext:
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


def _registry() -> PluginRegistry:
    registry = PluginRegistry(core_version="0.15.0")
    registry.load_plugin(Plugin("markdown-test"))
    registry.freeze()
    return registry


def _words(count: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def test_v2_contract_capabilities_and_registration_isolation() -> None:
    chunker = MarkdownChunker()
    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.MARKDOWN,)
    capabilities = chunker.capabilities()
    assert capabilities.supported_doc_types == (DocType.MARKDOWN,)
    assert capabilities.preserves_semantic_boundaries
    assert not capabilities.supports_parent_child
    assert not capabilities.supports_overlap
    registry = _registry()
    assert isinstance(registry.resolve_chunker_v2(DocType.MARKDOWN), MarkdownChunker)
    assert registry.resolve_chunker(DocType.MARKDOWN) is None


def test_root_content_and_heading_hierarchy_are_deterministic() -> None:
    document = _document(
        f"Root {_words(14, 'root')}.\n\n"
        f"# Guide\n\n{_words(15, 'guide')}\n\n"
        f"## Install\n\n{_words(15, 'install')}\n\n"
        f"### Windows\n\n{_words(15, 'windows')}\n\n"
        f"#### Notes\n\n{_words(15, 'notes')}\n"
    )
    drafts = MarkdownChunker().chunk(
        document, _context(document, target=100, maximum=200), WordCounter()
    )
    assert tuple(draft.heading_path for draft in drafts) == (
        (),
        ("Guide",),
        ("Guide", "Install"),
        ("Guide", "Install", "Windows"),
        ("Guide", "Install", "Windows", "Notes"),
    )
    assert tuple(draft.position.section_index for draft in drafts) == (0, 1, 2, 3, 4)
    assert all(draft.parent_index is None for draft in drafts)


def test_paragraphs_pack_inside_one_heading_section_with_contiguous_span() -> None:
    document = _document(f"# Topic\n\n{_words(8, 'a')}\n\n{_words(8, 'b')}\n")
    draft = MarkdownChunker().chunk(
        document, _context(document, target=20, maximum=40), WordCounter()
    )[0]
    assert draft.text == f"{_words(8, 'a')}\n\n{_words(8, 'b')}"
    assert draft.source_span == BlockSpan(start_ordinal=1, end_ordinal=2)
    assert draft.heading_path == ("Topic",)
    assert draft.metadata["chunker.markdown.source_kinds"] == (
        "paragraph",
        "paragraph",
    )


@pytest.mark.parametrize(
    ("markdown", "ordered", "marker", "depths"),
    [
        ("- Alpha\n  - Nested\n- Omega\n", False, "-", (0, 1, 0)),
        ("3. First\n4. Second\n", True, ".", (0, 0)),
    ],
)
def test_lists_preserve_exact_source_type_marker_nesting_and_order(
    markdown: str,
    ordered: bool,
    marker: str,
    depths: tuple[int, ...],
) -> None:
    document = _document(markdown)
    draft = MarkdownChunker().chunk(document, _context(document), WordCounter())[0]
    structure = draft.metadata["chunker.markdown.list"]
    assert isinstance(structure, FrozenMetadata)
    assert draft.text == markdown
    assert structure["ordered"] is ordered
    assert structure["marker"] == marker
    items = structure["items"]
    assert isinstance(items, tuple)
    assert tuple(item["depth"] for item in items if isinstance(item, FrozenMetadata)) == depths
    assert draft.source_span == BlockSpan(start_ordinal=0, end_ordinal=0)


def test_blockquote_remains_source_exact_and_distinguishable() -> None:
    markdown = "> Quoted **source** with [section](#target).\n> Continued line.\n"
    document = _document(markdown)
    draft = MarkdownChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.text == markdown
    assert draft.chunk_type is ChunkType.VERBATIM
    assert draft.metadata["chunker.markdown.kind"] == "blockquote"
    assert draft.metadata["chunker.markdown.links"] == (
        FrozenMetadata({"label": "section", "target": "#target", "title": None}),
    )


def test_thematic_break_is_a_hard_boundary_but_not_a_retrieval_draft() -> None:
    document = _document(f"{_words(8, 'before')}\n\n---\n\n{_words(8, 'after')}\n")
    drafts = MarkdownChunker().chunk(
        document, _context(document, target=100, maximum=200), WordCounter()
    )
    assert tuple(draft.text for draft in drafts) == (_words(8, "before"), _words(8, "after"))
    assert tuple(draft.position.section_index for draft in drafts) == (0, 1)
    assert tuple(draft.source_span for draft in drafts) == (
        BlockSpan(start_ordinal=0, end_ordinal=0),
        BlockSpan(start_ordinal=2, end_ordinal=2),
    )


def test_fenced_code_is_atomic_and_preserves_language_and_source() -> None:
    markdown = "```python\nprint('exact')\n```\n"
    document = _document(markdown)
    draft = MarkdownChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.text == "print('exact')"
    assert draft.chunk_type is ChunkType.CODE
    assert draft.metadata["chunker.markdown.code_language"] == "python"
    assert draft.metadata["chunker.markdown.sources"] == (markdown,)
    assert draft.source_span == BlockSpan(start_ordinal=0, end_ordinal=0)


def test_table_uses_exact_markdown_and_retains_structured_rows() -> None:
    markdown = "| Name | Value |\n|:--|--:|\n| A | 1 |\n"
    document = _document(markdown)
    draft = MarkdownChunker().chunk(document, _context(document), WordCounter())[0]
    table = draft.metadata["chunker.markdown.table"]
    assert draft.text == markdown
    assert draft.chunk_type is ChunkType.PASSAGE
    assert isinstance(table, FrozenMetadata)
    assert table["header_row_count"] == 1
    assert table["rows"] == (("Name", "Value"), ("A", "1"))


def test_internal_links_and_inline_source_are_preserved_without_reparsing() -> None:
    markdown = 'Read **bold** [guide](guide.md "Local") and [web](https://example.com).\n'
    document = _document(markdown)
    draft = MarkdownChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.text == "Read bold guide and web."
    assert draft.metadata["chunker.markdown.sources"] == (markdown,)
    assert draft.metadata["chunker.markdown.links"] == (
        FrozenMetadata({"label": "guide", "target": "guide.md", "title": "Local"}),
    )
    assert "https://example.com" not in repr(draft.metadata["chunker.markdown.links"])


def test_heading_links_are_retained_as_navigation_context() -> None:
    document = _document(f"# [Guide](guide.md)\n\n{_words(15)}\n")
    draft = MarkdownChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.heading_path == ("Guide",)
    assert draft.metadata["chunker.markdown.heading_links"] == (
        FrozenMetadata({"label": "Guide", "target": "guide.md", "title": None}),
    )


def test_mixed_and_consecutive_special_blocks_remain_separate() -> None:
    markdown = (
        "# Mixed\n\n"
        "> Quote.\n\n"
        "```text\ncode\n```\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "- list item\n"
    )
    document = _document(markdown)
    drafts = MarkdownChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.chunk_type for draft in drafts) == (
        ChunkType.VERBATIM,
        ChunkType.CODE,
        ChunkType.PASSAGE,
        ChunkType.PASSAGE,
    )
    assert tuple(draft.metadata["chunker.markdown.kind"] for draft in drafts) == (
        "blockquote",
        "code",
        "table",
        "list",
    )
    assert all(draft.heading_path == ("Mixed",) for draft in drafts)


def test_long_plain_prose_uses_sentence_then_word_boundaries() -> None:
    prose = " ".join(f"{_words(8, str(index))}." for index in range(6))
    document = _document(prose + "\n")
    counter = WordCounter()
    drafts = MarkdownChunker().chunk(document, _context(document), counter)
    assert len(drafts) > 1
    assert all(counter.count(draft.text) <= 40 for draft in drafts)
    assert " ".join(draft.text for draft in drafts) == prose
    assert len({draft.source_span for draft in drafts}) == 1

    sentence = _words(90) + "."
    one = _document(sentence + "\n")
    split = MarkdownChunker().chunk(one, _context(one), counter)
    assert len(split) > 1
    assert " ".join(draft.text for draft in split) == sentence
    assert all(counter.count(draft.text) <= 40 for draft in split)


def test_oversized_atomic_and_formatted_constructs_fail_closed() -> None:
    cases = (
        "```text\n" + "x" * 31 + "\n```\n",
        "| A |\n|---|\n| " + "x" * 31 + " |\n",
        "**" + "x" * 31 + "**\n",
    )
    for markdown in cases:
        document = _document(markdown)
        with pytest.raises(UnsupportedError):
            MarkdownChunker().chunk(
                document,
                _context(document, target=15, maximum=30),
                CharacterCounter(),
            )

    word = _document("x" * 31 + "\n")
    with pytest.raises(UnsupportedError):
        MarkdownChunker().chunk(word, _context(word, target=15, maximum=30), CharacterCounter())


def test_dispatcher_filters_short_leaves_and_preserves_final_provenance() -> None:
    document = _document("tiny text\n")
    context = _context(document)
    dispatcher = ChunkerDispatcher(_registry(), WordCounter())
    assert dispatcher.dispatch(document, context) == ()

    long_document = _document(_words(15) + "\n")
    chunk = dispatcher.dispatch(long_document, _context(long_document))[0]
    assert chunk.source_span == BlockSpan(start_ordinal=0, end_ordinal=0)
    assert chunk.parent_chunk_id is None
    assert chunk.sibling_ids == ()


def test_empty_document_and_empty_heading_sections_emit_no_drafts() -> None:
    empty = _document("")
    assert MarkdownChunker().chunk(empty, _context(empty), WordCounter()) == ()
    headings = _document("# Empty\n\n## Still Empty\n")
    assert MarkdownChunker().chunk(headings, _context(headings), WordCounter()) == ()


@pytest.mark.parametrize(
    "markdown",
    [
        (
            "# \u0905\u0927\u094d\u092f\u093e\u092f\n\n"
            "\u091c\u094d\u091e\u093e\u0928 \u0914\u0930 "
            "\u092a\u094d\u0930\u092f\u094b\u0917 \u0915\u093e "
            "\u0935\u093f\u0935\u0930\u0923\u0964\n"
        ),
        "# \u7ae0\u8282\n\n\u7814\u7a76\u7ed3\u679c\u4e0e\u8ba8\u8bba\u3002\n",
        (
            "# Unicode\n\ncaf\u00e9 cafe\u0301 "
            "\U0001f469\u200d\U0001f4bb mathematics \u222b\u2080\u00b9 x\u00b2 dx.\n"
        ),
    ],
)
def test_unicode_multilingual_markdown_is_deterministic(markdown: str) -> None:
    document = _document(markdown)
    context = _context(document)
    chunker = MarkdownChunker()
    assert chunker.chunk(document, context, WordCounter()) == chunker.chunk(
        document, context, WordCounter()
    )


def test_outputs_are_immutable_deterministic_and_preserve_document() -> None:
    document = _document(f"# Stable\n\n{_words(20)}\n")
    context = _context(document)
    before = document
    chunker = MarkdownChunker()
    first = chunker.chunk(document, context, WordCounter())
    second = chunker.chunk(document, context, WordCounter())
    assert first == second
    assert document is before
    with pytest.raises(FrozenInstanceError):
        first[0].text = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        first[0].metadata["chunker.markdown.kind"] = "changed"  # type: ignore[index]


def test_supplied_counter_is_used_and_dependency_failure_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(_words(20) + "\n")
    counter = WordCounter()

    def reject_network(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", reject_network)
    assert MarkdownChunker().chunk(document, _context(document), counter)
    assert counter.calls
    with pytest.raises(DependencyUnavailableError):
        MarkdownChunker().chunk(document, _context(document), MissingCounter())


@pytest.mark.parametrize(
    "metadata",
    [
        FrozenMetadata(),
        FrozenMetadata(
            {
                "parser.markdown.block_type": "paragraph",
                "parser.markdown.kind": "blockquote",
                "parser.markdown.source": "> quote\n",
            }
        ),
        FrozenMetadata(
            {
                "parser.markdown.block_type": "paragraph",
                "parser.markdown.kind": "paragraph",
                "parser.markdown.links": "invalid",
                "parser.markdown.source": "text\n",
            }
        ),
    ],
)
def test_missing_or_malformed_metadata_fails_closed(metadata: FrozenMetadata) -> None:
    valid = _document("text\n")
    malformed = replace(valid, blocks=(TextBlock(ordinal=0, text="text", metadata=metadata),))
    with pytest.raises(UnsupportedError):
        MarkdownChunker().chunk(malformed, _context(malformed), WordCounter())


def test_non_markdown_document_is_rejected() -> None:
    markdown = _document("text\n")
    generic = replace(markdown, doc_type=DocType.GENERIC)
    with pytest.raises(UnsupportedError):
        MarkdownChunker().chunk(generic, _context(generic), WordCounter())


def test_only_frozen_chunk_types_are_emitted() -> None:
    document = _document(
        "Text paragraph.\n\n> quote\n\n```python\npass\n```\n\n| A |\n|---|\n| B |\n"
    )
    drafts = MarkdownChunker().chunk(document, _context(document), WordCounter())
    assert {draft.chunk_type for draft in drafts} <= set(ChunkType)
    assert tuple(draft.chunk_type for draft in drafts) == (
        ChunkType.PASSAGE,
        ChunkType.VERBATIM,
        ChunkType.CODE,
        ChunkType.PASSAGE,
    )
