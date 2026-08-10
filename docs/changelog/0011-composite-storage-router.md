# Changelog 0011: Composite Storage Router

## Summary

Phase 2, Module 2.5 completes the storage subsystem with `CompositeStorage`,
the single `StorageInterfaceV1` facade over the filesystem, SQLite, Qdrant, and
SurrealDB adapters. `KnowledgeEngine` now registers this facade as the built-in
`primary` storage provider without opening external resources during runtime
composition.

## Engineering changes

- Routed blobs and parsed documents to `FilesystemBlobStore`.
- Routed metadata, notebooks, conversations, citations, chunks, and sparse
  search to `SQLiteStore`.
- Routed dense vector indexing and search to `QdrantStore`.
- Routed entity and graph operations to `SurrealDBStore`.
- Coordinated chunk writes across SQLite and Qdrant with reverse-order
  compensation on partial failure. A later correctness correction replaced the
  original document-wide delete compensation with exact affected-key snapshot
  restoration so failed replacements preserve pre-existing chunks.
- Rejected mixed-document or mixed-version chunk batches so rollback scope is
  deterministic.
- Surfaced compensation failures as typed `StorageError` results.
- Added facade lifecycle, capability aggregation, routing, failure, cascade,
  and rollback tests.
- Exported `CompositeStorage` and all four concrete storage adapters from
  `mnemo.storage`.
- Advanced the synchronized project version to `0.9.0`.

## Compatibility and dependencies

No public Phase 1 contract changed. `CompositeStorage` implements the existing
`StorageInterfaceV1`; backend-specific clients remain hidden behind the facade.
Phases 3 and later may depend on the `primary` storage slot without importing a
concrete database or filesystem adapter.

## Milestone

Phase 2 and milestone M2 are complete. Phase 3 has not started.
