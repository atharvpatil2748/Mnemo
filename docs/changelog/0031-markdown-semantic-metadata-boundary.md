# 0031: Markdown Semantic Metadata Boundary Correction

**Date:** 2026-08-11
**Scope:** Phase 3.4 boundary correction required by Phase 4, Module 4.6
**Version:** No version change (`v0.15.0` development baseline)
**ADRs:** [ADR-0011](../adr/ADR-0011-raw-parse-result-boundary.md), [ADR-0014](../adr/ADR-0014-ingestion-canonicalization-bridge.md)

## Summary

The Markdown parser previously used an AST but discarded Markdown semantics
before canonical `ParsedDocument` construction. Heading and code types survived,
but internal links, list nesting/type, blockquote identity, thematic breaks,
inline source, and original table Markdown did not. Module 4.6 could not satisfy
Architecture §10.5 without reconstructing or inventing information.

## Correction

- Added deterministic immutable `parser.markdown.*` metadata to existing raw
  blocks; no public model or interface was added.
- Retained `parser.markdown.block_type` as an exact compatibility alias for the
  frozen Book strategy pending the planned end-of-Phase-4 terminology audit.
- Preserved exact source-line slices for source-bearing blocks, resolved
  internal-link records, structured list nesting/type, and explicit block kind.
- Preserved thematic breaks as typed-by-metadata raw text boundary records.
- Confirmed the cleaner carries metadata unchanged and the canonicalizer copies
  it without taking ownership of Markdown interpretation.
- Kept AST/token objects, storage, network access, UUID generation, and source
  reparsing outside the boundary.

Module 4.6 remains unimplemented. Modules 4.1–4.5 and ADR-0015 are unchanged.
