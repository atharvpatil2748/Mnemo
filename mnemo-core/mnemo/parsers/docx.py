"""Built-in parser for Microsoft Word (.docx) files."""

import io

import docx
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.parts.image import ImagePart
from docx.table import Table
from docx.text.paragraph import Paragraph

from mnemo.interfaces.errors import ContractValidationError
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


class DOCXParser(ParserInterfaceV1):
    """Parses DOCX documents into structural blocks and transient assets."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".docx",)

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
            raise ContractValidationError(f"Cannot parse empty DOCX: {filename}")

        try:
            doc = docx.Document(io.BytesIO(data))
        except Exception as e:
            raise ContractValidationError(f"Failed to open DOCX: {e}") from e

        blocks: list[RawBlock] = []
        assets: list[TransientAsset] = []

        ordinal = 0
        current_list_items: list[str] = []

        def flush_list() -> None:
            nonlocal ordinal
            if current_list_items:
                blocks.append(
                    RawListBlock(
                        ordinal=ordinal,
                        items=tuple(current_list_items),
                    )
                )
                ordinal += 1
                current_list_items.clear()

        parent_elm = doc.element.body
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                p = Paragraph(child, doc)
                text = p.text.strip()
                style_name = p.style.name if p.style else ""

                if not text:
                    continue

                if style_name.startswith("Heading"):
                    flush_list()
                    try:
                        level = int(style_name.split(" ")[-1])
                        if level < 1 or level > 6:
                            level = 1
                    except ValueError:
                        level = 1
                    blocks.append(
                        RawHeadingBlock(
                            ordinal=ordinal,
                            text=text,
                            level=level,
                        )
                    )
                    ordinal += 1
                elif "List" in style_name:
                    current_list_items.append(text)
                else:
                    flush_list()
                    blocks.append(
                        RawTextBlock(
                            ordinal=ordinal,
                            text=text,
                        )
                    )
                    ordinal += 1
            elif isinstance(child, CT_Tbl):
                flush_list()
                t = Table(child, doc)
                rows = []
                for row in t.rows:
                    cells = []
                    for cell in row.cells:
                        cells.append(cell.text.strip())
                    rows.append(tuple(cells))

                if rows:
                    blocks.append(
                        RawTableBlock(
                            ordinal=ordinal,
                            rows=tuple(rows),
                            header_row_count=1 if len(rows) > 1 else 0,  # best effort header
                        )
                    )
                    ordinal += 1

        flush_list()

        # Extract images from relationships
        img_idx = 1
        # Use a set to prevent duplicating identical images that might be referenced multiple times
        seen_rids = set()

        for rel_id, rel in doc.part.rels.items():
            if isinstance(rel.target_part, ImagePart) and rel_id not in seen_rids:
                seen_rids.add(rel_id)
                image_part = rel.target_part
                parser_local_id = f"image-{img_idx}"

                blocks.append(
                    RawImageBlock(
                        ordinal=ordinal,
                        parser_local_id=parser_local_id,
                    )
                )
                ordinal += 1

                assets.append(
                    TransientAsset(
                        parser_local_id=parser_local_id,
                        raw_bytes=image_part.blob,
                        mime_type=image_part.content_type,
                    )
                )
                img_idx += 1

        from mnemo.models import DocType, DocumentMetadata
        from mnemo.models._shared import FrozenMetadata

        doc_meta = DocumentMetadata(
            content_hash=metadata.content_hash,
            title=filename,
            authors=(),
            page_count=None,
            metadata=FrozenMetadata(metadata.metadata),
        )

        return ParseResult(
            blocks=tuple(blocks),
            extracted_assets=tuple(assets),
            metadata=doc_meta,
            language="en",
            doc_type=DocType.GENERIC,
        )
