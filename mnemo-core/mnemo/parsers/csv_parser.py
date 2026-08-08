"""Built-in parser for CSV/TSV files.

Pure transformation component — no I/O, no storage, no canonicalization.
Conforms to ParserInterfaceV1 and returns a ParseResult (ADR-0011).
"""

import csv
import io
import logging

from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawBlock,
    RawTableBlock,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import DocType, DocumentMetadata
from mnemo.models._shared import FrozenMetadata

logger = logging.getLogger(__name__)


class CSVParser(ParserInterfaceV1):
    """Parses CSV/TSV files into a RawTableBlock.

    Implements ParserInterfaceV1 (ADR-0011). Pure transformation — performs
    zero storage, zero canonicalization, and zero identity generation.
    """

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".csv", ".tsv")

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_images=False,
            supports_tables=True,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        """Parse CSV/TSV bytes into a ParseResult."""
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractValidationError("CSV file is not valid UTF-8.") from exc

        doc_meta = DocumentMetadata(
            content_hash=metadata.content_hash,
            title=filename or "Untitled",
            metadata=FrozenMetadata(dict(metadata.metadata)),
        )

        if not content.strip():
            return ParseResult(
                blocks=(),
                extracted_assets=(),
                metadata=doc_meta,
                language="en",
                doc_type=DocType.GENERIC,
            )

        dialect: type[csv.Dialect] | csv.Dialect = csv.excel
        delimiter = "\t" if filename.lower().endswith(".tsv") else ","

        try:
            sniffer = csv.Sniffer()
            # Sniff only works if there is enough data
            sniffed_dialect = sniffer.sniff(content[:2048])
            # Only use sniffed dialect if it makes sense, otherwise fallback to delimiter
            if sniffed_dialect:
                dialect = sniffed_dialect
        except csv.Error:

            class FallbackDialect(csv.excel):
                pass

            FallbackDialect.delimiter = delimiter
            dialect = FallbackDialect()

        reader = csv.reader(io.StringIO(content), dialect=dialect)
        rows: list[tuple[str, ...]] = []
        try:
            for row in reader:
                rows.append(tuple(row))
        except csv.Error as exc:
            raise ContractValidationError("File is not valid CSV.") from exc

        blocks: list[RawBlock] = []
        if rows:
            # Pad rows to the same width just like we did for HTML tables
            max_w = max(len(r) for r in rows)
            padded: list[tuple[str, ...]] = []
            for r in rows:
                padded.append(r + ("",) * (max_w - len(r)))

            blocks.append(
                RawTableBlock(
                    ordinal=0,
                    rows=tuple(padded),
                    header_row_count=1,  # Assume 1 header row for standard CSVs
                )
            )

        return ParseResult(
            blocks=tuple(blocks),
            extracted_assets=(),
            metadata=doc_meta,
            language="en",
            doc_type=DocType.GENERIC,
        )
