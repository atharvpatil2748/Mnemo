"""Built-in OpenXML parser for PowerPoint presentations (.pptx).

Conforms to ParserInterfaceV1 and returns a ParseResult (ADR-0011, ADR-0036).
Pure transformation component — zero storage, zero canonicalization, zero identity generation.
"""

import mimetypes
import re
from pathlib import Path

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
    RawTableBlock,
    RawTextBlock,
    TransientAsset,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import (
    AssetContainerKind,
    AssetLocator,
    AssetLocatorKind,
    DocType,
    DocumentMetadata,
)
from mnemo.models._shared import FrozenMetadata

from .asset_extraction import (
    DEFAULT_ASSET_EXTRACTION_LIMITS,
    AssetExtractionLimits,
    asset_limit_reason,
    bounded_asset_result,
    resolve_archive_target,
    safe_xml_from_bytes,
    text_only_v1,
    validated_zip,
)

_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
_IMAGE_RELATIONSHIP_SUFFIXES = ("/image", "/hdphoto")
_PPTX_MEDIA_TYPES = {
    ".svg": "image/svg+xml",
    ".wdp": "image/vnd.ms-photo",
}


class PPTXParser(ParserInterfaceV2):
    """Parses Microsoft PowerPoint (.pptx) presentation files into slide-aware raw blocks."""

    def __init__(self, limits: AssetExtractionLimits = DEFAULT_ASSET_EXTRACTION_LIMITS) -> None:
        self._limits = limits

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
        return text_only_v1(self.parse_with_assets(data, filename, metadata).parse_result)

    def parse_with_assets(
        self, data: bytes, filename: str, metadata: FileMetadata
    ) -> ParseResultV2:
        """Parse text plus bounded slide-picture occurrences."""
        if not data:
            raise ContractValidationError(f"Cannot parse empty PPTX: {filename}")

        blocks: list[RawBlock] = []
        assets: list[TransientAsset] = []
        omissions: list[AssetExtractionOmission] = []
        slide_count = 0
        try:
            with validated_zip(data, self._limits) as z:
                slide_files = [
                    f for f in z.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", f)
                ]
                if not slide_files:
                    raise ContractValidationError(f"PPTX contains no slide files: {filename}")
                if len(slide_files) > self._limits.max_container_units:
                    raise ContractValidationError("PPTX exceeds configured slide-count limit")

                def _slide_order(sf: str) -> int:
                    m = re.search(r"\d+", sf)
                    return int(m.group(0)) if m else 0

                slide_files.sort(key=_slide_order)
                slide_count = len(slide_files)
                supplemental_asset_paths: set[str] = set()

                ordinal = 0
                for i, sf in enumerate(slide_files, start=1):
                    tree = safe_xml_from_bytes(z.read(sf))
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

                    ordinal = self._extract_slide_images(
                        archive=z,
                        slide_path=sf,
                        slide_number=i,
                        slide=tree,
                        ordinal=ordinal,
                        blocks=blocks,
                        assets=assets,
                        omissions=omissions,
                        supplemental_asset_paths=supplemental_asset_paths,
                    )

        except ContractValidationError as error:
            if str(error).startswith("document container"):
                raise ContractValidationError(f"Failed to open PPTX archive: {error}") from error
            raise
        except Exception as err:
            raise ContractValidationError(f"Failed to open PPTX archive: {err}") from err

        title = Path(filename).stem if filename else "Untitled"
        doc_metadata = DocumentMetadata(
            content_hash=metadata.content_hash,
            title=title,
            metadata=FrozenMetadata({"title": title, "slides_count": slide_count}),
        )

        parsed = ParseResult(
            doc_type=DocType.SLIDES,
            metadata=doc_metadata,
            blocks=tuple(blocks),
            extracted_assets=tuple(assets),
            language="en",
        )
        return bounded_asset_result(
            parsed,
            parser_id="mnemo.pptx",
            container_kind=AssetContainerKind.PPTX,
            limits=self._limits,
            omissions=tuple(omissions),
        )

    def _extract_slide_images(
        self,
        *,
        archive: object,
        slide_path: str,
        slide_number: int,
        slide: object,
        ordinal: int,
        blocks: list[RawBlock],
        assets: list[TransientAsset],
        omissions: list[AssetExtractionOmission],
        supplemental_asset_paths: set[str],
    ) -> int:
        import xml.etree.ElementTree as ET
        import zipfile

        if not isinstance(archive, zipfile.ZipFile) or not isinstance(slide, ET.Element):
            raise TypeError("invalid slide extraction inputs")
        relation_path = posix_slide_relationship_path(slide_path)
        relations: dict[str, tuple[str, bool, str]] = {}
        if relation_path in archive.namelist():
            relation_root = safe_xml_from_bytes(archive.read(relation_path))
            for relation in relation_root:
                relationship_id = relation.attrib.get("Id")
                target = relation.attrib.get("Target")
                if relationship_id and target:
                    relations[relationship_id] = (
                        target,
                        relation.attrib.get("TargetMode", "").lower() == "external",
                        relation.attrib.get("Type", ""),
                    )

        pictured_relationship_ids: set[str] = set()
        for shape_index, picture in enumerate(
            element for element in slide.iter() if element.tag.endswith("}pic")
        ):
            relationship_id = next(
                (
                    element.attrib.get(_REL_ID)
                    for element in picture.iter()
                    if element.tag.endswith("}blip") and element.attrib.get(_REL_ID)
                ),
                None,
            )
            if relationship_id is not None:
                pictured_relationship_ids.add(relationship_id)
            geometry = _pptx_geometry(picture)
            locator = AssetLocator(
                kind=AssetLocatorKind.PPTX_SLIDE,
                ordinal=ordinal,
                slide_number=slide_number,
                geometry=geometry,
            )
            picture_relation = relations.get(relationship_id or "")
            if picture_relation is None:
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                continue
            target, external, _ = picture_relation
            if external:
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.EXTERNAL_REFERENCE,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                continue
            try:
                asset_path = resolve_archive_target(slide_path, target)
            except ContractValidationError:
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                continue
            if asset_path not in archive.namelist():
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                continue
            media_type = mimetypes.guess_type(asset_path)[0] or "application/octet-stream"
            limit_reason = asset_limit_reason(
                asset_count=len(assets),
                total_bytes=sum(len(asset.raw_bytes) for asset in assets),
                next_bytes=archive.getinfo(asset_path).file_size,
                limits=self._limits,
            )
            if limit_reason is not None:
                omissions.append(
                    AssetExtractionOmission(
                        reason=limit_reason,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                        declared_media_type=media_type,
                    )
                )
                continue
            local_id = f"image-occurrence-{len(assets) + 1}"
            assets.append(
                TransientAsset(
                    parser_local_id=local_id,
                    raw_bytes=archive.read(asset_path),
                    mime_type=media_type,
                    page_number=slide_number,
                )
            )
            alt_text = _pptx_alt_text(picture)
            blocks.append(
                RawImageBlock(
                    ordinal=ordinal,
                    page_number=slide_number,
                    bounding_box=geometry,
                    parser_local_id=local_id,
                    alt_text=alt_text,
                    metadata=FrozenMetadata(
                        {
                            "parser.asset.relationship_id": relationship_id,
                            "parser.asset.shape_index": shape_index,
                            "parser.asset.geometry_unit": "emu",
                        }
                    ),
                )
            )
            ordinal += 1

        # Some valid OOXML images are slide backgrounds or alternate image
        # representations (for example SVG and JPEG XR) and therefore are not
        # represented by a ``p:pic`` node. Retain each such packaged binary
        # once, at its first authoritatively known slide relationship, rather
        # than silently dropping it or fabricating repeated geometry.
        for relationship_id, (target, external, relation_type) in sorted(relations.items()):
            if relationship_id in pictured_relationship_ids or not relation_type.endswith(
                _IMAGE_RELATIONSHIP_SUFFIXES
            ):
                continue
            locator = AssetLocator(
                kind=AssetLocatorKind.PPTX_SLIDE,
                ordinal=ordinal,
                slide_number=slide_number,
            )
            if external:
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.EXTERNAL_REFERENCE,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                continue
            try:
                asset_path = resolve_archive_target(slide_path, target)
            except ContractValidationError:
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                continue
            if asset_path in supplemental_asset_paths:
                continue
            if asset_path not in archive.namelist():
                omissions.append(
                    AssetExtractionOmission(
                        reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                continue
            media_type = _PPTX_MEDIA_TYPES.get(
                Path(asset_path).suffix.casefold(),
                mimetypes.guess_type(asset_path)[0] or "application/octet-stream",
            )
            limit_reason = asset_limit_reason(
                asset_count=len(assets),
                total_bytes=sum(len(asset.raw_bytes) for asset in assets),
                next_bytes=archive.getinfo(asset_path).file_size,
                limits=self._limits,
            )
            if limit_reason is not None:
                omissions.append(
                    AssetExtractionOmission(
                        reason=limit_reason,
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                        declared_media_type=media_type,
                    )
                )
                continue
            local_id = f"image-occurrence-{len(assets) + 1}"
            assets.append(
                TransientAsset(
                    parser_local_id=local_id,
                    raw_bytes=archive.read(asset_path),
                    mime_type=media_type,
                    page_number=slide_number,
                )
            )
            blocks.append(
                RawImageBlock(
                    ordinal=ordinal,
                    page_number=slide_number,
                    parser_local_id=local_id,
                    metadata=FrozenMetadata(
                        {
                            "parser.asset.relationship_id": relationship_id,
                            "parser.asset.package_fallback": True,
                        }
                    ),
                )
            )
            supplemental_asset_paths.add(asset_path)
            ordinal += 1
        return ordinal


def posix_slide_relationship_path(slide_path: str) -> str:
    path = Path(slide_path)
    return f"{path.parent.as_posix()}/_rels/{path.name}.rels"


def _pptx_geometry(picture: object) -> tuple[float, float, float, float] | None:
    import xml.etree.ElementTree as ET

    if not isinstance(picture, ET.Element):
        return None
    offset = next((item for item in picture.iter() if item.tag.endswith("}off")), None)
    extent = next((item for item in picture.iter() if item.tag.endswith("}ext")), None)
    if offset is None or extent is None:
        return None
    try:
        x = float(offset.attrib["x"])
        y = float(offset.attrib["y"])
        return (x, y, x + float(extent.attrib["cx"]), y + float(extent.attrib["cy"]))
    except (KeyError, TypeError, ValueError):
        return None


def _pptx_alt_text(picture: object) -> str | None:
    import xml.etree.ElementTree as ET

    if not isinstance(picture, ET.Element):
        return None
    for item in picture.iter():
        if item.tag.endswith("}cNvPr"):
            value = item.attrib.get("descr") or item.attrib.get("title")
            return value.strip() if value and value.strip() else None
    return None
