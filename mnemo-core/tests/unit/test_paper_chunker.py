"""Acceptance and invariant tests for Phase 4 Module 4.4 PaperChunker."""

import re
import socket
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from mnemo.chunkers import ChunkerDispatcher, PaperChunker
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


def _document(*blocks: Block, doc_type: DocType = DocType.PAPER) -> ParsedDocument:
    return ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(content_hash="c" * 64, title="A Research Paper"),
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


def _registry(chunker: PaperChunker) -> PluginRegistry:
    registry = PluginRegistry(core_version="0.15.0")

    def register(current: PluginRegistry) -> None:
        current.register_chunker_v2(DocType.PAPER, chunker, priority=10, plugin_name="paper-test")

    registry.load_plugin(Plugin("paper-test", register))
    registry.freeze()
    return registry


def test_v2_contract_capabilities_and_registry_isolation() -> None:
    chunker = PaperChunker()
    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.PAPER,)
    capabilities = chunker.capabilities()
    assert capabilities.supported_doc_types == (DocType.PAPER,)
    assert capabilities.preserves_semantic_boundaries
    assert not capabilities.supports_parent_child
    assert not capabilities.supports_overlap
    registry = _registry(chunker)
    assert registry.resolve_chunker_v2(DocType.PAPER) is chunker
    assert registry.resolve_chunker(DocType.PAPER) is None


def test_standard_paper_sections_remain_isolated() -> None:
    names = ("Introduction", "Methods", "Results", "Discussion", "Conclusion")
    blocks: list[Block] = []
    for index, name in enumerate(names):
        blocks.extend(
            (
                HeadingBlock(ordinal=index * 2, text=name, level=1),
                TextBlock(ordinal=index * 2 + 1, text=_words(8, name.casefold())),
            )
        )
    document = _document(*blocks)
    drafts = PaperChunker().chunk(
        document, _context(document, target=100, maximum=200), WordCounter()
    )
    assert len(drafts) == len(names)
    assert tuple(draft.heading_path for draft in drafts) == tuple((name,) for name in names)
    assert tuple(draft.metadata["chunker.paper.section"] for draft in drafts) == (
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
    )


@pytest.mark.parametrize(
    ("heading", "section"),
    [
        ("2 Related Work", "background"),
        ("II. Literature Review", "background"),
        ("3 Materials and Methods", "methods"),
        ("3.1 Experimental Setup", "methods"),
        ("Experiments", "methods"),
        ("Findings", "results"),
        ("Conclusions", "conclusion"),
        ("Future Work", "future_work"),
        ("Acknowledgments", "acknowledgements"),
    ],
)
def test_alternative_and_numbered_section_names(heading: str, section: str) -> None:
    document = _document(
        HeadingBlock(ordinal=0, text=heading, level=1),
        TextBlock(ordinal=1, text=_words(15)),
    )
    draft = PaperChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.metadata["chunker.paper.section"] == section


def test_nested_heading_levels_and_number_fallback() -> None:
    canonical = _document(
        HeadingBlock(ordinal=0, text="Methods", level=1),
        HeadingBlock(ordinal=1, text="Experimental Setup", level=2),
        HeadingBlock(ordinal=2, text="Hardware", level=3),
        TextBlock(ordinal=3, text=_words(20)),
    )
    draft = PaperChunker().chunk(canonical, _context(canonical), WordCounter())[0]
    assert draft.heading_path == ("Methods", "Experimental Setup", "Hardware")

    flat = _document(
        HeadingBlock(ordinal=0, text="3 Methods", level=1),
        HeadingBlock(ordinal=1, text="3.1 Dataset", level=1),
        HeadingBlock(ordinal=2, text="3.1.1 Filtering", level=1),
        TextBlock(ordinal=3, text=_words(20)),
    )
    inferred = PaperChunker().chunk(flat, _context(flat), WordCounter())[0]
    assert inferred.heading_path == ("3 Methods", "3.1 Dataset", "3.1.1 Filtering")

    limitations = _document(
        HeadingBlock(ordinal=0, text="Discussion", level=1),
        HeadingBlock(ordinal=1, text="Limitations", level=2),
        TextBlock(ordinal=2, text=_words(20)),
    )
    limited = PaperChunker().chunk(limitations, _context(limitations), WordCounter())[0]
    assert limited.metadata["chunker.paper.section"] == "limitations"


def test_missing_and_irregular_sections_remain_deterministic() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Study Design", level=1),
        TextBlock(ordinal=1, text=_words(15)),
        HeadingBlock(ordinal=2, text="Unexpected Observations", level=1),
        TextBlock(ordinal=3, text=_words(15)),
    )
    chunker = PaperChunker()
    first = chunker.chunk(document, _context(document), WordCounter())
    second = chunker.chunk(document, _context(document), WordCounter())
    assert first == second
    assert all(draft.metadata["chunker.paper.section"] == "other" for draft in first)


def test_abstract_is_one_exact_atomic_passage_and_never_merges_with_introduction() -> None:
    first = "  Source-authored abstract with deliberate spacing.  "
    second = "A second canonical abstract paragraph."
    document = _document(
        HeadingBlock(ordinal=0, text="Abstract", level=1),
        TextBlock(ordinal=1, text=first),
        TextBlock(ordinal=2, text=second),
        HeadingBlock(ordinal=3, text="Introduction", level=1),
        TextBlock(ordinal=4, text=_words(20, "intro")),
    )
    drafts = PaperChunker().chunk(
        document, _context(document, target=100, maximum=200), WordCounter()
    )
    assert drafts[0].text == f"{first}\n\n{second}"
    assert drafts[0].chunk_type is ChunkType.PASSAGE
    assert drafts[0].source_span == BlockSpan(start_ordinal=1, end_ordinal=2)
    assert drafts[0].heading_path == ("Abstract",)
    assert drafts[0].metadata["chunker.paper.content_kind"] == "abstract"
    assert drafts[1].heading_path == ("Introduction",)
    assert "intro0" not in drafts[0].text


def test_numbered_abstract_detection_and_empty_abstract() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="I. Abstract", level=1),
        TextBlock(ordinal=1, text="Exact abstract."),
    )
    assert PaperChunker().chunk(document, _context(document), WordCounter())[0].text == (
        "Exact abstract."
    )
    empty = _document(HeadingBlock(ordinal=0, text="Abstract", level=1))
    assert PaperChunker().chunk(empty, _context(empty), WordCounter()) == ()


def test_oversized_or_non_prose_abstract_fails_closed() -> None:
    oversized = _document(
        HeadingBlock(ordinal=0, text="Abstract", level=1),
        TextBlock(ordinal=1, text="x" * 31),
    )
    with pytest.raises(UnsupportedError, match="abstract"):
        PaperChunker().chunk(
            oversized, _context(oversized, target=15, maximum=30), CharacterCounter()
        )
    non_prose = _document(
        HeadingBlock(ordinal=0, text="Abstract", level=1),
        EquationBlock(ordinal=1, latex="x=y"),
    )
    with pytest.raises(UnsupportedError, match="non-prose"):
        PaperChunker().chunk(non_prose, _context(non_prose), WordCounter())


def test_references_and_bibliography_are_excluded_without_mutating_source_metadata() -> None:
    reference_metadata = FrozenMetadata({"parser.reference.doi": "10.1000/example"})
    document = _document(
        HeadingBlock(ordinal=0, text="Conclusion", level=1),
        TextBlock(ordinal=1, text=_words(15, "conclusion")),
        HeadingBlock(ordinal=2, text="References", level=1),
        TextBlock(ordinal=3, text="[1] First citation.", metadata=reference_metadata),
        TextBlock(ordinal=4, text="[2] Second unrelated citation."),
    )
    drafts = PaperChunker().chunk(document, _context(document), WordCounter())
    assert len(drafts) == 1
    assert drafts[0].heading_path == ("Conclusion",)
    assert "citation" not in drafts[0].text
    assert document.blocks[3].metadata == reference_metadata

    bibliography = _document(
        HeadingBlock(ordinal=0, text="Bibliography", level=1),
        TextBlock(ordinal=1, text="Reference only."),
    )
    assert PaperChunker().chunk(bibliography, _context(bibliography), WordCounter()) == ()


def test_nested_reference_headings_remain_excluded_but_later_major_section_resumes() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="References", level=1),
        HeadingBlock(ordinal=1, text="Primary Sources", level=2),
        TextBlock(ordinal=2, text="Citation content."),
        HeadingBlock(ordinal=3, text="Acknowledgements", level=1),
        TextBlock(ordinal=4, text=_words(15, "thanks")),
    )
    drafts = PaperChunker().chunk(document, _context(document), WordCounter())
    assert len(drafts) == 1
    assert drafts[0].metadata["chunker.paper.section"] == "acknowledgements"


def test_equation_preserves_exact_source_latex_context_and_provenance() -> None:
    latex = r"\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}"
    document = _document(
        HeadingBlock(ordinal=0, text="Methods", level=1),
        HeadingBlock(ordinal=1, text="Mathematical Model", level=2),
        EquationBlock(ordinal=2, latex=latex, display=True),
    )
    draft = PaperChunker().chunk(document, _context(document), WordCounter())[0]
    assert draft.text == latex
    assert draft.chunk_type is ChunkType.EQUATION
    assert draft.source_span == BlockSpan(start_ordinal=2, end_ordinal=2)
    assert draft.heading_path == ("Methods", "Mathematical Model")
    assert draft.metadata["chunker.paper.content_kind"] == "equation"


def test_equations_are_not_combined_and_oversized_equation_fails() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Results", level=1),
        EquationBlock(ordinal=1, latex="a=b"),
        EquationBlock(ordinal=2, latex="c=d"),
    )
    drafts = PaperChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.text for draft in drafts) == ("a=b", "c=d")
    oversized = _document(EquationBlock(ordinal=0, latex="x" * 31))
    with pytest.raises(UnsupportedError):
        PaperChunker().chunk(
            oversized, _context(oversized, target=15, maximum=30), CharacterCounter()
        )


def test_passage_paragraph_sentence_and_word_splitting_preserves_all_text() -> None:
    exact_text = "  Exact source prose with deliberate surrounding spacing.  "
    exact = _document(TextBlock(ordinal=0, text=exact_text))
    assert (
        PaperChunker().chunk(exact, _context(exact, target=100, maximum=200), WordCounter())[0].text
        == exact_text
    )

    paragraph = " ".join(f"{_words(12, str(index))}." for index in range(6))
    document = _document(
        HeadingBlock(ordinal=0, text="Methods", level=1),
        TextBlock(ordinal=1, text=paragraph),
    )
    counter = WordCounter()
    drafts = PaperChunker().chunk(document, _context(document), counter)
    assert all(counter.count(draft.text) <= 40 for draft in drafts)
    assert " ".join(draft.text for draft in drafts) == paragraph
    assert len({draft.source_span for draft in drafts}) == 1

    one_sentence = _words(90) + "."
    one = _document(TextBlock(ordinal=0, text=one_sentence))
    split = PaperChunker().chunk(one, _context(one), counter)
    assert " ".join(draft.text for draft in split) == one_sentence
    assert all(counter.count(draft.text) <= 40 for draft in split)


def test_multi_block_passage_has_contiguous_provenance_and_stays_in_section() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Results", level=1),
        TextBlock(ordinal=1, text=_words(8, "a")),
        TextBlock(ordinal=2, text=_words(8, "b")),
        HeadingBlock(ordinal=3, text="Discussion", level=1),
        TextBlock(ordinal=4, text=_words(8, "c")),
    )
    drafts = PaperChunker().chunk(
        document, _context(document, target=100, maximum=200), WordCounter()
    )
    assert drafts[0].source_span == BlockSpan(start_ordinal=1, end_ordinal=2)
    assert drafts[1].source_span == BlockSpan(start_ordinal=4, end_ordinal=4)
    assert drafts[0].heading_path == ("Results",)
    assert drafts[1].heading_path == ("Discussion",)


def test_special_blocks_preserve_existing_types_and_do_not_merge_as_prose() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Results", level=1),
        TableBlock(ordinal=1, rows=(("metric", "score"), ("accuracy", "0.9"))),
        CodeBlock(ordinal=2, code="result = evaluate(model)", code_language="python"),
        CaptionBlock(ordinal=3, text="Table 1: Results", target_ordinal=1),
        ImageBlock(ordinal=4, asset_id=uuid4(), alt_text="Figure 1 source alt text"),
    )
    drafts = PaperChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.chunk_type for draft in drafts) == (
        ChunkType.PASSAGE,
        ChunkType.CODE,
        ChunkType.CAPTION,
        ChunkType.CAPTION,
    )
    assert tuple(draft.metadata["chunker.paper.content_kind"] for draft in drafts) == (
        "table",
        "code",
        "caption",
        "image_alt",
    )
    assert "Figure 1 source alt text" in drafts[-1].text


def test_source_labeled_summary_is_preserved_but_never_generated() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Summary", level=1),
        TextBlock(ordinal=1, text=_words(15, "summary")),
        HeadingBlock(ordinal=2, text="Introduction", level=1),
        TextBlock(ordinal=3, text=_words(15, "intro")),
    )
    drafts = PaperChunker().chunk(document, _context(document), WordCounter())
    assert drafts[0].chunk_type is ChunkType.SUMMARY
    assert drafts[1].chunk_type is ChunkType.PASSAGE
    assert all("generated" not in draft.metadata for draft in drafts)


@pytest.mark.parametrize(
    "text",
    [
        "प्रयोग के परिणाम सांख्यिकीय रूप से महत्वपूर्ण हैं।",
        "研究結果は統計的に有意である。",
        "café cafe\u0301 and emoji 👩\u200d🔬",
    ],
)
def test_multilingual_unicode_paper_content_is_deterministic(text: str) -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Results", level=1),
        TextBlock(ordinal=1, text=text),
    )
    chunker = PaperChunker()
    assert chunker.chunk(document, _context(document), WordCounter()) == chunker.chunk(
        document, _context(document), WordCounter()
    )


def test_supplied_counter_no_network_no_mutation_and_dependency_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(TextBlock(ordinal=0, text=_words(20)))
    counter = WordCounter()
    before = document

    def reject_network(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", reject_network)
    drafts = PaperChunker().chunk(document, _context(document), counter)
    assert counter.calls
    assert document is before
    with pytest.raises(FrozenInstanceError):
        drafts[0].text = "changed"  # type: ignore[misc]
    with pytest.raises(DependencyUnavailableError):
        PaperChunker().chunk(document, _context(document), MissingCounter())


def test_dispatcher_preserves_provenance_and_heading_is_not_identity_material() -> None:
    first = _document(
        HeadingBlock(ordinal=0, text="Results", level=1),
        TextBlock(ordinal=1, text=_words(20)),
    )
    second = _document(
        HeadingBlock(ordinal=0, text="Findings", level=1),
        TextBlock(ordinal=1, text=_words(20)),
    )
    context = _context(first)
    dispatcher = ChunkerDispatcher(_registry(PaperChunker()), WordCounter())
    first_chunk = dispatcher.dispatch(first, context)[0]
    second_chunk = dispatcher.dispatch(second, context)[0]
    assert first_chunk.id == second_chunk.id
    assert first_chunk.heading_path != second_chunk.heading_path
    assert first_chunk.source_span == BlockSpan(start_ordinal=1, end_ordinal=1)
    assert first_chunk.parent_chunk_id is None
    assert first_chunk.sibling_ids == ()


def test_empty_irrelevant_and_non_paper_inputs() -> None:
    empty = _document()
    assert PaperChunker().chunk(empty, _context(empty), WordCounter()) == ()
    irrelevant = _document(ImageBlock(ordinal=0, asset_id=uuid4()))
    assert PaperChunker().chunk(irrelevant, _context(irrelevant), WordCounter()) == ()
    generic = _document(TextBlock(ordinal=0, text="text"), doc_type=DocType.GENERIC)
    with pytest.raises(UnsupportedError):
        PaperChunker().chunk(generic, _context(generic), WordCounter())


def test_no_disjoint_provenance_or_invalid_parent_indexes() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Methods", level=1),
        TextBlock(ordinal=1, text=_words(8, "a")),
        ImageBlock(ordinal=2, asset_id=uuid4()),
        TextBlock(ordinal=3, text=_words(8, "b")),
    )
    drafts = PaperChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.source_span for draft in drafts) == (
        BlockSpan(start_ordinal=1, end_ordinal=1),
        BlockSpan(start_ordinal=3, end_ordinal=3),
    )
    assert all(draft.parent_index is None for draft in drafts)
    assert all(draft.source_span.end_ordinal < len(document.blocks) for draft in drafts)
