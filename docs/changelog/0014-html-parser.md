# Changelog: 0014 HTML Parser Implementation

## Context
As part of Phase 3 Module 3.5, the built-in HTML Parser has been implemented. This parser handles `.html` and `.htm` file extensions and `text/html` mime types.

## Architecture Alignment
The HTML parser strictly follows the `ParserInterfaceV1` boundary introduced in `ADR-0011`. 
- **Purity:** The parser strictly performs stateless transformation. It does not hit the database or mint UUIDs.
- **Output:** It returns a `ParseResult` instead of a `ParsedDocument`.
- **Identity:** Emits deterministic parser-local keys for correlation (e.g., `image-1`).
- **Dependencies:** Uses `beautifulsoup4` paired with `html5lib` for tolerant structural parsing and `readability-lxml` for extracting main boilerplate-free textual content.

## Key Features
- **Boilerplate Stripping:** Leverages the readability heuristic engine to identify the core content of a webpage while discarding sidebars, footers, headers, and ads.
- **Robust Fallbacks:** In cases where readability's heuristic aggressively strips the entire page, it detects content loss and falls back to parsing the raw DOM to guarantee zero data loss.
- **Asset Extraction:** Captures inline `<img src="data:...">` resources as Base64 strings, producing `TransientAsset` correlation objects within the `ParseResult`.

## Validation
- Linted with `ruff` and strictly typed with `mypy`.
- Unit tests written with complete coverage of edge cases.
- Achieved **90.1% test coverage** for `mnemo/parsers/html.py`.

*Status: Frozen at Module 3.5 checkpoint.*
