# 0036: Slides Chunker

**Date:** 2026-08-12
**Module:** Phase 4, Module 4.9
**Release:** v0.19.0
**ADRs:** ADR-0015, ADR-0036

## Summary

Module 4.9 adds the built-in V2 `SlidesChunker` for `DocType.SLIDES`. The
strategy consumes canonical schema-v1 `parser.slide.*` metadata, emits one
atomic draft per source-ordered slide, and leaves final identity and
relationships to the Module 4.1 dispatcher.

## Behavior

- Preserves title, body, speaker notes, canonical image references, and source
  `BlockSpan` provenance.
- Emits the source title slide as `SUMMARY`; other slides remain `PASSAGE`.
- Uses deterministic section-divider navigation without fabricating parents.
- Rejects malformed, reordered, disjoint, empty-text, or oversized atomic
  slide input rather than truncating or guessing.
- Registers only in the version-qualified V2 `DocType.SLIDES` slot.
