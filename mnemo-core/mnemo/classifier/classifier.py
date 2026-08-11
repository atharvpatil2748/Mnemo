"""Pure, synchronous, deterministic Document Classifier."""

import dataclasses
import re
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from mnemo.interfaces.parser_models import (
    ParseResult,
    RawCodeBlock,
    RawHeadingBlock,
    RawListBlock,
    RawTableBlock,
    RawTextBlock,
)
from mnemo.models.documents import DocType


class DocumentClassifier:
    """Classifies a parsed document using rule-based heuristics.

    This is a pure Phase 3 component: it performs no storage or network I/O.
    LLM-assisted fallback is intentionally deferred to a later orchestration stage.
    """

    CODE_EXTENSIONS = frozenset(
        {
            ".py",
            ".js",
            ".ts",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".sh",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".css",
            ".html",
            ".xml",
            ".rb",
            ".php",
        }
    )

    MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})
    SLIDES_EXTENSIONS = frozenset({".ppt", ".pptx"})

    # Compiled patterns for heading-based classification
    # PAPER patterns
    _PAPER_PATTERN = re.compile(r"^(abstract|references|methodology|conclusion)$", re.IGNORECASE)
    # BOOK patterns
    _BOOK_PATTERN = re.compile(
        r"^(chapter\s+\d+|prologue|epilogue|table of contents)$", re.IGNORECASE
    )
    # RESUME patterns
    _RESUME_PATTERN = re.compile(
        r"^(experience|education|skills|employment history|resume|cv)$", re.IGNORECASE
    )
    # DOCUMENTATION patterns
    _DOCS_PATTERN = re.compile(
        r"^(api reference|getting started|installation|quickstart)$", re.IGNORECASE
    )
    # SLIDES patterns
    _SLIDES_PATTERN = re.compile(r"^(slide 1|presentation)$", re.IGNORECASE)

    _RESUME_SECTIONS: ClassVar[dict[re.Pattern[str], str]] = {
        re.compile(r"^(experience|employment history|work history)$", re.IGNORECASE): "experience",
        re.compile(r"^(education|academic background)$", re.IGNORECASE): "education",
        re.compile(r"^(skills|technical skills|core competencies)$", re.IGNORECASE): "skills",
        re.compile(r"^(projects|personal projects)$", re.IGNORECASE): "projects",
        re.compile(r"^(publications|papers|selected publications)$", re.IGNORECASE): "publications",
        re.compile(
            r"^(summary|profile|objectives|professional summary)$", re.IGNORECASE
        ): "summary",
        re.compile(r"^(contact|contact information)$", re.IGNORECASE): "contact",
    }

    def classify(self, result: ParseResult, filename: str | None = None) -> ParseResult:
        """Classify the parsed document and return a new ParseResult with the determined doc_type.

        Rules are evaluated in the following precedence (highest to lowest):
        1. Strong file extensions (e.g., .py -> CODE, .md -> MARKDOWN)
        2. Heading keywords (e.g., "Abstract" -> PAPER, "Chapter 1" -> BOOK)
        3. Structural features (e.g., mostly code blocks -> CODE)
        4. Fallback -> GENERIC

        If DocType.RESUME is detected, additionally performs deterministic semantic annotation
        of Resume boundaries (sections and roles).

        Args:
            result: The input ParseResult from the parsing (and cleaning) stage.
            filename: The original filename, if available from the orchestrator.

        Returns:
            A new ParseResult instance with the updated doc_type (and annotations).
        """
        doc_type = self._determine_type(result, filename)

        if doc_type != result.doc_type:
            result = dataclasses.replace(result, doc_type=doc_type)

        if result.doc_type == DocType.RESUME:
            return self._annotate_resume(result)
        elif result.doc_type == DocType.SLIDES:
            return self._annotate_slides(result)
        elif result.doc_type == DocType.DOCUMENTATION:
            return self._annotate_documentation(result)

        return result

    def _annotate_resume(self, result: ParseResult) -> ParseResult:
        from mnemo.models._shared import FrozenMetadata

        new_doc_metadata_dict = dict(result.metadata.metadata)
        new_doc_metadata_dict["parser.resume.schema_version"] = 1
        new_doc_metadata = dataclasses.replace(
            result.metadata, metadata=FrozenMetadata(new_doc_metadata_dict)
        )

        new_blocks = []
        current_section = None
        current_section_level = 0
        role_count = 0
        current_role_id = None
        current_role_level = None

        for block in result.blocks:
            block_meta_dict = dict(block.metadata)

            if isinstance(block, RawHeadingBlock):
                heading_text = block.text.strip()
                matched_section = None
                for pattern, section_name in self._RESUME_SECTIONS.items():
                    if pattern.search(heading_text):
                        matched_section = section_name
                        break

                if matched_section:
                    current_section = matched_section
                    current_section_level = block.level
                    if current_section == "experience":
                        current_role_id = None
                        current_role_level = None
                elif current_section == "experience" and block.level > current_section_level:
                    if current_role_level is None or block.level <= current_role_level:
                        role_count += 1
                        current_role_id = f"role-{role_count:06d}"
                        current_role_level = block.level

            if current_section:
                block_meta_dict["parser.resume.section"] = current_section
                if current_section == "experience" and current_role_id:
                    block_meta_dict["parser.resume.role_local_id"] = current_role_id

            new_block = dataclasses.replace(block, metadata=FrozenMetadata(block_meta_dict))
            new_blocks.append(new_block)

        return dataclasses.replace(result, metadata=new_doc_metadata, blocks=tuple(new_blocks))

    def _annotate_slides(self, result: ParseResult) -> ParseResult:
        from mnemo.models._shared import FrozenMetadata

        new_doc_metadata_dict = dict(result.metadata.metadata)
        new_doc_metadata_dict["parser.slide.schema_version"] = 1
        new_doc_metadata = dataclasses.replace(
            result.metadata, metadata=FrozenMetadata(new_doc_metadata_dict)
        )

        new_blocks = []
        slide_map: dict[int, int] = {}
        next_slide_num = 1
        seen_title_in_slide: set[int] = set()
        all_pages_missing = all(block.page_number is None for block in result.blocks)

        for block in result.blocks:
            block_meta_dict = dict(block.metadata)

            # Determine canonical slide number
            page = block.page_number
            if all_pages_missing:
                canonical_slide_num = 1
            elif page is None:
                canonical_slide_num = next_slide_num
                next_slide_num += 1
            else:
                if page not in slide_map:
                    slide_map[page] = next_slide_num
                    next_slide_num += 1
                canonical_slide_num = slide_map[page]
            block_meta_dict["parser.slide.number"] = canonical_slide_num

            # Determine title slide
            if canonical_slide_num == 1:
                block_meta_dict["parser.slide.is_title_slide"] = True
            else:
                block_meta_dict.pop("parser.slide.is_title_slide", None)

            # Determine role
            # Preserve existing explicitly parsed roles (like notes) if they exist
            existing_role = block_meta_dict.get("parser.slide.role")
            if existing_role:
                pass
            elif (
                isinstance(block, RawHeadingBlock)
                and canonical_slide_num not in seen_title_in_slide
            ):
                block_meta_dict["parser.slide.role"] = "title"
                seen_title_in_slide.add(canonical_slide_num)
            else:
                block_meta_dict["parser.slide.role"] = "body"

            new_block = dataclasses.replace(block, metadata=FrozenMetadata(block_meta_dict))
            new_blocks.append(new_block)

        return dataclasses.replace(result, metadata=new_doc_metadata, blocks=tuple(new_blocks))

    def _annotate_documentation(self, result: ParseResult) -> ParseResult:
        from mnemo.models._shared import FrozenMetadata

        new_doc_metadata_dict = dict(result.metadata.metadata)
        new_doc_metadata_dict["parser.documentation.schema_version"] = 1
        new_doc_metadata = dataclasses.replace(
            result.metadata, metadata=FrozenMetadata(new_doc_metadata_dict)
        )

        new_blocks = []
        callout_pattern = re.compile(r"^(note|warning|tip|caution|important)\b", re.IGNORECASE)
        toc_pattern = re.compile(
            r"^(table of contents|contents|in this article|on this page)$", re.IGNORECASE
        )
        api_pattern = re.compile(
            r"^(api(\s+reference)?|reference|endpoints?|functions?|methods?|classes?|"
            r"interfaces?|types?|parameters?|arguments?|returns?|responses?|properties?)$",
            re.IGNORECASE,
        )

        in_toc = False
        in_api_reference = False
        api_reference_level: int | None = None

        for block in result.blocks:
            block_meta_dict = dict(block.metadata)

            if isinstance(block, RawHeadingBlock):
                heading_text = block.text.strip()
                if toc_pattern.match(heading_text):
                    in_toc = True
                    in_api_reference = False
                    api_reference_level = None
                    block_meta_dict["parser.documentation.role"] = "toc"
                elif api_pattern.match(heading_text):
                    in_api_reference = True
                    in_toc = False
                    api_reference_level = block.level
                    block_meta_dict["parser.documentation.role"] = "api_reference"
                else:
                    in_toc = False
                    if (
                        in_api_reference
                        and api_reference_level is not None
                        and block.level > api_reference_level
                    ):
                        block_meta_dict["parser.documentation.role"] = "api_reference"
                    else:
                        in_api_reference = False
                        api_reference_level = None
            else:
                if in_toc and isinstance(block, (RawListBlock, RawTextBlock)):
                    block_meta_dict["parser.documentation.role"] = "toc"
                elif in_api_reference:
                    block_meta_dict["parser.documentation.role"] = "api_reference"

                is_callout = False
                callout_type = None
                md_source = str(block_meta_dict.get("parser.markdown.source", ""))

                if md_source:
                    docusaurus_match = re.search(
                        r"^:::(note|warning|tip|caution|important)\b",
                        md_source,
                        re.IGNORECASE | re.MULTILINE,
                    )
                    if docusaurus_match:
                        is_callout = True
                        callout_type = docusaurus_match.group(1).lower()
                    else:
                        bq_match = re.search(
                            r"^>\s*(?:\*\*)?(note|warning|tip|caution|important)(?:\*\*)?:?",
                            md_source,
                            re.IGNORECASE | re.MULTILINE,
                        )
                        if bq_match:
                            is_callout = True
                            callout_type = bq_match.group(1).lower()

                if not is_callout and isinstance(block, RawTextBlock):
                    text_start = block.text.strip().split("\n")[0]
                    text_match = callout_pattern.match(text_start)
                    if text_match and (
                        text_start.startswith(text_match.group(0) + ":") or text_start.isupper()
                    ):
                        is_callout = True
                        callout_type = text_match.group(1).lower()

                if is_callout:
                    block_meta_dict["parser.documentation.role"] = "callout"
                    block_meta_dict["parser.documentation.callout_type"] = callout_type

                if not is_callout and isinstance(block, RawListBlock):
                    list_meta = block_meta_dict.get("parser.markdown.list")
                    if isinstance(list_meta, Mapping) and list_meta.get("ordered") is True:
                        block_meta_dict["parser.documentation.role"] = "task_block"

            new_block = dataclasses.replace(block, metadata=FrozenMetadata(block_meta_dict))
            new_blocks.append(new_block)

        return dataclasses.replace(result, metadata=new_doc_metadata, blocks=tuple(new_blocks))

    def _determine_type(self, result: ParseResult, filename: str | None) -> DocType:
        # 1. Strong extension heuristics
        if filename:
            ext = Path(filename).suffix.lower()
            if ext in self.CODE_EXTENSIONS:
                return DocType.CODE
            if ext in self.MARKDOWN_EXTENSIONS:
                return DocType.MARKDOWN
            if ext == ".eml" or ext == ".msg":
                return DocType.EMAIL
            if ext in self.SLIDES_EXTENSIONS:
                return DocType.SLIDES

        # 2. Heading heuristics
        for block in result.blocks:
            if isinstance(block, RawHeadingBlock):
                text = block.text.strip()
                if self._PAPER_PATTERN.search(text):
                    return DocType.PAPER
                if self._BOOK_PATTERN.search(text):
                    return DocType.BOOK
                if self._RESUME_PATTERN.search(text):
                    return DocType.RESUME
                if self._DOCS_PATTERN.search(text):
                    return DocType.DOCUMENTATION
                if self._SLIDES_PATTERN.search(text):
                    return DocType.SLIDES

        # 3. Structural heuristics
        code_blocks = 0
        text_blocks = 0
        table_blocks = 0
        total_structural_blocks = 0

        for block in result.blocks:
            if isinstance(block, RawCodeBlock):
                code_blocks += 1
                total_structural_blocks += 1
            elif isinstance(block, RawTextBlock):
                text_blocks += 1
                total_structural_blocks += 1
            elif isinstance(block, RawTableBlock):
                table_blocks += 1
                total_structural_blocks += 1

        if total_structural_blocks > 0 and (code_blocks / total_structural_blocks > 0.8):
            return DocType.CODE

        return DocType.GENERIC
