# Module 6.2 Retrievers — Architectural Contradiction Report

## Status

Implementation is stopped before retriever code changes. Dense and sparse
retrieval can be implemented through the frozen contracts, but the requested
ParentRetriever behavior cannot be expressed through `RetrieverInterfaceV1`
without inventing an input encoding or adding a new public method. Both actions
are prohibited without architectural approval.

This report was produced on 2026-08-13 against HEAD
`94e3487656599fbea30b7465d76586556a3b7138`. The intended, uncommitted Module
6.1 work was preserved.

## Requirements

The requested Module 6.2 scope groups three mechanisms:

1. `DenseRetriever`: execute one vector search through `StorageInterface`;
2. `SparseRetriever`: execute one FTS5/BM25 search through
   `StorageInterface`; and
3. `ParentRetriever`: inspect already-retrieved chunks and promote a sibling
   family to its canonical parent when at least 50% of the stored family is
   present.

The architecture and roadmap define parent promotion as a set operation:

> For each retrieved chunk, inspect its stored sibling family. If at least 50%
> of chunks sharing its non-null parent are present, replace them with that
> explicitly linked parent chunk.

ADR-0015 fixes the underlying hierarchy as a single-parent forest. Sibling IDs
are symmetric, deterministic, exclude self, and exist only for chunks sharing
one non-null parent.

## Current contracts

### RetrieverInterfaceV1

The accepted ADR-0002 and current protocol expose exactly:

```python
async def retrieve(
    query: str,
    query_embedding: EmbeddingVector | None,
    filters: MetadataFilter,
    top_k: int,
) -> tuple[ScoredChunk, ...]:
    ...
```

The method has no input for previously retrieved chunks, child IDs, sibling
families, or grouped result sets. ADR-0002 states that all specialized
retrievers share this generic method and may not add specialized public methods
without ADR review.

### StorageInterfaceV1

The existing storage facade is otherwise sufficient for the backend work:

- `search_dense(embedding, filters, top_k)` delegates through
  `CompositeStorage` to Qdrant;
- `search_sparse(query, filters, top_k)` delegates through
  `CompositeStorage` to SQLite FTS5; and
- `get_chunk(chunk_id)` delegates through `CompositeStorage` to SQLite and can
  resolve a canonical parent after its ID is known.

The facade does not provide a candidate-set operation or batch family lookup.
That absence is not itself blocking if ParentRetriever receives candidates,
because `Chunk.sibling_ids` describes the stored family and `get_chunk()` can
resolve the selected parent. The blocking issue is that the retriever contract
cannot receive the candidate set.

### ScoredChunk

`ScoredChunk` preserves one provider's raw score, source, and rank. ADR-0001
explicitly forbids comparing unrelated raw score scales. No accepted document
defines the score and source assigned to a promoted parent when contributing
children may come from dense, sparse, or multiple retrieval sequences.

## Contradictions

### 1. Parent promotion input versus RetrieverInterfaceV1

The ≥50% co-occurrence decision requires the complete candidate set for the
stage. `RetrieverInterfaceV1.retrieve()` provides only a natural-language
query, optional vector, filter, and limit. A conforming ParentRetriever cannot
know which siblings were retrieved.

Encoding chunk IDs or serialized candidates inside `query` would violate its
non-empty natural-language query semantics, destroy type safety, and create an
undocumented protocol. Performing another semantic or lexical search would not
implement parent promotion.

### 2. Parent score semantics are unspecified

The architecture says to replace qualifying children with their parent, but it
does not define whether the parent inherits the maximum, minimum, mean, first,
or strategy-specific child score. It also does not define whether `source`
remains the originating retriever or becomes `parent`. Choosing any of these
would invent ranking behavior that affects later fusion.

### 3. Roadmap module numbering is internally inconsistent

The detailed roadmap assigns:

- Module 6.2: DenseRetriever;
- Module 6.3: SparseRetriever;
- Module 6.4: ParentRetriever; and
- Module 6.5: parallel execution, deduplication, and RRF.

The roadmap's later epic outline instead groups DenseRetriever,
SparseRetriever, and ParentRetriever under “Feature 6.2: Retrievers.” The
current request uses the epic grouping while also requiring Modules 6.3 and 6.4
to remain “NOT STARTED.” Implementing sparse and parent retrieval would
therefore both implement and not start those detailed modules.

### 4. Roadmap score wording conflicts with accepted ADRs

The detailed roadmap says dense and sparse results should be normalized to
0–1. ADR-0001 and ADR-0002 require raw backend scores and state that unrelated
score scales must not be compared. The current task also requires raw score
preservation. Accepted ADR semantics should win, but the stale roadmap wording
must be corrected when the module scope is approved.

## Candidate resolutions

### Option A — Add a typed parent-promotion contract (recommended)

Approve an ADR that treats parent promotion as a candidate-set transformation,
not an independent query backend. A narrowly scoped contract could accept an
immutable `ScoredChunk` sequence plus `top_k` and return promoted
`ScoredChunk` values. The ADR must define:

- whether promotion runs independently per originating retrieval source or
  after cross-source fusion;
- exact parent score/source/rank propagation;
- duplicate-parent handling;
- ordering and top-k behavior;
- missing parent and cross-document integrity failures; and
- whether individual `get_chunk()` calls are acceptable or a frozen storage
  evolution needs batch lookup.

This preserves `RetrieverInterfaceV1` for query-executing retrievers and makes
the set dependency explicit. It changes the architecture, so implementation
must wait for approval.

### Option B — Introduce RetrieverInterfaceV2

Define a V2 request model capable of carrying prior candidates. This makes the
interface more uniform but expands a frozen public contract for every
retriever, complicates registry versioning, and gives dense/sparse retrievers
irrelevant inputs. It is not the smallest solution.

### Option C — Keep the detailed roadmap split

Implement only DenseRetriever as Module 6.2, then implement SparseRetriever as
Module 6.3. Resolve ParentRetriever through an ADR before Module 6.4. This is
the smallest scheduling resolution and preserves current detailed roadmap
dependencies, but it does not satisfy the present three-retriever scope without
user approval.

### Rejected workaround — overload `query`

Passing JSON, comma-separated chunk IDs, or another hidden candidate encoding
through the `query` string is rejected. It violates the contract, is brittle,
and would make ordinary planner-generated parent sub-queries unsafe.

## Compatibility impact

DenseRetriever and SparseRetriever need no frozen interface changes. Both can
depend solely on `StorageInterfaceV1`, validate runtime inputs, preserve raw
scores and chunk identity, and register in the existing `dense` and `sparse`
slots.

Option A adds a new, explicit Phase 6 contract while leaving Phase 1 V1
protocols unchanged. Option B introduces a versioned breaking evolution.
Option C changes no contract but requires the requested work to be rescheduled
according to the detailed roadmap.

## Recommendation and required decision

Approve both of the following before implementation continues:

1. choose the scope convention:
   - implement only detailed Module 6.2 (DenseRetriever), or
   - approve the epic-style Feature 6.2 grouping of all three mechanisms; and
2. approve an ADR defining ParentRetriever as a typed candidate-set promotion
   stage, including exact score/source/rank semantics.

Until those decisions are made, Module 6.2 remains incomplete. No retriever,
registry, storage, roadmap-status, version, tag, release, or push change has
been made.
