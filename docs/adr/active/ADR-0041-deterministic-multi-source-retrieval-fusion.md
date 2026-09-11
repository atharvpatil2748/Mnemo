# ADR-0041: Deterministic Multi-Source Retrieval Orchestration and Fusion

- **Status:** Accepted
- **Date:** 2026-08-13
- **Decision owners:** Mnemo maintainers
- **Extends:** ADR-0002, ADR-0038, ADR-0039, ADR-0040
- **Supersedes in part:** ADR-0002 `HybridRetriever` ownership only
- **Resolves:** `module-6.5-multi-source-retrieval-orchestration-fusion-contradiction-report.md`

## Context

Modules 6.1 through 6.4 provide an immutable `RetrievalPlan`, bounded dense and
sparse retrievers, exact-version hard filters, and source-local parent
promotion. Module 6.5 must execute a plan, preserve the independent raw-score
domains, promote each stream before combination, deduplicate canonical chunks,
and establish one deterministic global order.

The existing contracts deliberately do not define a multi-stream result.
`ScoredChunk` represents one ranking source's raw score and local rank; it
cannot truthfully contain several raw scores or an RRF score. The planner can
also emit several vector-requiring subqueries while its convenience
`plan_with_hyde_embedding()` method returns only the first HyDE vector.

The Module 6.5 contradiction report correctly stopped implementation because
the RRF formula, hybrid ownership, embedding handoff, fused representation,
global bound, concurrency, failure policy, and plan-flag behavior were not
specified.

## Problem

Mnemo needs one additive orchestration contract that can execute every
currently supported plan without changing frozen Phase 1 interfaces or
confusing raw provider scores with fused evidence. The contract must be
deterministic regardless of task completion order and must leave reranking,
context, citations, synthesis, and multi-hop reasoning to Modules 6.6-6.10.

## Scope

This decision defines:

- Module 6.5 inputs, outputs, dependencies, and validation;
- subquery and retriever-invocation identity;
- execution-time embedding ownership;
- supported retrieval modes and hybrid expansion;
- source-local parent-promotion timing;
- exact RRF, deduplication, provenance, ranking, and candidate bounds; and
- concurrency, failure, cancellation, and plan-flag semantics.

It specifies contracts for later Module 6.5 implementation. It does not add
production code.

## Constraints and existing contracts

- `RetrieverInterfaceV1`, `StorageInterfaceV1`, `EmbeddingProviderV1`,
  `MetadataFilter`, `ScoredChunk`, `Chunk`, and
  `ParentPromotionInterfaceV1` remain unchanged.
- `RetrievalPlan` and its ordered `SubQuery` values remain the only planning
  schema.
- A retriever stream contains unique chunks, one non-empty source, descending
  raw scores, deterministic chunk-ID ties, and contiguous one-based local
  ranks.
- Dense and sparse scores are raw and mutually incomparable.
- Metadata filters execute inside storage before source-local ranking/top-k.
- ADR-0040 promotion is independent, source-local, single-pass, and
  non-expanding.
- Module 6.5 performs no backend access and resolves retriever and promoter
  capabilities through `PluginRegistry`.

## Alternatives considered

### Return fused `ScoredChunk` values

Rejected. Putting RRF in `ScoredChunk.score` would violate its raw-score
contract. Keeping an arbitrary source's raw score would lose other evidence
and make the global rank appear to belong to that raw domain.

### Add fusion fields to `ScoredChunk` or `Chunk`

Rejected. Both models are frozen, and retrieval evidence is neither canonical
chunk state nor one provider score.

### Dedicated `HybridRetriever`

Rejected for Phase 6.5. It would duplicate orchestration/fusion, obscure the
two source-local promotion calls, and conflict with the detailed roadmap.

### Caller-supplied embedding map

Rejected as the canonical path. It introduces a second transient identity
contract and makes completeness/model validation the caller's responsibility.

### Degraded partial success

Rejected for V1. No existing result contract can report partial failures
without making incomplete retrieval look successful.

## Decision

Module 6.5 introduces an additive, runtime-checkable
`MultiSourceRetrievalInterfaceV1` implemented by `MultiSourceRetriever`:

```python
async def execute(
    plan: RetrievalPlan,
    *,
    global_limit: int,
) -> RetrievalFusionResult
```

The implementation is constructed with:

- the frozen/configured `PluginRegistry`;
- an `EmbeddingProviderV1`, which may already be a cached provider; and
- `max_concurrency`, default 4 and constrained to 1 through 32.

It resolves `dense` and `sparse` retrievers from the existing `retriever`
capability family and resolves `parent_promotion/default` from the ADR-0040
capability family. Resolution is completed and validated before any task is
started. The orchestrator owns invocation scheduling, execution-time query
embedding, exactly one promotion call per successful source-local stream,
fusion, global rank, and final truncation. It owns no storage, LLM, reranking,
or synthesis operation.

This additive orchestration service is a core pipeline service, not another
query retriever and not a new registry capability family.

## Query, subquery, and invocation identity

Subquery identity is its immutable one-based position in
`RetrievalPlan.sub_queries`. Reordering a plan intentionally changes evidence
identity. Every executable source-local invocation has the deterministic ID:

```text
sq-<one-based-subquery-index>:<effective-mode>
```

Effective mode is `dense` or `sparse`. A normal dense/sparse subquery creates
one invocation. A hybrid subquery creates two IDs at the same subquery index,
with dense ordered before sparse. Therefore IDs are unique without random UUIDs
or task-order state.

Each invocation is traceable to its subquery index, declared planner mode,
effective retrieval mode, exact query text, filters, requested source-local
top-k, and pre/post-promotion streams.

## Additive evidence and result records

Module 6.5 introduces immutable additive Phase 6 records; it does not modify
`ScoredChunk`:

### `RetrievalInvocationTrace`

Contains invocation ID, one-based subquery index, declared mode, effective
mode, exact query text, filters, requested top-k, the raw retriever tuple, and
the promoted tuple. Both tuples contain canonical `ScoredChunk` values. This
preserves the full bounded before/after record of parent promotion.

### `FusionEvidence`

Contains invocation ID, subquery index, declared mode, effective mode, the
post-promotion `ScoredChunk`, and `identity_introduced_by_parent_promotion`.
The last flag is true exactly when the surviving post-promotion chunk ID was
absent from that invocation's raw stream. The accompanying invocation trace
records that promotion ran even when an already-present parent wins local
deduplication.

### `FusedChunkResult`

Contains the canonical `Chunk`, finite `rrf_score`, contiguous one-based
`global_rank`, and a non-empty tuple of `FusionEvidence`. It has no singular
`source` or raw `score`, because those values belong to individual evidence.

### `RetrievalFusionResult`

Contains the original immutable `RetrievalPlan`, ordered invocation traces,
and the bounded tuple of `FusedChunkResult`. Retaining the plan carries
`requires_multi_hop` and `requires_multi_doc` to later modules without
reinterpreting them.

All evidence records are bounded by at most 16 planner subqueries, at most two
invocations per subquery, and at most 100 raw results per invocation.

## Query embedding ownership

`MultiSourceRetriever` owns execution-time query embedding through its injected
`EmbeddingProviderV1`:

- each dense invocation embeds that invocation's exact `SubQuery.query_text`;
- the dense half of a hybrid subquery embeds the same exact hybrid query text;
- sparse invocations pass `None` and perform no embedding call;
- multiple dense/hybrid subqueries receive separate vectors keyed internally
  by invocation ID; and
- a vector is never reused for unrelated query text.

The planner continues to own HyDE text generation. At least the first
dense/hybrid subquery is the Module 6.1 HyDE paragraph, so embedding its exact
text preserves HyDE semantics. `plan_with_hyde_embedding()` remains a valid
Module 6.1 convenience API for standalone callers, but the canonical 6.5 path
uses `plan()` and performs all required embeddings itself.

The orchestrator adds no cache. If the configured provider is a
`CachedEmbeddingProvider`, ordinary provider calls supply model-specific cache
behavior; otherwise normal provider semantics apply.

## Intent and retrieval-mode matrix

Planner intent does not change dispatch:

| Intent | Module 6.5 behavior |
|---|---|
| `factual` | Execute the plan exactly as supplied. |
| `comparative` | Execute the plan exactly as supplied. |
| `exploratory` | Execute the plan exactly as supplied. |
| `synthesis` | Execute the plan exactly as supplied; do not synthesize. |

Retrieval modes behave as follows:

| Declared mode | Module 6.5 behavior |
|---|---|
| `dense` | Resolve `retriever/dense`; one dense invocation. |
| `sparse` | Resolve `retriever/sparse`; one sparse invocation. |
| `hybrid` | Expand deterministically into dense then sparse invocations; no `retriever/hybrid` lookup. |
| `graph` | Raise `UnsupportedError`; graph execution is unavailable in 6.5 and requires a later accepted contract. |
| `parent` | Raise `UnsupportedError`; ADR-0040 reserves this token and parent promotion is not query retrieval. |

A missing required dense, sparse, or parent-promotion registration raises
`DependencyUnavailableError`. Unsupported modes are never skipped or
downgraded.

## Relationship to ADR-0002 and hybrid ownership

ADR-0002's specification-only statement that a `HybridRetriever`
specialization owns dense/sparse fusion is superseded for Phase 6 by this
decision. The detailed roadmap and implemented source-local contracts require
Module 6.5 to expand hybrid subqueries, promote each effective stream
independently, and fuse all streams in one place.

`RetrieverInterfaceV1` itself and its raw-score semantics are not superseded.
Plugins may not satisfy a hybrid plan by registering `retriever/hybrid`; that
slot is not consulted by `MultiSourceRetriever` V1.

## Relationship to ADR-0040 and parent promotion

Every successfully returned source-local stream, including an empty tuple, is
passed exactly once to `parent_promotion/default`. ADR-0040 guarantees that an
empty call performs no storage work. Dense and sparse streams, including the
two halves of one hybrid subquery, are never combined before promotion.

The promoted stream is validated again as one unique, bounded, source-local
raw-score sequence. Parent promotion failure aborts the entire orchestration.

## Canonical deduplication and provenance

Deduplication happens after all source-local promotion. Results represent the
same global candidate exactly when `Chunk.id` is equal. If equal IDs carry
non-equal canonical `Chunk` values, orchestration raises `IntegrityError`
instead of selecting one snapshot.

One promoted chunk contributes at most once per invocation because every
promoted source stream must contain unique chunk IDs. The same canonical chunk
may contribute once from each distinct invocation, including repeated evidence
from different subqueries of the same effective mode. Every contribution is
retained in deterministic `FusionEvidence` order. No winner is chosen by
comparing raw scores.

## RRF mathematics

Module 6.5 always computes the baseline fusion order using unweighted
Reciprocal Rank Fusion:

```text
RRF(chunk) = fsum(1 / (60 + local_rank_e) for each evidence e)
```

The contract is:

- local ranks are one-based;
- `k = 60` exactly;
- every invocation has weight `1.0`;
- every effective retriever invocation is an independent evidence stream;
- repeated evidence from different subqueries contributes once per invocation;
- duplicate evidence within one invocation is an integrity failure, not an
  extra contribution;
- contributions are ordered by one-based subquery index and effective-mode
  order (`dense`, then `sparse`) before accumulation;
- arithmetic uses Python IEEE-754 binary64 `float`; and
- `math.fsum` performs the deterministic accumulation.

The value 60 is selected as Mnemo's explicit V1 contract, not inferred at
runtime. It provides conservative rank damping so a first-place result from one
stream does not overwhelm corroboration across independent streams. Changing
the constant or adding weights is a future versioned architectural change.

Raw dense/sparse scores are never normalized, summed, averaged, or compared by
fusion. They remain available only in `FusionEvidence`.

## Global ordering and rank

After grouping and RRF calculation, candidates are sorted by:

```text
(-rrf_score, chunk.id)
```

Chunk ID ascending is the complete deterministic tie-break. Task completion,
registry registration order, dictionary/set iteration, raw scores, and source
priority never influence global order. After final truncation, survivors
receive contiguous one-based `global_rank` values in tuple order.

## Global candidate bound

`global_limit` is a required caller input. It must be an integer, excluding
booleans, from 1 through 100 inclusive. There is no hidden default.

Each retriever receives its subquery's unchanged `max_results`. Parent
promotion cannot increase that stream. All promoted streams participate in
deduplication and RRF, then `global_limit` is applied to the deterministic
fused order. There is no refill, arbitrary overfetch, or arithmetic derivation
from the sum of subquery limits.

The maximum 100 matches the existing bounded `SubQuery.max_results` contract
and keeps the handoff to later local reranking bounded. A different bound
requires a later versioned decision.

## Concurrency

`max_concurrency` is constructor configuration, default 4, valid from 1 through
32. Thirty-two is the structural maximum produced by 16 subqueries with two
hybrid expansions each. Four is the explicit local-first V1 default; it bounds
simultaneous pressure on the embedding provider and both storage-backed
retrievers while retaining parallel dense/sparse execution.

One shared capacity limiter covers the complete invocation lifecycle:

```text
embedding when required -> retriever call -> parent promotion
```

Dense, sparse, and hybrid-expanded invocations share it. Providers and storage
may impose stricter internal limits. At most 32 bounded tasks are created, and
their results are collected in deterministic invocation-ID order rather than
completion order.

## Failure, cancellation, and timeout behavior

V1 is fail-fast and returns no degraded result:

- input type/bound violations raise `TypeError` or `ValueError` according to
  existing model conventions;
- unsupported `graph` or `parent` modes raise `UnsupportedError` before tasks
  start;
- missing registry capabilities raise `DependencyUnavailableError` before
  tasks start;
- malformed retriever/promoter streams or canonical identity conflicts raise
  `IntegrityError`;
- established provider, retriever, promotion, storage, and registry exceptions
  propagate unchanged;
- an unexpected plugin invocation exception is wrapped in `PluginError` with
  the deterministic invocation ID in details;
- the first task failure cancels unfinished peers, waits for their cleanup, and
  then raises; and
- all-stream failure is therefore the same failed operation, never an empty
  successful result.

Caller cancellation cancels all invocation tasks, waits for cleanup, and
propagates cancellation without returning candidates. V1 defines no internal
timeout and does not guess a deadline; a caller-owned deadline/cancellation
scope remains authoritative. A timeout surfaced by a dependency propagates
under the common error model.

If several tasks fail before cancellation is observed, the exception belonging
to the lowest invocation ordering key (numeric subquery index, then dense
before sparse) is raised; other failures may be logged/attached for diagnostics
but never alter output because no output is returned.

## `requires_multi_hop`

When `requires_multi_hop` is true, Module 6.5 executes exactly this plan as the
first standard retrieval stage and returns it in `RetrievalFusionResult` with
the flag intact. It does not extract entities, create another plan, recurse, or
execute another hop. Module 6.10 may consume the typed result and invoke later
bounded retrieval stages under its own accepted contract.

## `requires_multi_doc`

`requires_multi_doc` is preserved in the returned plan and does not rewrite
filters or ranking. Every subquery's immutable `MetadataFilter`, including
`notebook_id` and `source_ids`, is passed unchanged to every effective
retriever invocation.

The architecture phrase "not filtered by source" means Module 6.5 adds no
implicit single-source restriction. It does not mean caller/planner hard
filters are discarded. Multi-document intent is not a guarantee that the
eligible corpus contains multiple documents, and a restrictive but valid
filter may lawfully yield one or zero documents.

## Graph behavior

Graph retrieval is not implemented by Module 6.5. Although `GRAPH` remains
deserializable in `RetrievalMode`, a 6.5 plan containing it fails with
`UnsupportedError` before any retrieval task starts. It is not silently skipped
as graceful degradation. A future graph or multi-hop ADR may authorize graph
dispatch and define its evidence/rank contract without changing this V1
behavior silently.

## Determinism guarantees

Given equal plan, registry resolution, provider vectors, canonical storage,
and retriever outputs, Module 6.5 returns byte-for-byte equivalent model data:

- invocation IDs derive only from plan order and effective mode;
- result collection ignores task completion order;
- parent promotion is deterministic under ADR-0040;
- evidence is ordered by invocation identity;
- RRF uses fixed ranks, `k`, precision, and `math.fsum`; and
- global ties use canonical chunk ID.

## Module 6.5 boundary

Module 6.5 owns:

- the additive orchestration/evidence/fusion records;
- registry resolution and mode expansion;
- per-invocation embeddings;
- bounded parallel dispatch and cancellation;
- one parent-promotion call per stream;
- post-promotion canonical deduplication;
- RRF, global ordering/rank, and final candidate bound; and
- focused, integration, real-storage, and golden-corpus validation.

## Explicit exclusions for Modules 6.6-6.10

Module 6.5 does not:

- invoke or implement a cross-encoder or any reranker (6.6);
- build, compress, or budget context (6.7);
- create, resolve, or persist citations (6.8);
- call a synthesis LLM or stream answers (6.9); or
- extract entities, create follow-up plans, traverse graph hops, or recursively
  orchestrate retrieval (6.10).

Module 6.5 always supplies baseline RRF ordering. Module 6.6 may replace that
order when configured; "RRF fallback" means retaining the already-computed 6.5
order, not recomputing fusion inside the reranker. The exact 6.6 input contract
is outside this ADR and must preserve `RetrievalFusionResult` provenance.

## Compatibility impact

No frozen public contract changes. The new records and orchestration protocol
are additive Phase 6 API. DenseRetriever, SparseRetriever, ParentRetriever,
storage implementations, persisted chunks, and metadata projections retain
their accepted semantics.

ADR-0002 is clarified only where its specification-only `HybridRetriever`
ownership conflicts with the detailed implemented Phase 6 schedule. Existing
`retriever/hybrid` plugins are not silently adapted or invoked by this V1
orchestrator.

## Migration impact

No SQLite, Qdrant, SurrealDB, blob, chunk, embedding, or historical M4/M5
migration is required. Plugin configuration must provide active `dense`,
`sparse`, and `parent_promotion/default` capabilities for plans that need them.

## Rejected workarounds

- Reuse the first HyDE vector for unrelated subqueries.
- Normalize or compare dense and sparse raw scores.
- Store RRF scores in `ScoredChunk.score`.
- Select a duplicate winner by raw score.
- Combine streams before ADR-0040 promotion.
- Skip unsupported modes or failed streams.
- Return successful partial candidates without typed failures.
- Use task completion order for evidence or ranking.
- Derive a global limit by summing subquery limits.
- Strip notebook/source filters for multi-document intent.
- Implement graph or multi-hop execution early.

## Testing implications

Later Module 6.5 implementation acceptance must cover:

- all four intents and every retrieval mode outcome;
- single, multiple, and hybrid-expanded subqueries;
- exact query-text/vector mapping and cached-provider interaction;
- one independent promotion call per invocation, including empty streams;
- deterministic invocation traces before and after promotion;
- duplicate evidence across modes and subqueries;
- exact `k=60` RRF arithmetic and one contribution per invocation;
- canonical chunk conflict detection and full raw evidence preservation;
- RRF ties, chunk-ID tie-breaking, contiguous global ranks, and truncation;
- global limits 1, 100, and invalid values;
- concurrency limits 1, 4, and 32 and completion-order independence;
- every fail-fast, cancellation, registry, malformed-output, and unsupported
  mode path;
- first-stage-only behavior for multi-hop plans and unchanged filters for
  multi-document plans; and
- real dense, sparse, parent-promotion, Qdrant/SQLite, and golden-corpus paths.

## Consequences

Positive consequences:

- Frozen raw-score and canonical chunk contracts remain truthful.
- Every fused contribution remains inspectable.
- Hybrid execution and source-local promotion have one unambiguous owner.
- Bounded concurrency and fail-fast behavior are explicit.
- Results are reproducible independently of asynchronous completion order.
- Later reranking and multi-hop modules receive a typed, provenance-preserving
  boundary.

Costs and limitations:

- Invocation traces retain bounded pre/post-promotion tuples and therefore use
  more memory than a lossy fused `ScoredChunk` list.
- V1 requires all requested capabilities; it offers no degraded mode.
- Graph plans are rejected until a later architecture enables them.
- Changing RRF parameters, hybrid ownership, or partial-success policy is a
  versioned architectural change.

## Acceptance criteria

This ADR resolves the Module 6.5 architecture gate when documentation agrees
that:

1. orchestration uses the additive API and result/evidence records above;
2. every dense invocation embeds its own exact query text;
3. hybrid expands to independent dense and sparse streams;
4. every stream is promoted once before combination;
5. RRF uses one-based rank, equal weights, `k=60`, and deterministic `fsum`;
6. canonical chunk deduplication retains every invocation's raw evidence;
7. global order is `(-rrf_score, chunk.id)` and is truncated to a required
   `global_limit` from 1 through 100;
8. one shared configured limiter bounds the full invocation lifecycle;
9. execution is fail-fast with deterministic peer cancellation;
10. graph/parent modes fail explicitly and no requested stream is skipped;
11. multi-hop is returned as first-stage state and multi-document filters are
    preserved unchanged; and
12. no Module 6.6-6.10 responsibility or frozen-contract modification occurs.

Module 6.5 remains architecture-resolved but implementation-not-started until
a separate implementation task satisfies these criteria.
