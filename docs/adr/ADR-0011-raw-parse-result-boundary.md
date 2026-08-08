# ADR-0011: Raw Parse Result Boundary

**Status:** Accepted
**Date:** 2026-08-08
**Scope:** Phase 3
**Related documents:** ADR-0001, ADR-0002

## Context

During Phase 3 Module 3.2 (PDF Parser), we discovered a fundamental inconsistency in `ParserInterfaceV1` (ADR-0002). The interface required parsers to return a canonical `ParsedDocument`, which requires every extracted image to be represented as an `ImageBlock` with a mandatory permanent `asset_id: UUID` (ADR-0001). 

However, parsers must remain pure transformation components without side effects. A pure parser performs ZERO storage, ZERO BlobStore interaction, and generates ZERO permanent asset identities. A pure parser cannot persist blobs to generate permanent Asset IDs, nor should it mint temporary fake UUIDs that leak into the canonical domain model.

## Decision

We redesign the parser boundary to cleanly separate pure parsing from asset persistence and document canonicalization.

### 1. Transient Transport Models
The parser must NOT produce canonical domain models (`ParsedDocument` or `Block`). It produces parser transport models only. These transient objects are NEVER persisted, NEVER leave the ingestion pipeline, NEVER appear in public APIs outside parsing, and are NOT domain models.

We introduce the following transient hierarchy:

- `ParseResult`
- `RawBlock` (base)
  - `RawTextBlock`
  - `RawHeadingBlock`
  - `RawListBlock`
  - `RawTableBlock`
  - `RawCodeBlock`
  - `RawMathBlock`
  - `RawImageBlock`
- `TransientAsset`

`TransientAsset` contains raw bytes, MIME type, page number, and a parser-local identifier. `RawImageBlock` references this local identifier rather than a UUID.

### 2. The Ingestion Pipeline

The ingestion orchestration layer replaces "Phase 5/6" logic and becomes the exclusive owner of blob persistence and asset ID generation. The flow is:

```
bytes
  ↓
Parser
  ↓
ParseResult
  ↓
Blob Persistence
  ↓
Asset Resolution
  ↓
Document Canonicalizer
  ↓
ParsedDocument
  ↓
Cleaner
  ↓
Chunker
```

### 3. DocumentCanonicalizer

We introduce a new internal component: `DocumentCanonicalizer`. Its ONLY responsibility is converting `ParseResult` into a canonical `ParsedDocument`. 

It performs:
- Blob persistence coordination (resolving `TransientAsset` into `Asset`)
- Asset ID assignment
- Replacing `RawImageBlock` with `ImageBlock`
- Replacing all other `RawBlock` instances with their canonical `Block` counterparts
- Constructing the final `ParsedDocument`
- Validating canonical invariants

## Consequences

- **Domain Model Purity:** `ParsedDocument` and `ImageBlock` remain completely unchanged and canonical. `asset_id` remains a mandatory `UUID`.
- **Parser Purity:** Parsers remain 100% pure, side-effect free, and synchronous. They generate ZERO permanent identity and perform ZERO storage.
- **Clear Orchestration Boundaries:** Blob persistence and Asset ID generation belong exclusively to the ingestion orchestration layer.
