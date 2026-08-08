"""Built-in parser for JSON files.

Pure transformation component — no I/O, no storage, no canonicalization.
Conforms to ParserInterfaceV1 and returns a ParseResult (ADR-0011).
"""

import json
import logging
from typing import Any

from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawBlock,
    RawTextBlock,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import DocType, DocumentMetadata
from mnemo.models._shared import FrozenMetadata

logger = logging.getLogger(__name__)


class JSONParser(ParserInterfaceV1):
    """Parses JSON files into RawTextBlock by flattening keys with context.

    Implements ParserInterfaceV1 (ADR-0011). Pure transformation — performs
    zero storage, zero canonicalization, and zero identity generation.
    """

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".json",)

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_images=False,
            supports_tables=False,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        """Parse JSON bytes into a ParseResult."""
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractValidationError("JSON file is not valid UTF-8.") from exc

        if not content.strip():
            doc_meta = self._build_doc_meta(metadata, filename)
            return ParseResult(
                blocks=(),
                extracted_assets=(),
                metadata=doc_meta,
                language="en",
                doc_type=DocType.GENERIC,
            )

        try:
            parsed_json = json.loads(content)
        except json.JSONDecodeError as exc:
            # We don't fail parsing hard on invalid JSON to allow best-effort extraction,
            # but if it fails completely, we just return empty or error.
            # However, the prompt says "malformed input tests".
            # Raising ContractValidationError is appropriate.
            raise ContractValidationError("File is not valid JSON.") from exc

        doc_meta = self._build_doc_meta(metadata, filename)
        blocks: list[RawBlock] = []

        # Flatten JSON to text with key context
        for ordinal, line in enumerate(self._flatten_json(parsed_json)):
            blocks.append(RawTextBlock(ordinal=ordinal, text=line))

        return ParseResult(
            blocks=tuple(blocks),
            extracted_assets=(),
            metadata=doc_meta,
            language="en",
            doc_type=DocType.GENERIC,
        )

    @staticmethod
    def _build_doc_meta(metadata: FileMetadata, filename: str) -> DocumentMetadata:
        return DocumentMetadata(
            content_hash=metadata.content_hash,
            title=filename or "Untitled",
            metadata=FrozenMetadata(dict(metadata.metadata)),
        )

    def _flatten_json(self, data: Any, prefix: str = "") -> list[str]:
        """Flatten JSON structure into a list of strings with key context."""
        lines: list[str] = []
        if isinstance(data, dict):
            for k, v in data.items():
                new_prefix = f"{prefix}{k}." if prefix else f"{k}."
                lines.extend(self._flatten_json(v, new_prefix))
        elif isinstance(data, list):
            for i, v in enumerate(data):
                new_prefix = f"{prefix}[{i}]."
                lines.extend(self._flatten_json(v, new_prefix))
        else:
            # Base case: primitive value
            formatted_prefix = prefix[:-1] if prefix.endswith(".") else prefix
            if formatted_prefix:
                lines.append(f"{formatted_prefix}: {data}")
            else:
                lines.append(str(data))
        return lines
