# Engineering Changelog 0023: Ingestion Canonicalization Bridge

**Release:** v0.10.8

## Summary

Phase 3, Module 3.9 implements the accepted ADR-0014 boundary between transient
parser output and the canonical `ParsedDocument` required by Phase 4.

## Engineering changes

- Added an async `IngestionPipeline` that sequences router deduplication,
  cleaning, deterministic classification, asset persistence, canonicalization,
  and canonical IR publication.
- Added a pure synchronous `DocumentCanonicalizer` covering every V1 raw block
  type and exact image-asset correlation.
- Kept permanent `Asset` identity exclusively behind
  `StorageInterfaceV1.put_asset()`.
- Made canonical publication contingent on successful asset persistence and
  canonical model validation; content-addressed assets are never deleted as
  rollback compensation.
- Preserved the existing deduplication contract by loading the current
  version's canonical document and treating a missing IR as an integrity error.

## Compatibility and dependencies

No frozen public interface or domain model changed. Module 3.9 depends only on
Phase 1 contracts and models, Phase 2 storage, and the completed Phase 3 router,
cleaner, and classifier. It introduces no Phase 4 chunking implementation.
