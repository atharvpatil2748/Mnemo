# Module 3.2: PDF Parser

**Date:** 2026-08-08
**Version:** v0.10.1

## Overview
Implemented the PDF Parser (Module 3.2) conforming to the new `ParserInterfaceV1` boundary requirements established in `ADR-0011`. The parser purely transforms raw PDF bytes into a `ParseResult` and performs zero persistent storage.

## Architectural Enforcement
- **Parser-Local Identity**: Replaced `uuid.uuid4()` with deterministic parser-local identifiers (e.g. `block-{ordinal}`) to link `RawImageBlock` to `TransientAsset`. This explicitly enforces that `parser_local_id` is only a temporary correlation key and not a minted permanent `asset_id`.
- **Pure Transformation**: The parser extracts structural hierarchy (`RawHeadingBlock`, `RawTextBlock`, `RawTableBlock`, `RawListBlock`, `RawImageBlock`) and transient assets without performing any IO mutation or canonicalization.
- **Header/Footer Preservation**: No semantic cleanup or frequency analysis is performed inside the parser. All text is passed exactly as parsed to be handled by the future orchestrator.

## Details
- Adopted `pymupdf` for efficient extraction of text, images, and tables.
- Implemented robust capabilities (`ParserCapabilities`) declaring support for images and tables but not OCR or Math.
- `PDFParser` explicitly exported via `mnemo.parsers.__init__`.
- Added comprehensive unit tests in `test_pdf_parser.py` using dynamically generated PDF payloads to maintain isolation. Code coverage for `pdf.py` exceeds 90%.
