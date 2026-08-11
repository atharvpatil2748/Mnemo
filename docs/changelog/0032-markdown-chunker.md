# 0032: Markdown Chunker

**Date:** 2026-08-11
**Module:** Phase 4, Module 4.6
**Release:** v0.16.0
**ADR:** [ADR-0015](../adr/ADR-0015-phase-4-chunking-contract-evolution.md)

## Summary

Module 4.6 adds the built-in `DocType.MARKDOWN` strategy behind
`ChunkerInterfaceV2`. It consumes the immutable `parser.markdown.*` metadata
preserved by the Phase 3 boundary correction and emits deterministic
provenance-bearing drafts without reparsing source bytes.

## Behavior

- Builds deterministic heading paths and semantic sections from canonical
  heading levels; thematic breaks are hard boundaries.
- Emits paragraph passages using safe sentence/word fallback while leaving
  short-leaf filtering and final validation to the dispatcher.
- Preserves fenced code as atomic `CODE` drafts with language metadata.
- Preserves exact Markdown table and list source, structured table rows, list
  type/nesting, blockquote identity, and internal-link metadata.
- Keeps tables, lists, blockquotes, and code atomic and fails closed when an
  atomic construct exceeds the effective maximum.
- Emits only immutable root drafts with contiguous `BlockSpan` provenance;
  canonical IDs and relationships remain owned by Module 4.1.

## Registration and downstream impact

The core built-in plugin registers `MarkdownChunker` only in the V2
`DocType.MARKDOWN` slot. V1 behavior and Modules 4.1–4.5 remain unchanged.
Module 4.7 and later strategies have not started.
