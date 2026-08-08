"""Built-in parser for HTML files.

Pure transformation component — no I/O, no storage, no canonicalization.
Conforms to ParserInterfaceV1 and returns a ParseResult (ADR-0011).
"""

import base64
import logging
from typing import Any

try:
    from bs4 import BeautifulSoup
    from bs4.element import NavigableString
    from readability import Document  # type: ignore[import-untyped]

    HTML_AVAILABLE = True
except ImportError:  # pragma: no cover
    HTML_AVAILABLE = False

from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawBlock,
    RawCodeBlock,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawTableBlock,
    RawTextBlock,
    TransientAsset,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import DocType, DocumentMetadata
from mnemo.models._shared import FrozenMetadata

logger = logging.getLogger(__name__)

BLOCK_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "table",
    "pre",
    "blockquote",
    "figure",
}
CONTAINER_TAGS = {
    "div",
    "section",
    "article",
    "main",
    "header",
    "footer",
    "nav",
    "aside",
    "body",
    "html",
    "li",
    "td",
    "th",
    "blockquote",
}


class HTMLParser(ParserInterfaceV1):
    """Parses HTML documents into RawBlocks using readability-lxml and bs4.

    Implements ParserInterfaceV1 (ADR-0011). Pure transformation — performs
    zero storage, zero canonicalization, and zero identity generation.
    Image asset bytes (data-URI sources) are surfaced as TransientAsset
    entries linked to RawImageBlocks via parser_local_id.
    """

    def __init__(self) -> None:
        if not HTML_AVAILABLE:  # pragma: no cover
            raise ContractValidationError("beautifulsoup4 and readability-lxml are not installed.")

    # ------------------------------------------------------------------
    # ParserInterfaceV1
    # ------------------------------------------------------------------

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".html", ".htm")

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_images=True,
            supports_tables=True,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        """Parse HTML bytes into a ParseResult."""
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractValidationError("HTML file is not valid UTF-8.") from exc

        if not content.strip():
            doc_meta = self._build_doc_meta(metadata)
            return ParseResult(
                blocks=(),
                extracted_assets=(),
                metadata=doc_meta,
                language="en",
                doc_type=DocType.GENERIC,
            )

        # Apply readability-lxml to strip boilerplate
        doc = Document(content)
        try:
            doc_title = doc.title()
            if doc_title == "[no-title]":
                doc_title = None
        except Exception:
            doc_title = None

        try:
            summary = doc.summary()
            # If readability stripped EVERYTHING but the original had text, fallback.
            soup_summary = BeautifulSoup(summary, "html5lib").get_text(strip=True)
            soup_orig = BeautifulSoup(content, "html5lib").get_text(strip=True)
            if not soup_summary and soup_orig:
                summary = content
        except Exception as e:
            logger.debug("readability-lxml failed, using original HTML: %s", e)
            summary = content

        soup = BeautifulSoup(summary, "html5lib")

        doc_meta = self._build_doc_meta(metadata, doc_title)

        blocks: list[RawBlock] = []
        assets: list[TransientAsset] = []

        # We need a state object to pass into the walker
        state = {"ordinal": 0, "blocks": blocks, "assets": assets}

        self._walk(soup.body, state)

        return ParseResult(
            blocks=tuple(blocks),
            extracted_assets=tuple(assets),
            metadata=doc_meta,
            language="en",
            doc_type=DocType.GENERIC,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_doc_meta(metadata: FileMetadata, title: str | None = None) -> DocumentMetadata:
        """Construct DocumentMetadata from FileMetadata and optional extracted title."""
        # The schema doesn't have a title in FileMetadata directly.
        # Fallback to "Untitled" if it's completely missing.
        return DocumentMetadata(
            content_hash=metadata.content_hash,
            title=title or "Untitled",
            metadata=FrozenMetadata(dict(metadata.metadata)),
        )

    def _extract_text(self, node: Any) -> str:
        """Extract text from a bs4 node, converting <br> to newline."""
        if isinstance(node, NavigableString):
            return str(node)
        if node.name == "br":
            return "\n"

        text = ""
        for child in node.children:
            text += self._extract_text(child)
        return text

    def _is_block_node(self, node: Any) -> bool:
        if isinstance(node, NavigableString):
            return False
        return node.name in BLOCK_TAGS

    def _has_block_children(self, node: Any) -> bool:
        for child in node.children:
            if self._is_block_node(child):
                return True
            if getattr(child, "name", None) in CONTAINER_TAGS and self._has_block_children(child):
                return True
        return False

    def _walk(self, node: Any, state: dict[str, Any]) -> None:
        """Recursively walk the HTML tree and append RawBlocks to state."""
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                state["blocks"].append(RawTextBlock(ordinal=state["ordinal"], text=text))
                state["ordinal"] += 1
            return

        if node.name in {"script", "style", "meta", "title", "noscript", "link", "base"}:
            return

        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = self._extract_text(node).strip()
            if text:
                level = int(node.name[1])
                state["blocks"].append(
                    RawHeadingBlock(ordinal=state["ordinal"], level=level, text=text)
                )
                state["ordinal"] += 1
            return

        if node.name == "pre":
            code_tag = node.find("code")
            lang = None
            if code_tag and code_tag.has_attr("class"):
                classes = code_tag["class"]
                for c in classes:
                    if c.startswith("language-"):
                        lang = c.replace("language-", "")
                        break
            text = node.get_text().strip()
            if text:
                state["blocks"].append(
                    RawCodeBlock(ordinal=state["ordinal"], code=text, code_language=lang)
                )
                state["ordinal"] += 1
            return

        if node.name in {"ul", "ol"}:
            items: list[str] = []
            for li in node.find_all("li", recursive=False):
                li_text = self._extract_text(li).strip()
                if li_text:
                    items.append(li_text)
            if items:
                state["blocks"].append(RawListBlock(ordinal=state["ordinal"], items=tuple(items)))
                state["ordinal"] += 1
            return

        if node.name == "table":
            rows: list[tuple[str, ...]] = []
            header_count = 0

            # tables might have tbody/thead
            search_base = node
            # if we find rows directly under table, or under tbody, find_all handles it gracefully.
            # but we want to avoid nested tables breaking.
            for tr in search_base.find_all("tr"):
                # Make sure the tr is actually part of this table (not a nested one)
                parent_table = tr.find_parent("table")
                if parent_table is not node:
                    continue

                row: list[str] = []
                is_header = False
                for td in tr.find_all(["td", "th"], recursive=False):
                    if td.name == "th":
                        is_header = True
                    row.append(self._extract_text(td).strip())
                if row:
                    rows.append(tuple(row))
                    if is_header:
                        header_count += 1
            if rows:
                max_w = max(len(r) for r in rows)
                padded: list[tuple[str, ...]] = []
                for r in rows:
                    padded.append(r + ("",) * (max_w - len(r)))
                state["blocks"].append(
                    RawTableBlock(
                        ordinal=state["ordinal"],
                        rows=tuple(padded),
                        header_row_count=header_count,
                    )
                )
                state["ordinal"] += 1
            return

        if node.name == "img":
            src = node.get("src", "")
            if not isinstance(src, str):
                src = src[0] if isinstance(src, list) and src else ""
            alt = node.get("alt", "")
            if not isinstance(alt, str):
                alt = alt[0] if isinstance(alt, list) and alt else ""

            local_id = f"image-{len(state['assets'])}"
            state["blocks"].append(
                RawImageBlock(
                    ordinal=state["ordinal"],
                    parser_local_id=local_id,
                    alt_text=alt if alt else None,
                )
            )
            state["ordinal"] += 1

            if src.startswith("data:image/"):
                try:
                    header, b64 = src.split(",", 1)
                    mime_type = header.split(";")[0].split(":")[1]
                    raw = base64.b64decode(b64)
                    if raw:
                        state["assets"].append(
                            TransientAsset(
                                parser_local_id=local_id,
                                mime_type=mime_type,
                                raw_bytes=raw,
                            )
                        )
                except Exception:
                    logger.debug("Could not decode data URI for image %s", local_id)
            return

        # Paragraph or inline container without block children
        if node.name == "p" or (node.name in CONTAINER_TAGS and not self._has_block_children(node)):
            buf: list[str] = []

            def flush_text() -> None:
                text = "".join(buf).strip()
                buf.clear()
                if text:
                    state["blocks"].append(RawTextBlock(ordinal=state["ordinal"], text=text))
                    state["ordinal"] += 1

            for child in node.children:
                if getattr(child, "name", None) == "img":
                    flush_text()
                    self._walk(child, state)
                else:
                    buf.append(self._extract_text(child))

            flush_text()
            return

        # Container with block children (or unknown tag)
        for child in node.children:
            self._walk(child, state)
