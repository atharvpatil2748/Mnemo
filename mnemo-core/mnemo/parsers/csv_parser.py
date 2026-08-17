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

            header = padded[0]
            data_rows = padded[1:]

            if not data_rows:
                blocks.append(
                    RawTableBlock(
                        ordinal=0,
                        rows=(header,),
                        header_row_count=1,
                    )
                )
            else:
                # Estimate token budget: target ~400 tokens per partition (max limit 1024)
                # Tab-separated text approximation: ~3.5 chars per token + column delimiters
                def estimate_row_tokens(row: tuple[str, ...]) -> int:
                    chars = sum(len(cell) for cell in row) + len(row)
                    return max(1, (chars + 3) // 4)

                header_tokens = estimate_row_tokens(header)
                max_partition_tokens = 400
                max_rows_per_block = 50

                ordinal = 0
                current_batch: list[tuple[str, ...]] = []
                current_tokens = header_tokens

                for r in data_rows:
                    r_tokens = estimate_row_tokens(r)
                    if current_batch and (
                        current_tokens + r_tokens > max_partition_tokens
                        or len(current_batch) >= max_rows_per_block
                    ):
                        blocks.append(
                            RawTableBlock(
                                ordinal=ordinal,
                                rows=(header, *current_batch),
                                header_row_count=1,
                            )
                        )
                        ordinal += 1
                        current_batch = [r]
                        current_tokens = header_tokens + r_tokens
                    else:
                        current_batch.append(r)
                        current_tokens += r_tokens

                if current_batch:
                    blocks.append(
                        RawTableBlock(
                            ordinal=ordinal,
                            rows=(header, *current_batch),
                            header_row_count=1,
                        )
                    )

        return ParseResult(
            blocks=tuple(blocks),
            extracted_assets=(),
            metadata=doc_meta,
            language="en",
            doc_type=DocType.GENERIC,
        )
