# 0028: Book Chunker

**Date:** 2026-08-11
**Module:** Phase 4, Module 4.3
**Release:** v0.13.0
**ADR:** [ADR-0015](../adr/ADR-0015-phase-4-chunking-contract-evolution.md)

## Summary

Module 4.3 adds the built-in `DocType.BOOK` strategy behind
`ChunkerInterfaceV2`. It emits immutable, source-derived book drafts while
leaving final validation, identity, and relationship materialization to the
Module 4.1 dispatcher.

## Behavior

- Detects structurally supported tables of contents, extracts their hierarchy,
  and excludes only the identified ToC region from retrieval drafts.
- Falls back to deterministic canonical heading levels and common book
  numbering patterns when no usable ToC exists.
- Preserves title, part, chapter, section, and subsection context in
  `heading_path`, and never merges content across a chapter boundary.
- Emits source-authored `SUMMARY` and metadata-identified `VERBATIM` roles;
  ordinary narrative remains `PASSAGE`, with canonical special-block roles
  preserved.
- Uses only the supplied canonical token counter, contiguous `BlockSpan`
  provenance, and local deterministic paragraph/sentence/word boundaries.

## Registration and downstream impact

The core built-in plugin registers `BookChunker` only in the V2 `DocType.BOOK`
slot. V1 registration and the Generic strategy remain unchanged. Module 4.4
and later strategies have not started.
