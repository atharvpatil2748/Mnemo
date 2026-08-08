# 0018: Text, JSON, and CSV Parsers (Module 3.6)

**Date:** 2026-08-08  
**Module:** 3.6  
**Status:** Frozen  

## Implementation Summary
Added built-in parsing for `.txt`, `.json`, `.csv`, and related formats using three pure transformation parsers: `PlainTextParser`, `JSONParser`, and `CSVParser`. 

## Parser Capabilities
- **PlainTextParser**: Splits text (including `.txt`, `.log`, and `.md` fallback) by double newlines into paragraphs, yielding `RawTextBlock`.
- **JSONParser**: Parses `.json` inputs, flattening dictionaries and arrays into key-value strings to retain structural context for downstream RAG retrieval. Yields `RawTextBlock`.
- **CSVParser**: Parses tabular data (`.csv`, `.tsv`) utilizing Python's `csv` standard library. Automatically detects dialects and yields `RawTableBlock`.

## Dependencies
- Standard Library only (`csv`, `json`). No new external dependencies introduced.

## Architectural Notes (ADR-0011)
- Parsers adhere strictly to `ParserInterfaceV1`, guaranteeing side-effect-free execution.
- Parsers emit purely `RawBlock` components (`RawTextBlock`, `RawTableBlock`), delegating any Asset extraction or identity canonicalization to downstream pipeline layers.
- Zero network I/O, zero UUID generation, zero blob storage.

## Validation Summary
- Ruff format and lint checks pass cleanly.
- Mypy (`--strict`) is green for `mnemo-core` and `mnemo-server`.
- Comprehensive Pytest coverage successfully confirmed, covering valid inputs, empty files, incorrect encodings, and malformed structures.
- Total Repository Coverage: >90% (90.71%).
