# 0030: Code Chunker

**Date:** 2026-08-11
**Module:** Phase 4, Module 4.5
**Release:** v0.15.0
**ADR:** [ADR-0015](../adr/ADR-0015-phase-4-chunking-contract-evolution.md)

## Summary

Module 4.5 adds the built-in `DocType.CODE` strategy behind
`ChunkerInterfaceV2`. It uses pinned tree-sitter grammars to emit immutable,
source-exact declaration drafts while leaving final validation, identity, and
relationships to Module 4.1.

## Behavior

- Parses Python, JavaScript/TypeScript/TSX, Go, Rust, Java, C, and C++ with
  deterministic local AST grammars.
- Emits classes, functions, methods, nested declarations, types, and constants
  as atomic `CODE` drafts; declarations are never truncated or split mid-body.
- Preserves module docstrings and individual repository README documents as
  source-authored `SUMMARY` drafts without generated enrichment.
- Records imports, declaration kind, qualified symbol, direct calls, and
  within-document callers in immutable `chunker.code.*` metadata.
- Preserves explicit source hierarchy through earlier-only `parent_index`,
  canonical heading context, and contiguous `BlockSpan` provenance.
- Fails closed for unsupported or malformed source, oversized atomic
  declarations, and declarations indistinguishable under the frozen identity
  formula.

## Registration and downstream impact

The core built-in plugin registers `CodeChunker` only in the V2
`DocType.CODE` slot. V1 registration and the Generic, Book, and Paper strategies
remain unchanged. Module 4.6 and later strategies have not started.
