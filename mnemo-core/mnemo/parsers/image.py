"""Pure standalone-image parser for authoritative asset ingestion."""

from __future__ import annotations

from pathlib import Path

from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser import ParserInterfaceV2
from mnemo.interfaces.parser_models import ParseResult, ParseResultV2, RawImageBlock, TransientAsset
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import AssetContainerKind, DocType, DocumentMetadata, FrozenMetadata

from .asset_extraction import (
    DEFAULT_ASSET_EXTRACTION_LIMITS,
    AssetExtractionLimits,
    bounded_asset_result,
    validate_image_payload,
)


class StandaloneImageParser(ParserInterfaceV2):
    """Represent one supported image as one exact, analysis-free occurrence."""

    def __init__(self, limits: AssetExtractionLimits = DEFAULT_ASSET_EXTRACTION_LIMITS) -> None:
        self._limits = limits

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".tif",
            ".tiff",
            ".bmp",
            ".svg",
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "image/tiff",
            "image/bmp",
            "image/svg+xml",
        )

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_images=True,
            supports_tables=False,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        return self.parse_with_assets(data, filename, metadata).parse_result

    def parse_with_assets(
        self, data: bytes, filename: str, metadata: FileMetadata
    ) -> ParseResultV2:
        if not data:
            raise ContractValidationError(f"Cannot parse empty image: {filename}")
        observed = validate_image_payload(
            data, metadata.mime_type or "application/octet-stream", self._limits
        )
        local_id = "standalone-image"
        result = ParseResult(
            blocks=(
                RawImageBlock(
                    ordinal=0,
                    parser_local_id=local_id,
                    metadata=FrozenMetadata({"parser.asset.role": "standalone"}),
                ),
            ),
            extracted_assets=(
                TransientAsset(
                    parser_local_id=local_id,
                    raw_bytes=data,
                    mime_type=observed,
                ),
            ),
            metadata=DocumentMetadata(
                content_hash=metadata.content_hash,
                title=Path(filename).stem or "Untitled image",
                metadata=FrozenMetadata(
                    {
                        **dict(metadata.metadata),
                        "parser.asset.standalone": True,
                        "parser.asset.media_type": observed,
                    }
                ),
            ),
            language="und",
            doc_type=DocType.GENERIC,
        )
        return bounded_asset_result(
            result,
            parser_id="mnemo.image",
            container_kind=AssetContainerKind.STANDALONE,
            limits=self._limits,
        )
