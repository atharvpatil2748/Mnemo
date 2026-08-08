import pytest
from mnemo.interfaces.parser_models import (
    RawBlock,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawTableBlock,
    RawTextBlock,
    TransientAsset,
)


def test_transient_asset_validation() -> None:
    with pytest.raises(ValueError, match="raw_bytes"):
        TransientAsset(parser_local_id="1", raw_bytes=b"", mime_type="image/png")

    with pytest.raises(ValueError, match="page_number"):
        TransientAsset(parser_local_id="1", raw_bytes=b"123", mime_type="image/png", page_number=0)


def test_raw_block_abstract() -> None:
    with pytest.raises(TypeError, match="abstract"):
        RawBlock(ordinal=1)


def test_raw_block_validation() -> None:
    # bounding_box four coordinates
    with pytest.raises(ValueError, match="four coordinates"):
        RawTextBlock(ordinal=1, text="x", page_number=1, bounding_box=(1.0, 2.0))  # type: ignore[arg-type]

    # bounding_box ordered
    with pytest.raises(ValueError, match="ordered"):
        RawTextBlock(ordinal=1, text="x", page_number=1, bounding_box=(5.0, 5.0, 1.0, 6.0))

    # bounding_box requires page_number
    with pytest.raises(ValueError, match="page_number"):
        RawTextBlock(ordinal=1, text="x", bounding_box=(1.0, 1.0, 2.0, 2.0))


def test_raw_heading_validation() -> None:
    with pytest.raises(ValueError, match="level"):
        RawHeadingBlock(ordinal=1, text="x", level=7)


def test_raw_list_validation() -> None:
    with pytest.raises(ValueError, match="items"):
        RawListBlock(ordinal=1, items=())


def test_raw_table_validation() -> None:
    with pytest.raises(ValueError, match="rows"):
        RawTableBlock(ordinal=1, rows=())
    with pytest.raises(ValueError, match="header"):
        RawTableBlock(ordinal=1, rows=(("a",),), header_row_count=2)


def test_raw_image_validation() -> None:
    with pytest.raises(ValueError, match="parser_local_id"):
        RawImageBlock(ordinal=1, parser_local_id="")
