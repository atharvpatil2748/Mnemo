"""Built-in parser for Office Open XML workbooks (.xlsx)."""

from __future__ import annotations

import io
import mimetypes
import posixpath
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from openpyxl import load_workbook  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]

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

_MAX_ROWS_PER_BLOCK = 50
_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_REL_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def _cell_text(value: Any) -> str:
    """Return one deterministic, searchable cell representation."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _normalized_rows(rows: Iterable[tuple[Any, ...]]) -> tuple[tuple[str, ...], ...]:
    """Discard only wholly empty rows and pad remaining rows to a stable width."""
    materialized = [tuple(_cell_text(cell) for cell in row) for row in rows]
    meaningful = [row for row in materialized if any(cell != "" for cell in row)]
    if not meaningful:
        return ()
    width = max(len(row) for row in meaningful)
    return tuple(row + ("",) * (width - len(row)) for row in meaningful)


def _table_partitions(rows: tuple[tuple[str, ...], ...]) -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Partition large sheets without splitting or dropping logical rows."""
    if len(rows) <= _MAX_ROWS_PER_BLOCK:
        return (rows,)
    header = rows[0]
    data = rows[1:]
    capacity = _MAX_ROWS_PER_BLOCK - 1
    return tuple(
        (header, *data[start : start + capacity]) for start in range(0, len(data), capacity)
    )


class XLSXParser(ParserInterfaceV2):
    """Parse workbook sheets into titled, row-preserving table blocks."""

    def __init__(self, limits: AssetExtractionLimits = DEFAULT_ASSET_EXTRACTION_LIMITS) -> None:
        self._limits = limits

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (
            ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
        """Parse exact workbook bytes without evaluating formulas or following links."""
        return text_only_v1(self.parse_with_assets(data, filename, metadata).parse_result)

    def parse_with_assets(
        self, data: bytes, filename: str, metadata: FileMetadata
    ) -> ParseResultV2:
        """Parse exact workbook bytes and bounded drawing-image occurrences."""
        if not data:
            raise ContractValidationError(f"Cannot parse empty XLSX: {filename}")

        archive = validated_zip(data, self._limits)

        try:
            workbook = load_workbook(
                io.BytesIO(data),
                read_only=True,
                data_only=False,
                keep_links=False,
            )
        except Exception as error:
            archive.close()
            raise ContractValidationError(f"Failed to open XLSX workbook: {error}") from error

        blocks: list[RawBlock] = []
        sheet_names: list[str] = []
        ordinal = 0
        try:
            for worksheet in workbook.worksheets:
                rows = _normalized_rows(worksheet.iter_rows(values_only=True))
                if not rows:
                    continue
                sheet_names.append(worksheet.title)
                blocks.append(
                    RawHeadingBlock(
                        ordinal=ordinal,
                        text=worksheet.title,
                        level=1,
                    )
                )
                ordinal += 1
                for partition in _table_partitions(rows):
                    blocks.append(
                        RawTableBlock(
                            ordinal=ordinal,
                            rows=partition,
                            header_row_count=1 if len(partition) > 1 else 0,
                        )
                    )
                    ordinal += 1
        finally:
            workbook.close()

        assets: list[TransientAsset] = []
        omissions: list[AssetExtractionOmission] = []
        try:
            ordinal = self._extract_workbook_images(
                archive=archive,
                start_ordinal=ordinal,
                blocks=blocks,
                assets=assets,
                omissions=omissions,
            )
        finally:
            archive.close()

        title = Path(filename).stem if filename else "Untitled"
        document_metadata = DocumentMetadata(
            content_hash=metadata.content_hash,
            title=title,
            metadata=FrozenMetadata(
                {
                    **dict(metadata.metadata),
                    "sheet_count": len(sheet_names),
                    "sheet_names": tuple(sheet_names),
                }
            ),
        )
        parsed = ParseResult(
            blocks=tuple(blocks),
            extracted_assets=tuple(assets),
            metadata=document_metadata,
            language="en",
            doc_type=DocType.GENERIC,
        )
        return bounded_asset_result(
            parsed,
            parser_id="mnemo.xlsx",
            container_kind=AssetContainerKind.XLSX,
            limits=self._limits,
            omissions=tuple(omissions),
        )

    def _extract_workbook_images(
        self,
        *,
        archive: object,
        start_ordinal: int,
        blocks: list[RawBlock],
        assets: list[TransientAsset],
        omissions: list[AssetExtractionOmission],
    ) -> int:
        import zipfile

        if not isinstance(archive, zipfile.ZipFile):
            raise TypeError("archive must be a ZipFile")
        if "xl/workbook.xml" not in archive.namelist():
            return start_ordinal
        workbook = safe_xml_from_bytes(archive.read("xl/workbook.xml"))
        workbook_rels = _relationships(archive, "xl/_rels/workbook.xml.rels")
        ordinal = start_ordinal
        for sheet in (item for item in workbook.iter() if item.tag.endswith("}sheet")):
            sheet_name = sheet.attrib.get("name")
            relation_id = sheet.attrib.get(_REL_ID)
            relation = workbook_rels.get(relation_id or "")
            if not sheet_name or relation is None or relation[1]:
                continue
            try:
                sheet_path = resolve_archive_target("xl/workbook.xml", relation[0])
            except ContractValidationError:
                continue
            if sheet_path not in archive.namelist():
                continue
            sheet_root = safe_xml_from_bytes(archive.read(sheet_path))
            sheet_rels = _relationships(archive, _relationship_path(sheet_path))
            for drawing in (item for item in sheet_root.iter() if item.tag.endswith("}drawing")):
                drawing_id = drawing.attrib.get(_REL_ID)
                drawing_relation = sheet_rels.get(drawing_id or "")
                if drawing_relation is None or drawing_relation[1]:
                    omissions.append(
                        AssetExtractionOmission(
                            reason=(
                                AssetOmissionReason.EXTERNAL_REFERENCE
                                if drawing_relation and drawing_relation[1]
                                else AssetOmissionReason.MALFORMED_RELATIONSHIP
                            ),
                            ordinal=ordinal,
                            relationship_id=drawing_id,
                            metadata=FrozenMetadata({"sheet_name": sheet_name}),
                        )
                    )
                    continue
                try:
                    drawing_path = resolve_archive_target(sheet_path, drawing_relation[0])
                except ContractValidationError:
                    omissions.append(
                        AssetExtractionOmission(
                            reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                            ordinal=ordinal,
                            relationship_id=drawing_id,
                            metadata=FrozenMetadata({"sheet_name": sheet_name}),
                        )
                    )
                    continue
                ordinal = self._extract_drawing_images(
                    archive=archive,
                    drawing_path=drawing_path,
                    sheet_name=sheet_name,
                    ordinal=ordinal,
                    blocks=blocks,
                    assets=assets,
                    omissions=omissions,
                )
        return ordinal

    def _extract_drawing_images(
        self,
        *,
        archive: object,
        drawing_path: str,
        sheet_name: str,
        ordinal: int,
        blocks: list[RawBlock],
        assets: list[TransientAsset],
        omissions: list[AssetExtractionOmission],
    ) -> int:
        import zipfile

        if not isinstance(archive, zipfile.ZipFile) or drawing_path not in archive.namelist():
            omissions.append(
                AssetExtractionOmission(
                    reason=AssetOmissionReason.MALFORMED_RELATIONSHIP,
                    ordinal=ordinal,
                    metadata=FrozenMetadata({"sheet_name": sheet_name}),
                )
            )
            return ordinal
        drawing = safe_xml_from_bytes(archive.read(drawing_path))
        relations = _relationships(archive, _relationship_path(drawing_path))
        for anchor_index, anchor in enumerate(
            item for item in drawing if item.tag.endswith(("}oneCellAnchor", "}twoCellAnchor"))
        ):
            cell_reference = _anchor_reference(anchor)
            locator = AssetLocator(
                kind=AssetLocatorKind.XLSX_CELL,
                ordinal=ordinal,
                sheet_name=sheet_name,
                cell_reference=cell_reference,
            )
            relationship_id = next(
                (
                    item.attrib.get(_REL_EMBED)
                    for item in anchor.iter()
                    if item.tag.endswith("}blip") and item.attrib.get(_REL_EMBED)
                ),
                None,
            )
            relation = relations.get(relationship_id or "")
            if relation is None or relation[1]:
                omissions.append(
                    AssetExtractionOmission(
                        reason=(
                            AssetOmissionReason.EXTERNAL_REFERENCE
                            if relation and relation[1]
                            else AssetOmissionReason.MALFORMED_RELATIONSHIP
                        ),
                        ordinal=ordinal,
                        locator=locator,
                        relationship_id=relationship_id,
                    )
                )
                continue
            try:
                asset_path = resolve_archive_target(drawing_path, relation[0])
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
                )
            )
            blocks.append(
                RawImageBlock(
                    ordinal=ordinal,
                    parser_local_id=local_id,
                    metadata=FrozenMetadata(
                        {
                            "parser.asset.relationship_id": relationship_id,
                            "parser.asset.sheet_name": sheet_name,
                            "parser.asset.cell_reference": cell_reference,
                            "parser.asset.anchor_index": anchor_index,
                        }
                    ),
                )
            )
            ordinal += 1
        return ordinal


def _relationships(archive: object, path: str) -> dict[str, tuple[str, bool]]:
    import zipfile

    if not isinstance(archive, zipfile.ZipFile) or path not in archive.namelist():
        return {}
    root = safe_xml_from_bytes(archive.read(path))
    return {
        item.attrib["Id"]: (
            item.attrib["Target"],
            item.attrib.get("TargetMode", "").lower() == "external",
        )
        for item in root
        if item.attrib.get("Id") and item.attrib.get("Target")
    }


def _relationship_path(owner: str) -> str:
    return posixpath.join(posixpath.dirname(owner), "_rels", posixpath.basename(owner) + ".rels")


def _anchor_reference(anchor: ET.Element) -> str | None:
    points: list[str] = []
    for marker_name in ("from", "to"):
        marker = next((item for item in anchor if item.tag.endswith("}" + marker_name)), None)
        if marker is None:
            continue
        col = next((item.text for item in marker if item.tag.endswith("}col")), None)
        row = next((item.text for item in marker if item.tag.endswith("}row")), None)
        try:
            points.append(f"{get_column_letter(int(col or '0') + 1)}{int(row or '0') + 1}")
        except (TypeError, ValueError):
            continue
    if len(points) == 2:
        return f"{points[0]}:{points[1]}"
    return points[0] if points else None
