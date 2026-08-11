# 0027: Generic Chunker

**Date:** 2026-08-11
**Module:** Phase 4, Module 4.2
**Release:** v0.12.0
**ADR:** [ADR-0015](../adr/ADR-0015-phase-4-chunking-contract-evolution.md)

## Summary

Module 4.2 adds the built-in `DocType.GENERIC` strategy behind
`ChunkerInterfaceV2`. It emits immutable provenance-bearing `ChunkDraft`
values and delegates final validation, short-leaf filtering, identity, and
relationships to Module 4.1.

## Behavior

- Preserves real heading context and never crosses heading-defined sections.
- Prefers block and paragraph boundaries, then sentence boundaries, then safe
  word boundaries for oversized generic prose.
- Combines only contiguous canonical block provenance.
- Keeps tables and equations atomic and fails closed when they exceed the
  effective maximum.
- Uses only the supplied canonical `TokenCounterInterfaceV1` and performs no
  storage, network, UUID, embedding, retrieval, indexing, or LLM work.

## Registration and downstream impact

The core built-in plugin registers `GenericChunker` only in the V2
`DocType.GENERIC` slot. V1 registration remains unchanged. Modules 4.3-4.10
will add specialized strategies without changing this generic fallback's
ownership.
