# ADR-0012: Document Cleaner Boundary

**Status:** Accepted
**Date:** 2026-08-08
**Scope:** Phase 3
**Related documents:** ADR-0001, ADR-0011

## Context

The Engineering Roadmap and ADR-0011 originally specified the `DocumentCleaner` to operate on `ParsedDocument` (after the Document Canonicalizer). However, this created a logical inconsistency: cleaning operations (like duplicate whitespace removal, Unicode normalization, and hyphenated line break fixes) are fundamentally data normalization tasks on raw text. 

Operating on `ParsedDocument` would require the Cleaner to mutate or recreate immutable domain models, and would run *after* Blob Persistence and Asset ID generation, which should ideally process clean data. 

## Decision

We move the Cleaner boundary to operate exclusively on `ParseResult` before Canonicalization.

1. **Cleaner Signature:** The Cleaner behaves as a pure function: `ParseResult -> ParseResult`. 
2. **Immutability:** It does not mutate existing `RawBlock`s; it returns a new immutable `ParseResult` with new `RawBlock` instances.
3. **No Domain Leaks:** It does not create or interact with `ParsedDocument` or permanent `Asset` IDs.
4. **Pipeline Order Update:** The new ingestion pipeline is:
   ```text
   Parser
     ↓
   ParseResult
     ↓
   Cleaner
     ↓
   Cleaned ParseResult
     ↓
   Document Classifier
     ↓
   Module 3.9 Ingestion Pipeline (Blob Persistence and Asset Resolution)
     ↓
   Document Canonicalizer
     ↓
   ParsedDocument
     ↓
   Chunker
   ```

## Consequences

- **Pure Transformation:** The Cleaner remains a pure, side-effect-free component.
- **Architectural Clarity:** All text noise is removed before the domain model (`ParsedDocument`) and permanent blobs are created.
- **Testing:** The Cleaner can be tested entirely in isolation using mock `ParseResult` objects, without needing storage layer mocks.
