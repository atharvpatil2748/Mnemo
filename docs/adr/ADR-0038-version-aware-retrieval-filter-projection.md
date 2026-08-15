# ADR-0038: Version-Aware Retrieval Filter Projection

**Status:** Accepted
**Date:** 2026-08-13
**Decision owners:** Mnemo maintainers
**Scope:** Phase 6, Module 6.2
**Depends on:** ADR-0001, ADR-0002, ADR-0004
**Related evidence:** `module-6.2-dense-retriever-contradiction-report.md`, `module-6.2-retrievers-contradiction-report.md`

## Context

`MetadataFilter` is frozen and contains notebook, source, document-type, and publication-date constraints. `StorageInterfaceV1.search_dense()` accepts that model, but the v0.20.1 Qdrant payload contains only chunk-local fields. `QdrantStore` consequently could not enforce the complete filter before ANN ranking. Its attempted `doc_types` filter referenced a `doc_type` payload field that was not persisted, while notebook, source, and date fields were ignored.

The architecture deliberately retains superseded chunks. A logical-document-ID resolver is therefore insufficient: metadata from one version must never authorize a chunk from another version. Python post-filtering after Qdrant `top_k` is also incorrect because it cannot return the true top-k eligible points.

## Frozen contracts

This decision does not change `RetrieverInterfaceV1`, `StorageInterfaceV1`, `MetadataFilter`, `ScoredChunk`, or `Chunk`. No V2 interface or backend-specific public argument is introduced. `DenseRetriever` remains storage-agnostic.

## Canonical sources of truth

- `ParsedDocument.doc_type` is the version-specific canonical document type.
- `DocumentVersion.metadata.publication_date` is the version-specific canonical publication date.
- `Source` is the canonical association between one notebook and one logical document.
- `Chunk.document_id` and `Chunk.version_id` identify the exact vectorized version.

Qdrant payload metadata is derived search-index state. It is never authoritative and may be rebuilt from the canonical filesystem and SQLite stores.

## Decision

Adopt an internal, version-aware retrieval metadata projection coordinated by `CompositeStorage` and persisted with each Qdrant vector point.

At chunk persistence, `CompositeStorage` resolves the exact `DocumentVersion`, exact parsed IR, and all canonical `Source` rows before either chunk index is changed. It constructs an internal projection containing:

- version-specific `doc_type`;
- version-specific `publication_date` and its numeric ordinal used for range filtering;
- sorted, unique document-level `source_ids`;
- sorted, unique document-level `notebook_ids`.

`QdrantStore` owns serialization of that projection and translation of `MetadataFilter` into Qdrant-native pre-ranking conditions. The public storage method remains unchanged; the enriched upsert and membership refresh operations are private storage-implementation coordination methods.

### Version semantics

Document-type and date filters apply to the exact `(document_id, version_id)` carried by each chunk. They never use the current or latest logical-document version. Superseded chunks remain independently filterable.

### Date semantics

`date_after` and `date_before` are inclusive bounds on `DocumentMetadata.publication_date`, as defined by ADR-0001. The projection stores a date ordinal for exact, timezone-free date comparison. If publication date is absent and either bound is present, the point does not match because the indexed range field is absent. An absent publication date remains eligible when there is no date filter.

### Source and notebook semantics

Multiple `source_ids` are OR alternatives within that field. Multiple document types are likewise OR alternatives. Different non-empty filter fields intersect. Notebook membership and source membership remain document-level and are projected onto every indexed version of that document. Set semantics prevent duplicate vector results when several source rows match.

### Top-k and empty behavior

Qdrant applies all non-empty filter conditions before ANN ranking and `top_k` truncation. No Python post-filter or overfetch is permitted. `MetadataFilter()` uses the existing unfiltered fast path. A filter matching no projected metadata returns `()` and never falls back to an unfiltered search.

## Storage ownership and mutation propagation

`CompositeStorage` owns coordination:

1. `upsert_chunks` rebuilds exact-version projection data from canonical stores and writes chunks plus projection to Qdrant under the existing affected-key compensation boundary.
2. Source creation, movement, and deletion update SQLite first, then refresh source/notebook arrays on every Qdrant point for the affected logical documents.
3. Notebook deletion computes and writes the restrictive post-delete membership projection first, then performs the SQLite cascade. If either phase fails, projection is rebuilt from the still-authoritative canonical rows. This avoids pretending that every cascade-dependent SQLite record can be reconstructed.
4. Document cascade deletion continues to remove Qdrant points rather than retaining projection metadata for a deleted canonical document.
5. Version supersession needs no projection rewrite because both document type and publication date are immutable exact-version facts.

The accepted Source invariant `(notebook_id, document_id)` is enforced by SQLite schema migration 3. Migration refuses to proceed when pre-existing duplicate pairs exist; it never silently deletes or merges canonical rows.

A read-only audit of all eight repository-local milestone SQLite databases found
zero duplicate membership pairs before migration implementation.

## Failure and reconciliation semantics

Canonical filesystem/SQLite reads needed to construct a projection occur before chunk-index mutation. Missing or inconsistent canonical data fails explicitly.

Chunk writes retain the existing affected-key compensation model. Qdrant snapshots include derived projection payload so rollback restores both the vector/chunk and its filter metadata.

Mutable source operations synchronously update the derived index. If projection refresh fails, `CompositeStorage` compensates the canonical SQLite mutation and then rebuilds prior Qdrant membership from restored canonical rows. Notebook deletion uses an index-first restrictive projection because SQLite cascade dependents cannot be losslessly reconstructed after deletion; failure before or during the canonical delete rebuilds projection from unchanged canonical state. A failed compensation is surfaced as `StorageError` and logged as compromised consistency; it is never reported as success. Retrying the original idempotent operation performs reconciliation from canonical state.

Qdrant does not become a participant in a claimed distributed transaction. These are explicit synchronous writes with compensating recovery, consistent with the existing CompositeStorage architecture.

## Existing data and migration

Historical v0.20.1/M5 collections are not modified and remain evidence of the Phase 5 milestone. They do not contain this projection and must not be represented as filter-capable.

New or migrated production collections must be rebuilt by replaying canonical parsed documents, document versions, sources, chunks, and embeddings into a new collection. In-place payload invention is forbidden because canonical context must be re-read. Module 6.2 acceptance therefore uses a new collection.

## Performance implications

Filtered query work remains inside indexed Qdrant payload conditions and does not send large candidate-ID lists across backends. The empty-filter path performs no relational/blob lookup. Projection construction occurs on indexing writes, while mutable source/notebook operations refresh affected document points. Required payload indexes are keyword indexes for type/source/notebook and an integer index for publication-date ordinal.

## Alternatives considered

### Document-ID-only relational resolution

Rejected because version-specific metadata from one version could authorize chunks from another. Large candidate lists also create request-size and query-planning problems.

### Python post-filtering or overfetch

Rejected because filtering after ANN truncation violates true `top_k`, and unbounded overfetch is not an acceptable retrieval architecture.

### Add retrieval fields to `Chunk`

Rejected because `Chunk` is frozen and is not the canonical owner of type, publication date, or notebook/source membership.

### Make Qdrant authoritative

Rejected because projected values are derived and mutable membership must remain governed by canonical `Source` rows.

### Change public storage/retriever interfaces

Rejected because the existing contracts can express the request and CompositeStorage can coordinate the internal implementation.

## Compatibility impact

Public API compatibility is unchanged. Existing unprojected collections continue to support unfiltered dense retrieval but cannot satisfy non-empty metadata filters and require rebuild into a new collection for Module 6.2 behavior. The stale SQLite sparse-search reference to `documents.type` is not used by this design and is deferred to Module 6.3.

## Acceptance record

Accepted after focused projection/filter/version tests, 832 passing repository
tests with 90.16% coverage, formatting/lint/strict-mypy/pre-commit gates, and a
new real Bhagavad Gita/Ollama/Qdrant DenseRetriever acceptance run all passed on
2026-08-13. The new collection contains 1,000 projected real points; the
historical v0.20.1/M5 collection remains unchanged.
