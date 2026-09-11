"""Behavioral coverage for the bounded delivery transport selectors."""

from __future__ import annotations

from uuid import uuid4

import pytest
from mnemo.models import (
    AdjacentSelector,
    BlockRangeSelector,
    ChunkRangeSelector,
    FromEndSelector,
    FullDocumentSelector,
    PageRangeSelector,
    SectionSelector,
    SheetRangeSelector,
    SlideRangeSelector,
)
from mnemo_server.schemas.delivery import DocumentExpansionRequestBody
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("selector", "expected"),
    (
        ({"kind": "full"}, FullDocumentSelector),
        ({"kind": "page_range", "start": 1, "end": 2}, PageRangeSelector),
        ({"kind": "slide_range", "start": 1, "end": 2}, SlideRangeSelector),
        ({"kind": "sheet_range", "start": 1, "end": 2}, SheetRangeSelector),
        ({"kind": "block_range", "start": 0, "end": 2}, BlockRangeSelector),
        ({"kind": "chunk_range", "start": 0, "end": 2}, ChunkRangeSelector),
        ({"kind": "section", "heading_path": ["A", "B"]}, SectionSelector),
        ({"kind": "from_end", "unit": "chunk", "count": 2}, FromEndSelector),
        (
            {
                "kind": "adjacent",
                "anchor_kind": "block",
                "block_ordinal": 2,
                "before": 1,
            },
            AdjacentSelector,
        ),
    ),
)
def test_each_delivery_selector_maps_to_its_exact_core_contract(
    selector: dict[str, object], expected: type[object]
) -> None:
    body = DocumentExpansionRequestBody.model_validate(
        {"selector": selector, "max_bytes": 100, "max_items": 5}
    )
    core = body.to_core(notebook_id=uuid4(), document_id=uuid4(), version_id=uuid4())
    assert isinstance(core.selector, expected)
    assert (core.max_bytes, core.max_items) == (100, 5)


@pytest.mark.parametrize(
    "selector",
    (
        {"kind": "page_range", "start": 2, "end": 1},
        {"kind": "slide_range", "start": 2, "end": 1},
        {"kind": "sheet_range", "start": 2, "end": 1},
        {"kind": "block_range", "start": 2, "end": 1},
        {"kind": "chunk_range", "start": 2, "end": 1},
        {"kind": "section", "heading_path": [" "]},
        {"kind": "adjacent", "anchor_kind": "block"},
        {
            "kind": "adjacent",
            "anchor_kind": "block",
            "block_ordinal": 1,
            "chunk_id": "a" * 64,
        },
        {"kind": "adjacent", "anchor_kind": "chunk"},
        {
            "kind": "adjacent",
            "anchor_kind": "chunk",
            "chunk_id": "a" * 64,
            "block_ordinal": 1,
        },
        {
            "kind": "adjacent",
            "anchor_kind": "chunk",
            "chunk_id": "a" * 64,
            "include_anchor": False,
        },
    ),
)
def test_delivery_selector_validation_rejects_ambiguous_or_empty_ranges(
    selector: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        DocumentExpansionRequestBody.model_validate({"selector": selector})
