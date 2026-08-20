"""Acceptance tests for the Phase 4 Module 4.1 dispatcher contract."""

from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from mnemo.chunkers import ChunkerDispatcher, compute_chunk_id
from mnemo.interfaces import (
    ChunkerCapabilities,
    ChunkingContext,
    ChunkingOptions,
    ContractValidationError,
    IntegrityError,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    BlockSpan,
    ChunkDraft,
    ChunkPosition,
    ChunkType,
    DocType,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    ParsedDocument,
    TextBlock,
)
from mnemo.registry import CapabilityKind, PluginRegistry


class WordCounter:
    """Deterministic test counter whose instance identity is observable."""

    tokenizer_id = "tests/word-counter;adapter=v1"

    def count(self, text: str) -> int:
        return len(text.split())


class DraftChunker:
    def __init__(self, doc_type: DocType, drafts: tuple[ChunkDraft, ...]) -> None:
        self._doc_type = doc_type
        self._drafts = drafts
        self.received_counter: object | None = None

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        return (self._doc_type,)

    def capabilities(self) -> ChunkerCapabilities:
        return ChunkerCapabilities(
            supported_doc_types=(self._doc_type,),
            preserves_semantic_boundaries=True,
            supports_parent_child=True,
            supports_overlap=True,
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        self.received_counter = token_counter
        return self._drafts


@dataclass(slots=True)
class Plugin:
    name: str
    callback: object
    version: str = "1.0.0"
    core_version_range: str = ">=0.1.0,<1.0.0"

    def capabilities(self) -> tuple[str, ...]:
        return ("chunker",)

    def register(self, registry: PluginRegistry) -> None:
        assert callable(self.callback)
        self.callback(registry)


def _document(doc_type: DocType = DocType.GENERIC) -> ParsedDocument:
    content_hash = "a" * 64
    return ParsedDocument(
        blocks=(TextBlock(ordinal=0, text="canonical source"),),
        metadata=DocumentMetadata(content_hash=content_hash),
        language="en",
        doc_type=doc_type,
    )


def _context(document: ParsedDocument, *, target: int = 20, maximum: int = 40) -> ChunkingContext:
    metadata = document.metadata
    return ChunkingContext(
        document_version=DocumentVersion(
            version_id=uuid4(),
            document_id=uuid4(),
            content_hash=metadata.content_hash,
            metadata=metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        options=ChunkingOptions(target_tokens=target, max_tokens=maximum),
    )


def _draft(text: str, *, parent: int | None = None) -> ChunkDraft:
    return ChunkDraft(
        text=text,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        heading_path=("Context",),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        parent_index=parent,
        metadata=FrozenMetadata({"chunker.test.kind": "draft"}),
    )


def _registry(doc_type: DocType, chunker: DraftChunker) -> PluginRegistry:
    registry = PluginRegistry(core_version="0.15.0")

    def register(current: PluginRegistry) -> None:
        current.register_chunker_v2(doc_type, chunker, priority=10, plugin_name="v2-test")

    registry.load_plugin(Plugin("v2-test", register))
    registry.freeze()
    return registry


@pytest.mark.parametrize("doc_type", tuple(DocType))
def test_dispatch_materializes_parent_and_symmetric_siblings(doc_type: DocType) -> None:
    document = _document(doc_type)
    long = " ".join(f"token{i}" for i in range(15))
    drafts = (_draft(long), _draft(long + " a", parent=0), _draft(long + " b", parent=0))
    strategy = DraftChunker(document.doc_type, drafts)
    counter = WordCounter()
    result = ChunkerDispatcher(_registry(document.doc_type, strategy), counter).dispatch(
        document, _context(document)
    )

    assert strategy.received_counter is counter
    assert result[1].parent_chunk_id == result[0].id
    assert result[2].parent_chunk_id == result[0].id
    assert result[1].sibling_ids == (result[2].id,)
    assert result[2].sibling_ids == (result[1].id,)
    assert result[0].sibling_ids == ()
    assert result[0].source_span == drafts[0].source_span
    assert result[0].metadata == drafts[0].metadata


def test_short_leaf_filtering_remaps_multilevel_forest() -> None:
    document = _document()
    long = " ".join("word" for _ in range(15))
    drafts = (
        _draft(long),
        _draft("short", parent=0),
        _draft(long + " child", parent=0),
        _draft(long + " grandchild", parent=2),
        _draft(long + " root"),
    )
    result = ChunkerDispatcher(
        _registry(document.doc_type, DraftChunker(document.doc_type, drafts)), WordCounter()
    ).dispatch(document, _context(document))
    assert len(result) == 4
    assert result[2].parent_chunk_id == result[1].id
    assert result[3].parent_chunk_id is None


def test_explicitly_semantic_short_leaf_is_retained() -> None:
    document = _document()
    draft = replace(
        _draft("Slide 4"),
        metadata=FrozenMetadata({"chunker.preserve_short": True}),
    )
    result = ChunkerDispatcher(
        _registry(document.doc_type, DraftChunker(document.doc_type, (draft,))), WordCounter()
    ).dispatch(document, _context(document))

    assert len(result) == 1
    assert result[0].text == "Slide 4"


@pytest.mark.parametrize("count", [39, 40])
def test_effective_maximum_boundary_is_accepted(count: int) -> None:
    document = _document()
    draft = _draft(" ".join("word" for _ in range(count)))
    result = ChunkerDispatcher(
        _registry(document.doc_type, DraftChunker(document.doc_type, (draft,))), WordCounter()
    ).dispatch(document, _context(document, target=20, maximum=100))
    assert len(result) == 1


def test_oversized_duplicate_and_short_parent_fail_closed() -> None:
    document = _document()
    long = " ".join("word" for _ in range(15))
    cases = (
        (_draft(" ".join("word" for _ in range(41))),),
        (_draft(long), _draft(long)),
        (_draft("short"), _draft(long, parent=0)),
    )
    for drafts in cases:
        dispatcher = ChunkerDispatcher(
            _registry(document.doc_type, DraftChunker(document.doc_type, drafts)), WordCounter()
        )
        with pytest.raises(IntegrityError):
            dispatcher.dispatch(document, _context(document, target=20, maximum=100))


def test_missing_strategy_hash_mismatch_and_invalid_parent_fail_before_output() -> None:
    document = _document()
    context = _context(document)
    empty_registry = PluginRegistry(core_version="0.15.0")
    with pytest.raises(UnsupportedError):
        ChunkerDispatcher(empty_registry, WordCounter()).dispatch(document, context)

    strategy = DraftChunker(document.doc_type, ())
    bad_document = replace(document, metadata=replace(document.metadata, content_hash="b" * 64))
    with pytest.raises(ContractValidationError):
        ChunkerDispatcher(_registry(document.doc_type, strategy), WordCounter()).dispatch(
            bad_document, context
        )

    invalid = (_draft(" ".join("word" for _ in range(15)), parent=0),)
    with pytest.raises(ContractValidationError):
        ChunkerDispatcher(
            _registry(document.doc_type, DraftChunker(document.doc_type, invalid)), WordCounter()
        ).dispatch(document, context)


def test_identity_inputs_and_model_immutability() -> None:
    span = BlockSpan(start_ordinal=2, end_ordinal=3)
    version = uuid4()
    first = compute_chunk_id(version, span, "text")
    assert first == compute_chunk_id(version, span, "text")
    assert first != compute_chunk_id(version, span, "changed")
    assert first != compute_chunk_id(uuid4(), span, "text")
    assert first != compute_chunk_id(version, BlockSpan(start_ordinal=3, end_ordinal=3), "text")
    draft = _draft(" ".join("word" for _ in range(15)))
    with pytest.raises(FrozenInstanceError):
        draft.text = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError):
        BlockSpan(start_ordinal=2, end_ordinal=1)


def test_navigation_and_heading_changes_do_not_change_identity() -> None:
    document = _document()
    text = " ".join("word" for _ in range(15))
    original = _draft(text)
    changed = replace(
        original,
        heading_path=("Renamed",),
        position=replace(original.position, start_offset=10, end_offset=20),
    )
    context = _context(document)
    first = ChunkerDispatcher(
        _registry(document.doc_type, DraftChunker(document.doc_type, (original,))),
        WordCounter(),
    ).dispatch(document, context)
    second = ChunkerDispatcher(
        _registry(document.doc_type, DraftChunker(document.doc_type, (changed,))),
        WordCounter(),
    ).dispatch(document, context)
    assert first[0].id == second[0].id


@pytest.mark.parametrize(
    "options",
    [
        ChunkingOptions(target_tokens=14, max_tokens=20),
        ChunkingOptions(target_tokens=20, max_tokens=20, overlap_tokens=19),
    ],
)
def test_context_enforces_v2_options(options: ChunkingOptions) -> None:
    document = _document()
    version = _context(document).document_version
    if options.target_tokens < 15:
        with pytest.raises(ValueError):
            ChunkingContext(document_version=version, options=options)
    else:
        assert ChunkingContext(document_version=version, options=options).effective_max_tokens == 20


def test_out_of_range_span_and_non_tuple_output_are_rejected() -> None:
    document = _document()
    out_of_range = replace(
        _draft(" ".join("word" for _ in range(15))),
        source_span=BlockSpan(start_ordinal=1, end_ordinal=1),
    )
    with pytest.raises(ContractValidationError):
        ChunkerDispatcher(
            _registry(document.doc_type, DraftChunker(document.doc_type, (out_of_range,))),
            WordCounter(),
        ).dispatch(document, _context(document))

    strategy = DraftChunker(document.doc_type, ())
    strategy.chunk = lambda document, context, token_counter: []  # type: ignore[assignment,method-assign,return-value]
    with pytest.raises(ContractValidationError):
        ChunkerDispatcher(_registry(document.doc_type, strategy), WordCounter()).dispatch(
            document, _context(document)
        )


def test_empty_document_and_output_are_valid() -> None:
    document = replace(_document(), blocks=())
    result = ChunkerDispatcher(
        _registry(document.doc_type, DraftChunker(document.doc_type, ())), WordCounter()
    ).dispatch(document, _context(document))
    assert result == ()


def test_v1_and_v2_registry_candidates_are_isolated() -> None:
    document = _document()
    v2 = DraftChunker(document.doc_type, ())
    registry = _registry(document.doc_type, v2)
    assert registry.resolve_chunker(document.doc_type) is None
    assert registry.resolve_chunker_v2(document.doc_type) is v2
    assert registry.resolve(CapabilityKind.CHUNKER, document.doc_type.value) is None
    assert registry.list_registrations()[0].interface_version == "v2"
