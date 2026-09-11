# Phase 8.5.10 — Delivery contracts

## Added

- A shared `DocumentExpansionServiceV1` and bounded delivery models for exact
  document versions, canonical chunks, original bytes, asset occurrences,
  OCR/vision derivations, and immutable Final-QA V2 evidence snapshots.
- Signed, scope-bound continuation cursors and explicit completeness/usage
  metadata.
- Additive `/v2` capability, document, chunk, asset, analysis, and Final-QA
  evidence routes with typed error mapping and bounded binary streaming.
- Four additive MCP tools (`get_document`, `get_document_chunk`, `get_asset`,
  `get_image_analysis`) plus capability-resource discovery. The original six
  tools remain unchanged.

## Security and compatibility

- Delivery reauthorizes notebook/source/document/version/occurrence scope and
  validates stored byte length, MIME metadata, and SHA-256 identity.
- Binary responses expose no filesystem path, use safe headers, and enforce
  configuration-driven byte/item ceilings.
- Phase 0–8 V1 HTTP, retrieval, Final-QA, MCP, canonical chunks, and optional
  Qdrant behavior are unchanged. No schema migration was required.

## Validation

- Full suite: 1,652 passed, 1 skipped; 90.05% coverage.
- Ruff format/check, strict mypy, all three package builds, and diff checking
  passed.
