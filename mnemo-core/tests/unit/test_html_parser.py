"""Unit tests for the HTMLParser (Module 3.5)."""

from typing import Any
from unittest.mock import patch

import pytest
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawCodeBlock,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawTableBlock,
    RawTextBlock,
)
from mnemo.interfaces.types import FileMetadata
from mnemo.parsers.html import HTMLParser

_SHA256 = "a" * 64


@pytest.fixture
def parser() -> HTMLParser:
    """Provide a fresh HTMLParser instance."""
    return HTMLParser()


@pytest.fixture
def metadata() -> FileMetadata:
    """Provide valid FileMetadata for tests."""
    return FileMetadata(
        content_hash=_SHA256,
        size_bytes=1024,
        mime_type="text/html",
    )


# ── Empty / trivial inputs ─────────────────────────────────────────────────


def test_empty_bytes_returns_empty_result(parser: HTMLParser, metadata: FileMetadata) -> None:
    """An empty byte stream produces an empty ParseResult."""
    result = parser.parse(b"", "", metadata)
    assert isinstance(result, ParseResult)
    assert result.blocks == ()
    assert result.extracted_assets == ()


def test_whitespace_only_returns_empty_result(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Whitespace-only input produces an empty ParseResult."""
    result = parser.parse(b"   \n\t  ", "", metadata)
    assert result.blocks == ()
    assert result.extracted_assets == ()


def test_invalid_utf8_raises_contract_error(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Invalid UTF-8 raises ContractValidationError."""
    from mnemo.interfaces.errors import ContractValidationError

    with pytest.raises(ContractValidationError):
        parser.parse(b"\xff\xfe invalid", "", metadata)


# ── Metadata extraction ────────────────────────────────────────────────────


def test_title_extraction(parser: HTMLParser, metadata: FileMetadata) -> None:
    """The <title> tag is extracted into DocumentMetadata.title."""
    html = b"<html><head><title>Test Title</title></head><body><h1>H1</h1></body></html>"
    result = parser.parse(html, "test.html", metadata)
    assert result.metadata.title == "Test Title"


def test_no_title_fallback(parser: HTMLParser, metadata: FileMetadata) -> None:
    """A document with no title falls back to 'Untitled'."""
    html = b"<html><body><h1>H1</h1></body></html>"
    result = parser.parse(html, "test.html", metadata)
    assert result.metadata.title == "Untitled"


# ── Headings ───────────────────────────────────────────────────────────────


def test_heading_levels(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Headings h1-h6 are correctly mapped to RawHeadingBlock with correct levels."""
    html = b"""
    <body>
        <h1>Heading 1</h1>
        <h2>Heading 2</h2>
        <h6>Heading 6</h6>
    </body>
    """
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 3
    for i, level in enumerate([1, 2, 6]):
        block = result.blocks[i]
        assert isinstance(block, RawHeadingBlock)
        assert block.level == level
        assert block.text == f"Heading {level}"


# ── Paragraphs / Text ──────────────────────────────────────────────────────


def test_paragraphs_and_linebreaks(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Paragraphs and <br> tags are extracted into RawTextBlock."""
    html = b"""
    <body>
        <p>First paragraph.</p>
        <p>Second <b>paragraph</b><br/>with newline.</p>
    </body>
    """
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 2
    assert isinstance(result.blocks[0], RawTextBlock)
    assert result.blocks[0].text == "First paragraph."
    assert isinstance(result.blocks[1], RawTextBlock)
    assert result.blocks[1].text == "Second paragraph\nwith newline."


def test_ignored_tags(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Script and style tags are ignored."""
    html = b"""
    <body>
        <script>console.log('ignored');</script>
        <style>body { color: red; }</style>
        <p>Real text</p>
    </body>
    """
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 1
    b0 = result.blocks[0]
    assert isinstance(b0, RawTextBlock)
    assert b0.text == "Real text"


# ── Code blocks ────────────────────────────────────────────────────────────


def test_pre_code_block(parser: HTMLParser, metadata: FileMetadata) -> None:
    """<pre> blocks containing <code> are extracted with language class."""
    html = b"""
    <body>
        <pre><code class="language-python">print('hi')</code></pre>
        <pre>plain text</pre>
    </body>
    """
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 2
    assert isinstance(result.blocks[0], RawCodeBlock)
    assert result.blocks[0].code == "print('hi')"
    assert result.blocks[0].code_language == "python"

    assert isinstance(result.blocks[1], RawCodeBlock)
    assert result.blocks[1].code == "plain text"
    assert result.blocks[1].code_language is None


# ── Lists ──────────────────────────────────────────────────────────────────


@patch("mnemo.parsers.html.Document.summary")
def test_lists(mock_summary: Any, parser: HTMLParser, metadata: FileMetadata) -> None:
    """<ul> and <ol> are extracted as RawListBlock."""
    html = b"""
    <body>
        <ul>
            <li>Item 1</li>
            <li>Item 2 <b>bold</b></li>
        </ul>
        <ol>
            <li>First</li>
        </ol>
    </body>
    """
    mock_summary.return_value = html.decode("utf-8")
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 2
    b1, b2 = result.blocks
    assert isinstance(b1, RawListBlock)
    assert b1.items == ("Item 1", "Item 2 bold")
    assert isinstance(b2, RawListBlock)
    assert b2.items == ("First",)


# ── Tables ─────────────────────────────────────────────────────────────────


def test_tables(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Tables are extracted as RawTableBlock, counting header rows and padding."""
    html = b"""
    <body>
        <table>
            <thead>
                <tr><th>Name</th><th>Age</th></tr>
            </thead>
            <tbody>
                <tr><td>Alice</td><td>30</td></tr>
                <tr><td>Bob</td></tr> <!-- missing column -->
            </tbody>
        </table>
    </body>
    """
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 1
    assert isinstance(result.blocks[0], RawTableBlock)
    block = result.blocks[0]
    assert block.header_row_count == 1
    assert block.rows == (
        ("Name", "Age"),
        ("Alice", "30"),
        ("Bob", ""),  # padded
    )


# ── Images ─────────────────────────────────────────────────────────────────


def test_remote_image(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Remote image URLs are not emitted without resolvable asset bytes."""
    html = b'<body><img src="https://example.com/a.jpg" alt="A photo" /></body>'
    result = parser.parse(html, "", metadata)
    assert result.blocks == ()
    assert result.extracted_assets == ()


def test_data_uri_image(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Data URI image generates RawImageBlock and TransientAsset."""
    b64 = "iVBORw0KGgo="
    html = f'<body><img src="data:image/png;base64,{b64}" alt="Inline" /></body>'.encode()
    result = parser.parse(html, "", metadata)

    assert len(result.blocks) == 1
    img_block = result.blocks[0]
    assert isinstance(img_block, RawImageBlock)

    assert len(result.extracted_assets) == 1
    asset = result.extracted_assets[0]

    assert img_block.parser_local_id == asset.parser_local_id
    assert asset.mime_type == "image/png"
    assert asset.raw_bytes == b"\x89PNG\r\n\x1a\n"


def test_image_inside_paragraph(parser: HTMLParser, metadata: FileMetadata) -> None:
    """An unresolved image inside a paragraph does not create a dangling block."""
    html = b'<body><p>Text before <img src="a.jpg" alt="img" /> Text after</p></body>'
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 2
    assert isinstance(result.blocks[0], RawTextBlock)
    assert result.blocks[0].text == "Text before"

    assert isinstance(result.blocks[1], RawTextBlock)
    assert result.blocks[1].text == "Text after"


# ── Boilerplate / Document structural tests ────────────────────────────────


def test_boilerplate_stripping_preserves_main_content(
    parser: HTMLParser, metadata: FileMetadata
) -> None:
    """readability-lxml should extract the main article."""
    html = b"""
    <html>
        <head><title>Real Article</title></head>
        <body>
            <nav>
                <ul><li>Home</li><li>About</li></ul>
            </nav>
            <div id="main-content">
                <h1>Important news</h1>
                <p>This is the core content that must be preserved.</p>
                <p>It contains multiple paragraphs so readability recognizes it.</p>
                <p>We need enough text here to pass the heuristics.</p>
                <p>Otherwise it might be considered boilerplate.</p>
            </div>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    """
    result = parser.parse(html, "", metadata)

    texts = [b.text for b in result.blocks if isinstance(b, RawTextBlock)]

    # The nav and footer should be stripped (readability heuristics).
    assert "Home" not in texts
    assert "Copyright 2026" not in texts

    # Core content should be present
    assert "This is the core content that must be preserved." in texts

    # Title extracted
    assert result.metadata.title == "Real Article"


def test_malformed_html_graceful_handling(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Malformed HTML is parsed gracefully without crashing."""
    html = b"<body><h1>Unclosed heading<p>Nested unclosed paragraph"
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) > 0
    # Both beautifulsoup and html5lib handle unclosed tags gracefully.


@patch("mnemo.parsers.html.Document.summary")
def test_ordinals_contiguous(mock_summary: Any, parser: HTMLParser, metadata: FileMetadata) -> None:
    """Block ordinals are contiguous and start from 0."""
    html = b"<body><h1>A</h1><p>B</p><ul><li>C</li></ul></body>"
    mock_summary.return_value = html.decode("utf-8")
    result = parser.parse(html, "", metadata)

    assert len(result.blocks) == 3
    ordinals = [b.ordinal for b in result.blocks]
    assert ordinals == [0, 1, 2]


def test_html_parser_edge_cases(parser: HTMLParser, metadata: FileMetadata) -> None:
    """Cover edge cases: no body, malformed data uri, empty strings."""
    # HTML without body tag
    html = b"<div>Just text</div>"
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 1

    # Malformed data URI
    html = b'<body><img src="data:image/png;base64,invalid!@#$" alt="broken" /></body>'
    result = parser.parse(html, "", metadata)
    assert result.blocks == ()
    assert result.extracted_assets == ()

    # Empty table row
    html = b"<body><table><tr></tr></table></body>"
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 0

    # Image alt as list
    html = b'<body><img src="data:image/png;base64,iVBORw0KGgo=" alt="alt1" alt="alt2" /></body>'
    result = parser.parse(html, "", metadata)
    assert len(result.blocks) == 1
