# 0017: HTML Parser (Module 3.5)

## Implementation Summary
The HTML Parser (Module 3.5) has been successfully implemented, audited, and frozen. It adheres strictly to the `ADR-0011` raw parser boundary. It uses `beautifulsoup4` combined with the `html5lib` parser to robustly handle standard and malformed HTML input, and leverages `readability-lxml` as a heuristic to strip navigational boilerplate, ads, and footers. The parser translates HTML semantically into a pure `RawBlock` hierarchy and extracts any embedded images as `TransientAsset`s.

## Architectural Notes
- **Purity Preserved**: The parser is a pure function. It accepts raw bytes and `FileMetadata` and returns a `ParseResult`.
- **Identity Isolation**: It strictly uses deterministic correlation keys (e.g., `local-img-0`) instead of minting persistent UUIDs, deferring all persistent ID generation to the upcoming DocumentCanonicalizer.
- **Storage Isolation**: Zero storage writes occur during parsing.

## Dependencies Added
- `beautifulsoup4`: For DOM traversal and block generation.
- `html5lib`: As the backend for `beautifulsoup4` to ensure HTML5-compliant, robust parsing that handles missing tags like `<body>` gracefully.
- `readability-lxml`: For boilerplate stripping and main content extraction.

## Parser Capabilities
- Parses semantic HTML headings `<h1>`–`<h6>` into `RawHeadingBlock`.
- Parses paragraphs `<p>` and standard flow content into `RawTextBlock`.
- Extracts lists (`<ul>`, `<ol>`) into `RawListBlock`.
- Extracts tables (`<table>`) into `RawTableBlock`.
- Captures `<img>` elements, including Base64-encoded Data URIs, and packages them safely into `TransientAsset` structures paired with `RawImageBlock`.
- Strips heavy boilerplate safely without throwing fatal errors.

## Validation Summary
- `ruff` formatting and linting: PASS
- `mypy --strict`: PASS
- `pytest`: PASS (372 tests)
- Lockfile validation: PASS
- Builds (`mnemo-core`, `mnemo-server`): PASS

## Coverage
Total project coverage is **90.53%**, meeting the >90% requirement. `mnemo/parsers/html.py` specifically achieved exactly 90% coverage through thorough edge case handling.

## Important Implementation Decisions
1. **Fallback for Empty Documents**: If `readability-lxml` aggressively strips the content to the point where the `<body>` is empty, the parser falls back to parsing the original raw HTML.
2. **Missing `<body>` handling**: Using `html5lib` ensures that a `<body>` element always exists, allowing the recursive DOM walk function to operate safely without None-checks at the root iteration layer.
