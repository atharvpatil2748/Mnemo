# Module 6.2 DenseRetriever Contradiction Report

## Status

**BLOCKED — Module 6.2 is incomplete.**

The thin `DenseRetriever` implementation and its focused unit tests were completed, but the real Qdrant/golden-dataset acceptance path exposed a storage-schema contradiction at the mandatory architecture stop gate. No frozen interface was changed, the roadmap was not marked complete, and no workaround was implemented.

The earlier ParentRetriever contradiction remains recorded in `docs/module-6.2-retrievers-contradiction-report.md` and remains deferred to Module 6.4.

## Required contract

Module 6.2 must pass the existing `MetadataFilter` to `StorageInterfaceV1.search_dense()` and obtain results that honor all requested constraints:

- `notebook_id`
- `doc_types`
- `date_after`
- `date_before`
- `source_ids`

The approved scope explicitly forbids ignoring filters or retrieving an arbitrarily large unfiltered result set and filtering it in `DenseRetriever`. `DenseRetriever` must also remain isolated from Qdrant and other concrete storage implementations.

## Confirmed implementation conflict

The public call shape is sufficient: `StorageInterfaceV1.search_dense(embedding, filters, top_k)` accepts the canonical filter. The concrete dense-storage path cannot currently honor that filter:

1. `CompositeStorage.search_dense()` delegates directly to `QdrantStore.search_dense()` and does not resolve notebook, source, document-type, or date constraints through its relational store.
2. `QdrantStore.search_dense()` translates only `filters.doc_types`, using the Qdrant payload key `doc_type`.
3. `QdrantStore._chunk_payload()` does not persist `doc_type`.
4. The Qdrant payload also has no canonical fields for `notebook_id`, `source_ids`, `date_after`, or `date_before`.
5. Consequently, notebook/source/date constraints are silently ignored, while a document-type constraint targets a payload field that is absent from persisted points.

This is not a `DenseRetriever` input-validation problem. Fixing it within the retriever would require direct access to concrete storage backends, Python-side post-filtering, or a change to the frozen retrieval/storage boundary—all prohibited by the approved Module 6.2 scope.

## Real M5 collection evidence

The contradiction was checked against the existing verified Phase 5 service and data rather than inferred only from unit code:

- Qdrant endpoint: repository-configured local service (`127.0.0.1:6333`)
- Collection: `mnemo_m5_gita_20260813t060713393050z`
- Collection point count: 1,000
- Vector size: 768
- Expected golden document ID: `d8ef0c53-8596-5b6d-b250-da5d91d3a20c`

A read-only inspection of a real persisted point showed the canonical chunk payload (including `document_id`, `version_id`, `chunk_type`, source span, heading path, relationships, and metadata), but no `doc_type`, `notebook_id`, `source_id`/`source_ids`, or canonical date field usable by `MetadataFilter`.

No point, payload, collection, dataset, or service state was modified during this inspection.

## Consequences

- A filtered dense query cannot be proven to respect notebook/source/date isolation.
- Silently ignoring those fields risks returning results outside the requested scope.
- A `doc_types` filter can produce false negatives because persisted points lack the field queried by `QdrantStore`.
- `top_k` correctness cannot be recovered by bounded post-filtering after an unfiltered vector search.
- The required real Qdrant/golden-dataset filtered acceptance test cannot truthfully pass.

## Affected architecture

The contradiction spans existing persistence and routing decisions:

- `MetadataFilter` is frozen and describes relational as well as document constraints.
- `StorageInterfaceV1.search_dense()` is frozen and accepts that filter.
- `Chunk` is frozen and does not carry `Document.doc_type`, notebook membership, or source membership as canonical fields.
- Qdrant point payloads are produced only from `Chunk`.
- `CompositeStorage` owns both the relational and vector stores but currently performs no dense-filter resolution before Qdrant search.

The raw-score contract is not involved in the conflict. The partial `DenseRetriever` preserves backend scores without normalization and preserves backend order and canonical chunk identity.

## Resolution options requiring approval

### A. Index-time filter projection and reindexing

Define an approved denormalized retrieval-filter payload derived from `Document` and `Source` relationships at indexing time. Persist the required document type, date, source, and notebook values with each vector point, then translate every canonical `MetadataFilter` field into Qdrant filters.

This requires a defined indexing context or storage evolution because `store_embeddings(chunks)` currently receives only chunks. It also requires migration/reindexing of existing collections and explicit semantics for documents connected to multiple sources or notebooks.

### B. CompositeStorage relational resolution

Have `CompositeStorage` resolve a canonical `MetadataFilter` to an allowed document-ID set through the relational store and push that set to Qdrant as a `document_id` constraint. This needs an approved internal/public resolver contract, empty-set behavior, date semantics, and a strategy that remains correct and efficient for large allowed sets.

### Rejected workarounds

- Ignoring unsupported filter fields: violates filter semantics and can leak unrelated results.
- Overfetching and filtering in Python: violates the approved storage boundary and cannot guarantee `top_k` without potentially unbounded retrieval.
- Query-string encoding: violates the frozen retriever contract.
- Direct SQLite/Qdrant access from `DenseRetriever`: violates the storage abstraction.
- Adding fields to `Chunk` or creating V2 interfaces without approval: violates frozen contracts.

## Recommended next decision

Approve an ADR that selects either an index-time filter projection or a CompositeStorage filter-resolution contract, defines notebook/source multiplicity and date semantics, and specifies migration/reindexing for existing Qdrant collections. Module 6.2 can then resume without changing `RetrieverInterfaceV1`, `MetadataFilter`, `ScoredChunk`, or `Chunk`.

## Work completed before the stop

- Added a thin, stateless `DenseRetriever` using only `StorageInterfaceV1`.
- Added focused tests for delegation, filter and `top_k` propagation, empty results, exact raw-score preservation, identity/order preservation, storage failures, invalid inputs, dimensionality delegation, Qdrant import isolation, and registry loading.
- Focused result: **22 passed**.
- Focused Ruff checks: **PASS**.
- Focused mypy checks: **PASS**.
- Real services preflight: Ollama and Qdrant reachable; verified Phase 5 collection present.
- Real acceptance execution: **STOPPED/BLOCKED before retrieval acceptance** because the required filter semantics cannot be satisfied.

The full repository regression, coverage, pre-commit, and Module 6.2 completion documentation were intentionally not run or claimed after the mandatory stop condition. Module 6.2 remains **INCOMPLETE**; Modules 6.3, 6.4, and 6.5 remain **NOT STARTED**; M6 remains **NOT VERIFIED**.

## Files involved in partial Module 6.2 work

- `mnemo-core/mnemo/retrieval/dense.py`
- `mnemo-core/mnemo/retrieval/__init__.py`
- `mnemo-core/tests/unit/test_dense_retriever.py`
- `docs/module-6.2-dense-retriever-contradiction-report.md`

No version, commit, tag, release, or push was created.

## 2026-08-13 architecture-resolution investigation addendum

This addendum preserves the original contradiction evidence above and records the requested comparison of Option A and Option B. The investigation did **not** establish enough semantics to select or implement either option safely, so no ADR was created or marked Accepted.

### Confirmed canonical semantics

- ADR-0001 defines `date_after` and `date_before` as inclusive lower and upper bounds on `DocumentMetadata.publication_date`, not ingestion time.
- `Source` is the sole notebook-to-document association. Each source belongs to exactly one notebook and one logical document; multiple sources may reference the same document from different notebooks.
- Multiple `source_ids` therefore have set/OR semantics within that field. Different non-empty filter fields intersect.
- `DocType` is canonical on `ParsedDocument`, which is version-specific parsed IR stored by `FilesystemBlobStore`.
- Qdrant already stores both `document_id` and `version_id`, and Qdrant keyword filters can constrain those existing payload fields before ANN ranking.
- Empty `MetadataFilter()` can retain the current direct Qdrant fast path. An empty resolved candidate set must return `()` without an unfiltered Qdrant request.

### Repository/schema discrepancies discovered

1. SQLite's `documents` table has no `type` column, although `SQLiteStore.search_sparse()` currently emits a query against `documents.type` when `doc_types` is non-empty.
2. Neither `documents` nor `document_versions` persists `ParsedDocument.doc_type`. `document_versions.metadata` contains `DocumentMetadata`, whose typed fields do not include document type.
3. The accepted ADR requires `(notebook_id, document_id)` to be unique in `sources`, but the actual SQLite schema has no corresponding unique constraint. A resolver can use `DISTINCT` to prevent duplicate candidates, but the storage invariant itself is presently unenforced.
4. The roadmap and Qdrant changelog claim payload fields such as `notebook_id` and `doc_type` were implemented, while `_chunk_payload()` proves they were not. The real M5 point inspection confirms the implementation, not those historical claims.

### Option B: CompositeStorage relational resolution

Option B is the smaller read-path design for notebook and source membership:

- resolve matching logical `document_id` values from `sources` using set semantics and `DISTINCT`;
- resolve publication dates from the canonical version metadata stored in `document_versions.metadata`;
- pass the resulting constraint into Qdrant before ranking and truncation;
- preserve raw Qdrant scores, ordering, identities, and true filtered `top_k`.

It cannot currently satisfy the complete frozen filter contract as a purely relational resolver:

- canonical `DocType` is absent from SQLite;
- fetching every parsed IR blob to evaluate a type-only filter would turn a relational filter into an unbounded filesystem scan and does not meet the intended Phase 6 query workload;
- the architecture states that superseded chunks remain queryable by default, while publication date and document type belong to version-specific metadata/parsed IR;
- resolving only logical document IDs can admit a nonmatching version of a matching document, so the conceptual `allowed document IDs` representation is insufficient for version-correct filtering;
- the frozen contract does not specify whether a document version with `publication_date=None` matches either date bound;
- no approved representation or operational bound exists for pushing a potentially very large candidate set to Qdrant without an arbitrary limit.

Option B would require an approved internal metadata projection or resolver keyed at least by `(document_id, version_id)`, plus explicit missing-date and large-candidate semantics. That is materially more than the currently described document-ID resolver.

### Option A: index-time projection and reindexing

Option A aligns with the original roadmap intent to apply filters inside Qdrant and naturally preserves pre-`top_k` filtering. It could project version-specific `doc_type` and `publication_date`, and document-level notebook/source memberships, into vector payloads.

It is not presently implementable without additional architectural decisions:

- `StorageInterfaceV1.upsert_chunks()` receives only `Chunk`; it does not receive `ParsedDocument`, `Document`, or `Source` context.
- `doc_type` is available when parsed IR is written, publication date when document versions are written, and notebook/source membership when source associations are written. These are separate public operations whose ordering and cross-store atomicity are not defined for a Qdrant projection.
- Source associations are mutable. Correct payloads would require Qdrant updates on source upsert/delete and notebook deletion, including rollback/failure semantics.
- Superseded versions require version-keyed payload values rather than one logical-document snapshot.
- Existing v0.20.1/M5 collections would require documented payload migration or reindexing. No existing collection was changed during this investigation.

Option A offers better steady-state filtered-query performance but has greater write-path, migration, and operational complexity. It cannot be selected by silently adding fields in `_chunk_payload()` because `Chunk` is deliberately not the source of those values.

### New unresolved decisions at the contradiction gate

The following required semantics remain undefined and prevent an ADR decision:

1. **Version semantics:** whether date/type filters apply to each returned chunk's exact `version_id` or to the logical document's current version. The architecture retains superseded chunks, so these differ observably.
2. **Missing publication dates:** whether `publication_date=None` is excluded whenever either date bound is present, or follows another explicit rule.
3. **Candidate representation:** whether CompositeStorage may pass version-keyed candidate pairs, a Qdrant-native internal filter, or another internal value to QdrantStore while preserving the public V1 boundary.
4. **Large candidate sets:** the approved exact representation and failure/performance behavior when the relational result contains many document/version identities.
5. **Projection consistency:** if Option A or a hybrid projection is chosen, the required atomicity and rollback behavior across filesystem parsed IR, SQLite document/source records, and Qdrant payload updates.
6. **Existing-data migration:** whether verified v0.20.1 collections are immutable historical evidence, migrated in place, or copied/reindexed into a new compatible collection.

### Resolution verdict

The repository can support a compliant design without changing `RetrieverInterfaceV1`, `StorageInterfaceV1`, `MetadataFilter`, `ScoredChunk`, or `Chunk`, but the exact internal storage design cannot be chosen until the six semantics above are approved. Implementing either option now would invent behavior prohibited by the contradiction gate.

Accordingly:

- no frozen public contract was modified;
- no SQLite migration was added;
- no Qdrant payload or collection was modified;
- no ADR was created or accepted because there is not yet a complete decision to record;
- the partial thin `DenseRetriever` remains unchanged;
- Module 6.2 remains **INCOMPLETE/BLOCKED**.

## Resolution record

The unresolved decisions above were subsequently approved by the maintainer and
formalized in ADR-0038. The selected design is a version-aware retrieval
metadata projection coordinated by `CompositeStorage`, with Qdrant-native
filtering before ANN `top_k`. Implementation, deterministic semantic fixtures,
full regression, and a new real golden/Ollama/Qdrant acceptance collection all
passed on 2026-08-13. This report remains the historical evidence for why that
decision was required; the completion evidence is recorded in
`docs/module-6.2-dense-retriever-report.md`.
