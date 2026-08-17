"""Deterministic tree-sitter chunking for canonical source-code documents."""

from dataclasses import dataclass
from pathlib import PurePath

import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_rust
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from mnemo.interfaces import (
    ChunkerCapabilities,
    ChunkingContext,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    BlockSpan,
    ChunkDraft,
    ChunkPosition,
    ChunkType,
    CodeBlock,
    DocType,
    FrozenMetadata,
    HeadingBlock,
    ParsedDocument,
    TextBlock,
)


@dataclass(frozen=True, slots=True)
class _LanguageSpec:
    language: Language
    declaration_types: frozenset[str]
    container_types: frozenset[str]
    import_types: frozenset[str]
    call_types: frozenset[str]
    module_docstring: bool = False


@dataclass(frozen=True, slots=True)
class _Source:
    text: str
    language_name: str
    span: BlockSpan
    heading_path: tuple[str, ...]
    section_index: int
    page_number: int | None


@dataclass(frozen=True, slots=True)
class _Declaration:
    text: str
    kind: str
    symbol: str
    qualified_symbol: str
    parent_local_index: int | None
    calls: tuple[str, ...]
    is_summary: bool = False


_COMMON_CALLS = frozenset({"call_expression"})
_SPECS: dict[str, _LanguageSpec] = {
    "python": _LanguageSpec(
        Language(tree_sitter_python.language()),
        frozenset({"assignment", "class_definition", "function_definition"}),
        frozenset({"class_definition", "function_definition"}),
        frozenset({"import_statement", "import_from_statement"}),
        frozenset({"call"}),
        True,
    ),
    "javascript": _LanguageSpec(
        Language(tree_sitter_javascript.language()),
        frozenset(
            {
                "class_declaration",
                "function_declaration",
                "generator_function_declaration",
                "lexical_declaration",
                "method_definition",
                "variable_declaration",
            }
        ),
        frozenset({"class_declaration", "function_declaration", "method_definition"}),
        frozenset({"import_statement"}),
        _COMMON_CALLS,
    ),
    "typescript": _LanguageSpec(
        Language(tree_sitter_typescript.language_typescript()),
        frozenset(
            {
                "abstract_class_declaration",
                "class_declaration",
                "enum_declaration",
                "function_declaration",
                "interface_declaration",
                "lexical_declaration",
                "method_definition",
                "type_alias_declaration",
                "variable_declaration",
            }
        ),
        frozenset(
            {
                "abstract_class_declaration",
                "class_declaration",
                "function_declaration",
                "method_definition",
            }
        ),
        frozenset({"import_statement"}),
        _COMMON_CALLS,
    ),
    "tsx": _LanguageSpec(
        Language(tree_sitter_typescript.language_tsx()),
        frozenset(
            {
                "class_declaration",
                "function_declaration",
                "lexical_declaration",
                "method_definition",
            }
        ),
        frozenset({"class_declaration", "function_declaration", "method_definition"}),
        frozenset({"import_statement"}),
        _COMMON_CALLS,
    ),
    "go": _LanguageSpec(
        Language(tree_sitter_go.language()),
        frozenset(
            {
                "const_declaration",
                "function_declaration",
                "method_declaration",
                "type_declaration",
                "var_declaration",
            }
        ),
        frozenset({"function_declaration", "method_declaration", "type_declaration"}),
        frozenset({"import_declaration"}),
        _COMMON_CALLS,
    ),
    "rust": _LanguageSpec(
        Language(tree_sitter_rust.language()),
        frozenset(
            {
                "const_item",
                "enum_item",
                "function_item",
                "impl_item",
                "mod_item",
                "static_item",
                "struct_item",
                "trait_item",
                "type_item",
            }
        ),
        frozenset({"function_item", "impl_item", "mod_item", "trait_item"}),
        frozenset({"use_declaration"}),
        _COMMON_CALLS,
    ),
    "java": _LanguageSpec(
        Language(tree_sitter_java.language()),
        frozenset(
            {
                "class_declaration",
                "constructor_declaration",
                "enum_declaration",
                "field_declaration",
                "interface_declaration",
                "method_declaration",
                "record_declaration",
            }
        ),
        frozenset(
            {
                "class_declaration",
                "constructor_declaration",
                "enum_declaration",
                "interface_declaration",
                "method_declaration",
                "record_declaration",
            }
        ),
        frozenset({"import_declaration"}),
        _COMMON_CALLS,
    ),
    "c": _LanguageSpec(
        Language(tree_sitter_c.language()),
        frozenset(
            {
                "declaration",
                "enum_specifier",
                "function_definition",
                "struct_specifier",
                "type_definition",
            }
        ),
        frozenset({"function_definition", "struct_specifier"}),
        frozenset({"preproc_include"}),
        _COMMON_CALLS,
    ),
    "cpp": _LanguageSpec(
        Language(tree_sitter_cpp.language()),
        frozenset(
            {
                "alias_declaration",
                "class_specifier",
                "declaration",
                "enum_specifier",
                "function_definition",
                "namespace_definition",
                "struct_specifier",
                "template_declaration",
                "type_definition",
            }
        ),
        frozenset(
            {"class_specifier", "function_definition", "namespace_definition", "struct_specifier"}
        ),
        frozenset({"preproc_include"}),
        _COMMON_CALLS,
    ),
}

_ALIASES = {
    "c++": "cpp",
    "cxx": "cpp",
    "golang": "go",
    "js": "javascript",
    "jsx": "javascript",
    "py": "python",
    "rs": "rust",
    "ts": "typescript",
}
_EXTENSIONS = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "tsx",
}


class CodeChunker:
    """Extract source declarations as immutable, provenance-bearing drafts."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the sole classification owned by this strategy."""
        return (DocType.CODE,)

    def capabilities(self) -> ChunkerCapabilities:
        """Describe the strategy's implemented behavior."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=True,
            supports_overlap=False,
            metadata=FrozenMetadata(
                {
                    "chunker.code.languages": tuple(_SPECS),
                    "chunker.code.version": "v1",
                }
            ),
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        """Parse code locally and return source-exact declaration drafts."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        if document.doc_type is not DocType.CODE:
            raise UnsupportedError("CodeChunker supports only DocType.CODE")

        drafts: list[ChunkDraft] = []
        identity_inputs: set[tuple[BlockSpan, str]] = set()
        for source in self._sources(document):
            declarations, imports = self._parse(source)
            local_to_global: dict[int, int] = {}
            for local_index, declaration in enumerate(declarations):
                if token_counter.count(declaration.text) > context.effective_max_tokens:
                    raise UnsupportedError(
                        f"atomic code declaration {declaration.qualified_symbol!r} exceeds "
                        "the effective token maximum"
                    )
                identity_input = (source.span, declaration.text)
                if identity_input in identity_inputs:
                    raise UnsupportedError(
                        "source contains declarations indistinguishable under the "
                        "canonical chunk identity"
                    )
                identity_inputs.add(identity_input)
                parent_index = (
                    local_to_global.get(declaration.parent_local_index)
                    if declaration.parent_local_index is not None
                    else None
                )
                calls = declaration.calls
                called_by = tuple(
                    candidate.qualified_symbol
                    for candidate in declarations
                    if declaration.symbol in candidate.calls
                )
                global_index = len(drafts)
                local_to_global[local_index] = global_index
                drafts.append(
                    ChunkDraft(
                        text=declaration.text,
                        chunk_type=(
                            ChunkType.SUMMARY if declaration.is_summary else ChunkType.CODE
                        ),
                        position=ChunkPosition(
                            section_index=source.section_index,
                            chunk_index_in_section=local_index,
                            page_number=source.page_number,
                        ),
                        heading_path=(*source.heading_path, declaration.qualified_symbol),
                        source_span=source.span,
                        parent_index=parent_index,
                        metadata=FrozenMetadata(
                            {
                                "chunker.code.called_by": called_by,
                                "chunker.code.calls": calls,
                                "chunker.code.declaration_kind": declaration.kind,
                                "chunker.code.imports": imports,
                                "chunker.code.language": source.language_name,
                                "chunker.code.strategy": "tree-sitter-v1",
                                "chunker.code.symbol": declaration.qualified_symbol,
                            }
                        ),
                    )
                )
        return tuple(drafts)

    def _sources(self, document: ParsedDocument) -> tuple[_Source, ...]:
        result: list[_Source] = []
        headings: list[str] = []
        section_index = 0
        pending: list[CodeBlock | TextBlock] = []
        pending_language: str | None = None

        def flush() -> None:
            nonlocal pending, pending_language
            if not pending:
                return
            if pending_language is None:
                raise UnsupportedError("code language is required for AST chunking")
            texts = tuple(
                block.code if isinstance(block, CodeBlock) else block.text for block in pending
            )
            result.append(
                _Source(
                    text="\n\n".join(texts),
                    language_name=pending_language,
                    span=BlockSpan(
                        start_ordinal=pending[0].ordinal,
                        end_ordinal=pending[-1].ordinal,
                    ),
                    heading_path=tuple(headings),
                    section_index=section_index,
                    page_number=pending[0].page_number,
                )
            )
            pending = []
            pending_language = None

        for block in document.blocks:
            if isinstance(block, HeadingBlock):
                flush()
                headings = headings[: block.level - 1]
                headings.append(block.text)
                section_index += 1
                continue
            if not isinstance(block, (CodeBlock, TextBlock)):
                flush()
                continue
            language_name = self._language_name(block, document)
            if pending and language_name != pending_language:
                flush()
            pending.append(block)
            pending_language = language_name
        flush()
        return tuple(result)

    def _language_name(self, block: CodeBlock | TextBlock, document: ParsedDocument) -> str:
        candidate: str | None = block.code_language if isinstance(block, CodeBlock) else None
        for key in ("parser.code_language", "chunker.code.language"):
            value = block.metadata.get(key)
            if candidate is None and isinstance(value, str):
                candidate = value
        if candidate is None and document.metadata.title:
            if PurePath(document.metadata.title).stem.casefold() == "readme":
                return "readme"
            candidate = _EXTENSIONS.get(PurePath(document.metadata.title).suffix.casefold())
        normalized = _ALIASES.get(candidate.casefold(), candidate.casefold()) if candidate else None
        if normalized not in _SPECS:
            raise UnsupportedError(f"unsupported or missing code language: {candidate!r}")
        return normalized

    def _parse(self, source: _Source) -> tuple[tuple[_Declaration, ...], tuple[str, ...]]:
        if source.language_name == "readme":
            return (
                (
                    _Declaration(
                        source.text,
                        "repository_readme",
                        "README",
                        "README",
                        None,
                        (),
                        True,
                    ),
                ),
                (),
            )
        spec = _SPECS[source.language_name]
        encoded = source.text.encode("utf-8")
        root = Parser(spec.language).parse(encoded).root_node
        if root.has_error:
            raise UnsupportedError(f"malformed {source.language_name} source cannot be chunked")
        imports = tuple(
            self._node_text(node, encoded)
            for node in self._walk(root)
            if node.type in spec.import_types
        )
        result: list[_Declaration] = []
        if spec.module_docstring:
            docstring = self._python_module_docstring(root)
            if docstring is not None:
                result.append(
                    _Declaration(
                        self._node_text(docstring, encoded),
                        "module_docstring",
                        "<module-docstring>",
                        "<module-docstring>",
                        None,
                        (),
                        True,
                    )
                )
        self._collect_declarations(root, encoded, spec, None, (), result)
        return tuple(result), imports

    def _collect_declarations(
        self,
        node: Node,
        source: bytes,
        spec: _LanguageSpec,
        parent_index: int | None,
        scope: tuple[str, ...],
        result: list[_Declaration],
    ) -> None:
        for child in node.named_children:
            actual = child
            if child.type == "decorated_definition" and child.named_children:
                actual = child.named_children[-1]
            if actual.type in spec.import_types:
                continue
            if actual.type in spec.declaration_types:
                if self._is_local_value_declaration(actual, parent_index, result):
                    self._collect_declarations(actual, source, spec, parent_index, scope, result)
                    continue
                symbol = self._symbol(actual, source)
                qualified = ".".join((*scope, symbol)) if scope else symbol
                current_index = len(result)
                result.append(
                    _Declaration(
                        self._node_text(child, source),
                        actual.type,
                        symbol,
                        qualified,
                        parent_index,
                        self._calls(actual, source, spec),
                    )
                )
                if actual.type in spec.container_types:
                    self._collect_declarations(
                        actual, source, spec, current_index, (*scope, symbol), result
                    )
                continue
            self._collect_declarations(child, source, spec, parent_index, scope, result)

    @staticmethod
    def _is_local_value_declaration(
        node: Node,
        parent_index: int | None,
        declarations: list[_Declaration],
    ) -> bool:
        value_types = {
            "assignment",
            "const_declaration",
            "declaration",
            "lexical_declaration",
            "var_declaration",
            "variable_declaration",
        }
        if node.type not in value_types:
            return False
        if parent_index is not None and declarations[parent_index].kind in {
            "constructor_declaration",
            "function_declaration",
            "function_definition",
            "function_item",
            "generator_function_declaration",
            "method_declaration",
            "method_definition",
        }:
            return True
        curr = node.parent
        while curr is not None:
            if curr.type in {
                "arrow_function",
                "closure_expression",
                "constructor_declaration",
                "func_literal",
                "function_declaration",
                "function_definition",
                "function_expression",
                "function_item",
                "generator_function_declaration",
                "lambda_expression",
                "method_declaration",
                "method_definition",
            }:
                return True
            curr = curr.parent
        return False

    @staticmethod
    def _python_module_docstring(root: Node) -> Node | None:
        if not root.named_children:
            return None
        first = root.named_children[0]
        if first.type != "expression_statement" or not first.named_children:
            return None
        expression = first.named_children[0]
        return expression if expression.type in {"string", "concatenated_string"} else None

    def _calls(self, node: Node, source: bytes, spec: _LanguageSpec) -> tuple[str, ...]:
        result: list[str] = []
        stack = list(reversed(node.named_children))
        while stack:
            candidate = stack.pop()
            actual = candidate
            if candidate.type == "decorated_definition" and candidate.named_children:
                actual = candidate.named_children[-1]
            if actual.type in spec.declaration_types:
                continue
            if candidate.type not in spec.call_types:
                stack.extend(reversed(candidate.named_children))
                continue
            target = candidate.child_by_field_name("function")
            if target is None and candidate.named_children:
                target = candidate.named_children[0]
            if target is None:
                stack.extend(reversed(candidate.named_children))
                continue
            name = self._node_text(target, source).split(".")[-1].strip()
            if name and name not in result:
                result.append(name)
            stack.extend(reversed(candidate.named_children))
        return tuple(result)

    @staticmethod
    def _symbol(node: Node, source: bytes) -> str:
        name = node.child_by_field_name("name")
        if name is None:
            name = node.child_by_field_name("left")
        if name is None:
            declarator = node.child_by_field_name("declarator")
            name = CodeChunker._find_identifier(declarator) if declarator is not None else None
        if name is None:
            type_node = node.child_by_field_name("type")
            name = CodeChunker._find_identifier(type_node) if type_node is not None else None
        if name is None:
            return f"<{node.type}@{node.start_point.row + 1}>"
        return CodeChunker._node_text(name, source)

    @staticmethod
    def _find_identifier(node: Node) -> Node | None:
        if node.type in {"field_identifier", "identifier", "type_identifier"}:
            return node
        for child in node.named_children:
            found = CodeChunker._find_identifier(child)
            if found is not None:
                return found
        return None

    @staticmethod
    def _walk(node: Node) -> tuple[Node, ...]:
        result: list[Node] = []
        stack = list(reversed(node.named_children))
        while stack:
            current = stack.pop()
            result.append(current)
            stack.extend(reversed(current.named_children))
        return tuple(result)

    @staticmethod
    def _node_text(node: Node, source: bytes) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8")
