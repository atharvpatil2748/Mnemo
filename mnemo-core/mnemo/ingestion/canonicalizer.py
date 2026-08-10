"""Pure conversion from transient parser output to canonical domain models."""

from collections.abc import Mapping

from mnemo.interfaces.errors import IntegrityError
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawBlock,
    RawCodeBlock,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawMathBlock,
    RawTableBlock,
    RawTextBlock,
)
from mnemo.models import (
    Asset,
    Block,
    CodeBlock,
    EquationBlock,
    HeadingBlock,
    ImageBlock,
    ParsedDocument,
    TableBlock,
    TextBlock,
)


class DocumentCanonicalizer:
    """Deterministically convert a classified ParseResult without side effects."""

    def canonicalize(
        self,
        result: ParseResult,
        assets_by_local_id: Mapping[str, Asset],
    ) -> ParsedDocument:
        """Resolve assets, convert blocks, and construct the canonical document."""
        referenced_ids = tuple(
            block.parser_local_id for block in result.blocks if isinstance(block, RawImageBlock)
        )
        if len(referenced_ids) != len(frozenset(referenced_ids)):
            raise IntegrityError("RawImageBlock parser_local_id values must be unique")
        expected_ids = frozenset(asset.parser_local_id for asset in result.extracted_assets)
        supplied_ids = frozenset(assets_by_local_id)
        if supplied_ids != expected_ids:
            missing = sorted(expected_ids - supplied_ids)
            unexpected = sorted(supplied_ids - expected_ids)
            raise IntegrityError(
                "asset resolution map does not exactly match ParseResult assets: "
                f"missing={missing}, unexpected={unexpected}"
            )
        if any(not isinstance(local_id, str) or not local_id for local_id in assets_by_local_id):
            raise IntegrityError("asset resolution map keys must be non-empty strings")
        if any(not isinstance(asset, Asset) for asset in assets_by_local_id.values()):
            raise IntegrityError("asset resolution map values must be Asset instances")

        blocks = tuple(self._convert_block(block, assets_by_local_id) for block in result.blocks)
        return ParsedDocument(
            blocks=blocks,
            metadata=result.metadata,
            language=result.language,
            doc_type=result.doc_type,
        )

    def _convert_block(self, block: RawBlock, assets: Mapping[str, Asset]) -> Block:
        if isinstance(block, RawTextBlock):
            return TextBlock(
                ordinal=block.ordinal,
                page_number=block.page_number,
                bounding_box=block.bounding_box,
                language=block.language,
                metadata=block.metadata,
                text=block.text,
            )
        if isinstance(block, RawHeadingBlock):
            return HeadingBlock(
                ordinal=block.ordinal,
                page_number=block.page_number,
                bounding_box=block.bounding_box,
                language=block.language,
                metadata=block.metadata,
                text=block.text,
                level=block.level,
            )
        if isinstance(block, RawListBlock):
            return TextBlock(
                ordinal=block.ordinal,
                page_number=block.page_number,
                bounding_box=block.bounding_box,
                language=block.language,
                metadata=block.metadata,
                text="\n".join(block.items),
            )
        if isinstance(block, RawTableBlock):
            return TableBlock(
                ordinal=block.ordinal,
                page_number=block.page_number,
                bounding_box=block.bounding_box,
                language=block.language,
                metadata=block.metadata,
                rows=block.rows,
                header_row_count=block.header_row_count,
            )
        if isinstance(block, RawCodeBlock):
            return CodeBlock(
                ordinal=block.ordinal,
                page_number=block.page_number,
                bounding_box=block.bounding_box,
                language=block.language,
                metadata=block.metadata,
                code=block.code,
                code_language=block.code_language,
            )
        if isinstance(block, RawMathBlock):
            return EquationBlock(
                ordinal=block.ordinal,
                page_number=block.page_number,
                bounding_box=block.bounding_box,
                language=block.language,
                metadata=block.metadata,
                latex=block.latex,
                display=block.display,
            )
        if isinstance(block, RawImageBlock):
            asset = assets.get(block.parser_local_id)
            if asset is None:
                raise IntegrityError(f"RawImageBlock asset is unresolved: {block.parser_local_id}")
            return ImageBlock(
                ordinal=block.ordinal,
                page_number=block.page_number,
                bounding_box=block.bounding_box,
                language=block.language,
                metadata=block.metadata,
                asset_id=asset.asset_id,
                alt_text=block.alt_text,
            )
        raise IntegrityError(f"unsupported raw block type: {type(block).__name__}")
