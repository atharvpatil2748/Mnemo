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

`TransientAsset` contains raw bytes, MIME type, page number, and a deterministic parser-local identifier (e.g. `block-1`, `page1-image1`). This identifier is ONLY a temporary correlation key between a `RawImageBlock` and a `TransientAsset` within a single `ParseResult`. It is NEVER persisted, NEVER exposed outside of `ParseResult`, and NEVER treated as a permanent Asset ID. `RawImageBlock` references this deterministic local identifier rather than a UUID.

### 2. The Ingestion Pipeline

The ingestion orchestration layer replaces "Phase 5/6" logic and becomes the exclusive owner of blob persistence and asset ID generation. The flow is:

```
bytes
  ↓
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
Blob Persistence
  ↓
Asset Resolution
  ↓
Document Canonicalizer
  ↓
ParsedDocument
  ↓
ChunkingContext + ChunkerInterfaceV2 (ADR-0015)
```

### 3. DocumentCanonicalizer

We introduce a new internal component: `DocumentCanonicalizer`. Its ONLY
responsibility is converting a `ParseResult` with an already-resolved immutable
asset map into a canonical `ParsedDocument`.

It performs:
- Replacing `RawImageBlock` with `ImageBlock`
- Replacing all other `RawBlock` instances with their canonical `Block` counterparts
- Constructing the final `ParsedDocument`
- Validating canonical invariants

ADR-0014 supersedes the earlier assignment of blob persistence coordination and
asset ID assignment to this component. The Module 3.9 `IngestionPipeline` owns
that sequencing and calls `StorageInterfaceV1`; permanent identity remains
owned by storage. `DocumentCanonicalizer` is pure, synchronous, deterministic,
and performs no I/O or identity generation.

## Consequences

- **Domain Model Purity:** `ParsedDocument` and `ImageBlock` remain completely unchanged and canonical. `asset_id` remains a mandatory `UUID`.
- **Parser Purity:** Parsers remain 100% pure, side-effect free, and synchronous. They generate ZERO permanent identity and perform ZERO storage.
- **Clear Orchestration Boundaries:** `IngestionPipeline` coordinates blob
  persistence exclusively through `StorageInterfaceV1`; storage alone creates
  permanent Asset identities.
