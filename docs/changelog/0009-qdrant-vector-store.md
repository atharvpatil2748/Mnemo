# Changelog 0009: Qdrant Vector Store

## Implementation Summary
Module 2.3 integrates Qdrant as the dense vector storage backend for Mnemo, implementing the `StorageInterfaceV1` contract for vector-specific operations (`upsert_chunks`, `search_dense`, `delete_chunks_for_document`). This component forms the foundation for semantic search capabilities in the retrieval pipeline.

## Architectural Decisions
- The `qdrant-client`'s `AsyncQdrantClient` is utilized for asynchronous interactions.
- We standardized Chunk IDs to 32-character valid UUIDs (using the first 32 characters of the 64-character SHA256 chunk hash) to conform with Qdrant's `PointId` requirements.
- We leveraged Qdrant Payload for relational metadata that is heavily used in dense search filtering, including `notebook_id`, `document_id`, `version_id`, `chunk_type`, and nested payload indexing for `MetadataFilter`.
- Unsupported `StorageInterfaceV1` operations (assets, parsed documents) deliberately raise `NotImplementedError`, respecting the separation of concerns governed by the future `CompositeStorage`.
- The `search` method was replaced with `query_points` to align with the modern asynchronous API of `qdrant-client`.

## Public APIs Introduced
- `mnemo.storage.qdrant.QdrantStore`: The concrete storage implementation supporting vector operations.
- `mnemo.storage.qdrant.QdrantStorageConfig`: Typed configuration for the Qdrant backend, supporting both HTTP endpoints and `:memory:` locations for testing.

## Dependencies Added
- `qdrant-client` was already present in the workspace configuration, but this phase validates its usage and configuration.

## Testing Summary
- Coverage for `mnemo/storage/qdrant.py` meets the >90% threshold.
- Unit tests (`tests/unit/test_qdrant_store.py`) validate the full vector lifecycle, including collection initialization, chunk upsert, and vector search with payload filtering.
- MyPy types are strictly verified, ensuring seamless integration with `StorageInterfaceV1`.
- Unsupported methods correctly raise `NotImplementedError` in tests.

## Future Integration with CompositeStorage
`QdrantStore` will be orchestrated by `CompositeStorage` in Module 2.5, which will map vector-specific operations to Qdrant while deferring blob storage to the Filesystem Store and relational metadata/sparse search to SQLite.

## Known Intentional Limitations
- No support for non-vector methods (`put_asset`, `get_asset`, etc.).
- Qdrant's ID constraints prevent raw 64-character hex strings, necessitating our deterministic slicing to a 32-character UUID representation.

## Downstream Modules Affected
- **Module 2.5 (Composite Storage):** Must properly orchestrate requests to avoid relying on `QdrantStore` for non-vector tasks.
- **Module 6.2 (Dense Retriever):** Will rely on `QdrantStore.search_dense` for semantic similarity search.
