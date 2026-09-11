# 0015 — DOCX Parser

## Architectural Overview
This changelog documents the completion and freeze of Phase 3 Module 3.3 (DOCX Parser). The `DOCXParser` was implemented in strict adherence to the parser boundary architecture defined in ADR-0011.

- **Parser Purity**: Maintained as a pure transformation component.
- **Data Models**: Emits only `ParseResult` (containing `RawBlock`s and `TransientAsset`s). It does *not* output `ParsedDocument`.
- **Identity & Storage**: It performs zero blob storage operations and generates zero persistent Asset IDs. Temporary images use parser-local identifiers (e.g. `image-1`).

## Implementation Details
- **Dependency**: Integrated `python-docx` for parsing.
- **Capabilities**:
  - Extracts Word Headings natively, mapping them to `RawHeadingBlock`s (H1-H6).
  - Identifies and groups consecutive list items into cohesive `RawListBlock` structures.
  - Recursively navigates `<w:tbl>` elements to extract `RawTableBlock` grids.
  - Extracts inline `ImagePart` binary data as `TransientAsset`s coupled with `RawImageBlock`s.

## Validation and Metrics
- All features validated using dynamic dummy DOCX objects without committing binary blobs to the repository.
- Unit test coverage for `DOCXParser` reached 96%.
- Repository total coverage safely maintained at >90%.
- Passed strict `mypy` type checking and `ruff` formatting/linting rules.

## Known Limitations
- Embedded objects (OLE, SmartArt) inside `.docx` are skipped.
- Some complex nested table structures might be flattened or skipped based on `python-docx` API limits.

## Future Integration
The transient `ParseResult` (including binary `TransientAsset`s) output by the `DOCXParser` requires the ingestion canonicalization bridge proposed in ADR-0014. That bridge is planned before Phase 4; it is not Module 5/6 work.
