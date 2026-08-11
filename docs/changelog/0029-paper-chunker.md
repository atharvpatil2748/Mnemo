# 0029: Paper Chunker

**Date:** 2026-08-11
**Module:** Phase 4, Module 4.4
**Release:** v0.14.0
**ADR:** [ADR-0015](../adr/ADR-0015-phase-4-chunking-contract-evolution.md)

## Summary

Module 4.4 adds the built-in `DocType.PAPER` strategy behind
`ChunkerInterfaceV2`. It emits immutable canonical-section drafts while
leaving final validation, identity, and relationships to Module 4.1.

## Behavior

- Recognizes standard, alternative, numbered, nested, and incomplete research
  paper section structures from canonical headings.
- Preserves a source-authored Abstract as one exact atomic `PASSAGE` and fails
  closed if that atomic unit exceeds the effective maximum.
- Excludes References/Bibliography content from retrieval drafts while leaving
  the immutable source document and parser metadata intact.
- Preserves source LaTeX as atomic `EQUATION` drafts without rewriting or
  generated descriptions.
- Keeps prose within semantic sections and splits only by deterministic
  paragraph, sentence, and safe word boundaries.
- Preserves tables, code, captions, image alternatives, heading context, and
  contiguous `BlockSpan` provenance using existing frozen chunk types.

## Registration and downstream impact

The core built-in plugin registers `PaperChunker` only in the V2
`DocType.PAPER` slot. V1 registration, GenericChunker, and BookChunker remain
unchanged. Module 4.5 and later strategies have not started.
