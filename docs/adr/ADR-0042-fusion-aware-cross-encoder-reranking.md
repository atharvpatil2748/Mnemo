# ADR-0042: Fusion-Aware Cross-Encoder Reranking

- **Status:** Accepted
- **Date:** 2026-08-13
- **Decision owners:** Mnemo maintainers
- **Extends:** ADR-0002, ADR-0041
- **Preserves:** ADR-0001, ADR-0038, ADR-0039, ADR-0040
- **Resolves:** `module-6.6-reranking-contradiction-report.md`

## Context

Module 6.5 now returns `RetrievalFusionResult`, not a homogeneous source-local
`ScoredChunk` stream. Each `FusedChunkResult` carries a canonical `Chunk`, RRF
score, global rank, and every contributing `FusionEvidence` record. Those
records preserve dense/sparse raw scores, invocation identity, source-local
rank, retrieval mode, and parent-promotion provenance.

The frozen Phase 1 `RerankerInterfaceV1` accepts and returns
`tuple[ScoredChunk, ...]`. A `ScoredChunk` intentionally represents one raw
score, one source, and one local rank. Flattening the Module 6.5 result into
that shape would discard or mislabel accepted ADR-0041 evidence.

The architecture also lacked a canonical original query, a place for a
cross-encoder score, exact model/score semantics, a meaningful threshold,
deterministic ties, candidate-bound semantics, a complete fallback policy, and
a typed Module 6.7 handoff.

## Problem

Mnemo needs a bounded cross-encoder stage that can reorder fused candidates
without changing canonical chunks, raw retrieval scores, RRF scores, or
invocation provenance. It must support an explicit no-provider fallback while
surfacing actual provider failures, and it must remain compatible with the
frozen Phase 1 reranker and composition contracts.

## Existing contracts and ADR constraints

- `Chunk`, `ScoredChunk`, `RetrievalPlan`, `MetadataFilter`,
  `RetrieverInterfaceV1`, `StorageInterfaceV1`, `EmbeddingProviderV1`,
  `LLMInterfaceV1`, `ParentPromotionInterfaceV1`, and
  `MultiSourceRetrievalInterfaceV1` remain unchanged.
- `RerankerInterfaceV1` remains unchanged and retains its Phase 1/source-local
  compatibility purpose.
- ADR-0041 `RetrievalFusionResult` is the canonical Module 6.5 output.
- RRF and all raw retrieval evidence are immutable input evidence. Module 6.6
  does not recompute or overwrite them.
- The Module 6.5 `global_limit` already bounds the candidate set to at most 100.
- Filtering, retrieval, parent promotion, deduplication, and fusion are complete
  before Module 6.6 begins.

## Decision

Adopt an additive fusion-aware reranking boundary.

Module 6.6 consists conceptually of:

```text
canonical original query + RetrievalFusionResult
    -> RerankingModule
    -> optional fusion_reranker/primary capability
    -> pinned cross-encoder pair scoring when present
    -> deterministic reranked order OR typed RRF fallback
    -> RetrievalRerankResult
```

`RerankingModule` is the core stage. It resolves an optional
`FusionRerankerInterfaceV1` from a frozen `PluginRegistry`. Absence means an
explicit typed RRF fallback. A registered provider that fails never silently
falls back.

## Input contract

The additive stage protocol is:

```python
@runtime_checkable
class FusionRerankingInterfaceV1(Protocol):
    def capabilities(self) -> FusionRerankerCapabilities: ...

    async def rerank_fused(
        self,
        query: str,
        fusion_result: RetrievalFusionResult,
    ) -> RetrievalRerankResult: ...
```

`FusionRerankerCapabilities` is an additive frozen record with
`supports_cross_encoder: bool`, `supports_batch: bool`,
`preserves_fusion_evidence: bool`, `max_candidates: int`, `model_id: str`,
`model_revision: str`, and immutable metadata. V1 requires all three Boolean
capabilities true and `max_candidates == 100` for the reference provider.

The core `RerankingModule.execute()` exposes the same data inputs and output:

```python
async def execute(
    query: str,
    fusion_result: RetrievalFusionResult,
) -> RetrievalRerankResult: ...
```

The query is a separate required argument. `RetrievalPlan` is not changed.
The caller that owns the user request must pass the same canonical original
question used to request planning. Module 6.6 normalizes it with
`" ".join(query.split())`, rejects an empty result, stores the normalized value
in its output, and never substitutes a planner subquery or HyDE paragraph.

`fusion_result` is retained by identity and value in the output. The complete
bounded `fusion_result.results` tuple is processed. Module 6.6 performs no
retrieval, refill, overfetch, or candidate expansion.

## Output contract

The following additive immutable records are authoritative. Exact Python field
types use the existing immutable dataclass/Pydantic conventions.

### `RerankPolicy`

An enum with:

- `CROSS_ENCODER`: every non-empty candidate received a valid score;
- `RRF_FALLBACK`: no `fusion_reranker/primary` capability was registered; and
- `UNCHANGED_EMPTY`: the input candidate tuple was empty and no provider work
  occurred.

### `CrossEncoderEvidence`

Contains:

- `chunk_id: str`;
- `raw_logit: float`;
- `relevance_score: float`;
- `below_relevance_threshold: bool`;
- `model_id: str`; and
- `model_revision: str`.

Both scores must be finite. `relevance_score` must be strictly between zero and
one and equal the specified sigmoid transform of `raw_logit` within the
explicit validation tolerance `rel_tol=1e-12, abs_tol=1e-15`. The Boolean must equal
`relevance_score < 0.4`.

### `RerankedChunkResult`

Contains:

- `fused_result: FusedChunkResult`;
- `rerank_evidence: CrossEncoderEvidence | None`; and
- `reranked_rank: int`.

It does not duplicate or mutate `Chunk`, RRF, raw score, source, or invocation
fields. Cross-encoder policy requires evidence; fallback/empty policy forbids
it. Ranks are contiguous, one-based, and match tuple order.

### `RetrievalRerankResult`

Contains:

- `query: str` (normalized canonical original query);
- `fusion_result: RetrievalFusionResult` (the unchanged complete input);
- `policy: RerankPolicy`;
- `results: tuple[RerankedChunkResult, ...]`; and
- `fallback_reason: RerankFallbackReason | None`.

`RerankFallbackReason` V1 has exactly `PROVIDER_UNAVAILABLE`. It is present only
for `RRF_FALLBACK`. Empty input uses `UNCHANGED_EMPTY`, not a failure reason.
The output has exactly the same candidate identities and count as the Module
6.5 result.

This is the canonical Module 6.6-to-6.7 handoff.

## Query semantics

The cross-encoder pairs the one normalized original user question with each
candidate's canonical `Chunk.text`:

```text
(original_user_query, fused_result.chunk.text)
```

Planner subqueries, sparse keyword forms, and HyDE paragraphs remain available
as provenance but are not cross-encoder queries. No aggregation across
subqueries occurs.

The tokenizer must preserve the query. The reference provider uses a maximum
pair length of 512 tokens and `only_second` truncation: candidate text may be
truncated at the tail, but the query is never truncated. A query that cannot
fit with required special tokens fails contract validation.

## Model semantics

The built-in reference provider is fixed to:

- **Model ID:** `cross-encoder/ms-marco-MiniLM-L6-v2`
- **Revision:** `233902d25c440f23af6f7d6e94d2946bac0bee0a`
- **Architecture:** one-logit BERT sequence classifier, six MiniLM layers
- **Maximum pair length:** 512 tokens
- **License:** Apache-2.0
- **Backend:** sentence-transformers/PyTorch, `trust_remote_code=False`
- **Reference device:** CPU

The immutable revision was verified against the model repository's `main` ref
on 2026-08-13. The pinned model is maintained by the Sentence Transformers
cross-encoder organization and is documented for MS MARCO passage reranking.
The official model documentation reports NDCG@10 74.30, MRR@10 39.01, and
approximately 1,800 documents/second on a V100; these figures justify selecting
the L6 model as the smallest documented quality/throughput balance rather than
choosing it only by popularity.

Primary references:

- <https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2>
- <https://www.sbert.net/docs/cross_encoder/pretrained_models.html>
- <https://www.sbert.net/docs/package_reference/cross_encoder/model.html>

The reference provider must load only the pinned revision, prefer safetensors,
and refuse remote custom code. Normal operation may download the pinned public
artifact into the standard configured model cache during startup; air-gapped
operation requires the exact revision to be pre-provisioned and uses local-only
loading. No download occurs during a rerank call.

Alternative plugins may implement the same capability only if they expose a
single finite relevance logit per pair and stable model ID/revision. The
Module 6.6 acceptance milestone for the built-in implementation remains tied
to the pinned reference model.

## Score semantics

The provider returns the model's single **raw relevance logit** with identity
activation. Core Module 6.6 computes a stable sigmoid explicitly:

```text
relevance_score = 1 / (1 + exp(-raw_logit))
```

The stable implementation must avoid overflow. Sigmoid is monotonic, so it
does not change cross-encoder ordering. It supplies the defined `(0, 1)` domain
needed by the roadmap threshold while retaining the raw logit for audit.

`relevance_score` is a model-derived relevance value, **not a calibrated
probability or factual confidence**. The stale “confidence threshold” wording
is replaced by a low-relevance UI flag:

```text
below_relevance_threshold = relevance_score < 0.4
```

The boundary is strict: exactly `0.4` is not flagged. The threshold is a V1
architectural constant, not silently configurable.

RRF score, original global rank, every raw provider score, and all source-local
evidence remain unchanged inside `fused_result`. Cross-encoder score is never
written into `ScoredChunk.score`, `Chunk.metadata`, or `FusedChunkResult.rrf_score`.

## Candidate bound and truncation

Module 6.6 accepts exactly the complete Module 6.5 result (zero through 100
candidates) and emits exactly the same candidates. It has no `top_k` argument.
It cannot retrieve, request more, refill, expand, or drop candidates.

The Module 6.5 caller `global_limit` is authoritative for cross-encoder work.
Any later context/token selection belongs to Module 6.7 and operates on the
complete ordered `RetrievalRerankResult`.

For non-empty input with a registered provider, `RerankingModule` validates
that the provider returns `CROSS_ENCODER`, the same normalized query, the exact
input `RetrievalFusionResult`, and every candidate exactly once. A provider may
not return its own fallback policy. Any mismatch is an integrity failure.

## Ranking and determinism

For cross-encoder policy, order by:

```text
(-relevance_score, fused_result.global_rank, fused_result.chunk.id)
```

The prior global rank is the first tie-break so exact score ties retain the
already deterministic ADR-0041 order. Chunk ID is the final corruption-safe
tie-break. Completion order, batch boundaries, dictionary order, and device
scheduling never determine output.

After ordering, assign contiguous one-based `reranked_rank` values. Do not
alter `fused_result.global_rank`.

For RRF fallback and empty input, preserve Module 6.5 tuple order exactly and
set each non-empty wrapper's `reranked_rank` equal to its existing global rank.

## Provenance

Every `RerankedChunkResult` holds its original `FusedChunkResult`, and the
top-level result holds the original `RetrievalFusionResult`. Consequently the
following survive by construction:

- canonical chunk/document/version identity;
- RRF score and original global rank;
- every invocation ID and subquery index;
- declared/effective retrieval mode;
- source-local source, raw score, and rank;
- exact filters and requested top-k from invocation traces; and
- parent-promotion identity provenance.

No provenance is reconstructed from flattened data.

## Registry semantics

Add a distinct versioned capability family:

```text
CapabilityKind.FUSION_RERANKER = "fusion_reranker"
FUSION_RERANKER_INTERFACE_VERSION = "v1"
```

`PluginRegistry` gains additive methods consistent with existing families:

```text
register_fusion_reranker("primary", implementation, priority=..., plugin_name=...)
resolve_fusion_reranker("primary")
```

Existing registration validation, plugin compatibility, priority ordering,
equal-priority conflict detection, freeze behavior, deterministic descriptors,
and capability metadata apply unchanged.

The existing `reranker/v1` family and `RerankerInterfaceV1` are not modified.
A concrete cross-encoder plugin may explicitly implement and register both
interfaces, but there is no automatic flattening adapter and no legacy
registration is silently treated as fusion-aware.

`KnowledgeEngine` continues to resolve its historical required
`reranker/primary` exactly as ADR-0004 specifies. Module 6.6 independently
resolves optional `fusion_reranker/primary`. Therefore “no reranker configured”
at this boundary means no fusion-aware capability is registered; it does not
weaken the existing engine initialization contract.

## Provider lifecycle

Construction and plugin registration are inert. The reference provider loads
and validates the pinned model in an async registry startup hook before
capability resolution, following ADR-0018's established lifecycle pattern.
Initialization verifies:

- exact model ID/revision;
- local artifact completeness and license metadata;
- single-logit output shape;
- tokenizer maximum length of 512;
- identity output activation; and
- a deterministic finite smoke-score result.

Initialization failure is fatal when the plugin is registered. It is not
converted to RRF fallback.

Additive registry shutdown hooks release provider-owned executors and model
references in reverse registration order. All hooks are attempted; after
cleanup the first failure in deterministic reverse execution order is
surfaced. Existing providers need not register a shutdown hook. No frozen
provider interface gains lifecycle methods.

The reference provider owns one dedicated worker executor because PyTorch
inference is synchronous. It loads the model once, sets evaluation mode, uses
inference/no-gradient execution, and releases its resources only during the
registered shutdown hook.

## Batch and concurrency semantics

The input is one bounded request of at most 100 pairs. The reference provider:

- uses batch size 16;
- processes batches in input order;
- permits one active inference request per provider instance;
- queues concurrent calls in FIFO request-arrival order behind an async lock;
- performs no multi-device or multi-process inference in V1; and
- returns scores aligned to canonical input chunk IDs.

Batch boundaries do not change score or output ordering. A provider must return
exactly one score for every input identity, in input order, with no duplicate,
missing, or extra identity.

Reference CPU acceptance requires exact repeated identities/ranks and scores
equal within absolute tolerance `1e-6`; it does not claim bitwise stability
across different PyTorch, CPU, or operating-system builds.

## Failure, fallback, timeout, and cancellation semantics

V1 distinguishes absence from failure:

| Condition | Behavior |
|---|---|
| No `fusion_reranker/primary` registered | Return typed `RRF_FALLBACK` with `PROVIDER_UNAVAILABLE`; preserve ADR-0041 order |
| Reranking intentionally disabled by not registering the capability | Same typed fallback |
| Empty candidates | Return `UNCHANGED_EMPTY`; no provider resolution/work required |
| Registered provider fails initialization/model load | Engine/startup failure; no fallback |
| Inference/model execution failure | Propagate provider/plugin error; no partial result or fallback |
| Missing, extra, duplicate, reordered, malformed, or non-finite score | Raise integrity error; no partial result or fallback |
| Internal timeout | None in V1; no hidden deadline |
| Caller deadline/cancellation | Propagate cancellation; no result or fallback |
| Shutdown failure | Attempt all cleanup, then surface deterministic first failure |

This reconciles ADR-0002 and the roadmap: **unavailability** falls back;
**failure after registration** is surfaced. The roadmap regression requirement
must say “fusion reranker unavailable → existing RRF result retained,” not
“reranker failure → fallback succeeds.”

Cancellation of an awaited synchronous CPU inference cannot stop a PyTorch
kernel already running in the dedicated worker thread. The asyncio operation
still propagates cancellation immediately and discards its eventual result;
the bounded worker finishes at most the current 100-pair request before serving
another call or shutting down. There is no partial output.

## Module 6.7 handoff

Module 6.7 receives exactly one `RetrievalRerankResult`, regardless of policy.
It uses `results` in `reranked_rank` order and accesses each unchanged
`fused_result.chunk` for content and provenance. It does not rerun retrieval,
reconstruct evidence, guess score domains, or branch on incompatible input
types.

Module 6.7 may use the low-relevance flag as presentation/selection metadata
only under its future accepted contract. This ADR does not define context token
budgets, compression, or answer behavior.

## Alternatives rejected

### Flatten fused candidates into `ScoredChunk`

Rejected because it destroys or mislabels RRF and multi-invocation evidence.

### Modify `ScoredChunk`, `Chunk`, or `RerankerInterfaceV1`

Rejected because transient query evidence does not belong in canonical chunk
state and additive Phase 6 contracts solve the problem without breaking Phase
1.

### Store only cross-encoder ordering

Rejected because downstream modules require explicit score evidence and the
roadmap requires a threshold flag.

### Use one planner subquery or aggregate subquery scores

Rejected because neither represents the canonical user request and aggregation
would introduce an unspecified second fusion algorithm.

### Use raw model logits with threshold 0.4

Rejected because the roadmap threshold assumes a bounded domain. The explicit
sigmoid retains raw logit evidence and gives the threshold a stable meaning.

### Treat all provider errors as RRF fallback

Rejected because it disguises an explicitly configured broken provider as
successful reranking and contradicts ADR-0002 failure propagation.

### Change Module 6.5 global bounds or refill after reranking

Rejected because retrieval and candidate collection belong to Module 6.5.

## Compatibility impact

The decision is additive. All frozen models and interfaces remain unchanged.
Existing `reranker/v1` plugins and KnowledgeEngine behavior remain compatible.
New fusion-aware plugins opt into a separate capability family. Modules
6.1–6.5 and all persisted storage/index formats remain unchanged.

## Migration impact

No database, chunk, Qdrant, SQLite, blob, or historical milestone migration is
required. Reranking evidence is query-transient derived state.

Plugin authors who want canonical Phase 6 reranking must implement and register
`FusionRerankerInterfaceV1`. Existing plugins remain valid for the legacy
family but are not auto-adapted.

## Security and resource considerations

- Pinning the immutable model revision prevents upstream drift.
- `trust_remote_code=False` prevents model-supplied code execution.
- Safetensors is preferred over pickle-based weight loading.
- The model cache path must use repository/user configuration, never a private
  hard-coded path.
- Pair count, sequence length, batch size, and active inference are bounded.
- Candidate text is treated as data; it cannot change model/provider settings.
- Model download occurs only at startup/provisioning, never per query.
- Cancellation leaves at most one bounded CPU inference finishing in the
  provider-owned worker.

## Testing requirements

Implementation acceptance must cover:

- immutable model/result validation and protocol runtime checks;
- original-query normalization and proof that subqueries/HyDE are not used;
- empty, single, and 100-candidate inputs;
- exact identity/cardinality alignment;
- raw-logit retention, stable sigmoid, finite checks, exact 0.4 boundary;
- deterministic score/RRF-rank/chunk-ID ordering and contiguous reranked ranks;
- byte/value-equivalent preservation of the complete fusion result and every
  ADR-0041 evidence record;
- no retrieval, refill, RRF recomputation, chunk mutation, or score overwrite;
- registry registration, resolution, priority, conflict, freeze, descriptor,
  and legacy coexistence;
- unavailable typed fallback versus initialization/inference/integrity failure;
- caller cancellation and bounded residual-worker behavior;
- startup/model-revision validation and shutdown cleanup;
- deterministic controlled-provider tests; and
- real pinned-model reranking over a real Module 6.5 golden result.

## Acceptance requirements

Module 6.6 may be marked complete only after:

1. the additive contracts and registry capability are implemented;
2. the pinned reference provider is initialized and executed locally;
3. real Module 6.5 Bhagavad Gita output is reranked twice deterministically;
4. all raw, RRF, invocation, parent-promotion, document, and version evidence is
   verified unchanged;
5. unavailable fallback and actual provider failure paths are independently
   validated;
6. focused, cumulative Phase 6, full pytest, coverage, Ruff format/check,
   production mypy, pre-commit, and diff checks pass; and
7. documentation truthfully distinguishes unit, repository, and real-model
   validation.

## Consequences

### Positive

- Accepted ADR-0041 evidence survives reranking without flattening.
- Cross-encoder and RRF scores retain separate, explicit meanings.
- The roadmap threshold now has a stable domain and honest name.
- Optional fallback no longer disguises configured provider failures.
- Module 6.7 receives one uniform typed input for both scored and fallback paths.
- Phase 1 contracts and historical storage remain unchanged.

### Negative

- Module 6.6 adds a new capability family and immutable result types.
- The built-in model adds substantial optional runtime dependencies and a
  roughly 90 MB model artifact.
- CPU inference is serialized and cancellation cannot preempt an active native
  kernel, although residual work is strictly bounded.
- A concrete plugin that supports both legacy and fusion-aware paths must
  register both capabilities explicitly.

## Module boundary

Module 6.6 owns pair scoring, score validation/transform, deterministic
reranking, typed unavailable fallback, and the final reranked evidence record.
It does not own retrieval, RRF, context construction, answer generation,
citations, provenance persistence, or final QA integration.

At ADR acceptance time:

- Modules 6.1–6.5 are complete.
- Module 6.6 is **architecture resolved / implementation not started**.
- Modules 6.7–6.10 are not started.
- M6 is not verified.
- Version remains 0.20.1; no commit, push, tag, or release is authorized.
