# 0026: Chunker Dispatcher and Phase 4 Contract Infrastructure

**Date:** 2026-08-11
**Module:** Phase 4, Module 4.1
**Release:** v0.11.0
**ADR:** [ADR-0015](../adr/ADR-0015-phase-4-chunking-contract-evolution.md)

## Summary

Module 4.1 establishes the deterministic boundary between semantic chunking
strategies and persisted canonical chunks. It does not implement a semantic
strategy; Modules 4.2–4.10 remain future work.

## Public contract changes

- Added immutable `BlockSpan`, `ChunkDraft`, and `ChunkingContext` records.
- Added required persisted `Chunk.source_span` provenance.
- Added `ChunkerInterfaceV2` and `TokenCounterInterfaceV1` while retaining V1
  aliases and methods during their compatibility window.
- Added version-isolated V2 chunker registration and resolution.

## Runtime and persistence

- Added dispatcher validation, short-leaf filtering, canonical identity,
  parent links, and symmetric sibling links.
- Added SQLite migration and Qdrant payload support for `source_span`.
- Added the offline `tiktoken==0.13.0` adapter and explicit user-side
  provisioner. Mnemo artifacts contain no tokenizer asset.

## Downstream impact

Semantic strategies emit ordered `ChunkDraft` values. Phase 5 consumes final
chunks without changing identity, and Phase 6 ParentRetriever uses the stored
parent/sibling graph. Atomic full-version rechunk replacement remains later
indexing/storage work as specified by ADR-0015.
