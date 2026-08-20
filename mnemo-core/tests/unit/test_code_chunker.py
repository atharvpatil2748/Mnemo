"""Acceptance and invariant tests for Phase 4 Module 4.5 CodeChunker."""

import re
import socket
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from mnemo.chunkers import ChunkerDispatcher, CodeChunker
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
    ChunkType,
    CodeBlock,
    DocType,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    HeadingBlock,
    ParsedDocument,
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


def _document(
    *blocks: Block,
    title: str = "module.py",
    doc_type: DocType = DocType.CODE,
) -> ParsedDocument:
    return ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(content_hash="d" * 64, title=title),
        language="en",
        doc_type=doc_type,
    )


def _context(document: ParsedDocument, *, target: int = 100, maximum: int = 200) -> ChunkingContext:
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


def _registry(chunker: CodeChunker) -> PluginRegistry:
    registry = PluginRegistry(core_version="0.15.0")

    def register(current: PluginRegistry) -> None:
        current.register_chunker_v2(DocType.CODE, chunker, priority=10, plugin_name="code-test")

    registry.load_plugin(Plugin("code-test", register))
    registry.freeze()
    return registry


def test_v2_contract_capabilities_and_registry_isolation() -> None:
    chunker = CodeChunker()
    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.CODE,)
    capabilities = chunker.capabilities()
    assert capabilities.supports_parent_child
    assert capabilities.preserves_semantic_boundaries
    assert not capabilities.supports_overlap
    assert capabilities.metadata["chunker.code.languages"] == (
        "python",
        "javascript",
        "typescript",
        "tsx",
        "go",
        "rust",
        "java",
        "c",
        "cpp",
    )
    registry = _registry(chunker)
    assert registry.resolve_chunker_v2(DocType.CODE) is chunker
    assert registry.resolve_chunker(DocType.CODE) is None


def test_python_declarations_are_source_exact_and_hierarchical() -> None:
    source = '''class Service:
    """Service docs."""

    def run(self, value: int) -> int:
        return helper(value)

def helper(value: int) -> int:
    return value + 1'''
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.metadata["chunker.code.symbol"] for draft in drafts) == (
        "Service",
        "Service.run",
        "helper",
    )
    assert drafts[0].text == source.split("\n\ndef helper", maxsplit=1)[0]
    assert drafts[1].text.startswith("def run")
    assert drafts[1].parent_index == 0
    assert drafts[2].parent_index is None
    assert drafts[1].metadata["chunker.code.calls"] == ("helper",)
    assert drafts[2].metadata["chunker.code.called_by"] == ("Service.run",)


def test_nested_function_scope_and_decorator_are_preserved() -> None:
    source = """@decorator
def outer(value, second, third, fourth, fifth, sixth):
    def inner(item):
        return item + 1
    combined = value + second + third + fourth + fifth + sixth
    return inner(combined)"""
    document = _document(CodeBlock(ordinal=0, code=source, code_language="py"))
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert drafts[0].text.startswith("@decorator")
    assert drafts[1].metadata["chunker.code.symbol"] == "outer.inner"
    assert drafts[1].parent_index == 0


def test_module_docstring_and_repository_readme_are_source_summaries() -> None:
    source = '"""Exact module documentation.\nSecond line."""\n\ndef execute():\n    return 1'
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert drafts[0].chunk_type is ChunkType.SUMMARY
    assert drafts[0].text == '"""Exact module documentation.\nSecond line."""'

    readme = _document(
        TextBlock(ordinal=0, text="# Repository\n\nExact source documentation."),
        title="README.md",
    )
    readme_drafts = CodeChunker().chunk(readme, _context(readme), WordCounter())
    assert len(readme_drafts) == 1
    assert readme_drafts[0].chunk_type is ChunkType.SUMMARY
    assert readme_drafts[0].text == "# Repository\n\nExact source documentation."


def test_imports_are_metadata_not_separate_chunks() -> None:
    source = (
        "import os\nfrom pathlib import Path\n\nCONSTANT = 3\n\n"
        "def use():\n    return Path(os.getcwd())"
    )
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert all(draft.text not in {"import os", "from pathlib import Path"} for draft in drafts)
    assert drafts[0].metadata["chunker.code.imports"] == (
        "import os",
        "from pathlib import Path",
    )
    assert drafts[0].metadata["chunker.code.symbol"] == "CONSTANT"


@pytest.mark.parametrize(
    ("language", "title", "source", "expected"),
    [
        ("javascript", "module.js", "import x from 'x'; function run(){ return x(); }", "run"),
        (
            "typescript",
            "module.ts",
            "interface Value { name: string }\nfunction run(v: Value){ return v.name }",
            "Value",
        ),
        ("tsx", "view.tsx", "function View(){ return <div>Hello</div> }", "View"),
        ("go", "main.go", 'package main\nimport "fmt"\nfunc Run(){ fmt.Println("x") }', "Run"),
        ("rust", "lib.rs", 'use std::fmt; fn run(){ println!("x"); }', "run"),
        (
            "java",
            "Main.java",
            "import java.util.List; class Main { void run(){ work(); } }",
            "Main",
        ),
        ("c", "main.c", '#include <stdio.h>\nvoid run(void){ puts("x"); }', "run"),
        ("cpp", "main.cpp", "#include <vector>\nnamespace app { void run() {} }", "app"),
    ],
)
def test_supported_tree_sitter_grammars(
    language: str, title: str, source: str, expected: str
) -> None:
    document = _document(CodeBlock(ordinal=0, code=source, code_language=language), title=title)
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert drafts
    assert expected in tuple(str(draft.metadata["chunker.code.symbol"]) for draft in drafts)
    assert all(draft.metadata["chunker.code.language"] == language for draft in drafts)


def test_title_extension_and_namespaced_metadata_resolve_language() -> None:
    by_title = _document(TextBlock(ordinal=0, text="def run():\n    return 1"), title="tool.py")
    assert (
        CodeChunker().chunk(by_title, _context(by_title), WordCounter())[0].chunk_type
        is ChunkType.CODE
    )
    by_metadata = _document(
        TextBlock(
            ordinal=0,
            text="function run(){ return 1; }",
            metadata=FrozenMetadata({"parser.code_language": "js"}),
        ),
        title="source.unknown",
    )
    draft = CodeChunker().chunk(by_metadata, _context(by_metadata), WordCounter())[0]
    assert draft.metadata["chunker.code.language"] == "javascript"


def test_multiple_canonical_blocks_have_contiguous_provenance_and_heading_context() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Utilities", level=1),
        TextBlock(ordinal=1, text="def first():\n    return 1"),
        TextBlock(ordinal=2, text="def second():\n    return first()"),
    )
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert {draft.source_span for draft in drafts} == {BlockSpan(start_ordinal=1, end_ordinal=2)}
    assert tuple(draft.heading_path[0] for draft in drafts) == ("Utilities", "Utilities")


def test_empty_source_document_returns_no_drafts() -> None:
    document = _document()
    assert CodeChunker().chunk(document, _context(document), WordCounter()) == ()


@pytest.mark.parametrize(
    ("block", "message"),
    [
        (CodeBlock(ordinal=0, code="def broken(: pass", code_language="python"), "malformed"),
        (CodeBlock(ordinal=0, code="data", code_language="brainlang"), "unsupported"),
    ],
)
def test_malformed_and_unknown_languages_fail_closed(block: CodeBlock, message: str) -> None:
    document = _document(block)
    with pytest.raises(UnsupportedError, match=message):
        CodeChunker().chunk(document, _context(document), WordCounter())


def test_wrong_document_type_is_rejected() -> None:
    document = _document(
        CodeBlock(ordinal=0, code="def run(): pass", code_language="python"),
        doc_type=DocType.GENERIC,
    )
    with pytest.raises(UnsupportedError, match=r"DocType\.CODE"):
        CodeChunker().chunk(document, _context(document), WordCounter())


def test_oversized_declaration_is_split_without_content_loss() -> None:
    source = "def huge():\n    return '" + " ".join(f"word{i}" for i in range(50)) + "'"
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))
    drafts = CodeChunker().chunk(document, _context(document, target=15, maximum=20), WordCounter())

    assert len(drafts) > 1
    assert "".join(draft.text for draft in drafts) == source
    assert all(WordCounter().count(draft.text) <= 20 for draft in drafts)
    assert tuple(draft.metadata["chunker.code.part_index"] for draft in drafts) == tuple(
        range(len(drafts))
    )
    assert {draft.metadata["chunker.code.part_count"] for draft in drafts} == {len(drafts)}


def test_module_level_statements_are_retained_with_declarations() -> None:
    source = "// startup\nconst enabled = true;\nconsole.log(enabled);\nif (enabled) boot();"
    document = _document(CodeBlock(ordinal=0, code=source, code_language="javascript"))

    drafts = CodeChunker().chunk(document, _context(document), WordCounter())

    text = "\n".join(draft.text for draft in drafts)
    assert "console.log(enabled);" in text
    assert "if (enabled) boot();" in text
    assert "// startup" in text


def test_dispatcher_preserves_short_root_provenance_but_not_import_chunks() -> None:
    source = (
        '"""Module API."""\n'
        "import os\n"
        "# configured logger\n"
        "LOGGER = os.getenv('LOGGER')\n\n"
        "def execute(first, second, third, fourth, fifth):\n"
        "    return first + second + third + fourth + fifth\n"
    )
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))

    chunks = ChunkerDispatcher(_registry(CodeChunker()), WordCounter()).dispatch(
        document, _context(document, target=100, maximum=200)
    )

    text = "\n".join(chunk.text for chunk in chunks)
    assert '"""Module API."""' in text
    assert "# configured logger" in text
    assert "LOGGER = os.getenv('LOGGER')" in text
    assert "import os" not in {chunk.text for chunk in chunks}
    assert all(chunk.metadata["chunker.code.imports"] == ("import os",) for chunk in chunks)


def test_duplicate_canonical_identity_input_fails_closed() -> None:
    source = "def same():\n    return 1\n\ndef same():\n    return 1"
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))
    with pytest.raises(UnsupportedError, match="canonical chunk identity"):
        CodeChunker().chunk(document, _context(document), WordCounter())


def test_supplied_token_counter_is_used_and_dependency_failure_propagates() -> None:
    source = "def run(value):\n    return value + 1"
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))
    counter = WordCounter()
    CodeChunker().chunk(document, _context(document), counter)
    assert source in counter.calls
    with pytest.raises(DependencyUnavailableError):
        CodeChunker().chunk(document, _context(document), MissingCounter())


def test_deterministic_immutable_output_and_no_input_mutation() -> None:
    source = "class Value:\n    def read(self):\n        return 42"
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))
    before = document
    first = CodeChunker().chunk(document, _context(document), WordCounter())
    second = CodeChunker().chunk(document, _context(document), WordCounter())
    assert first == second
    assert document == before
    with pytest.raises(FrozenInstanceError):
        first[0].text = "changed"  # type: ignore[misc]


def test_chunker_does_not_use_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def prohibited(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is prohibited")

    monkeypatch.setattr(socket, "create_connection", prohibited)
    document = _document(
        CodeBlock(ordinal=0, code="def run():\n    return 1", code_language="python")
    )
    assert CodeChunker().chunk(document, _context(document), WordCounter())


def test_dispatcher_materializes_parent_and_stable_chunks() -> None:
    source = """class Service:
    def execute(self, first, second, third, fourth, fifth):
        combined = first + second + third + fourth + fifth
        checked = combined if combined > 0 else 0
        return checked + first + second + third + fourth + fifth"""
    document = _document(CodeBlock(ordinal=0, code=source, code_language="python"))
    context = _context(document, target=100, maximum=200)
    dispatcher = ChunkerDispatcher(_registry(CodeChunker()), WordCounter())
    first = dispatcher.dispatch(document, context)
    second = dispatcher.dispatch(document, context)
    assert first == second
    assert len(first) == 2
    assert first[1].parent_chunk_id == first[0].id
    assert first[0].source_span == BlockSpan(start_ordinal=0, end_ordinal=0)
    assert first[0].chunk_type is ChunkType.CODE


def test_javascript_arrow_function_callback_locals_not_emitted_as_root_declarations() -> None:
    source = """
app.post('/x', async (req, res) => {
    const x = 1;
});
"""
    document = _document(
        CodeBlock(ordinal=0, code=source, code_language="javascript"), title="server.js"
    )
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert len(drafts) == 1
    assert drafts[0].text == source.strip()
    assert drafts[0].metadata["chunker.code.symbol"] == "<module-0>"


def test_javascript_function_expression_locals_not_emitted_as_root_declarations() -> None:
    source = """
const handler = function(req, res) {
    const localInExpr = 4;
};
"""
    document = _document(
        CodeBlock(ordinal=0, code=source, code_language="javascript"), title="server.js"
    )
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert len(drafts) == 1
    assert "const handler =" in drafts[0].text


def test_repeated_identical_declarations_in_separate_arrow_functions_do_not_collide() -> None:
    source = """
app.post('/first', async (req, res) => {
    const { executeTool } = require('@tools/toolRegistry');
    const result = await executeTool(1);
});

app.post('/second', async (req, res) => {
    const { executeTool } = require('@tools/toolRegistry');
    const result = await executeTool(2);
});
"""
    document = _document(
        CodeBlock(ordinal=0, code=source, code_language="javascript"), title="server.js"
    )
    drafts = CodeChunker().chunk(document, _context(document), WordCounter())
    assert len(drafts) == 2
    assert all("executeTool" in draft.text for draft in drafts)
