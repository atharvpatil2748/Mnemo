"""Built-in parser for Plain Text files.

Pure transformation component — no I/O, no storage, no canonicalization.
Conforms to ParserInterfaceV1 and returns a ParseResult (ADR-0011).
"""

import logging
from pathlib import PurePath

from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawBlock,
    RawCodeBlock,
    RawTextBlock,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import DocType, DocumentMetadata
from mnemo.models._shared import FrozenMetadata

logger = logging.getLogger(__name__)

_CODE_EXTENSIONS: dict[str, str] = {
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


class PlainTextParser(ParserInterfaceV1):
    """Parses plain text files into RawTextBlock (for prose) or RawCodeBlock (for code).

    Implements ParserInterfaceV1 (ADR-0011). Pure transformation — performs
    zero storage, zero canonicalization, and zero identity generation.
    """

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".txt", ".log", *sorted(_CODE_EXTENSIONS.keys()))

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_images=False,
            supports_tables=False,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        """Parse plain text or code bytes into a ParseResult."""
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractValidationError("Text file is not valid UTF-8.") from exc

        # Construct basic document metadata (no extracted title from plain text)
        doc_meta = DocumentMetadata(
            content_hash=metadata.content_hash,
            title=filename or "Untitled",
            metadata=FrozenMetadata(dict(metadata.metadata)),
        )

        blocks: list[RawBlock] = []

        ext = PurePath(filename).suffix.casefold() if filename else ""
        if ext in _CODE_EXTENSIONS:
            if content.strip():
                blocks.append(
                    RawCodeBlock(
                        ordinal=0,
                        code=content,
                        code_language=_CODE_EXTENSIONS[ext],
                    )
                )
        else:
            # Split by double newline to form paragraphs for prose text
            paragraphs = content.split("\n\n")
            ordinal = 0

            for p in paragraphs:
                text = p.strip()
                if text:
                    blocks.append(RawTextBlock(ordinal=ordinal, text=text))
                    ordinal += 1

        return ParseResult(
            blocks=tuple(blocks),
            extracted_assets=(),
            metadata=doc_meta,
            language="en",  # Default, cleaner will override
            doc_type=DocType.GENERIC,
        )
