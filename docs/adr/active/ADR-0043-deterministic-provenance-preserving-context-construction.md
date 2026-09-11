# ADR-0043: Deterministic Provenance-Preserving Context Construction

- **Status:** Accepted
- **Date:** 2026-08-13
- **Decision owners:** Mnemo maintainers
- **Extends:** ADR-0015, ADR-0042
- **Preserves:** ADR-0002, ADR-0040, ADR-0041
- **Resolves:** `module-6.7-context-construction-contradiction-report.md`

## Context

ADR-0042 establishes `RetrievalRerankResult` as the complete Module 6.6 output
and the exact Module 6.7 input. Its ordered `RerankedChunkResult` records retain
canonical chunks, RRF evidence, raw source-local evidence, cross-encoder
evidence when available, and the original `RetrievalFusionResult`.

The roadmap requires Module 6.7 to build bounded attributed context, preserve
the top three candidates verbatim, and compress lower-ranked candidates through
the Extractor LLM. Existing documents did not define the output, exact budget
accounting, selection, compression, attribution, empty outcomes, or Module 6.8
handoff. ADR-0042 intentionally deferred those decisions.

## Problem and scope

Module 6.7 needs one deterministic, backend-neutral contract that converts an
already bounded `RetrievalRerankResult` into attributed context without
retrieval, reranking, candidate expansion, provenance reconstruction, or
canonical `Chunk` mutation.

This ADR owns context budgeting, selection, optional compression, rendering,
and the typed Module 6.8 handoff. It does not define answer generation,
citations, persistence, final QA orchestration, or any Module 6.8–6.10 behavior.

## Existing constraints

- `RetrievalRerankResult.results` is complete, bounded to at most 100, and
  ordered by contiguous `reranked_rank`.
- `TokenCounterInterfaceV1` is the existing token abstraction. ADR-0015 fixes
  the canonical implementation to the verified offline `o200k_base` asset and
  `tiktoken==0.13.0` adapter V1.
- `LLMInterfaceV1` and registry slot `llm/extractor` already provide the
  provider-neutral compression boundary.
- `Chunk` exposes exact document/version identity, heading path, page position,
  and text, but it does not guarantee a document title.
- All Phase 1 interfaces and Modules 6.1–6.6 result contracts remain frozen.

## Alternatives considered

### Return only a rendered string

Rejected because Module 6.8 would have to reconstruct source numbering and
provenance from text.

### Resolve document titles from storage inside ContextBuilder

Rejected because context construction is a pure transformation and must not
depend on SQLite, Qdrant, SurrealDB, or `StorageInterfaceV1` lookups.

### Truncate arbitrary chunks to fill every token

Rejected because it creates blind semantic splitting and undermines canonical
chunk boundaries. Compression is the authorized lower-ranked reduction path.

### Group and reorder by document

Rejected because it would override the authoritative reranked order. Item
markers provide source segmentation without reordering.

### Exclude all low-relevance candidates

Rejected because ADR-0042 defines the flag as model-derived presentation
metadata, not factual confidence or an eligibility filter.

### Add a compression-specific provider interface or registry family

Rejected because `LLMInterfaceV1` and the existing `llm/extractor` slot are
sufficient.

## Decision

Adopt an additive immutable context-construction boundary. `ContextBuilder`
depends on a frozen `PluginRegistry` and one `TokenCounterInterfaceV1`; it has
no storage or retrieval dependency.

The canonical async operation is:

```python
async def build(
    rerank_result: RetrievalRerankResult,
    *,
    context_budget: int,
    system_prompt: str,
    session_history: tuple[Message, ...] = (),
    document_labels: tuple[DocumentContextLabel, ...] = (),
) -> ContextBuildResult
```

The question is always `rerank_result.query`. It is not supplied a second time.
Construction validates that results are in `reranked_rank` order and never
reruns an earlier pipeline stage.

## Additive immutable records

The implementation adds these frozen, slotted records and enums without
changing existing models:

### `DocumentContextLabel`

```text
document_id: UUID
version_id: UUID
title: str
```

Labels are caller-supplied display data keyed by exact
`(document_id, version_id)`. The tuple must have unique keys. It may be partial;
missing labels do not fail construction. Labels never authorize retrieval or
change canonical identity.

### `ContextItemKind`

Exactly `VERBATIM` or `COMPRESSED`.

### `CompressionEvidence`

Present only for compressed items and contains:

```text
extractor_provider: str
extractor_model: str
target_tokens: 100
hard_max_tokens: 120
compressed_token_count: int
```

It does not duplicate chunk/retrieval evidence.

### `ContextItem`

```text
source_number: int
reranked_result: RerankedChunkResult
kind: ContextItemKind
content: str
content_token_count: int
rendered_text: str
rendered_token_count: int
compression_evidence: CompressionEvidence | None
```

`reranked_result` is the exact original object. Verbatim `content` equals
`reranked_result.fused_result.chunk.text`. Compressed content is query-transient
and never replaces or mutates canonical chunk text.

### `ContextEmptyReason`

Exactly:

- `NO_CANDIDATES`
- `FIXED_OVERHEAD_EXHAUSTED`
- `VERBATIM_PREFIX_DOES_NOT_FIT`
- `NO_ITEM_FITS`

### `ContextBuildResult`

```text
rerank_result: RetrievalRerankResult
tokenizer_id: str
context_budget: int
fixed_overhead_tokens: int
available_context_tokens: int
context_tokens: int
rendered_context: str
items: tuple[ContextItem, ...]
omitted_results: tuple[RerankedChunkResult, ...]
compression_available: bool
empty_reason: ContextEmptyReason | None
```

The top-level `rerank_result` and every selected/omitted result are retained by
identity. Selected plus omitted identities exactly partition the input
candidates. Non-empty output has no `empty_reason`; empty output has exactly one.
Module 6.8 consumes this complete `ContextBuildResult` and must not parse the
rendered context to recover provenance.

## Token-budget semantics

`context_budget` is a strict positive integer from 1 through 1,000,000. There
is no Module 6.7 default: transport/caller configuration must supply it. The
upper bound is a V1 resource-safety ceiling, not a model context claim.

`system_prompt` is a string and may be empty. `session_history` is an immutable
tuple of validated `Message` records. The canonical fixed-input serialization
is exactly:

```text
SYSTEM
{system_prompt}
QUESTION
{rerank_result.query}
HISTORY
{role.value}\n{content}\n  # repeated in tuple order; absent when empty
```

There is one newline after `HISTORY`, including for empty history. No message
metadata is serialized. `fixed_overhead_tokens` is
`token_counter.count(canonical_fixed_serialization)`.

This is a text-envelope budget. Provider-specific chat framing and future
answer-generation reserve are outside Module 6.7 and must be accounted for by
the caller when choosing `context_budget`; Module 6.7 adds no guessed framing
constant.

```text
available_context_tokens = max(0, context_budget - fixed_overhead_tokens)
```

The rendered context, including every marker and the exact `"\n\n"` separator
between items, is counted as one complete string. A candidate is accepted only
when `token_counter.count(prospective_rendered_context) <=
available_context_tokens`. Thus token-boundary merges are accounted for and the
reported context count is exact rather than the sum of independently counted
pieces.

The tokenizer must satisfy `TokenCounterInterfaceV1`. The reference and real
acceptance implementation uses ADR-0015 `O200KBaseTokenCounter`; the result
records its exact `tokenizer_id`.

If fixed overhead is greater than or equal to the total budget, return a typed
empty result with `FIXED_OVERHEAD_EXHAUSTED` and perform no Extractor work.

## Attribution marker contract

`[N]` identifies exactly one selected context item, not a document or mutable
Source relationship. Numbering occurs after selection in final item order and
is contiguous from one. Multiple chunks from the same version receive distinct
numbers. Multiple versions never share an identity.

The one-line marker is assembled in this exact field order:

```text
=== Source [N] | document_id=<UUID> | version_id=<UUID>[ | title=<JSON string>][ | heading=<JSON string>][ | page=<positive integer>] ===
```

- `document_id` and `version_id` are always present and use canonical lowercase
  UUID string form.
- `title` is included only when an exact `DocumentContextLabel` exists and is
  encoded as a compact JSON string (`ensure_ascii=False`). No metadata key or
  placeholder title is invented.
- `heading` is included only when `heading_path` is non-empty, rendered by
  joining entries with `" > "`, then encoded as a compact JSON string.
- `page` is included only when `Chunk.position.page_number` is present.
- Missing optional fields are omitted, not replaced with `unknown`.

`rendered_text` is `marker + "\n" + content`. The full context joins item
renderings with exactly two newline characters. Document grouping is visual by
markers only; it never reorders the authoritative reranked stream.

## Normative selection algorithm

Let `ordered` be the input results in ascending `reranked_rank`. Let
`mandatory = ordered[:min(3, len(ordered))]`.

1. Validate input, labels, budget, and fixed serialization.
2. If there are no candidates, return empty `NO_CANDIDATES`; no Extractor work.
3. If fixed overhead exhausts the budget, return empty
   `FIXED_OVERHEAD_EXHAUSTED`; all candidates are omitted.
4. Render all mandatory candidates verbatim with prospective source numbers
   1..M. If their combined rendered context does not fit, return an entirely
   empty `VERBATIM_PREFIX_DOES_NOT_FIT`. Do not partially include, truncate, or
   compress the mandatory prefix.
5. Accept the complete mandatory prefix verbatim.
6. Traverse every remaining candidate once in `reranked_rank` order:
   a. Render it verbatim using the next prospective source number. If the whole
      prospective context fits, accept it verbatim.
   b. Otherwise, if `llm/extractor` is absent, omit it and continue.
   c. Otherwise request one per-chunk compression. If the validated compressed
      rendering fits, accept it; if it does not fit, omit it and continue.
7. Never stop merely because one candidate does not fit: later smaller
   candidates may fill remaining space. This is deterministic skip-over greedy
   selection.
8. Never truncate canonical or compressed text. Exact fits are accepted.
9. Assign final contiguous source numbers in the already selected order and
   produce the exact rendered context. Since prospective numbering is
   contiguous and selection never removes an accepted item, final numbering is
   identical to prospective numbering.

There is no separate minimum useful item size. A complete non-empty canonical
chunk or valid compression is useful if its fully rendered form fits. If the
mandatory prefix is empty and no later item can fit (a defensive condition),
return `NO_ITEM_FITS`.

The “top three verbatim” rule therefore means reranked ranks 1 through
`min(3, candidate_count)` are an all-or-empty mandatory prefix. Budget
invariants take precedence over partial degradation: inability to fit the
prefix returns a typed empty result rather than violating either rule.

## Compression contract

Only candidates after the mandatory prefix whose verbatim prospective context
does not fit are compression eligible. Compression is one candidate per call,
sequential in traversal order. V1 concurrency is exactly one; no task fan-out
or combined summaries are allowed.

ContextBuilder resolves the existing `llm/extractor` slot from its frozen
`PluginRegistry`. No new capability or interface is introduced. Absence is
graceful: `compression_available=False`; eligible candidates are omitted.
Resolution is a side-effect-free registry lookup performed once per build,
including typed empty builds, so `compression_available` always reports the
actual frozen-registry state. Empty builds never call the resolved provider.

The exact system prompt is:

```text
Compress one retrieved passage for grounded question answering. Preserve only claims supported by the passage, retain names, dates, quantities, qualifications, and negation, and do not add facts. Return JSON matching the supplied schema. The summary must be self-contained and at most 100 o200k_base tokens.
```

The sole `USER` message content is compact canonical JSON (`ensure_ascii=False`,
`sort_keys=True`, separators `(',', ':')`) with exactly:

```json
{
  "chunk_id": "<canonical SHA-256 id>",
  "document_id": "<UUID>",
  "query": "<rerank_result.query>",
  "text": "<canonical Chunk.text>",
  "version_id": "<UUID>"
}
```

The `structured_output` argument is the immutable JSON schema for exactly one
required string field `summary`, with no additional properties. Call
`complete(..., max_tokens=120)`. The prompt/message token count plus 120 must
not exceed `extractor.max_context_tokens`; otherwise raise
`ContractValidationError` before invoking the provider.

The response must be structured data with exactly `summary`; the value is
whitespace-normalized by `" ".join(summary.split())`, must remain non-empty,
must contain no unpaired Unicode surrogate, and must count from 1 through 120
tokens. The prompt target is 100; 120 is the hard validation allowance. Output
over 120 is malformed and is never silently truncated.

No retry, timeout, or cache is added in V1. Caller cancellation propagates.
Registered provider exceptions, malformed output, nonconforming schema, and
input-window violations propagate; no partial `ContextBuildResult` is returned.
The caller owns any external timeout. Provider absence is the only compression
degradation path.

LLM text is not claimed byte-deterministic. Contract-level determinism means
fixed candidate traversal, call order, prompts, validation, selection,
numbering, and rendering: given identical validated provider outputs, the
result is identical. Evidence records the provider/model; V1 does not cache
compressions.

## Low-relevance semantics

`CrossEncoderEvidence.below_relevance_threshold` has no selection or
compression effect in V1. Low-relevance candidates follow the same ranked
algorithm and retain their evidence. The flag is not factual confidence,
probability, hallucination score, or a retrieval failure. An RRF-fallback item
with no cross-encoder evidence is treated identically.

## Empty and failure semantics

- Empty rerank candidates: valid empty `NO_CANDIDATES` result.
- Fixed overhead greater than or equal to budget: valid empty
  `FIXED_OVERHEAD_EXHAUSTED` result.
- Mandatory verbatim prefix cannot fit: valid empty
  `VERBATIM_PREFIX_DOES_NOT_FIT` result.
- Extractor unavailable: graceful compression degradation; eligible candidates
  are omitted and `compression_available=False`. Already accepted verbatim
  items remain valid.
- Only low-relevance candidates: normal selection; no special empty state.
- Compressed rendering still does not fit: omit it and continue.
- Extractor returns unusable output or fails: integrity/provider failure;
  propagate with no partial result.
- All compression attempts fail: the first failure propagates because calls are
  sequential; it is not represented as valid empty context.

Module 6.8 receives every valid empty result as typed input and decides answer
behavior later. This ADR does not prescribe an answer.

## Provenance and immutability

Every selected `ContextItem` holds its exact original `RerankedChunkResult`:

```text
ContextItem
  -> RerankedChunkResult
    -> FusedChunkResult
      -> FusionEvidence
        -> ScoredChunk
```

The top-level result retains the exact `RetrievalRerankResult`, including its
complete `RetrievalFusionResult`. Thus chunk/document/version identity, RRF
score, original global rank, reranked rank, invocation IDs, subquery index,
retrieval modes, source-local source/rank/raw score, parent-promotion evidence,
and cross-encoder evidence survive without duplication or reconstruction.

Compression and display labels are query-transient. They never mutate `Chunk`,
`Chunk.metadata`, or any prior-stage evidence.

## Determinism and ordering guarantees

- Candidate traversal is ascending `reranked_rank`; malformed order fails.
- Existing rerank tie-breaking remains authoritative; Module 6.7 adds none.
- Selection is the normative sequential skip-over algorithm above.
- Compression calls are sequential and ordered by candidate traversal.
- Source numbering is post-selection contiguous item order.
- No document grouping reorders results.
- Canonical JSON, marker fields, separators, and token counting are exact.
- Provider completion timing cannot affect ordering.
- Identical inputs, tokenizer, labels, and validated compression outputs produce
  an identical immutable result.

## Registry and lifecycle

ContextBuilder receives a frozen existing `PluginRegistry` and resolves
`llm/extractor` once per build before compression begins. Existing registry
priority, conflict, version, freeze, startup, and provider lifecycle semantics
apply unchanged. ContextBuilder does not construct, initialize, or shut down the
LLM. No new registry capability is introduced.

## Compatibility and migration

The decision is additive. `Chunk`, `ScoredChunk`, `RetrieverInterfaceV1`,
`RerankerInterfaceV1`, `StorageInterfaceV1`, `EmbeddingProviderV1`,
`LLMInterfaceV1`, `ParentPromotionInterfaceV1`,
`MultiSourceRetrievalInterfaceV1`, `RetrievalPlan`, `RetrievalFusionResult`,
and `RetrievalRerankResult` remain unchanged.

No database, vector index, tokenizer asset, or historical evidence migration is
required. Callers that want titles provide immutable exact-version labels;
otherwise markers remain complete through required UUID identity.

## Testing requirements

Implementation acceptance must cover:

- immutable model validation and exact provenance references;
- canonical fixed serialization and `o200k_base` accounting;
- budget bounds, exhaustion, exact fits, and marker/separator overhead;
- mandatory candidate counts zero through three and all-or-empty failure;
- skip-over greedy selection and oversized chunks without truncation;
- exact markers with present/missing title, heading, and page;
- version-specific label matching and duplicate-label rejection;
- per-item sequential compression, exact prompt/schema, 100/120-token rules,
  context-window validation, and compressed-fit/omit behavior;
- absent Extractor degradation versus registered failure/malformed output;
- cancellation and no partial output;
- low-relevance neutrality and RRF-fallback compatibility;
- multi-document/multi-version order and distinct item numbering;
- deterministic repeat with controlled identical compressor output; and
- real Module 6.6 golden handoff using the provisioned ADR-0015 tokenizer.

## Acceptance criteria

Module 6.7 is complete only when:

1. the additive models and ContextBuilder implement this exact contract;
2. no frozen contract or prior-stage evidence is changed;
3. focused, adjacent, cumulative, repository, formatting, lint, type, and
   pre-commit gates pass;
4. real Bhagavad Gita Module 6.6 output is converted twice into the same bounded
   context for identical compression outputs;
5. reported context tokens never exceed the available context tokens;
6. selected/omitted records exactly partition candidates and retain provenance;
7. no retrieval, reranking, backend access, or Module 6.8 behavior occurs; and
8. roadmap/report documentation distinguishes Module 6.7 completion from the
   still-unverified M6 milestone.

## Consequences

- Module 6.8 receives a complete typed context/provenance record rather than a
  lossy string.
- Exact item-level markers avoid storage coupling and ambiguous Source identity.
- Small budgets can lawfully produce typed empty context instead of violating
  top-three or token invariants.
- Provider absence degrades only optional lower-ranked compression; configured
  provider failures remain visible.
- Sequential compression favors deterministic behavior and simplicity over
  throughput for the bounded maximum of 97 eligible candidates.
- LLM wording can vary across runs; the contract guarantees deterministic
  orchestration and rendering for identical validated outputs, not universal
  byte-identical generation.
