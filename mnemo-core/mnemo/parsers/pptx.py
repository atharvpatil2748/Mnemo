"""Built-in OpenXML parser for PowerPoint presentations (.pptx).

Conforms to ParserInterfaceV1 and returns a ParseResult (ADR-0011, ADR-0036).
Pure transformation component — zero storage, zero canonicalization, zero identity generation.
"""

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawBlock,
    RawHeadingBlock,
    RawTableBlock,
    RawTextBlock,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import DocType, DocumentMetadata
from mnemo.models._shared import FrozenMetadata


class PPTXParser(ParserInterfaceV1):
    """Parses Microsoft PowerPoint (.pptx) presentation files into slide-aware raw blocks."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (
            ".pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_images=False,
            supports_tables=True,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        """Parse PPTX bytes into a slide-aware ParseResult."""
        if not data:
            raise ContractValidationError(f"Cannot parse empty PPTX: {filename}")

        blocks: list[RawBlock] = []
        slide_count = 0
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as z:
                slide_files = [
                    f for f in z.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", f)
                ]
                if not slide_files:
                    raise ContractValidationError(f"PPTX contains no slide files: {filename}")

                def _slide_order(sf: str) -> int:
                    m = re.search(r"\d+", sf)
                    return int(m.group(0)) if m else 0

                slide_files.sort(key=_slide_order)
                slide_count = len(slide_files)

                ordinal = 0
                for i, sf in enumerate(slide_files, start=1):
                    tree = ET.fromstring(z.read(sf))
                    titles: list[str] = []
                    bodies: list[str] = []
                    tables: list[list[tuple[str, ...]]] = []

                    for sp in tree.iter():
                        # Shape text
                        if sp.tag.endswith("}sp"):
                            is_title = False
                            for ph in sp.iter():
                                if ph.tag.endswith("}ph"):
                                    ph_type = ph.attrib.get("type", "")
                                    if ph_type in ("title", "ctrTitle"):
                                        is_title = True
                                        break

                            for p in sp.iter():
                                if p.tag.endswith("}p"):
                                    texts = [
                                        t.text for t in p.iter() if t.tag.endswith("}t") and t.text
                                    ]
                                    p_text = " ".join(texts).strip()
                                    if p_text:
                                        if is_title:
                                            titles.append(p_text)
                                        else:
                                            bodies.append(p_text)

                        # Table elements
                        elif sp.tag.endswith("}tbl"):
                            tbl_rows: list[tuple[str, ...]] = []
                            for tr in sp.iter():
                                if tr.tag.endswith("}tr"):
                                    row_cells: list[str] = []
                                    for tc in tr.iter():
                                        if tc.tag.endswith("}tc"):
                                            cell_texts = [
                                                t.text
                                                for t in tc.iter()
                                                if t.tag.endswith("}t") and t.text
                                            ]
                                            row_cells.append(" ".join(cell_texts).strip())
                                    if row_cells:
                                        tbl_rows.append(tuple(row_cells))
                            if tbl_rows:
                                tables.append(tbl_rows)

                    slide_title = " ".join(titles) if titles else f"Slide {i}"
                    blocks.append(
                        RawHeadingBlock(
                            text=slide_title,
                            level=1,
                            ordinal=ordinal,
                            page_number=i,
                        )
                    )
                    ordinal += 1

                    for body_text in bodies:
                        blocks.append(
                            RawTextBlock(
                                text=body_text,
                                ordinal=ordinal,
                                page_number=i,
                            )
                        )
                        ordinal += 1

                    for tbl_rows in tables:
                        blocks.append(
                            RawTableBlock(
                                rows=tuple(tbl_rows),
                                header_row_count=1 if len(tbl_rows) > 1 else 0,
                                ordinal=ordinal,
                                page_number=i,
                            )
                        )
                        ordinal += 1

        except ContractValidationError:
            raise
        except Exception as err:
            raise ContractValidationError(f"Failed to open PPTX archive: {err}") from err

        title = Path(filename).stem if filename else "Untitled"
        doc_metadata = DocumentMetadata(
            content_hash=metadata.content_hash,
            title=title,
            metadata=FrozenMetadata({"title": title, "slides_count": slide_count}),
        )

        return ParseResult(
            doc_type=DocType.SLIDES,
            metadata=doc_metadata,
            blocks=tuple(blocks),
            extracted_assets=(),
            language="en",
        )
