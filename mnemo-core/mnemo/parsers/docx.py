"""Built-in parser for Microsoft Word (.docx) files."""

import io

import docx
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.parts.image import ImagePart
from docx.table import Table
from docx.text.paragraph import Paragraph

from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser import ParserInterfaceV2
from mnemo.interfaces.parser_models import (
    AssetExtractionOmission,
    AssetOmissionReason,
    ParseResult,
    ParseResultV2,
    RawBlock,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawTableBlock,
    RawTextBlock,
    TransientAsset,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import (
    AssetContainerKind,
    AssetLocator,
    AssetLocatorKind,
    FrozenMetadata,
)

from .asset_extraction import (
    DEFAULT_ASSET_EXTRACTION_LIMITS,
    AssetExtractionLimits,
    asset_limit_reason,
    bounded_asset_result,
    unique_image_v1,
    validated_zip,
)

_RELATIONSHIP_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


class DOCXParser(ParserInterfaceV2):
    """Parses DOCX documents into structural blocks and transient assets."""

    def __init__(self, limits: AssetExtractionLimits = DEFAULT_ASSET_EXTRACTION_LIMITS) -> None:
        self._limits = limits

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
        return unique_image_v1(self.parse_with_assets(data, filename, metadata).parse_result)

    def parse_with_assets(
        self, data: bytes, filename: str, metadata: FileMetadata
    ) -> ParseResultV2:
        if not data:
            raise ContractValidationError(f"Cannot parse empty DOCX: {filename}")

        try:
            with validated_zip(data, self._limits):
                pass
        except ContractValidationError as error:
            raise ContractValidationError(f"Failed to open DOCX: {error}") from error

        try:
            doc = docx.Document(io.BytesIO(data))
        except Exception as e:
            raise ContractValidationError(f"Failed to open DOCX: {e}") from e

        blocks: list[RawBlock] = []
        assets: list[TransientAsset] = []
        omissions: list[AssetExtractionOmission] = []

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
        for body_position, child in enumerate(parent_elm.iterchildren()):
            if isinstance(child, CT_P):
                p = Paragraph(child, doc)
                text = p.text.strip()
                style_name = p.style.name if p.style else ""

                if text and style_name.startswith("Heading"):
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
                elif text and "List" in style_name:
                    current_list_items.append(text)
                elif text:
                    flush_list()
                    blocks.append(
                        RawTextBlock(
                            ordinal=ordinal,
                            text=text,
                        )
                    )
                    ordinal += 1
                ordinal = self._append_paragraph_images(
                    paragraph=p,
                    document=doc,
                    body_position=body_position,
                    ordinal=ordinal,
                    blocks=blocks,
                    assets=assets,
                    omissions=omissions,
                )
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

        from mnemo.models import DocType, DocumentMetadata

        doc_meta = DocumentMetadata(
            content_hash=metadata.content_hash,
            title=filename,
            authors=(),
            page_count=None,
            metadata=FrozenMetadata(metadata.metadata),
        )

        parsed = ParseResult(
            blocks=tuple(blocks),
            extracted_assets=tuple(assets),
            metadata=doc_meta,
            language="en",
            doc_type=DocType.GENERIC,
        )
        return bounded_asset_result(
            parsed,
            parser_id="mnemo.docx",
            container_kind=AssetContainerKind.DOCX,
            limits=self._limits,
            omissions=tuple(omissions),
        )

    def _append_paragraph_images(
        self,
        *,
        paragraph: Paragraph,
        document: docx.document.Document,
        body_position: int,
        ordinal: int,
        blocks: list[RawBlock],
        assets: list[TransientAsset],
        omissions: list[AssetExtractionOmission],
    ) -> int:
        """Append drawing occurrences in paragraph XML order without deduplicating uses."""
        occurrence_index = 0
        for element in paragraph._p.iter():
            if not element.tag.endswith("}blip"):
                continue
            relationship_id = element.attrib.get(_RELATIONSHIP_EMBED)
            locator = AssetLocator(
                kind=AssetLocatorKind.DOCX_POSITION,
                ordinal=ordinal,
                inline_position=body_position,
            )
            if not relationship_id:
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                        ordinal=ordinal,
                        locator=locator,
                    )
                )
                occurrence_index += 1
                continue
            image_part = document.part.related_parts.get(relationship_id)
            if not isinstance(image_part, ImagePart):
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                occurrence_index += 1
                continue
            limit_reason = asset_limit_reason(
                asset_count=len(assets),
                total_bytes=sum(len(asset.raw_bytes) for asset in assets),
                next_bytes=len(image_part.blob),
                limits=self._limits,
            )
            if limit_reason is not None:
                omissions.append(
                    AssetExtractionOmission(
                        reason=limit_reason,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                        declared_media_type=image_part.content_type,
                    )
                )
                occurrence_index += 1
                continue
            parser_local_id = f"image-occurrence-{len(assets) + 1}"
            assets.append(
                TransientAsset(
                    parser_local_id=parser_local_id,
                    raw_bytes=image_part.blob,
                    mime_type=image_part.content_type,
                )
            )
            blocks.append(
                RawImageBlock(
                    ordinal=ordinal,
                    parser_local_id=parser_local_id,
                    metadata=FrozenMetadata(
                        {
                            "parser.asset.relationship_id": relationship_id,
                            "parser.asset.inline_position": body_position,
                            "parser.asset.occurrence_index": occurrence_index,
                        }
                    ),
                )
            )
            ordinal += 1
            occurrence_index += 1
        return ordinal
