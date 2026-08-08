import re
import unicodedata
from collections import defaultdict
from dataclasses import replace

import langdetect  # type: ignore

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


class DocumentCleaner:
    """Cleans and normalizes RawBlocks within a ParseResult."""

    def clean(self, parse_result: ParseResult) -> ParseResult:
        """Apply pure transformations to ParseResult."""

        # 1. First pass: clean text inside blocks and detect language
        cleaned_blocks: list[RawBlock] = []
        for block in parse_result.blocks:
            cleaned_blocks.append(self._clean_block(block))

        # 2. Second pass: detect and remove headers/footers
        filtered_blocks = self._filter_headers_footers(cleaned_blocks)

        # 3. Third pass: fix ordinals
        final_blocks = self._reassign_ordinals(filtered_blocks)

        return replace(parse_result, blocks=tuple(final_blocks))

    def _clean_block(self, block: RawBlock) -> RawBlock:
        if isinstance(block, (RawTextBlock, RawHeadingBlock)):
            cleaned_text = self._normalize_text(block.text)
            lang = self._detect_language(cleaned_text) or block.language
            return replace(block, text=cleaned_text, language=lang)

        elif isinstance(block, RawListBlock):
            cleaned_items = tuple(self._normalize_text(item) for item in block.items)
            combined_text = " ".join(cleaned_items)
            lang = self._detect_language(combined_text) or block.language
            return replace(block, items=cleaned_items, language=lang)

        elif isinstance(block, RawTableBlock):
            cleaned_rows = tuple(
                tuple(self._normalize_text(cell) for cell in row) for row in block.rows
            )
            # detect language from first few cells
            sample_text = " ".join(c for r in cleaned_rows for c in r if c)[:500]
            lang = self._detect_language(sample_text) or block.language
            return replace(block, rows=cleaned_rows, language=lang)

        elif isinstance(block, RawCodeBlock):
            # We don't mess with code block whitespaces/hyphens, just unicode maybe?
            # Actually, code should probably be left strictly raw except for NFC
            cleaned_code = unicodedata.normalize("NFC", block.code)
            return replace(block, code=cleaned_code)

        elif isinstance(block, RawMathBlock):
            cleaned_latex = unicodedata.normalize("NFC", block.latex)
            return replace(block, latex=cleaned_latex)

        elif isinstance(block, RawImageBlock):
            if block.alt_text:
                cleaned_alt = self._normalize_text(block.alt_text)
                lang = self._detect_language(cleaned_alt) or block.language
                return replace(block, alt_text=cleaned_alt, language=lang)
            return block

        return block

    def _normalize_text(self, text: str) -> str:
        """Applies normalization heuristics."""
        # Fix hyphenated line breaks (e.g. end-\nof-line)
        text = re.sub(r"-\s*\n\s*", "", text)
        # Collapse whitespace (including multiple spaces, newlines, tabs)
        text = re.sub(r"\s+", " ", text).strip()
        # Unicode normalization (NFC)
        text = unicodedata.normalize("NFC", text)
        return text

    def _detect_language(self, text: str) -> str | None:
        """Detect language, returning None if uncertain or error."""
        if not text or len(text.strip()) < 5:
            return None
        try:
            return langdetect.detect(text)  # type: ignore
        except langdetect.lang_detect_exception.LangDetectException:
            return None

    def _filter_headers_footers(self, blocks: list[RawBlock]) -> list[RawBlock]:
        """Detects and removes repetitive text appearing across multiple pages."""
        pages = {b.page_number for b in blocks if b.page_number is not None}
        total_pages = len(pages)

        # Only apply header/footer detection if doc has multiple pages
        if total_pages < 2:
            return blocks

        # Map cleaned text to a set of pages it appears on
        text_page_map: dict[str, set[int]] = defaultdict(set)

        for block in blocks:
            if block.page_number is None:
                continue
            text = self._extract_comparable_text(block)
            if text:
                text_page_map[text].add(block.page_number)

        # Find noisy text (appears on >50% of total pages)
        noisy_texts = {
            text
            for text, present_pages in text_page_map.items()
            if len(present_pages) > (total_pages / 2.0)
        }

        if not noisy_texts:
            return blocks

        filtered = []
        for block in blocks:
            text = self._extract_comparable_text(block)
            if text and text in noisy_texts:
                # It's a header/footer artifact, skip it
                continue
            filtered.append(block)

        return filtered

    def _extract_comparable_text(self, block: RawBlock) -> str | None:
        """Extracts text for header/footer comparison."""
        if isinstance(block, (RawTextBlock, RawHeadingBlock)):
            return block.text
        return None

    def _reassign_ordinals(self, blocks: list[RawBlock]) -> list[RawBlock]:
        """Reassigns ordinals after filtering to preserve contiguous numbering."""
        new_blocks = []
        for i, block in enumerate(blocks):
            new_blocks.append(replace(block, ordinal=i))
        return new_blocks
