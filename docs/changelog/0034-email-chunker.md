# 0034: Email Chunker

**Date:** 2026-08-11
**Module:** Phase 4, Module 4.7
**Version:** `0.18.0`
**ADRs:** [ADR-0015](../adr/ADR-0015-phase-4-chunking-contract-evolution.md), [ADR-0016](../adr/ADR-0016-email-ingestion-semantic-boundary.md)

## Summary

Adds the built-in V2 `EmailChunker` for `DocType.EMAIL`. The strategy consumes
only canonical schema-v1 `parser.email.*` metadata, partitions source thread
components, preserves message regions and attachment correlation, and emits
immutable provenance-bearing `ChunkDraft` values.

## Behavior

- Validates the complete ADR-0016 document, message, attachment, reply, and
  block-correlation schema before producing output.
- Keeps different messages, thread components, body formats, quoted regions,
  and signatures at deterministic semantic boundaries.
- Expresses verified same-document reply relationships through earlier-only
  `parent_index` values; final IDs and sibling relationships remain dispatcher
  responsibilities.
- Splits prose locally at paragraph, sentence, then safe word boundaries using
  the supplied canonical token counter. Inline-image captions remain atomic.
- Performs no source reparsing, network, filesystem, storage, UUID, LLM,
  embedding, retrieval, or indexing work.

Module 4.8 is not included.
