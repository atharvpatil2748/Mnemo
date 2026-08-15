# Module 6.5 Multi-Source Retrieval Orchestration and Fusion Contradiction Report

## Status

**BLOCKED at the architectural gate.** No Module 6.5 production implementation,
interface, registry capability, test, acceptance runner, roadmap completion
mark, or changelog was added.

This report records repository state inspected on 2026-08-13. Module 6.5 must
not proceed until an accepted decision defines the missing orchestration and
fusion semantics below.

## Scope inspected

The investigation read the current repository versions of:

- `docs/mnemo_architecture_v2.md`;
- `docs/mnemo_engineering_roadmap.md`;
- ADR-0002, ADR-0015, ADR-0038, ADR-0039, and ADR-0040;
- the Module 6.1–6.4 reports and contradiction history;
- `RetrievalPlan`, `SubQuery`, `RetrievalMode`, `MetadataFilter`, and
  `ScoredChunk`;
- `QueryPlanner`, `DenseRetriever`, `SparseRetriever`, and `ParentRetriever`;
- `RetrieverInterfaceV1`, `StorageInterfaceV1`, and
  `ParentPromotionInterfaceV1`;
- `PluginRegistry`, `CompositeStorage`, SQLiteStore, and QdrantStore; and
- all existing retrieval package files and relevant tests.

Global searches covered RRF/fusion, reciprocal ranks, candidate/global bounds,
failure/partial-success policy, concurrency, deduplication, rank/source/score,
retrieval modes, query embeddings, and multi-document/multi-hop flags.

## What is already coherent

The following boundary is unambiguous and remains binding:

1. Each query retriever invocation returns one bounded source-local stream.
2. `ParentPromotionInterfaceV1.promote()` runs exactly once on each stream.
3. Dense and sparse streams are not combined before parent promotion.
4. Cross-source combination, deduplication, fusion, global ranking, failure
   policy, and later candidate bounds belong to Module 6.5.
5. `RetrievalMode.PARENT` is compatibility-reserved and must be rejected rather
   than dispatched as `RetrieverInterfaceV1`.
6. Dense and sparse raw scores are mutually incomparable and must not be
   normalized or compared directly.
7. Modules 6.6–6.10 remain outside this boundary.

These facts are insufficient to implement deterministic Module 6.5 behavior.

## Blocking contradiction 1 — RRF mathematics are undefined

The roadmap says only “Implement Reciprocal Rank Fusion.” The architecture
mentions RRF but supplies no formula or parameters. ADR-0040 explicitly states:

> This ADR does not define RRF mathematics, weighted fusion, global ranking,
> reranker fallback, or cross-source score comparison.

The repository does not define:

- whether the formula is `sum(1 / (k + rank))` or another variant;
- the rank constant `k` (commonly chosen values are not a contract);
- whether streams are equally weighted;
- whether every retriever invocation is one evidence list or results are first
  grouped by retrieval mode/subquery;
- whether repeated evidence from several subqueries of one mode contributes
  once or repeatedly; or
- the numerical type/precision rules for the fused score.

Choosing any of these would invent ranking behavior.

## Blocking contradiction 2 — fused `ScoredChunk` semantics are undefined

ADR-0002 defines `ScoredChunk.score` as a raw provider score and `source` as the
retrieval mode. After RRF, a duplicate canonical chunk has several source-local
scores/ranks but the frozen model has one `score`, one `source`, and one `rank`.

No accepted document defines whether the global result should contain:

- the RRF score or one retained raw score in `score`;
- `source="rrf"`, one winning source, or another value;
- which source/raw evidence survives when the same chunk appears in several
  streams; or
- how source evidence remains traceable without adding a field to
  `ScoredChunk`.

ADR-0040 resolves only local parent replacement and deliberately defers these
cross-source semantics. Cross-source deduplication therefore has no lawful
winner representation yet.

## Blocking contradiction 3 — hybrid ownership conflicts

Accepted ADR-0002 describes `HybridRetriever` as a `RetrieverInterfaceV1`
specialization that owns fusion of dense and sparse sequences. The detailed
roadmap assigns dense/sparse combination and RRF fusion to Module 6.5. The
current repository contains no `HybridRetriever`, while `QueryPlanner` may emit
`RetrievalMode.HYBRID`.

It is undefined whether a hybrid subquery:

- resolves one registry `retriever/hybrid` plugin;
- expands into dense and sparse registry invocations in Module 6.5;
- contributes one or two source-local streams;
- uses `max_results` per expanded retriever or across the hybrid operation; or
- participates in RRF independently from explicit dense/sparse subqueries.

Implementing orchestration under either interpretation would silently override
the other authoritative source.

## Blocking contradiction 4 — query-embedding handoff is incomplete

`DenseRetriever.retrieve()` requires a query embedding. `QueryPlanner` permits
up to sixteen subqueries and may emit several dense/hybrid subqueries, but
`plan_with_hyde_embedding()` returns exactly one vector: the embedding of the
first dense/hybrid subquery.

The repository does not define whether Module 6.5:

- receives a per-subquery embedding map;
- receives an embedding provider and embeds every dense/hybrid query;
- reuses the first HyDE vector for every dense/hybrid subquery; or
- rejects plans containing more than one vector-requiring subquery.

The conceptual input “RetrievalPlan” alone cannot execute all valid plans
against `DenseRetriever`. Adding hidden embedding generation or reusing the
wrong vector would violate the existing boundary.

## Blocking contradiction 5 — orchestration API and global bound are undefined

There is no existing orchestration contract or implementation. ADR-0040 says
Module 6.5 owns a later global candidate bound, but no document specifies:

- the orchestration method inputs and output;
- whether the caller supplies a global `top_k`;
- whether the bound is the maximum, sum, or another function of subquery
  `max_results`;
- whether truncation happens immediately after fusion or only at Module 6.6;
  or
- the allowed maximum global result count.

Per-subquery `max_results <= 100` and at most sixteen subqueries bound task
creation and individual retrieval, but they do not define the final global
candidate bound.

## Blocking contradiction 6 — global ordering and tie-breaking are undefined

ADR-0002 defines chunk-ID tie-breaking for one raw retriever stream. No accepted
contract extends that rule to fused scores, and ADR-0040 explicitly defers
global ranking. Completion order must not affect results, but the canonical
global tie-break sequence is not specified.

It is also undefined whether equal RRF scores are ordered by chunk ID, best
source-local rank, first planner-subquery position, source priority, or another
key. Global rank cannot be assigned without that decision.

## Blocking contradiction 7 — failure policy is undefined

ADR-0040 assigns parallel scheduling and failure policy to Module 6.5 without
choosing a policy. General ADR-0002 pipeline rules prohibit disguising failure
as success, but no Module 6.5 pipeline-result contract exists and no document
defines fail-fast versus explicit degraded success.

Undefined cases include:

- one retriever/subquery failure while other streams succeed;
- one parent-promotion or storage failure;
- unavailable registry slots for dense, sparse, hybrid, or graph modes;
- malformed retriever output;
- all streams failing; and
- cancellation of peer tasks after one failure.

Silently returning surviving streams is prohibited, but fail-fast behavior and
its cancellation/aggregation rules are not yet an accepted Module 6.5 contract.

## Blocking contradiction 8 — concurrency limit is unspecified

The plan bounds the number of subqueries, but no retrieval concurrency setting,
capability field, or fixed limit exists. “Run in parallel” does not specify
whether all bounded invocations run together or through a capacity limiter.
Provider/retriever capability metadata does not expose a concurrency limit.

The implementation therefore cannot satisfy the requested “configured
concurrency” or report a canonical observed concurrency policy without adding
an unapproved configuration or choosing a constant.

## Blocking contradiction 9 — reserved and future retrieval modes

The canonical enum also permits `GRAPH` and compatibility-reserved `PARENT`:

- ADR-0040 defines explicit rejection of `PARENT`, but says the rejection is a
  Module 6.5 responsibility.
- `GRAPH` is planner-valid, yet there is no completed Phase 6 GraphRetriever
  module or accepted unavailable-capability/degradation policy.
- `HYBRID` has the ownership conflict described above.

The executable-mode matrix and exact exception behavior require an accepted
decision before dispatch can be complete.

## Blocking contradiction 10 — plan flags at the 6.5 boundary

`requires_multi_hop=True` belongs to Module 6.10, but the current architecture
does not say whether Module 6.5 should execute only hop one, reject/defer the
plan, or return a status consumed by Module 6.10.

For `requires_multi_doc=True`, the architecture says retrieval is not filtered
by source, while each immutable `SubQuery` may still carry `source_ids` or a
`notebook_id`. Module 6.5 cannot strip immutable planner filters without
changing semantics, and no accepted invariant says such a plan is invalid.

Both flags must be consumed without reinterpreting Module 6.1 or implementing
Module 6.10, but the required behavior is not specified.

## Decisions required to unblock implementation

A new accepted ADR or explicit architectural resolution must define at least:

1. the Module 6.5 orchestration API and dependency set;
2. per-subquery query-vector ownership and identity;
3. the executable-mode matrix, especially `HYBRID`, `GRAPH`, and `PARENT`;
4. exact source-stream identity across retrievers and repeated subqueries;
5. RRF formula, constant, weights, contribution multiplicity, and precision;
6. cross-source duplicate aggregation and the resulting `ScoredChunk` score,
   source, and provenance semantics;
7. deterministic global tie-breaking and rank assignment;
8. the global candidate bound and when it is applied;
9. concurrency limiting and deterministic task/result collection;
10. fail-fast/degraded-result/cancellation semantics; and
11. exact handling of `requires_multi_hop` and inconsistent
    `requires_multi_doc` filters.

The decision must also reconcile ADR-0002's `HybridRetriever` ownership with
the detailed Module 6.5 schedule. Frozen `RetrieverInterfaceV1`,
`StorageInterfaceV1`, `MetadataFilter`, `ScoredChunk`, `Chunk`, and
`ParentPromotionInterfaceV1` must remain unchanged unless that decision
explicitly authorizes otherwise.

## Rejected workarounds

This investigation does not:

- assume the conventional RRF constant 60;
- compare, normalize, average, or sum dense and sparse raw scores;
- choose the first/strongest duplicate by incompatible raw score;
- put cross-source evidence into ad hoc metadata;
- treat every hybrid query as implicitly dense plus sparse;
- reuse one HyDE vector for unrelated dense subqueries;
- derive a global limit from arbitrary arithmetic over `max_results`;
- swallow one stream's failure and return partial success;
- use unbounded task spawning;
- strip planner filters to satisfy `requires_multi_doc`;
- implement hop-one policy on behalf of Module 6.10; or
- modify a frozen interface to force progress.

## Repository impact

- Module 6.1: remains COMPLETE.
- Module 6.2: remains COMPLETE.
- Module 6.3: remains COMPLETE.
- Module 6.4: remains COMPLETE.
- Module 6.5: **BLOCKED / NOT IMPLEMENTED**.
- Modules 6.6–6.10: NOT STARTED.
- M6: NOT VERIFIED.
- Version remains 0.20.1.
- No historical M4/M5 evidence or existing tag is modified.

## Verdict

The repository establishes where Module 6.5 belongs but not the deterministic
contract needed to implement it. ADR-0040 explicitly preserves this gate by
deferring RRF, global ranking, failure policy, and candidate bounds. Combined
with the unresolved hybrid ownership and query-vector handoff, proceeding would
require several speculative architectural choices.

Module 6.5 therefore remains **BLOCKED** pending an accepted orchestration and
fusion decision. No implementation or acceptance claim is permitted yet.

## Resolution addendum — ADR-0041

Accepted ADR-0041, `Deterministic Multi-Source Retrieval Orchestration and
Fusion`, resolves every blocker recorded above without rewriting this
historical investigation or changing a frozen contract.

The accepted resolution defines:

- an additive `MultiSourceRetrievalInterfaceV1` and provenance-preserving
  `RetrievalFusionResult` boundary;
- execution-time per-invocation embeddings through `EmbeddingProviderV1`;
- deterministic hybrid expansion into independent dense and sparse streams;
- one ADR-0040 promotion call per source-local stream before combination;
- immutable invocation traces and fused evidence rather than overloading
  `ScoredChunk`;
- unweighted RRF using one-based rank, `k=60`, and deterministic `math.fsum`;
- canonical chunk-ID grouping, global `(-rrf_score, chunk.id)` ordering, and a
  required caller `global_limit` from 1 through 100;
- shared configured concurrency (default 4, range 1 through 32);
- fail-fast execution with deterministic peer cancellation and no partial
  successful result;
- explicit rejection of graph and compatibility-reserved parent modes; and
- first-stage-only multi-hop behavior plus unchanged multi-document filters.

ADR-0041 supersedes only ADR-0002's specification-only `HybridRetriever`
ownership statement; the frozen `RetrieverInterfaceV1` and its raw-score
semantics remain intact.

The contradiction is therefore **ARCHITECTURALLY RESOLVED**. Module 6.5
production implementation and acceptance remain **NOT STARTED**.

## Implementation addendum — 2026-08-13

The historical stop and architectural resolution above are preserved. The
accepted ADR-0041 contract has since been implemented by the additive
`MultiSourceRetrievalInterfaceV1` and `MultiSourceRetriever`, validated by 83
focused implementation tests, the 970-pass repository suite, and a real
Bhagavad Gita/Ollama/Qdrant/SQLite acceptance run. Exact evidence is recorded
in `module-6.5-multi-source-retrieval-fusion-report.md` and
`milestone-evidence/module-6.5-fusion.json`.

Module 6.5 is now **COMPLETE**. Modules 6.6–6.10 remain **NOT STARTED**, and M6
remains **NOT VERIFIED**.
