# ADR-0061: OCR and Derived Text Representations

- **Status:** Accepted
- **Implementation:** Complete — Phase 8.5.4 (provider-neutral contract,
  governed operation, immutable OCR projections, schema v9)
- **Date:** 2026-08-24
- **Extends:** ADR-0008, ADR-0059, ADR-0060
- **Supersedes:** Nothing

## Context

Current parsers preserve some image bytes but provide no built-in OCR and
cannot recover text from scanned/image-only pages.

## Problem

OCR must make visual text searchable while preserving the original asset,
language uncertainty, geometry, provider provenance, and failure semantics.

## Decision

Add `OCRProviderV1` with typed request/result contracts. Requests identify an
authorized occurrence or bounded page rendering, requested languages, provider
profile, resource budgets, and cancellation. Results contain ordered text
regions, bounding geometry, confidence, language/script observations, provider
and model revision, config digest, and partial/failure status.

OCR runs only as an ADR-0060 job. Scanned-page detection is a deterministic,
versioned heuristic that schedules eligible work but never declares text
absence as certainty. OCR text enters a separate derived sparse/vector
projection linked to occurrence and derivation IDs; it never mutates parser
IR, `Chunk.text`, or original language. Search results label OCR evidence.

## Alternatives

- Mandatory OCR inside parsers: rejected due to cost and non-determinism.
- Replace canonical text with OCR: rejected due to provenance loss.
- Store only a page transcript: rejected because region-level citations need
  geometry.

## Consequences

Scanned content becomes discoverable with explicit confidence and provenance.
Partial page results and language errors remain visible.

## Compatibility

Parser V1, existing image blocks, chunks, indexes, and citations are unchanged.
OCR evidence is consumed only by V2 retrieval/context contracts.

## Migration

Add derivation and OCR-region projections. Existing assets are processed only
through explicit jobs; no automatic cloud calls or corpus rebuild.

## Security implications

Workers enforce decoded-pixel/time/memory limits, sandbox unsafe decoders, and
treat recognized instructions as untrusted document content.

## Testing requirements

Test English/Hindi/Marathi scripts, mixed scripts, geometry, low confidence,
partial pages, cancellation, retry, cache invalidation, bombs, and prompt
injection text.

## Observability

Record pages/regions, latency, resource use, language confidence, and failure
classes without recognized text.

## Rollback/recovery

Disable OCR providers/index aliases. Original assets and Phase 0–8 text remain
available; incomplete derivations remain non-publishable.

## Future-phase impact

Phase 9 can display searchable overlays; Phase 11 may reason over OCR evidence
only through typed provenance.

## Explicit non-goals

This ADR does not guarantee handwriting recognition or select a provider/model.
