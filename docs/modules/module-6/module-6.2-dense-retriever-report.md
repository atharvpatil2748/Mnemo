# Module 6.2 DenseRetriever Verification Report

## Verdict

**Module 6.2: COMPLETE**

DenseRetriever, version-aware retrieval metadata projection, pre-ANN Qdrant filtering, mutable Source/Notebook propagation, and real golden-corpus retrieval were implemented and validated. Modules 6.3, 6.4, and 6.5 remain not started. M6 remains unverified.

## Scope and architecture

ADR-0038 resolves the storage-filter contradiction without changing `RetrieverInterfaceV1`, `StorageInterfaceV1`, `MetadataFilter`, `ScoredChunk`, or `Chunk`.

`DenseRetriever` remains a stateless delegate. `CompositeStorage` derives exact-version type/date plus document-level source/notebook membership from canonical stores when chunks enter the vector index. `QdrantStore` persists this derived projection and translates canonical filters into indexed Qdrant conditions before ANN ranking and `top_k`.

Canonical sources remain:

- `ParsedDocument.doc_type` for exact-version type;
- `DocumentVersion.metadata.publication_date` for exact-version date;
- `Source` for notebook/document membership;
- `(Chunk.document_id, Chunk.version_id)` for retrieval identity.

Qdrant payload is rebuildable derived state, not canonical truth.

## Filter semantics validated

- Multiple `source_ids` and multiple `doc_types` use OR semantics within each field.
- Different non-empty fields intersect.
- Date bounds are inclusive.
- Missing publication dates are excluded only when a date bound is present.
- Superseded and current versions are filtered by their own type/date.
- Notebook/source arrays use sets and do not duplicate vector results.
- Empty filters use the direct unfiltered Qdrant path.
- Nonmatching filters return `()` without fallback.
- Filtering occurs in Qdrant before ANN ranking/truncation.
- Backend scores and ordering are preserved.

## Mutation and recovery

Source creation, movement, and deletion synchronously refresh affected document points and compensate their canonical mutation on projection failure. Notebook deletion writes the restrictive post-delete projection before its relational cascade, then restores projection from unchanged canonical rows if either phase fails. This avoids attempting to reconstruct cascade-dependent notebook records. Failed compensation is surfaced as `StorageError`; success is never reported for inconsistent state.

SQLite schema migration 3 adds the accepted unique `(notebook_id, document_id)` Source invariant. It audits existing rows first and fails without destructive deduplication if a duplicate pair exists.
All eight repository-local milestone databases were inspected read-only; every
database contained zero duplicate membership pairs.

The stale `SQLiteStore.search_sparse()` reference to nonexistent `documents.type` is confirmed but not used by Module 6.2. Its implementation correction is deferred to Module 6.3.

## Real golden acceptance

Executed 2026-08-13 against real local services:

- Corpus: `goldenDataset/Bhagavad-gita-As-It-Is.pdf`
- SHA-256: `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583`
- Physical pages: 952
- Parsed blocks: 6,512
- Real chunks: 1,275
- Acceptance vectors: first deterministic 1,000 chunks
- Ollama model: `nomic-embed-text`
- Dimensions: 768
- New collection: `mnemo_m5_gita_20260813t082746167930z`
- Points before/write/read-back/count: 0 / 1,000 / 1,000 / 1,000
- Embedding time: 29.0637 seconds
- Embedding throughput: 34.4072 chunks/second
- Qdrant write time: 3.0591 seconds

Historical collection `mnemo_m5_gita_20260813t060713393050z` was not mutated.

### DenseRetriever query

- Query: `What does the Bhagavad Gita teach about duty?`
- Query embedding: real `nomic-embed-text`
- `top_k`: 5
- Filter: generated acceptance notebook ID AND generated source ID AND `doc_types=[book]`
- Unfiltered results: 5
- Filtered results: 5
- Nonmatching `doc_types=[paper]`: empty tuple
- Filtered ranking: identical to the eligible unfiltered ranking
- Exact returned version: `ee50fc6e-cc8d-59cb-97c2-17dbd8d166e9`
- Raw scores: `0.73382306`, `0.7331376`, `0.73038065`, `0.71500844`, `0.712392`

Returned chunk IDs, in order:

1. `04f156543005258b6833d636f9bcda957ce61bd68f681392dc0c33763da0fd80`
2. `13af9334fd485712ae94056945657d2866322e07b431d011ef13867bf99faf57`
3. `fb0eff399442aea2b5729862eb1578751813f98e18041cfa28f8f1b3edc888a7`
4. `3c8dcb0bfba173029ff590e6a064178743aefe9ee0b73dbcd5821ad9efef53dd`
5. `c4e1656e44c90f0cd725ac281411af9604d11b7ef1143aecc6bf57a428347710`

The golden corpus naturally supplies one book version. Exact-version divergence, inclusive date boundaries, missing dates, and differing superseded/current types were therefore validated with deterministic storage fixtures rather than fabricated as golden-corpus facts.

## Automated validation

- Focused affected suites: 76 passed
- Full repository: 832 passed, 1 skipped
- Coverage: 90.16%
- Ruff format check: pass
- Ruff lint: pass
- Production strict mypy: pass
- Pre-commit: pass
- `git diff --check`: pass
- Real Ollama: pass
- Real Qdrant: pass
- Golden dataset: pass

An early full pytest run passed all tests and coverage but Windows returned a cleanup error for an inaccessible global pytest temporary directory. Subsequent complete suites used repository-local `TEMP`/`TMP`; the final run exited successfully with the results above.

## Files changed for Module 6.2

- `mnemo-core/mnemo/retrieval/dense.py`
- `mnemo-core/mnemo/retrieval/__init__.py`
- `mnemo-core/mnemo/storage/retrieval_projection.py`
- `mnemo-core/mnemo/storage/composite.py`
- `mnemo-core/mnemo/storage/qdrant.py`
- `mnemo-core/mnemo/storage/sqlite.py`
- `mnemo-core/tests/unit/test_dense_retriever.py`
- `mnemo-core/tests/unit/test_retrieval_projection.py`
- relevant CompositeStorage, QdrantStore, and SQLiteStore unit tests
- `scripts/verify_phase_4_5_milestones.py`
- ADR-0038 and synchronized architecture/roadmap/storage documentation

## Limitations and phase boundary

- Historical v0.20.1/M5 collections lack projected filter metadata and require rebuild into a new collection.
- The 10,000-chunk Phase 5 benchmark remains unverified and was not executed.
- SparseRetriever and its stale SQLite document-type SQL are Module 6.3 work.
- ParentRetriever remains deferred to Module 6.4 and its required ADR.
- Parallel retrieval, deduplication, and RRF remain Module 6.5 work.
- No version bump, commit, push, tag, or release was performed.
