"""Bounded, pure helpers for Phase 8.5 parser asset discovery."""

from __future__ import annotations

import io
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser_models import (
    AssetExtractionOmission,
    AssetExtractionOutcome,
    AssetOmissionReason,
    ParseResult,
    ParseResultV2,
    RawImageBlock,
    TransientAsset,
    TransientAssetOccurrence,
)
from mnemo.interfaces.versions import PARSER_INTERFACE_V2_VERSION
from mnemo.models import (
    AssetContainerKind,
    AssetExtractionProvenance,
    AssetLocator,
    AssetLocatorKind,
    FrozenMetadata,
    thaw_metadata,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetExtractionLimits:
    """Hard parser bounds; deployments may inject stricter values."""

    max_assets: int = 1_024
    max_asset_bytes: int = 32 * 1024 * 1024
    max_total_asset_bytes: int = 128 * 1024 * 1024
    max_archive_entries: int = 10_000
    max_archive_uncompressed_bytes: int = 512 * 1024 * 1024
    max_container_units: int = 5_000
    max_compression_ratio: float = 200.0

    def __post_init__(self) -> None:
        for name in (
            "max_assets",
            "max_asset_bytes",
            "max_total_asset_bytes",
            "max_archive_entries",
            "max_archive_uncompressed_bytes",
            "max_container_units",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_total_asset_bytes < self.max_asset_bytes:
            raise ValueError("max_total_asset_bytes cannot be smaller than max_asset_bytes")
        if self.max_compression_ratio <= 1:
            raise ValueError("max_compression_ratio must be greater than one")


DEFAULT_ASSET_EXTRACTION_LIMITS = AssetExtractionLimits()


def asset_limit_reason(
    *, asset_count: int, total_bytes: int, next_bytes: int, limits: AssetExtractionLimits
) -> AssetOmissionReason | None:
    """Classify a prospective extraction before allocating/copying its bytes."""
    if asset_count >= limits.max_assets or next_bytes > limits.max_asset_bytes:
        return AssetOmissionReason.LIMIT_EXCEEDED
    if total_bytes + next_bytes > limits.max_total_asset_bytes:
        return AssetOmissionReason.LIMIT_EXCEEDED
    return None


def validated_zip(data: bytes, limits: AssetExtractionLimits) -> zipfile.ZipFile:
    """Open an in-memory archive only after traversal and expansion preflight."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), "r")
    except (OSError, zipfile.BadZipFile) as error:
        raise ContractValidationError("document container is not a valid ZIP archive") from error
    try:
        entries = archive.infolist()
        if len(entries) > limits.max_archive_entries:
            raise ContractValidationError("document container exceeds entry-count limit")
        total = 0
        for entry in entries:
            _validate_archive_name(entry.filename)
            if entry.flag_bits & 0x1:
                raise ContractValidationError("encrypted archive entries are unsupported")
            if entry.file_size > limits.max_archive_uncompressed_bytes:
                raise ContractValidationError("archive entry exceeds expansion limit")
            total += entry.file_size
            if total > limits.max_archive_uncompressed_bytes:
                raise ContractValidationError("document container exceeds expansion limit")
            if entry.file_size and entry.compress_size == 0:
                raise ContractValidationError("archive entry has an invalid compression ratio")
            if (
                entry.compress_size
                and entry.file_size / entry.compress_size > limits.max_compression_ratio
            ):
                raise ContractValidationError("archive entry exceeds compression-ratio limit")
        return archive
    except Exception:
        archive.close()
        raise


def resolve_archive_target(owner_path: str, target: str) -> str:
    """Resolve one internal OOXML relationship without permitting traversal."""
    if not isinstance(target, str) or not target or "\x00" in target or "\\" in target:
        raise ContractValidationError("relationship target is invalid")
    if "://" in target or target.startswith("//"):
        raise ContractValidationError("external relationship targets are not extractable")
    resolved = (
        posixpath.normpath(target.lstrip("/"))
        if target.startswith("/")
        else posixpath.normpath(posixpath.join(posixpath.dirname(owner_path), target))
    )
    _validate_archive_name(resolved)
    return resolved


def safe_xml_from_bytes(data: bytes) -> ET.Element:
    """Parse bounded package XML without allowing document type/entity declarations."""
    lowered = data[:8192].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ContractValidationError("XML entity declarations are unsupported")
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise ContractValidationError("document container contains malformed XML") from error


def validate_image_payload(
    data: bytes, declared_media_type: str, limits: AssetExtractionLimits
) -> str:
    """Verify bounded image bytes and return their signature MIME type."""
    if not isinstance(data, bytes) or not data:
        raise ContractValidationError("embedded asset is empty")
    if len(data) > limits.max_asset_bytes:
        raise ContractValidationError("embedded asset exceeds byte limit")
    observed = image_signature_media_type(data)
    if observed is None:
        raise ContractValidationError("embedded asset type is unsupported or malformed")
    declared = declared_media_type.split(";", 1)[0].strip().lower()
    aliases = {"image/jpg": "image/jpeg", "image/x-png": "image/png"}
    declared = aliases.get(declared, declared)
    if declared not in {observed, "application/octet-stream"}:
        raise ContractValidationError("embedded asset MIME does not match its bytes")
    return observed


def image_signature_media_type(data: bytes) -> str | None:
    """Recognize supported raster/SVG image signatures without decoding pixels."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    # JPEG XR / HD Photo (the OOXML ``.wdp`` representation). The two-byte
    # TIFF byte-order prefix is followed by the JPEG XR identifier 0x01bc.
    if data.startswith((b"II\xbc\x01", b"MM\x01\xbc")):
        return "image/vnd.ms-photo"
    if data.startswith(b"BM"):
        return "image/bmp"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    prefix = data[:4096].lstrip()
    if prefix.startswith(b"<?xml") or prefix.startswith(b"<svg"):
        lowered = prefix.lower()
        if b"<!doctype" in lowered or b"<!entity" in lowered or b"<script" in lowered:
            raise ContractValidationError("unsafe SVG active content is unsupported")
        if b'href="http:' in lowered or b"href='http:" in lowered or b'href="https:' in lowered:
            raise ContractValidationError("SVG external references are unsupported")
        if b"<svg" in lowered:
            return "image/svg+xml"
    return None


def extraction_from_parse_result(
    parse_result: ParseResult,
    *,
    parser_id: str,
    container_kind: AssetContainerKind,
    omissions: tuple[AssetExtractionOmission, ...] = (),
) -> ParseResultV2:
    """Create typed occurrences from V1 image blocks without changing V1 text."""
    occurrences: list[TransientAssetOccurrence] = []
    for block in parse_result.blocks:
        if not isinstance(block, RawImageBlock):
            continue
        metadata = thaw_metadata(block.metadata)
        locator = _locator(container_kind, block, metadata)
        occurrences.append(
            TransientAssetOccurrence(
                parser_local_id=block.parser_local_id,
                locator=locator,
                authored_alt_text=block.alt_text,
                extraction_provenance=AssetExtractionProvenance(
                    parser_id=parser_id,
                    parser_version=PARSER_INTERFACE_V2_VERSION,
                    parser_local_id=block.parser_local_id,
                    block_ordinal=block.ordinal,
                    metadata=FrozenMetadata({"source_metadata": metadata}),
                ),
            )
        )
    if occurrences and omissions:
        outcome = AssetExtractionOutcome.PARTIAL
    elif occurrences:
        outcome = AssetExtractionOutcome.COMPLETE
    elif omissions:
        outcome = AssetExtractionOutcome.REJECTED
    else:
        outcome = AssetExtractionOutcome.NO_ASSETS
    return ParseResultV2(
        parse_result=parse_result,
        asset_occurrences=tuple(occurrences),
        omissions=omissions,
        outcome=outcome,
    )


def bounded_asset_result(
    parse_result: ParseResult,
    *,
    parser_id: str,
    container_kind: AssetContainerKind,
    limits: AssetExtractionLimits,
    omissions: tuple[AssetExtractionOmission, ...] = (),
) -> ParseResultV2:
    """Validate/filter optional images while preserving all textual raw blocks."""
    accepted: list[TransientAsset] = []
    rejected: dict[str, AssetOmissionReason] = {}
    total_bytes = 0
    for asset in parse_result.extracted_assets:
        if len(accepted) >= limits.max_assets or len(asset.raw_bytes) > limits.max_asset_bytes:
            rejected[asset.parser_local_id] = AssetOmissionReason.LIMIT_EXCEEDED
            continue
        try:
            observed = validate_image_payload(asset.raw_bytes, asset.mime_type, limits)
        except ContractValidationError:
            rejected[asset.parser_local_id] = AssetOmissionReason.CORRUPT_ASSET
            continue
        if total_bytes + len(asset.raw_bytes) > limits.max_total_asset_bytes:
            rejected[asset.parser_local_id] = AssetOmissionReason.LIMIT_EXCEEDED
            continue
        total_bytes += len(asset.raw_bytes)
        accepted.append(replace(asset, mime_type=observed))

    retained_blocks = []
    derived_omissions = list(omissions)
    for block in parse_result.blocks:
        if isinstance(block, RawImageBlock) and block.parser_local_id in rejected:
            metadata = thaw_metadata(block.metadata)
            relation = metadata.get("parser.asset.relationship_id")
            derived_omissions.append(
                AssetExtractionOmission(
                    reason=rejected[block.parser_local_id],
                    ordinal=block.ordinal,
                    locator=_locator(container_kind, block, metadata),
                    relationship_id=relation if isinstance(relation, str) else None,
                    metadata=FrozenMetadata({"parser_id": parser_id}),
                )
            )
            continue
        retained_blocks.append(block)
    normalized_blocks = tuple(
        replace(block, ordinal=index) for index, block in enumerate(retained_blocks)
    )
    filtered = replace(
        parse_result,
        blocks=normalized_blocks,
        extracted_assets=tuple(accepted),
    )
    return extraction_from_parse_result(
        filtered,
        parser_id=parser_id,
        container_kind=container_kind,
        omissions=tuple(derived_omissions),
    )


def text_only_v1(parse_result: ParseResult) -> ParseResult:
    """Return the frozen text/table projection for formerly text-only parsers."""
    blocks = tuple(block for block in parse_result.blocks if not isinstance(block, RawImageBlock))
    return replace(
        parse_result,
        blocks=tuple(replace(block, ordinal=index) for index, block in enumerate(blocks)),
        extracted_assets=(),
    )


def unique_image_v1(parse_result: ParseResult) -> ParseResult:
    """Adapt ordered V2 occurrences to the released one-image-per-relation V1 shape."""
    text_blocks = [
        replace(block, ordinal=index)
        for index, block in enumerate(
            block for block in parse_result.blocks if not isinstance(block, RawImageBlock)
        )
    ]
    image_blocks: list[RawImageBlock] = []
    assets: list[TransientAsset] = []
    assets_by_id = {asset.parser_local_id: asset for asset in parse_result.extracted_assets}
    seen_relations: set[str] = set()
    for block in parse_result.blocks:
        if not isinstance(block, RawImageBlock):
            continue
        metadata = thaw_metadata(block.metadata)
        relationship = metadata.get("parser.asset.relationship_id")
        key = relationship if isinstance(relationship, str) else block.parser_local_id
        if key in seen_relations:
            continue
        seen_relations.add(key)
        asset = assets_by_id[block.parser_local_id]
        legacy_id = f"image-{len(assets) + 1}"
        assets.append(replace(asset, parser_local_id=legacy_id))
        image_blocks.append(
            replace(
                block,
                parser_local_id=legacy_id,
                ordinal=len(text_blocks) + len(image_blocks),
                metadata=FrozenMetadata(),
            )
        )
    return replace(
        parse_result,
        blocks=tuple(text_blocks) + tuple(image_blocks),
        extracted_assets=tuple(assets),
    )


def _locator(
    container: AssetContainerKind,
    block: RawImageBlock,
    metadata: Mapping[str, object],
) -> AssetLocator:
    if container is AssetContainerKind.PDF and block.page_number is not None:
        return AssetLocator(
            kind=AssetLocatorKind.PDF_PAGE,
            ordinal=block.ordinal,
            page_number=block.page_number,
            geometry=block.bounding_box,
        )
    if container is AssetContainerKind.PPTX and block.page_number is not None:
        return AssetLocator(
            kind=AssetLocatorKind.PPTX_SLIDE,
            ordinal=block.ordinal,
            slide_number=block.page_number,
            geometry=block.bounding_box,
        )
    if container is AssetContainerKind.DOCX:
        inline_position = metadata.get("parser.asset.inline_position", block.ordinal)
        return AssetLocator(
            kind=AssetLocatorKind.DOCX_POSITION,
            ordinal=block.ordinal,
            inline_position=inline_position if isinstance(inline_position, int) else block.ordinal,
            geometry=block.bounding_box,
        )
    if container is AssetContainerKind.XLSX:
        sheet_name = metadata.get("parser.asset.sheet_name")
        cell = metadata.get("parser.asset.cell_reference")
        if isinstance(sheet_name, str) and sheet_name:
            return AssetLocator(
                kind=AssetLocatorKind.XLSX_CELL,
                ordinal=block.ordinal,
                sheet_name=sheet_name,
                cell_reference=cell if isinstance(cell, str) and cell else None,
                geometry=block.bounding_box,
            )
    if container in (AssetContainerKind.MARKDOWN, AssetContainerKind.HTML):
        dom_path = metadata.get("parser.asset.dom_path")
        if isinstance(dom_path, str) and dom_path:
            return AssetLocator(
                kind=AssetLocatorKind.DOM_POSITION,
                ordinal=block.ordinal,
                dom_path=dom_path,
                geometry=block.bounding_box,
            )
    if container is AssetContainerKind.STANDALONE:
        return AssetLocator(kind=AssetLocatorKind.STANDALONE, ordinal=block.ordinal)
    return AssetLocator(
        kind=AssetLocatorKind.DOCUMENT_POSITION,
        ordinal=block.ordinal,
        geometry=block.bounding_box,
    )


def _validate_archive_name(name: str) -> None:
    if not name or "\x00" in name or "\\" in name:
        raise ContractValidationError("archive entry name is invalid")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractValidationError("archive entry path is unsafe")
