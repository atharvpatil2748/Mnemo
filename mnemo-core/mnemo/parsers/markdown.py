"""Built-in parser for Markdown files.

Pure transformation component — no I/O, no storage, no canonicalization.
Conforms to ParserInterfaceV1 and returns a ParseResult (ADR-0011).
"""

import base64
import logging
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

try:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token

    MARKDOWN_AVAILABLE = True
except ImportError:  # pragma: no cover
    MARKDOWN_AVAILABLE = False

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


class MarkdownParser(ParserInterfaceV1):
    """Parses Markdown documents into RawBlocks using markdown-it-py.

    Implements ParserInterfaceV1 (ADR-0011).  Pure transformation — performs
    zero storage, zero canonicalization, and zero identity generation.
    Image asset bytes (data-URI sources) are surfaced as TransientAsset
    entries linked to RawImageBlocks via parser_local_id.
    """

    def __init__(self) -> None:
        if not MARKDOWN_AVAILABLE:  # pragma: no cover
            raise ContractValidationError(
                "markdown-it-py is not installed. Add markdown-it-py to your dependencies."
            )
        self._md = MarkdownIt("commonmark", {"html": False}).enable("table")

    # ------------------------------------------------------------------
    # ParserInterfaceV1
    # ------------------------------------------------------------------

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".md", ".markdown")

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_images=True,
            supports_tables=True,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        """Parse Markdown bytes into a ParseResult."""
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractValidationError(f"Markdown file is not valid UTF-8: {filename}") from exc

        doc_meta = self._build_doc_meta(metadata)

        if not content.strip():
            return ParseResult(
                blocks=(),
                extracted_assets=(),
                metadata=doc_meta,
                language="en",
                doc_type=DocType.GENERIC,
            )

        try:
            tokens = self._md.parse(content)
        except Exception as exc:  # pragma: no cover
            raise ContractValidationError(f"Failed to tokenise Markdown: {exc}") from exc

        blocks: list[RawBlock] = []
        assets: list[TransientAsset] = []
        source_lines = content.splitlines(keepends=True)
        ordinal = 0
        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]

            # ── Headings ──────────────────────────────────────────────
            if tok.type == "heading_open":
                opening = tok
                heading_tokens: list[Token] = []
                level = int(tok.tag[1:]) if tok.tag and tok.tag[0] == "h" else 1
                i += 1
                text_parts: list[str] = []
                while i < n and tokens[i].type != "heading_close":
                    heading_tokens.append(tokens[i])
                    if tokens[i].type == "inline":
                        text_parts.append(self._inline_text(tokens[i]))
                    i += 1
                text = "".join(text_parts).strip()
                if text:
                    blocks.append(
                        RawHeadingBlock(
                            ordinal=ordinal,
                            level=level,
                            text=text,
                            metadata=self._markdown_metadata(
                                "heading",
                                self._source_slice(source_lines, opening),
                                self._internal_links(heading_tokens),
                            ),
                        )
                    )
                    ordinal += 1

            # ── Paragraphs ────────────────────────────────────────────
            elif tok.type == "paragraph_open":
                opening = tok
                paragraph_tokens: list[Token] = []
                end = i + 1
                while end < n and tokens[end].type != "paragraph_close":
                    paragraph_tokens.append(tokens[end])
                    end += 1
                paragraph_metadata = self._markdown_metadata(
                    "paragraph",
                    self._source_slice(source_lines, opening),
                    self._internal_links(paragraph_tokens),
                )
                i += 1
                while i < n and tokens[i].type != "paragraph_close":
                    if tokens[i].type == "inline":
                        new_blocks, new_assets, ordinal = self._process_inline(
                            tokens[i], ordinal, assets, paragraph_metadata
                        )
                        blocks.extend(new_blocks)
                        assets.extend(new_assets)
                    i += 1

            # ── Blockquotes (flatten to text) ─────────────────────────
            elif tok.type == "blockquote_open":
                opening = tok
                quote_tokens: list[Token] = []
                i += 1
                parts: list[str] = []
                while i < n and tokens[i].type != "blockquote_close":
                    quote_tokens.append(tokens[i])
                    if tokens[i].type == "inline":
                        parts.append(self._inline_text(tokens[i]))
                    i += 1
                text = "\n".join(p for p in parts if p).strip()
                if text:
                    blocks.append(
                        RawTextBlock(
                            ordinal=ordinal,
                            text=text,
                            metadata=self._markdown_metadata(
                                "blockquote",
                                self._source_slice(source_lines, opening),
                                self._internal_links(quote_tokens),
                            ),
                        )
                    )
                    ordinal += 1

            # ── Lists (bullet or ordered) ─────────────────────────────
            elif tok.type in ("bullet_list_open", "ordered_list_open"):
                opening = tok
                start_index = i
                end_type = tok.type.replace("_open", "_close")
                items: list[str] = []
                i += 1
                while i < n and tokens[i].type != end_type:
                    if tokens[i].type == "list_item_open":
                        item_parts: list[str] = []
                        i += 1
                        depth = 1
                        while i < n:
                            t = tokens[i]
                            if t.type == "list_item_open":
                                depth += 1
                            elif t.type == "list_item_close":
                                depth -= 1
                                if depth == 0:
                                    break
                            elif t.type == "inline":
                                item_parts.append(self._inline_text(t))
                            i += 1
                        item_text = "\n".join(p for p in item_parts if p).strip()
                        if item_text:
                            items.append(item_text)
                    i += 1
                if items:
                    list_tokens = tokens[start_index : i + 1]
                    blocks.append(
                        RawListBlock(
                            ordinal=ordinal,
                            items=tuple(items),
                            metadata=self._markdown_metadata(
                                "list",
                                self._source_slice(source_lines, opening),
                                self._internal_links(list_tokens),
                                {"parser.markdown.list": self._list_structure(list_tokens)},
                            ),
                        )
                    )
                    ordinal += 1

            # ── Fenced code / indented code ───────────────────────────
            elif tok.type in ("fence", "code_block"):
                code = tok.content.strip()
                lang = tok.info.strip() if tok.info else None
                if code:
                    blocks.append(
                        RawCodeBlock(
                            ordinal=ordinal,
                            code=code,
                            code_language=lang or None,
                            metadata=self._markdown_metadata(
                                "code",
                                self._source_slice(source_lines, tok),
                            ),
                        )
                    )
                    ordinal += 1

            # ── Tables ────────────────────────────────────────────────
            elif tok.type == "table_open":
                opening = tok
                start_index = i
                rows: list[tuple[str, ...]] = []
                header_count = 0
                i += 1
                while i < n and tokens[i].type != "table_close":
                    if tokens[i].type == "tr_open":
                        cells: list[str] = []
                        is_th = False
                        i += 1
                        while i < n and tokens[i].type != "tr_close":
                            if tokens[i].type in ("th_open", "td_open"):
                                is_th = is_th or tokens[i].type == "th_open"
                                cell_parts: list[str] = []
                                i += 1
                                while i < n and tokens[i].type not in (
                                    "th_close",
                                    "td_close",
                                ):
                                    if tokens[i].type == "inline":
                                        cell_parts.append(self._inline_text(tokens[i]))
                                    i += 1
                                cells.append("".join(cell_parts).strip())
                            i += 1
                        if cells:
                            rows.append(tuple(cells))
                            if is_th:
                                header_count += 1
                    i += 1
                if rows:
                    blocks.append(
                        RawTableBlock(
                            ordinal=ordinal,
                            rows=tuple(rows),
                            header_row_count=header_count,
                            metadata=self._markdown_metadata(
                                "table",
                                self._source_slice(source_lines, opening),
                                self._internal_links(tokens[start_index : i + 1]),
                            ),
                        )
                    )
                    ordinal += 1

            elif tok.type == "hr":
                source = self._source_slice(source_lines, tok)
                blocks.append(
                    RawTextBlock(
                        ordinal=ordinal,
                        text=source.strip(),
                        metadata=self._markdown_metadata("thematic_break", source),
                    )
                )
                ordinal += 1

            # HTML blocks and unknown token types remain intentionally ignored.
            # else: ignore unknown token types

            i += 1

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
    def _build_doc_meta(metadata: FileMetadata) -> DocumentMetadata:
        """Construct a minimal DocumentMetadata from FileMetadata."""
        return DocumentMetadata(
            content_hash=metadata.content_hash,
            metadata=FrozenMetadata(dict(metadata.metadata)),
        )

    @staticmethod
    def _inline_text(tok: "Token") -> str:
        """Flatten an inline token to plain text, inserting newlines at softbreaks."""
        if not tok.children:
            return tok.content
        parts: list[str] = []
        for child in tok.children:
            if child.type == "softbreak":
                parts.append("\n")
            elif child.type != "image":
                parts.append(child.content)
        return "".join(parts)

    def _process_inline(
        self,
        tok: "Token",
        ordinal: int,
        existing_assets: list[TransientAsset],
        metadata: FrozenMetadata,
    ) -> "tuple[list[RawBlock], list[TransientAsset], int]":
        """Expand an inline token into RawBlocks, splitting on images."""
        out_blocks: list[RawBlock] = []
        out_assets: list[TransientAsset] = []
        text_buf: list[str] = []
        metadata_used = False

        def text_metadata() -> FrozenMetadata:
            nonlocal metadata_used
            if not metadata_used:
                metadata_used = True
                return metadata
            return FrozenMetadata(
                {
                    "parser.markdown.block_type": "paragraph_fragment",
                    "parser.markdown.kind": "paragraph_fragment",
                }
            )

        def flush_text() -> None:
            nonlocal ordinal
            t = "".join(text_buf).strip()
            text_buf.clear()
            if t:
                out_blocks.append(RawTextBlock(ordinal=ordinal, text=t, metadata=text_metadata()))
                ordinal += 1

        if not tok.children:
            t = tok.content.strip()
            if t:
                out_blocks.append(RawTextBlock(ordinal=ordinal, text=t, metadata=text_metadata()))
                ordinal += 1
            return out_blocks, out_assets, ordinal

        for child in tok.children:
            if child.type == "image":
                flush_text()
                src_value = child.attrs.get("src", "") if child.attrs else ""
                src = str(src_value)
                alt: str = child.content or ""
                # Only embed bytes for data URIs
                if src.startswith("data:image/"):
                    try:
                        header, b64 = src.split(",", 1)
                        mime_type = header.split(";")[0].split(":")[1]
                        raw = base64.b64decode(b64, validate=True)
                        if raw:
                            asset_index = len(existing_assets) + len(out_assets)
                            local_id = f"image-{asset_index}"
                            out_assets.append(
                                TransientAsset(
                                    parser_local_id=local_id,
                                    mime_type=mime_type,
                                    raw_bytes=raw,
                                )
                            )
                            out_blocks.append(
                                RawImageBlock(
                                    ordinal=ordinal,
                                    parser_local_id=local_id,
                                    alt_text=alt or None,
                                    metadata=FrozenMetadata(
                                        {
                                            "parser.markdown.block_type": "inline_image",
                                            "parser.markdown.kind": "inline_image",
                                        }
                                    ),
                                )
                            )
                            ordinal += 1
                    except Exception:
                        logger.debug("Could not decode inline image data")
            elif child.type == "softbreak":
                text_buf.append("\n")
            else:
                text_buf.append(child.content)

        flush_text()
        return out_blocks, out_assets, ordinal

    @staticmethod
    def _source_slice(lines: list[str], tok: "Token") -> str:
        """Return the exact source lines owned by a block token."""
        if tok.map is None:
            return ""
        start, end = tok.map
        return "".join(lines[start:end])

    @staticmethod
    def _markdown_metadata(
        kind: str,
        source: str,
        links: tuple[Mapping[str, object], ...] = (),
        extra: Mapping[str, object] | None = None,
    ) -> FrozenMetadata:
        """Build serializable Markdown semantic metadata."""
        values: dict[str, object] = {
            "parser.markdown.block_type": kind,
            "parser.markdown.kind": kind,
            "parser.markdown.source": source,
        }
        if links:
            values["parser.markdown.links"] = links
        if extra is not None:
            values.update(extra)
        return FrozenMetadata(values)

    @classmethod
    def _internal_links(cls, tokens: Iterable["Token"]) -> tuple[Mapping[str, object], ...]:
        """Extract resolved internal links in deterministic source order."""
        result: list[Mapping[str, object]] = []
        for tok in tokens:
            if tok.type != "inline" or not tok.children:
                continue
            active: dict[str, object] | None = None
            label_parts: list[str] = []
            for child in tok.children:
                if child.type == "link_open":
                    target_value = child.attrs.get("href", "") if child.attrs else ""
                    title_value = child.attrs.get("title") if child.attrs else None
                    active = {"target": str(target_value), "title": title_value}
                    label_parts = []
                elif child.type == "link_close" and active is not None:
                    if cls._is_internal_target(str(active["target"])):
                        active["label"] = "".join(label_parts)
                        result.append(active)
                    active = None
                    label_parts = []
                elif active is not None and child.type not in {
                    "em_open",
                    "em_close",
                    "strong_open",
                    "strong_close",
                }:
                    label_parts.append(child.content)
        return tuple(result)

    @staticmethod
    def _is_internal_target(target: str) -> bool:
        """Return whether a Markdown link targets local source content."""
        parsed = urlsplit(target)
        return bool(target) and not parsed.scheme and not parsed.netloc

    @classmethod
    def _list_structure(cls, tokens: list["Token"]) -> Mapping[str, object]:
        """Return a compact preorder description of list type and nesting."""
        list_stack: list[tuple[bool, str, int | None]] = []
        items: list[Mapping[str, object]] = []
        for index, tok in enumerate(tokens):
            if tok.type in {"bullet_list_open", "ordered_list_open"}:
                start_value = tok.attrs.get("start") if tok.attrs else None
                start = int(start_value) if start_value is not None else None
                list_stack.append((tok.type == "ordered_list_open", tok.markup, start))
            elif tok.type in {"bullet_list_close", "ordered_list_close"}:
                list_stack.pop()
            elif tok.type == "list_item_open" and list_stack:
                ordered, marker, start = list_stack[-1]
                direct_parts: list[str] = []
                for candidate in tokens[index + 1 :]:
                    if candidate.type == "list_item_close" and candidate.level == tok.level:
                        break
                    if candidate.type == "inline" and candidate.level == tok.level + 2:
                        direct_parts.append(cls._inline_text(candidate))
                items.append(
                    {
                        "depth": len(list_stack) - 1,
                        "marker": marker,
                        "ordered": ordered,
                        "start": start,
                        "text": "\n".join(direct_parts),
                    }
                )
        root = tokens[0]
        root_start_value = root.attrs.get("start") if root.attrs else None
        return {
            "items": tuple(items),
            "marker": root.markup,
            "ordered": root.type == "ordered_list_open",
            "start": int(root_start_value) if root_start_value is not None else None,
        }
