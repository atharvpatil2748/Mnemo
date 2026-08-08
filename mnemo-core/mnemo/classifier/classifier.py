"""Pure, synchronous, deterministic Document Classifier."""

import dataclasses
import re
from pathlib import Path

from mnemo.interfaces.parser_models import (
    ParseResult,
    RawCodeBlock,
    RawHeadingBlock,
    RawTableBlock,
    RawTextBlock,
)
from mnemo.models.documents import DocType


class DocumentClassifier:
    """Classifies a parsed document using rule-based heuristics.

    This is a pure Phase 3 component: it performs no storage or network I/O.
    LLM-assisted fallback is intentionally deferred to a later orchestration stage.
    """

    CODE_EXTENSIONS = frozenset(
        {
            ".py",
            ".js",
            ".ts",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".sh",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".css",
            ".html",
            ".xml",
            ".rb",
            ".php",
        }
    )

    MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})

    # Compiled patterns for heading-based classification
    # PAPER patterns
    _PAPER_PATTERN = re.compile(r"^(abstract|references|methodology|conclusion)$", re.IGNORECASE)
    # BOOK patterns
    _BOOK_PATTERN = re.compile(
        r"^(chapter\s+\d+|prologue|epilogue|table of contents)$", re.IGNORECASE
    )
    # RESUME patterns
    _RESUME_PATTERN = re.compile(
        r"^(experience|education|skills|employment history|resume|cv)$", re.IGNORECASE
    )
    # DOCUMENTATION patterns
    _DOCS_PATTERN = re.compile(
        r"^(api reference|getting started|installation|quickstart)$", re.IGNORECASE
    )

    def classify(self, result: ParseResult, filename: str | None = None) -> ParseResult:
        """Classify the parsed document and return a new ParseResult with the determined doc_type.

        Rules are evaluated in the following precedence (highest to lowest):
        1. Strong file extensions (e.g., .py -> CODE, .md -> MARKDOWN)
        2. Heading keywords (e.g., "Abstract" -> PAPER, "Chapter 1" -> BOOK)
        3. Structural features (e.g., mostly code blocks -> CODE)
        4. Fallback -> GENERIC

        Args:
            result: The input ParseResult from the parsing (and cleaning) stage.
            filename: The original filename, if available from the orchestrator.

        Returns:
            A new ParseResult instance with the updated doc_type.
        """
        doc_type = self._determine_type(result, filename)

        if doc_type != result.doc_type:
            return dataclasses.replace(result, doc_type=doc_type)

        return result

    def _determine_type(self, result: ParseResult, filename: str | None) -> DocType:
        # 1. Strong extension heuristics
        if filename:
            ext = Path(filename).suffix.lower()
            if ext in self.CODE_EXTENSIONS:
                return DocType.CODE
            if ext in self.MARKDOWN_EXTENSIONS:
                return DocType.MARKDOWN
            if ext == ".eml" or ext == ".msg":
                return DocType.EMAIL

        # 2. Heading heuristics
        for block in result.blocks:
            if isinstance(block, RawHeadingBlock):
                text = block.text.strip()
                if self._PAPER_PATTERN.search(text):
                    return DocType.PAPER
                if self._BOOK_PATTERN.search(text):
                    return DocType.BOOK
                if self._RESUME_PATTERN.search(text):
                    return DocType.RESUME
                if self._DOCS_PATTERN.search(text):
                    return DocType.DOCUMENTATION

        # 3. Structural heuristics
        code_blocks = 0
        text_blocks = 0
        table_blocks = 0
        total_structural_blocks = 0

        for block in result.blocks:
            if isinstance(block, RawCodeBlock):
                code_blocks += 1
                total_structural_blocks += 1
            elif isinstance(block, RawTextBlock):
                text_blocks += 1
                total_structural_blocks += 1
            elif isinstance(block, RawTableBlock):
                table_blocks += 1
                total_structural_blocks += 1

        if total_structural_blocks > 0 and (code_blocks / total_structural_blocks > 0.8):
            return DocType.CODE

        return DocType.GENERIC
