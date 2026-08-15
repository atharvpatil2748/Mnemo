# Module 6.4 ParentRetriever Contradiction Report

## Status

**BLOCKED — Module 6.4 remains incomplete.**

Investigation was performed on 2026-08-13 against HEAD
`94e3487656599fbea30b7465d76586556a3b7138`, with the uncommitted Module
6.1–6.3 work preserved. No retrieval interface, storage interface, model,
registry, implementation, roadmap status, version, tag, or release was changed.

## Contradiction

The architecture defines ParentRetriever as a transformation over an already
retrieved candidate set:

1. inspect candidate children;
2. group children by canonical non-null parent;
3. compare represented children with the complete stored sibling family;
4. replace a qualifying family with its stored parent when representation is
   at least 50 percent.

`RetrieverInterfaceV1.retrieve()` accepts only query text, an optional query
embedding, `MetadataFilter`, and `top_k`. It has no candidate-set input. An
implementation cannot determine sibling co-occurrence from those values.
ADR-0002 also states that specialized retrievers share this method and may not
add specialized public methods without ADR review.

The contradiction previously recorded in
`module-6.2-retrievers-contradiction-report.md` therefore remains active. No
subsequent accepted ADR, including ADR-0038 or ADR-0039, defines the missing
candidate transformation contract.

## Affected contracts

- `RetrieverInterfaceV1`: cannot receive previously retrieved candidates.
- `ScoredChunk`: represents one raw provider score/source/rank, but does not
  define promotion provenance.
- `PluginRegistry`: can register a `parent` RetrieverInterface implementation,
  but registration does not solve its missing typed input.
- Phase ordering: architecture step 6 places parent promotion after retrieval,
  while Module 6.5 owns parallel execution, cross-retriever deduplication, and
  fusion. The repository does not decide whether parent promotion sees each
  source independently or their combined candidates.

`StorageInterfaceV1` is not the primary blocker. Once a qualifying parent ID is
known, `get_chunk(parent_id)` can load the canonical parent through
`CompositeStorage` without a backend dependency.

## Semantics that are already defined

### Canonical stored family

ADR-0015 is sufficient. A family is the complete set of stored children that
share one non-null `parent_chunk_id`. For any valid child this is the child
itself plus its symmetric, deterministic `sibling_ids`. Roots are not siblings;
a sole child has an empty sibling tuple. No heading, position, page, or text
heuristic is needed.

The threshold is therefore:

```text
represented unique children in the candidate set
-------------------------------------------------  >= 0.5
stored children sharing the same non-null parent
```

The identity key must include canonical parent ID, document ID, and version ID,
and the loaded parent must match the children's document/version.

### Filter semantics

ADR-0038 and ADR-0039 constrain every `MetadataFilter` field at document or
exact-version scope. A canonical parent belonging to the same
`(document_id, version_id)` as eligible children consequently has the same
notebook/source/type/date eligibility. Parent promotion need not rerun a
backend filter, but it must reject a loaded parent crossing document/version
boundaries. This conclusion does not resolve the candidate-input contradiction.

### Parent lookup

The existing backend-neutral `StorageInterfaceV1.get_chunk()` is sufficient for
canonical parent lookup. Missing parents and inconsistent document/version
identity must be explicit integrity failures; reconstructing parent text is
prohibited.

## Undefined semantics

### Candidate stage and source scope

The repository does not define whether ParentRetriever transforms:

- each dense/sparse result sequence independently before Module 6.5;
- a concatenated dense/sparse candidate set before fusion;
- deduplicated candidates inside Module 6.5; or
- a fused result sequence after RRF.

These choices change whether a family qualifies. For example, one dense child
and one sparse child may reach exactly 2/4 only when sources are combined.
Selecting a choice here would prematurely define Module 6.5.

### Score and source

No accepted document specifies whether a promoted parent receives the best,
first, mean, summed, or otherwise aggregated child score. Dense and sparse raw
scores are explicitly incomparable under ADR-0002. It is also undefined
whether `ScoredChunk.source` remains `dense`/`sparse`, becomes `parent`, or
requires multi-source provenance that the frozen model cannot represent.

### Rank and top-k

No accepted rule defines the rank of one parent replacing several children,
the relative order between promoted parents and unpromoted children, or whether
`top_k` is applied before or after promotion. These decisions affect later
fusion and reranking.

## Rejected workarounds

- Encode candidate IDs or serialized candidates in `query`.
- Rerun dense or sparse search inside ParentRetriever and pretend those results
  are the upstream candidate set.
- Read candidates from hidden global/thread-local state.
- Add an unofficial method to `RetrieverInterfaceV1` or introduce an
  unapproved V2 interface.
- Make ParentRetriever depend directly on SQLite, Qdrant, or SurrealDB.
- Choose best/mean/sum score propagation without an accepted decision.
- Implement cross-source concatenation, deduplication, or RRF from Module 6.5.

## Candidate architectural options

### Option A — Typed candidate-promotion contract (recommended)

Approve an ADR defining ParentRetriever as a distinct Phase 6 transformation,
not a query-executing `RetrieverInterfaceV1`. A narrow protocol should accept
an immutable `tuple[ScoredChunk, ...]` and a bound, then return an immutable
promoted sequence. The ADR must define stage placement, source scope,
score/source/rank propagation, top-k timing, missing-parent behavior, and
ordering. PluginRegistry may need a new versioned capability family rather than
misusing the existing retriever slot.

This preserves every frozen Phase 1 contract and accurately models the
operation's data dependency.

### Option B — Make ParentRetriever a decorator over one retriever

Inject one `RetrieverInterfaceV1`, execute it, then promote its output. This
fits the current public method but only defines source-local promotion. It
cannot combine dense and sparse evidence without additional orchestration and
would make the 50-percent outcome depend on which retriever is wrapped. It is
not recommended unless source-local promotion is explicitly approved.

### Option C — Place parent promotion inside Module 6.5 orchestration

Define an internal candidate transformation owned by the later parallel/fusion
pipeline. This naturally exposes combined candidates but changes the detailed
module boundary and must specify whether transformation occurs before or after
deduplication/fusion. Module 6.4 could then define the pure algorithm and
Module 6.5 its invocation. This requires an explicit roadmap/ADR decision.

### Option D — RetrieverInterfaceV2

Introduce a versioned request capable of carrying candidates. This is broader
than necessary and burdens ordinary dense/sparse retrievers with irrelevant
inputs. It is the highest-compatibility-cost option.

## Recommended resolution

Approve Option A through the next ADR. The decision should state:

1. the exact typed candidate-promotion method;
2. whether candidates are source-local, combined, deduplicated, or fused;
3. whether promotion precedes Module 6.5 fusion;
4. exact score, source, rank, ordering, and top-k semantics;
5. explicit missing-parent and hierarchy-integrity failures;
6. registry capability/versioning behavior; and
7. whether bounded per-family `get_chunk()` calls are acceptable or an internal
   batch lookup is required.

Only after that decision can threshold, family, version, filter, score, rank,
real-storage, and golden-corpus acceptance tests assert non-invented behavior.

## Migration and compatibility implications

The canonical Chunk and SQLite schemas require no migration: parent and sibling
identities are already persisted. Option A would add a new Phase 6 protocol and
possibly a PluginRegistry capability family, while leaving
`RetrieverInterfaceV1`, `StorageInterfaceV1`, `MetadataFilter`, `ScoredChunk`,
and `Chunk` unchanged. Option D would require explicit interface-version
migration and plugin compatibility work.

Existing M4/M5 and Module 6.2/6.3 evidence remains valid and was not mutated.

## Test implications

Implementation tests are intentionally not added while semantics are blocked.
After approval, tests must cover 1/4, 2/4, 3/4, and 4/4 families; multiple
families; duplicate parent elimination; exact-version and cross-document
integrity; all filter categories; missing parents; storage failures;
score/source/rank/order/top-k rules; registry resolution; real SQLite parent
lookup; and the real Bhagavad Gita hierarchy.

## Verdict

The family graph, threshold denominator, parent lookup, version boundary, and
filter eligibility are expressible with current canonical data. The operation
itself is not expressible through the frozen retriever input contract, and its
ranking provenance remains undefined. Module 6.4 is therefore **BLOCKED** until
an ADR resolves the candidate-stage and score/source/rank semantics. Module 6.5
and later modules remain not started; M6 remains unverified.

## Resolution addendum — 2026-08-13

Accepted ADR-0040 resolves this gate without changing the historical findings
above. It selects a separate `ParentPromotionInterfaceV1`, source-local
single-pass promotion before Module 6.5 fusion, first-ranked-child score/source
inheritance, local rank recomputation, upstream-only top-k, strict hierarchy
integrity failures, and a separate versioned `parent_promotion` registry
capability. Module 6.4 is now **architecture resolved / implementation not
started**. This report remains the evidence that prohibited implementation
before that decision.

## Implementation addendum — 2026-08-13

Module 6.4 was subsequently implemented and validated under ADR-0040. See
`docs/module-6.4-parent-retriever-report.md`. This addendum records resolution;
the original contradiction and architecture-gate evidence above remain
unchanged.
