# ADR-0059: Original Document Assets and Occurrence Provenance

- **Status:** Accepted
- **Implementation:** Implemented and tested in Phase 8.5.1–8.5.2
- **Date:** 2026-08-24
- **Extends:** ADR-0001, ADR-0008, ADR-0011, ADR-0014
- **Supersedes:** Nothing

## Context

Mnemo already has immutable content-addressed `Asset` bytes and parser-level
image blocks, but it does not retain every uploaded original as a
version-addressable asset or model repeated image locations independently.

## Problem

Reparse, visual evidence, exact page/slide attribution, and authorized binary
delivery require a durable separation between bytes, occurrence, and derived
interpretation.

## Decision

Reuse canonical `Asset`. Add three records:

- `DocumentBinaryReference(document_id, version_id, asset_id, role, media_type,
  byte_size)` for the immutable uploaded original;
- `AssetOccurrence(occurrence_id, asset_id, document_id, version_id,
  container_kind, locator, authored_alt_text, extraction_provenance)`;
- `AssetDerivation(derivation_id, occurrence_id, operation, provider_identity,
  model_identity, config_digest, output_asset_or_payload, status, confidence,
  language, timestamps)`.

Asset identity remains its verified content hash/UUID contract. One byte object
may have many authorized occurrences. Locators are typed page, slide, section,
sheet/cell, DOM, or standalone positions and retain ordering and geometry when
known. Original bytes are authoritative; OCR, VLM, translations, thumbnails,
and embeddings are derived and never overwrite them.

New ingestion retains originals by default, subject to explicit deployment
retention policy. Historical versions without bytes report `UNAVAILABLE`; they
are never fabricated from chunks. Exact-byte re-supply may attach only after
hash and version authorization validation.

## Alternatives

- Put occurrence data on `Asset`: rejected because deduplicated bytes can occur
  in multiple places.
- Inject image descriptions into `Chunk.text`: rejected because it corrupts
  canonical textual evidence.
- Depend on source paths: rejected because paths are mutable and nonportable.

## Consequences

Storage grows, but reprocessing becomes reproducible and provenance becomes
explicit. Shared hashes improve deduplication without granting shared access.

## Compatibility

Existing `Asset`, `ImageBlock`, document/version/chunk identities, and parser
V1 behavior remain valid. New records are additive.

## Migration

Create additive catalog tables. Existing parser assets may be backfilled only
when exact provenance is already available. Original bytes require exact
re-supply; no Golden Corpus re-ingestion is implied by schema migration.

## Security implications

Authorization follows an occurrence-to-version-to-notebook path, never bare
asset possession. MIME sniffing, hash verification, size/pixel limits, and
safe download headers are mandatory.

## Testing requirements

Test repeated/shared assets, exact hashes, locator round trips, missing bytes,
cross-notebook denial, malformed media, migration rollback, and garbage
collection with live references.

## Observability

Record byte counts, dedup hits, extraction outcomes, and typed omissions; never
log bytes or sensitive locators.

## Rollback/recovery

Disable catalog reads and retain additive rows/blobs for a controlled cleanup.
Canonical Phase 0–8 records remain untouched.

## Future-phase impact

Phase 9 gains original/derived viewers; Phase 12 providers consume occurrence
and derivation contracts rather than parser internals.

## Explicit non-goals

This ADR does not perform OCR/VLM, define UI layout, or authorize cloud egress.
