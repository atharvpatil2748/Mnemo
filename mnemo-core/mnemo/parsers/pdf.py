"""Built-in parser for Portable Document Format (PDF) files."""

from typing import Any

import fitz  # type: ignore[import-untyped]

from mnemo.interfaces.errors import ContractValidationError, UnsupportedError
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawBlock,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawTableBlock,
    RawTextBlock,
    TransientAsset,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import DocType, DocumentMetadata
from mnemo.models._shared import BoundingBox, FrozenMetadata


class PDFParser(ParserInterfaceV1):
    """Parses PDF documents into structural blocks and transient assets."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".pdf",)

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_images=True,
            supports_tables=True,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        if not data:
            raise ContractValidationError(f"Cannot parse empty PDF: {filename}")

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as e:
            raise ContractValidationError(f"Failed to open PDF: {e}") from e

        if doc.needs_pass:
            doc.close()
            raise UnsupportedError(f"Encrypted PDFs are not supported: {filename}")

        try:
            return self._parse_doc(doc, data, filename, metadata)
        finally:
            doc.close()

    def _parse_doc(
        self, doc: fitz.Document, data: bytes, filename: str, file_metadata: FileMetadata
    ) -> ParseResult:
        blocks: list[RawBlock] = []
        assets: list[TransientAsset] = []

        doc_meta = self._extract_metadata(doc, filename, file_metadata)

        # We need to process pages and assign ordinals
        ordinal = 0
        for page_num, page in enumerate(doc, start=1):
            ordinal = self._extract_page(page, page_num, ordinal, blocks, assets)

        return ParseResult(
            blocks=tuple(blocks),
            extracted_assets=tuple(assets),
            metadata=doc_meta,
            language="en",  # PyMuPDF doesn't natively detect language easily
            doc_type=DocType.GENERIC,
        )

    def _extract_metadata(
        self, doc: fitz.Document, filename: str, file_metadata: FileMetadata
    ) -> DocumentMetadata:
        pdf_meta = doc.metadata or {}

        # PyMuPDF dates are typically D:YYYYMMDDHHmmSSZ, but we let
        # the model default the date, so we do not extract created_at.

        title = pdf_meta.get("title") or filename
        author_str = pdf_meta.get("author")
        authors = (author_str,) if author_str else ()

        extracted_custom: dict[str, Any] = {}
        if pdf_meta.get("creator"):
            extracted_custom["creator"] = pdf_meta.get("creator")
        if pdf_meta.get("producer"):
            extracted_custom["producer"] = pdf_meta.get("producer")
        if pdf_meta.get("creationDate"):
            extracted_custom["creation_date"] = pdf_meta.get("creationDate")
        if pdf_meta.get("modDate"):
            extracted_custom["modification_date"] = pdf_meta.get("modDate")

        extracted_custom["page_count"] = doc.page_count

        custom_meta = {**file_metadata.metadata, **extracted_custom}

        return DocumentMetadata(
            content_hash=file_metadata.content_hash,
            title=title,
            authors=authors,
            page_count=doc.page_count,
            metadata=FrozenMetadata(custom_meta),
        )

    def _extract_page(
        self,
        page: fitz.Page,
        page_num: int,
        start_ordinal: int,
        blocks: list[RawBlock],
        assets: list[TransientAsset],
    ) -> int:
        ordinal = start_ordinal

        # 1. Extract tables first, to avoid duplicating text in regular text blocks.
        tables = page.find_tables()
        table_bboxes: list[fitz.Rect] = []
        if tables:
            for table in tables:
                table_bboxes.append(table.bbox)
                rows = []
                for row in table.extract():
                    rows.append(tuple(cell or "" for cell in row))

                if rows and rows[0]:
                    width = len(rows[0])
                    # Ensure all rows have same width
                    normalized_rows = []
                    for row in rows:
                        if len(row) < width:
                            row = tuple(list(row) + [""] * (width - len(row)))
                        elif len(row) > width:
                            row = row[:width]
                        normalized_rows.append(row)

                    if normalized_rows:
                        header_count = 1 if table.header else 0
                        blocks.append(
                            RawTableBlock(
                                ordinal=ordinal,
                                page_number=page_num,
                                bounding_box=self._to_bbox(table.bbox),
                                rows=tuple(normalized_rows),
                                header_row_count=header_count,
                            )
                        )
                        ordinal += 1

        # 2. Extract text blocks and images using get_text("dict")
        page_dict = page.get_text("dict")
        median_size = self._compute_median_font_size(page_dict)

        for block in page_dict.get("blocks", []):
            bbox = fitz.Rect(block["bbox"])

            # Text block
            if block["type"] == 0:
                # PyMuPDF may group adjacent table and non-table spans into one
                # text block.  Filtering the whole block by its bounding box can
                # therefore discard unique text outside the table.  Remove only
                # spans substantially covered by a table projection.
                filtered_block = self._without_table_spans(block, table_bboxes)
                text, is_heading, is_list = self._analyze_text_block(filtered_block, median_size)
                if not text.strip():
                    continue

                b_box = self._to_bbox(bbox)
                if is_heading:
                    blocks.append(
                        RawHeadingBlock(
                            ordinal=ordinal,
                            page_number=page_num,
                            bounding_box=b_box,
                            text=text.strip(),
                            level=1,  # Defaulting to H1 for all headings for now
                        )
                    )
                elif is_list:
                    # Very simple list handling: just split by newlines
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    if lines:
                        blocks.append(
                            RawListBlock(
                                ordinal=ordinal,
                                page_number=page_num,
                                bounding_box=b_box,
                                items=tuple(lines),
                            )
                        )
                    else:
                        continue
                else:
                    blocks.append(
                        RawTextBlock(
                            ordinal=ordinal,
                            page_number=page_num,
                            bounding_box=b_box,
                            text=text.strip(),
                        )
                    )
                ordinal += 1

            # Image block
            elif block["type"] == 1:
                img_bytes = block.get("image")
                ext = block.get("ext", "jpeg")
                if img_bytes:
                    local_id = f"block-{ordinal}"
                    mime = f"image/{ext}"
                    assets.append(
                        TransientAsset(
                            parser_local_id=local_id,
                            raw_bytes=img_bytes,
                            mime_type=mime,
                            page_number=page_num,
                        )
                    )
                    blocks.append(
                        RawImageBlock(
                            ordinal=ordinal,
                            page_number=page_num,
                            bounding_box=self._to_bbox(bbox),
                            parser_local_id=local_id,
                        )
                    )
                    ordinal += 1

        return ordinal

    def _without_table_spans(
        self,
        block: dict[str, Any],
        table_bboxes: list[fitz.Rect],
    ) -> dict[str, Any]:
        """Return a text block with table-covered spans removed."""
        filtered_lines: list[dict[str, Any]] = []
        for line in block.get("lines", []):
            retained_spans = [
                span
                for span in line.get("spans", [])
                if "bbox" not in span
                or not self._overlaps_any(fitz.Rect(span["bbox"]), table_bboxes)
            ]
            if retained_spans:
                filtered_lines.append({**line, "spans": retained_spans})
        return {**block, "lines": filtered_lines}

    def _to_bbox(self, rect: fitz.Rect | tuple[float, float, float, float]) -> BoundingBox:
        if isinstance(rect, fitz.Rect):
            return (rect.x0, rect.y0, rect.x1, rect.y1)
        return (rect[0], rect[1], rect[2], rect[3])

    def _overlaps_any(self, rect: fitz.Rect, table_bboxes: list[fitz.Rect]) -> bool:
        rect_area = rect.get_area()
        if rect_area <= 0:
            return False
        for t_rect in table_bboxes:
            if rect.intersects(t_rect):
                # ``Rect.intersect`` mutates its receiver.  Intersect a copy so
                # both the denominator and subsequent comparisons continue to
                # use the canonical text-block rectangle.
                intersect = fitz.Rect(rect).intersect(t_rect)
                if intersect.get_area() > 0.5 * rect_area:
                    return True
        return False

    def _compute_median_font_size(self, page_dict: dict[str, Any]) -> float:
        sizes = []
        for block in page_dict.get("blocks", []):
            if block["type"] == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        sizes.append(span.get("size", 11.0))
        if not sizes:
            return 11.0
        sizes.sort()
        return float(sizes[len(sizes) // 2])

    def _analyze_text_block(
        self, block: dict[str, Any], median_size: float
    ) -> tuple[str, bool, bool]:
        text_parts = []
        nonempty_span_sizes: list[float] = []

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                text_parts.append(span_text)
                if span_text.strip():
                    nonempty_span_sizes.append(float(span.get("size", 0.0)))
            text_parts.append("\n")

        text = "".join(text_parts).strip()
        # A text block is a heading only when all of its meaningful spans use
        # heading-sized type.  Using the maximum alone misclassifies mixed
        # blocks (for example, body bullets followed by a larger section label)
        # and can make the body text disappear into heading-path metadata.
        heading_threshold = median_size * 1.2
        is_heading = bool(nonempty_span_sizes) and all(
            size > heading_threshold for size in nonempty_span_sizes
        )

        # Check if list (starts with bullet)
        bullets = {"•", "-", "1.", "*"}
        is_list = False
        for bullet in bullets:
            if text.startswith(bullet):
                is_list = True
                break

        return text, is_heading, is_list
