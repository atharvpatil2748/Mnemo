# Module 6.6 Reranking Contradiction Report

## Status

**BLOCKED at the architectural gate.** Module 6.6 production code, tests,
acceptance runner, roadmap completion marks, and changelog were not created.

This report records the repository state inspected on 2026-08-13. An accepted
architectural decision is required before implementation because the canonical
Module 6.5 handoff and the frozen Phase 1 reranker contract cannot be connected
without losing required semantics.

## 1. Requirement

The engineering roadmap requires Module 6.6 to:

- implement a `CrossEncoderReranker` using a sentence-transformers MS MARCO
  model;
- batch-score `(query, chunk)` pairs;
- order candidates by cross-encoder score;
- flag confidence below `0.4`;
- retain the already-computed ADR-0041 RRF order when no reranker is available;
  and
- preserve Module 6.5 identity and provenance while remaining bounded and
  deterministic.

Module 6.6 must not retrieve more chunks, recompute RRF, mutate canonical
chunks, build context, synthesize answers, generate citations, or implement
final QA integration.

## 2. Existing architecture

The implemented retrieval flow is:

```text
RetrievalPlan
  -> MultiSourceRetriever
  -> bounded source-local dense/sparse streams
  -> ParentPromotionInterfaceV1 once per stream
  -> chunk-ID deduplication
  -> deterministic RRF
  -> RetrievalFusionResult
  -> Module 6.6
```

ADR-0041 makes `RetrievalFusionResult` the canonical Module 6.5 output. It
contains the original plan, every `RetrievalInvocationTrace`, and bounded
`FusedChunkResult` values. Each fused result contains one canonical `Chunk`, an
RRF score, a global rank, and every contributing `FusionEvidence` record.

`FusionEvidence` retains invocation identity, subquery index, declared and
effective retrieval modes, the source-local `ScoredChunk` (raw score, source,
rank), and whether parent promotion introduced the surviving identity.

ADR-0041 explicitly says the exact Module 6.6 input contract is outside its
scope and must preserve this provenance.

## 3. Existing contracts

### Frozen `RerankerInterfaceV1`

The Phase 1 protocol is:

```python
async def rerank(
    query: str,
    candidates: tuple[ScoredChunk, ...],
    top_k: int,
) -> tuple[ScoredChunk, ...]: ...
```

ADR-0002 says it preserves input scores, returns candidates ordered by
descending reranker score, assigns contiguous ranks, and surfaces provider
failure. `RerankerCapabilities.preserves_raw_scores` reinforces the raw-score
requirement.

`ScoredChunk` represents exactly one ranking source's raw score, singular
source, and local rank. It cannot represent an RRF score plus multiple raw
evidence records plus a cross-encoder score.

### Registry and configuration

`PluginRegistry` already has the versioned `reranker` capability family and
resolves `RerankerInterfaceV1`. `KnowledgeEngine` requires the `primary`
reranker slot during initialization. `RerankerConfig` contains only required
`provider` and `model` strings; it has no enabled flag, candidate limit,
threshold, batch size, concurrency, score transform, or failure-policy field.

### Frozen domain models

- `Chunk` is immutable canonical content. Its `metadata` is canonical chunk
  metadata, not transient reranking state.
- `ScoredChunk` is immutable source-local raw evidence.
- `FusedChunkResult` is immutable fused evidence with RRF score/global rank.
- `RetrievalFusionResult` is the immutable provenance-preserving orchestration
  output.

None has an authorized cross-encoder-score or low-confidence field.

## 4. Relevant ADRs

- **ADR-0001** freezes `Chunk` and `ScoredChunk` domain semantics.
- **ADR-0002** freezes `RerankerInterfaceV1`, raw-score preservation, async
  execution, provider failure propagation, and registry behavior.
- **ADR-0038** and **ADR-0039** require exact-version filtering before dense or
  sparse ranking; reranking must not broaden that eligible set.
- **ADR-0040** requires parent-promotion provenance and source-local operation.
- **ADR-0041** defines the canonical fused representation, raw-evidence
  preservation, RRF/global rank, Module 6.5 candidate bound, and the no-recompute
  RRF fallback. It deliberately leaves the exact Module 6.6 contract undecided.

No accepted ADR bridges `RetrievalFusionResult` to `RerankerInterfaceV1` or
defines the missing Module 6.6 semantics below.

## 5. Actual Module 6.5 output contract

`MultiSourceRetrievalInterfaceV1.execute()` returns one
`RetrievalFusionResult`. The result is already bounded by the caller's
`global_limit` (1 through 100). Its ordered `results` are globally ranked
`FusedChunkResult` values. Module 6.6 therefore receives neither a homogeneous
`ScoredChunk` stream nor one raw score/source domain.

The result may represent up to sixteen planner subqueries and two effective
retrieval invocations per hybrid subquery. `RetrievalPlan` retains those
subquery texts but does not retain a separate canonical original user query.

## 6. Genuine contradictions

### 6.1 Input and output types are incompatible

The canonical handoff is `RetrievalFusionResult`, but
`RerankerInterfaceV1.rerank()` accepts `tuple[ScoredChunk, ...]` and returns the
same type. Converting each fused candidate to a `ScoredChunk` requires choosing
one singular source and score. Every possible choice loses or mislabels at
least one of:

- RRF score and global rank;
- multiple invocation identities;
- multiple dense/sparse raw scores and local ranks;
- declared/effective modes; or
- parent-promotion provenance.

Passing `rrf_score` as `ScoredChunk.score` would violate its raw-provider-score
meaning. Choosing one evidence record would silently discard other evidence.

### 6.2 Cross-encoder score has no lawful representation

ADR-0002 simultaneously requires descending reranker-score ordering and says
the reranker does not mutate input scores. The frozen output provides no
separate reranker-score field. `FusedChunkResult` likewise has no reranker
score. Writing transient confidence into immutable `Chunk.metadata`, as the
roadmap wording suggests through `ScoredChunk.metadata`, is impossible because
`ScoredChunk` has no metadata field and would corrupt canonical `Chunk` state.

### 6.3 The scoring query is undefined

The cross-encoder requires one `(query, chunk)` pair per candidate. A
`RetrievalFusionResult` can contain several decomposed, sparse, dense, hybrid,
or HyDE-like subquery texts, while `RerankerInterfaceV1` accepts one query.
`RetrievalPlan` does not preserve a separate original user query. The
repository does not say whether reranking uses:

- the original user question (which is unavailable in the canonical handoff);
- the first subquery;
- every subquery with an aggregation rule;
- only evidence-contributing subqueries; or
- a HyDE paragraph.

These choices produce materially different rankings and cannot be inferred.

### 6.4 Model and score semantics are underspecified

“sentence-transformers ms-marco model” identifies a model family, not an exact
model/revision. No sentence-transformers dependency or concrete cross-encoder
provider exists. The repository does not define:

- exact model identifier and immutable revision;
- raw logit versus sigmoid/probability output;
- finite score validation and valid score range;
- batching/device behavior;
- maximum input length or truncation policy; or
- whether `0.4` is meaningful in the chosen score domain.

Calling an unspecified raw logit a confidence value, or applying an arbitrary
normalization, would invent architecture.

### 6.5 Fallback and failure semantics conflict

ADR-0002 says provider failures are surfaced and fallback belongs to the
retrieval pipeline. The architecture describes retaining RRF when no model is
configured. The roadmap regression requirement says “reranker failure → RRF
fallback succeeds.” These do not define whether fallback applies to:

- deliberate disablement;
- missing registry capability;
- provider initialization failure;
- per-batch inference failure;
- malformed/non-finite provider output;
- cancellation; or
- only an explicitly unavailable model.

`KnowledgeEngine` currently requires a `primary` reranker, while configuration
requires provider/model values, contradicting the “no reranker configured”
path unless a no-op provider or a new optional orchestration capability is
approved.

### 6.6 Deterministic ranking and truncation are incomplete

ADR-0002 requires deterministic ties but does not specify the tie key. It is
undefined whether equal cross-encoder scores retain RRF order or use chunk ID.
The input is already bounded by Module 6.5, but the roadmap does not define
whether Module 6.6 may truncate further, what its `top_k` is, or whether the
future Module 6.7 consumes the whole reranked candidate set. Retrieving or
refilling additional candidates would violate the 6.5 boundary and is
therefore not a lawful inference.

### 6.7 Batch, concurrency, and cancellation semantics are incomplete

The protocol is asynchronous and advertises batch support, but no authoritative
batch size, concurrency limit, executor/thread policy, timeout, or cancellation
contract exists for a local synchronous cross-encoder library. Partial batch
success is also undefined.

### 6.8 Module 6.7 handoff is undefined

Architecture prose says ContextBuilder consumes ranked chunks, but no accepted
typed contract says whether it consumes fused results, reranked results, or a
fallback union. Implementing Module 6.6 without its output contract would only
move the contradiction to Module 6.7.

## 7. Why the contradictions are architectural

These are not implementation details. They determine public/additive types,
score meaning, provenance retention, provider lifecycle, deterministic rank,
failure visibility, and the next module's handoff. Any implementation choice
would either modify a frozen contract, discard accepted ADR-0041 evidence, or
silently select semantics that the repository does not authorize.

Unit tests cannot make those choices authoritative. A concrete model cannot be
safely installed or invoked until its score and lifecycle contract are fixed.

## 8. Affected files and contracts

An approved resolution will affect or clarify at least:

- `mnemo-core/mnemo/interfaces/reranker.py` (preserved or explicitly scoped as
  the legacy/source-local Phase 1 contract);
- a new additive Phase 6 reranking interface, if selected;
- `mnemo-core/mnemo/models/retrieval.py` through additive result/evidence
  records only;
- `mnemo-core/mnemo/registry.py` capability ownership or slot semantics;
- `mnemo-core/mnemo/config.py` if disablement, threshold, batch, device, or
  concurrency become configurable;
- the future concrete cross-encoder provider and composition lifecycle;
- Module 6.6 architecture/roadmap text; and
- the typed Module 6.7 input boundary.

The frozen `Chunk`, `ScoredChunk`, `RetrievalPlan`, `MetadataFilter`, storage,
retriever, embedding, parent-promotion, and multi-source interfaces need not be
changed under the recommended solution.

## 9. Possible compliant solutions

### Option A — Additive fusion-aware reranking contract

Define an immutable Phase 6 contract that accepts the original user query
explicitly plus `RetrievalFusionResult` and returns a new immutable
provenance-preserving result. Each output item would contain:

- the unchanged `FusedChunkResult`;
- a separately named finite cross-encoder score;
- an explicit low-confidence flag in the approved score domain; and
- a contiguous reranked rank.

The complete result would retain the original `RetrievalFusionResult`, the
effective policy (cross-encoder or RRF fallback), and any typed non-success
state approved by the failure decision. The contract would be asynchronous,
bounded by its input, and unable to retrieve/refill candidates.

The ADR must decide whether this orchestration contract resolves an existing
`RerankerInterfaceV1` scoring provider or introduces a narrowly typed
cross-encoder scoring-provider capability. The existing frozen interface may
remain available for backward compatibility but cannot be the canonical
Module 6.5-to-6.6 handoff unchanged.

### Option B — Explicitly revise `RerankerInterfaceV1`

Change its input/output to fusion-aware records. This is simpler superficially
but is a breaking Phase 1 contract change affecting registry compatibility,
engine composition, tests, and plugins. It violates the preferred additive
discipline and is not recommended.

### Option C — Flatten fused results into `ScoredChunk`

Rejected. This loses evidence or overloads raw-score/source semantics and
contradicts ADR-0041.

### Option D — Mutate `Chunk.metadata`

Rejected. Cross-encoder confidence is query-transient derived evidence, not
canonical chunk state. It would alter chunk snapshots and identities across
queries.

### Option E — Leave RRF order unchanged and call it reranking

Rejected. That is only the fallback result from Module 6.5 and does not
implement the roadmap's cross-encoder requirement.

## 10. Recommended smallest compliant solution

Create and approve the next unique ADR defining a **fusion-aware additive
reranking boundary**. It should:

1. preserve `RetrievalFusionResult` unchanged as input evidence;
2. require the canonical original user query as an explicit input rather than
   inferring one from subqueries;
3. add immutable `RerankEvidence`, `RerankedChunkResult`, and
   `RetrievalRerankResult`-style records (exact names subject to ADR);
4. store cross-encoder score separately from RRF and raw provider scores;
5. retain every invocation and parent-promotion record through a reference to
   the unchanged fused candidate/result;
6. define one exact model/revision and its raw/normalized score semantics before
   adopting the `0.4` threshold;
7. define equal-score ordering, preferably cross-encoder score descending then
   prior RRF global rank then canonical chunk ID;
8. prohibit retrieval, refill, RRF recomputation, and candidate expansion;
9. define optional/unavailable versus failed/cancelled behavior explicitly;
10. define the concrete batch/concurrency/cancellation policy;
11. define the registry relationship while leaving
    `RerankerInterfaceV1` frozen; and
12. establish this result as the exact Module 6.7 input or explicitly defer
    that handoff with enough retained information for 6.7.

This is the smallest approach that preserves ADR-0041 provenance and Phase 1
compatibility without pretending a fused result is a source-local
`ScoredChunk`.

## 11. Compatibility impact

The recommended option is additive. Existing Phase 1 plugins and registry
descriptors remain compatible. Modules 6.1–6.5 remain unchanged. Persisted
chunks, relational data, Qdrant collections, SQLite FTS state, and historical
M4/M5 evidence remain untouched.

A new capability family or explicit adapter policy may require additive
registry/version metadata and composition wiring. That must be specified by
the accepted ADR rather than implemented implicitly.

## 12. Migration impact

No data migration or reindexing is required because reranker scores are
query-transient derived evidence. No historical Qdrant, SQLite, or milestone
collection should be modified.

Plugin migration is unnecessary if the Phase 1 reranker capability remains
frozen. If the accepted decision supersedes that capability for the canonical
Phase 6 path, it must define coexistence and discovery rules.

## 13. Future-module isolation

The recommended result preserves canonical chunks, all raw and RRF evidence,
and the final reranked order without constructing context. Module 6.7 can
consume it without rerunning retrieval. Modules 6.8–6.10 remain unaffected:
there is no answer generation, citation persistence, or multi-hop execution in
the decision.

## 14. Explicit approval required

Implementation must not proceed until maintainers approve an ADR resolving:

1. the fusion-aware input/output contract;
2. the canonical scoring query;
3. exact provider/model/revision and score domain;
4. confidence-threshold semantics;
5. registry/capability ownership;
6. unavailable, failure, malformed-output, timeout, and cancellation behavior;
7. exact tie-breaking and truncation behavior;
8. batch/concurrency policy; and
9. the typed Module 6.7 handoff.

Until then:

- Modules 6.1–6.5 remain **COMPLETE**.
- Module 6.6 is **BLOCKED / NOT IMPLEMENTED**.
- Modules 6.7–6.10 remain **NOT STARTED**.
- M6 remains **NOT VERIFIED**.
- Version remains **0.20.1**.
- No commit, push, tag, or release is permitted.

## Resolution addendum — ADR-0042

Accepted ADR-0042, `Fusion-Aware Cross-Encoder Reranking`, resolves every
contradiction above without changing a frozen contract or deleting this
historical investigation.

The accepted resolution defines:

- a separate original-user-query plus `RetrievalFusionResult` input;
- additive immutable `CrossEncoderEvidence`, `RerankedChunkResult`, and
  `RetrievalRerankResult` records;
- a distinct `fusion_reranker/v1` registry capability, with no implicit legacy
  adapter;
- pinned `cross-encoder/ms-marco-MiniLM-L6-v2` revision
  `233902d25c440f23af6f7d6e94d2946bac0bee0a`;
- raw single-logit evidence plus an explicit stable sigmoid relevance score;
- strict low-relevance threshold `score < 0.4`, not probabilistic confidence;
- exact cardinality preservation, no retrieval/refill/recomputation, and
  ordering by relevance descending, prior RRF rank, then chunk ID;
- typed fallback only when the fusion-aware capability is absent, while
  initialization/inference/integrity failures and cancellation propagate;
- bounded CPU batching, single-flight provider execution, startup/shutdown
  ownership, and caller-owned deadlines; and
- `RetrievalRerankResult` as the exact future Module 6.7 input.

The contradiction is therefore **ARCHITECTURALLY RESOLVED**. Module 6.6
production implementation and acceptance remain **NOT STARTED**. Modules
6.7–6.10 remain **NOT STARTED**, and M6 remains **NOT VERIFIED**.

## Implementation resolution addendum — 2026-08-13

Module 6.6 was subsequently implemented and validated exactly under ADR-0042.
The historical contradiction and architecture-resolution statements above are
preserved. Durable implementation and live evidence are recorded in
`docs/module-6.6-reranking-report.md` and
`docs/milestone-evidence/module-6.6-reranking.json`. Module 6.7 remains not
started and milestone M6 remains unverified.
