# ADR-0006: Document Deduplication Gate

- **Status:** Accepted
- **Date:** 2026-08-08
- **Decision owners:** Mnemo maintainers
- **Scope:** Phase 3, Module 3.1
- **Depends on:** ADR-0002
- **Related documents:** `mnemo_architecture_v2.md`, `mnemo_engineering_roadmap.md`

## 1. Context

During the design of the Parser Router (Module 3.1), the architecture required a deduplication gate: "Compute SHA-256 before parsing and return the existing document if the content already exists."

The existing `StorageInterfaceV1` provided `contains_hash(content_hash: str) -> bool`, which was insufficient because the parser router must return the stable `Document` identity to subsequent phases. A boolean result forces either a linear scan of the entire document registry to find the matching hash, or forces the ingestion pipeline to lose the canonical `document_id` for deduplicated assets.

## 2. Decision

We will evolve the storage contract to explicitly support document retrieval by content hash.

1. **New Interface Method**: We will add `get_document_by_content_hash(content_hash: str) -> Document | None` to `StorageInterfaceV1`.
2. **Return Immutable Domain Model**: We return the full `Document` domain model rather than just the UUID to avoid an immediate second lookup and to maintain consistency with the domain-driven architecture.
3. **Delegation**: `CompositeStorage` will expose this public API. The lookup is delegated to the metadata backend responsible for document registry ownership in the current implementation.
4. **Backend Ownership**: This avoids coupling the public architecture to today's storage implementation. The other stores (filesystem, vector, graph) will stub this method.


## 3. Consequences

- **Positive**: The Parser Router can natively enforce deduplication and return the correct `Document` object instantly.
- **Positive**: Prevents an O(N) linear scan over all ingested documents.
- **Positive**: Retains architecture intent and prepares for future versioning, notebooks, indexing, citations, sessions, and retrieval tasks.
- **Negative**: Requires modifying `StorageInterfaceV1` and updating all 4 storage backends.

## 4. Updates

- `mnemo-core/mnemo/interfaces/storage.py`: Add `get_document_by_content_hash`.
- Backend classes: Implement or stub `get_document_by_content_hash`.
