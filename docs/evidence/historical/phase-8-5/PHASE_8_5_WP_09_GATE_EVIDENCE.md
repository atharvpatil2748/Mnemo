# Phase 8.5 WP-09 Gate Evidence

## Status

WP-09 implementation is complete as an additive, generation-gated semantic
asset/evidence discovery layer. It is implemented, but runtime capabilities
remain truthfully unavailable when no compatible OCR, Vision, or shared-space
visual generation is active; behavioral certification remains WP-16/WP-17.

## Implemented

- Added occurrence-scoped `asset_metadata`, OCR-text, Vision-text, and optional
  shared visual-vector sources to the existing `AdvancedRetrievalService`.
- Reused schema-v14 projection generations, active-generation coverage,
  occurrence/catalog provenance, authorization scope, rank fusion, and
  `CursorCodecV2` through the existing `search_evidence` HTTP/MCP surface.
- Preserved original asset versus occurrence versus derivation identity.
- Added machine-facing next actions linking discovered occurrences to
  `get_asset` and `get_image_analysis`.
- Added visual query-vector validation (profile, shared space, dimensions,
  metric, finite values). Visual text-query embedding remains optional and is
  never substituted with an incompatible provider.

## Validation

- Focused multimodal-source tests: 2 passed.
- Existing advanced retrieval, runtime, multimodal, MCP-contract, and HTTP
  retrieval regressions: 83 passed across the affected focused runs.
- Ruff check on all modified production modules: passed.
- Strict mypy on affected core modules: passed.
- Capability-matrix JSON validation: passed.
- SQLite smoke check confirmed asset-catalog source and empty authorized scope
  behavior without mutating any corpus or evaluation database.

The focused pytest invocations enable the repository's global coverage gate;
their isolated subsets report low aggregate coverage by design. No full suite,
benchmark, ingestion, model call, migration, or corpus mutation was performed.

## Runtime truth and boundaries

Search sources are composed only when their active complete generation exists.
Missing/stale/failed generations are reported as unavailable coverage by the
existing retrieval envelope. Semantic image discovery is not conflated with
binary delivery or derived analysis. Multilingual activation, structured
comparison, Final-QA V2, capability discovery, external-agent certification,
and Phase 11 planning remain deferred to their assigned work packages.
