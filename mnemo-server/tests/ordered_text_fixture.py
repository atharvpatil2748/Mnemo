"""Explicit, nonproduction persisted IR truth for ordered-delivery certification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from mnemo.models import CodeBlock, EquationBlock, HeadingBlock, ImageBlock, TableBlock, TextBlock
from mnemo.storage.filesystem import FilesystemBlobStore

TEXT_PARTS = (
    "Ordered fixture",
    "Paragraph α — नमस्ते\n\nIntentional blank line.",  # noqa: RUF001 -- deliberate Unicode truth
    "Name\tValue\nCafé\t東京",
    "def greeting():\n    return '🙂'",
    r"E = mc^2",
    "Image alt: diagram → result",
    "Page seven: résumé",
    "Second heading",
    "Tabs\tand newlines\nare retained.",
    "Final table\t2\nΔ\t3",
    r"\int_0^1 x\,dx = \frac12",
    "Final paragraph.",
)
EXPECTED_TEXT = "\n".join(TEXT_PARTS)
EXPECTED_BLOCKS = (
    {"kind": "HeadingBlock", "text": TEXT_PARTS[0], "level": 1},
    {"kind": "TextBlock", "text": TEXT_PARTS[1]},
    {"kind": "TableBlock", "rows": [["Name", "Value"], ["Café", "東京"]], "header_row_count": 1},
    {"kind": "CodeBlock", "code": TEXT_PARTS[3], "code_language": "python"},
    {"kind": "EquationBlock", "latex": TEXT_PARTS[4], "display": True},
    {"kind": "ImageBlock", "alt_text": TEXT_PARTS[5], "asset_id": str(UUID(int=50))},
    {"kind": "TextBlock", "text": TEXT_PARTS[6]},
    {"kind": "HeadingBlock", "text": TEXT_PARTS[7], "level": 2},
    {"kind": "TextBlock", "text": TEXT_PARTS[8]},
    {"kind": "TableBlock", "rows": [["Final table", "2"], ["Δ", "3"]], "header_row_count": 0},
    {"kind": "EquationBlock", "latex": TEXT_PARTS[10], "display": True},
    {"kind": "TextBlock", "text": TEXT_PARTS[11]},
)


def truth_manifest() -> dict[str, object]:
    return {
        "notebook_id": str(UUID(int=1)),
        "source_id": str(UUID(int=4)),
        "document_id": str(UUID(int=2)),
        "version_id": str(UUID(int=3)),
        "total_items": 12,
        "expected_text": EXPECTED_TEXT,
        "text_sha256_utf8": hashlib.sha256(EXPECTED_TEXT.encode()).hexdigest(),
        "expected_blocks": EXPECTED_BLOCKS,
        "block_fields_sha256": hashlib.sha256(
            json.dumps(
                EXPECTED_BLOCKS, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
    }


async def install_ordered_fixture(reader, root: Path) -> None:  # type: ignore[no-untyped-def]
    """Persist explicit supported blocks, close, then read only from reopened IR."""
    classes = {
        cls.__name__: cls
        for cls in (TextBlock, HeadingBlock, TableBlock, CodeBlock, EquationBlock, ImageBlock)
    }
    blocks = []
    for index, record in enumerate(EXPECTED_BLOCKS):
        fields = {key: value for key, value in record.items() if key != "kind"}
        if "rows" in fields:
            fields["rows"] = tuple(tuple(row) for row in fields["rows"])
        if "asset_id" in fields:
            fields["asset_id"] = UUID(fields["asset_id"])
        blocks.append(classes[record["kind"]](ordinal=index, page_number=index + 1, **fields))
    original = await reader.get_parsed_document(UUID(int=3))
    writer = FilesystemBlobStore(root / "ordered-blobs")
    await writer.open()
    await writer.put_parsed_document(
        UUID(int=3),
        replace(original, blocks=tuple(blocks), metadata=replace(original.metadata, page_count=12)),
    )
    await writer.close()

    async def persisted(version_id: UUID):  # type: ignore[no-untyped-def]
        store = FilesystemBlobStore(root / "ordered-blobs")
        await store.open()
        try:
            return await store.get_parsed_document(version_id)
        finally:
            await store.close()

    reader.get_parsed_document = persisted
