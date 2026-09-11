# ADR-0013: Document Classifier Boundary and LLM Deferral

**Status:** Accepted
**Date:** 2026-08-08
**Scope:** Phase 3
**Related documents:** ADR-0001, ADR-0011, ADR-0012, ADR-0014, ADR-0017, ADR-0036, ADR-0037

## Context

The Engineering Roadmap defined Module 3.8 as the Document Classifier, responsible for determining the `DocType` of an ingested document for chunker selection. The roadmap specified two subtasks:
1. Rule-based classification (DocType from extension, heading patterns, structure).
2. LLM-assisted classification (fallback for ambiguous cases, using an Extractor LLM).

However, ADR-0011 strictly established that Phase 3 components (Parsers, Cleaners) are 100% pure, synchronous, side-effect-free transformations. Implementing an LLM call inside a Phase 3 component introduces network I/O, violating this purity constraint. Furthermore, the updated ingestion pipeline omitted the classification stage entirely.

## Decision

To resolve the architectural contradiction and maintain domain purity, we make the following decisions:

### 1. Pure Classifier Boundary
Module 3.8 (`DocumentClassifier`) is implemented as a pure, synchronous, deterministic component. It holds two deterministic responsibilities over the `ParseResult -> ParseResult` transformation:
1. Deterministic `DocType` classification.
2. Deterministic, type-specific semantic annotation when `DocType.RESUME`,
   `DocType.SLIDES`, or `DocType.DOCUMENTATION` is detected, as defined by
   ADR-0017, ADR-0036, and ADR-0037.

It uses ONLY information already present in the `ParseResult` (and optionally the filename) to perform rule-based classification (checking file extensions, heading text, block structure). It updates `ParseResult.doc_type` (and when applicable, semantic boundaries for Resume) and returns a new immutable `ParseResult`, preserving all other data.

These annotations use immutable namespaced `parser.resume.*`, `parser.slide.*`,
and `parser.documentation.*` metadata. The classifier does not parse original
source bytes, allocate permanent identities, or perform I/O. Parser-owned
Markdown and Email metadata remains parser-owned and is not reinterpreted.

### 2. Deferral of LLM Classification
The LLM-assisted classification fallback is explicitly removed from Module 3.8.
Module 3.9 performs no LLM call. A later ingestion enhancement may add the
optional fallback at the location reserved by ADR-0014.

### 3. Pipeline Order Update
The formal Phase 3 ingestion pipeline is updated to:
```text
Parser
  ↓
ParseResult
  ↓
DocumentCleaner
  ↓
Cleaned ParseResult
  ↓
DocumentClassifier
  ↓
Classified ParseResult
  ↓
Module 3.9 Ingestion Pipeline (No LLM in V1)
  ↓
Blob Persistence
  ↓
DocumentCanonicalizer
  ↓
ParsedDocument
  ↓
ChunkingContext + ChunkerInterfaceV2 (ADR-0015)
```

## Consequences

- **Purity Maintained**: Parsers, the cleaner, the classifier, and the
  canonicalizer remain free of storage and network I/O. Module 3.9 isolates the
  required storage I/O in `IngestionPipeline`.
- **Testability**: The `DocumentClassifier` can be tested instantly and deterministically using mock `ParseResult` objects.
- **Graceful Degradation**: Documents that cannot be classified by rules fall back to `DocType.GENERIC`, waiting for future orchestration layers to optionally enhance them via an LLM.
