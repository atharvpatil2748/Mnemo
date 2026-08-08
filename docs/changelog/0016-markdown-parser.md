# Changelog 0016: Markdown Parser

## Summary

Phase 3 Module 3.4 adds the built-in `MarkdownParser` using `markdown-it-py`.
It implements `ParserInterfaceV1` and returns only transient `ParseResult`
records in accordance with ADR-0011.

## Engineering changes

- Parses headings, paragraphs, nested lists, fenced code, tables, blockquotes,
  inline images, and soft line breaks from the Markdown token stream.
- Emits typed raw blocks with contiguous ordinals.
- Preserves fenced-code language through `code_language`.
- Preserves image alternative text through `alt_text`.
- Returns data-URI image bytes as `TransientAsset` values with detected MIME
  types; remote images create no persistent assets.
- Performs no storage, canonicalization, or persistent identity generation.
- Exports `MarkdownParser` from `mnemo.parsers`.
- Adds focused unit coverage for valid, empty, malformed, structural, image,
  metadata, and immutability cases.

## Compatibility

No public parser contract changed. The synchronized project version is
`0.10.3`. Module 3.5 has not started.
