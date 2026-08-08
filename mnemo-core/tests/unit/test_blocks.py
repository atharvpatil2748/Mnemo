from typing import cast

"""Tests for the complete parsed-document block hierarchy."""

import uuid
from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest
from mnemo.models import (
    Block,
    CaptionBlock,
    CodeBlock,
    EquationBlock,
    HeadingBlock,
    ImageBlock,
    TableBlock,
    TextBlock,
)


def test_all_block_types_construct_and_are_hashable() -> None:
    """Every approved concrete block is an immutable hashable value object."""
    blocks = (
        TextBlock(ordinal=0, text="Paragraph", page_number=1),
        HeadingBlock(ordinal=1, text="Heading", level=2),
        TableBlock(ordinal=2, rows=(("A", "B"), ("1", "2")), header_row_count=1),
        ImageBlock(ordinal=3, asset_id=uuid4(), alt_text="Diagram"),
        CodeBlock(ordinal=4, code="print('hi')", code_language="python"),
        EquationBlock(ordinal=5, latex="x^2", display=False),
        CaptionBlock(ordinal=6, text="Figure 1", target_ordinal=3),
    )

    assert len(set(blocks)) == 7
    assert blocks[0] == TextBlock(ordinal=0, text="Paragraph", page_number=1)
    with pytest.raises(FrozenInstanceError):
        blocks[0].ordinal = 2  # type: ignore[misc]


def test_common_block_layout_validation() -> None:
    """Valid source geometry requires an ordered finite box and page."""
    block = TextBlock(
        ordinal=0,
        text="Positioned",
        page_number=1,
        bounding_box=(0.0, 1.0, 20.0, 30.0),
        language="en",
    )
    assert block.bounding_box == (0.0, 1.0, 20.0, 30.0)

    with pytest.raises(TypeError):
        Block(ordinal=0)
    for kwargs in (
        {"ordinal": -1},
        {"ordinal": 0, "page_number": 0},
        {"ordinal": 0, "page_number": 1, "bounding_box": [0.0, 0.0, 1.0, 1.0]},
        {"ordinal": 0, "bounding_box": (0.0, 0.0, 1.0, 1.0)},
        {"ordinal": 0, "page_number": 1, "bounding_box": (2.0, 0.0, 1.0, 1.0)},
        {
            "ordinal": 0,
            "page_number": 1,
            "bounding_box": (0.0, 0.0, float("inf"), 1.0),
        },
        {"ordinal": 0, "language": " "},
        {"ordinal": 0, "metadata": {}},
    ):
        with pytest.raises((TypeError, ValueError)):
            TextBlock(text="x", **kwargs)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TextBlock(ordinal=0, text=""),
        lambda: HeadingBlock(ordinal=0, text="H", level=0),
        lambda: HeadingBlock(ordinal=0, text="H", level=7),
        lambda: TableBlock(ordinal=0, rows=()),
        lambda: TableBlock(ordinal=0, rows=cast(tuple[tuple[str, ...], ...], [["a"]])),
        lambda: TableBlock(ordinal=0, rows=cast(tuple[tuple[str, ...], ...], (["a"],))),
        lambda: TableBlock(ordinal=0, rows=(("a",), ("b", "c"))),
        lambda: TableBlock(ordinal=0, rows=(("a",),), header_row_count=2),
        lambda: ImageBlock(ordinal=0, asset_id=cast(uuid.UUID, "bad")),
        lambda: ImageBlock(ordinal=0, asset_id=uuid4(), alt_text=" "),
        lambda: CodeBlock(ordinal=0, code=""),
        lambda: CodeBlock(ordinal=0, code="x", code_language=" "),
        lambda: EquationBlock(ordinal=0, latex=""),
        lambda: EquationBlock(ordinal=0, latex="x", display=cast(bool, 1)),
        lambda: CaptionBlock(ordinal=0, text="caption", target_ordinal=0),
        lambda: CaptionBlock(ordinal=0, text="caption", target_ordinal=-1),
    ],
)
def test_block_subtype_edge_cases(factory: object) -> None:
    """Subtype-specific invariants reject malformed values."""
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]
