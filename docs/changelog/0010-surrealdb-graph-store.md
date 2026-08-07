# Changelog: Module 2.4 - SurrealDB Graph Store

## Module Overview
Implementation of the `SurrealDBStore` to satisfy graph storage operations as defined in `StorageInterfaceV1`.

## Changes Made
- Added `surrealdb` client dependency to `mnemo-core/pyproject.toml`.
- Added `SurrealDBStorageConfig` to `mnemo-core/mnemo/config.py`.
- Updated `Entity` and `GraphEdge` in `mnemo-core/mnemo/models/graph.py` to use UUID-based canonical identification for vertices.
- Authored ADR-0005 to document the shift from String-based graph identification to UUID-based graph identification.
- Updated ADR-0001 and ADR-0002 to match the new models.
- Implemented `SurrealDBStore` inside `mnemo-core/mnemo/storage/surrealdb.py` to handle the graph queries using `RELATE`, `SELECT`, etc.
- Added comprehensive unit tests in `mnemo-core/tests/unit/test_surrealdb_store.py` with an in-memory test double to stub out the SurrealDB client (since the test suite requires no external DB connections during unit tests).
- Passed type checking, formatting, and tests.

## Architectural Alignment
The implementation conforms precisely to the Phase 2 requirements for graph storage. No architectural deviations occurred other than standardizing graph identifiers to UUIDs (documented in ADR-0005).
