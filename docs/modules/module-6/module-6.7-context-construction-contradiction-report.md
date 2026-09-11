# Module 6.7 Context Construction Contradiction Report

**Status:** BLOCKED at the architectural gate on 2026-08-13.

No Module 6.7 production code, implementation tests, roadmap completion marks,
or Module 6.8 work were created. Modules 6.1–6.6 remain the established input
baseline, and milestone M6 remains unverified.

## Requirement

The roadmap requires Module 6.7 to consume the complete ADR-0042
`RetrievalRerankResult`, compute an available token budget, greedily select
ranked chunks, compress lower-priority content through the Extractor LLM,
format source-attribution markers, and hand a typed context representation to
Module 6.8. Context must remain deterministic, fit its token budget, and retain
the complete Modules 6.1–6.6 provenance.

## Established input boundary

ADR-0042 defines only the input boundary:

```text
RetrievalRerankResult.results in reranked_rank order
    -> Module 6.7 ContextBuilder
```

Every `RerankedChunkResult` retains its exact `FusedChunkResult`; the top-level
record retains the exact `RetrievalFusionResult`. Module 6.7 cannot retrieve,
rerank, expand candidates, flatten evidence, or mutate `Chunk`.

ADR-0042 explicitly states that it does **not** define context token budgets,
compression, or answer behavior. It also says the low-relevance flag may affect
selection only under a future accepted contract.

## Existing reusable contracts

- `TokenCounterInterfaceV1` provides a deterministic synchronous `count(text)`
  operation and a stable `tokenizer_id`.
- `O200KBaseTokenCounter` implements the accepted ADR-0015
  `tiktoken==0.13.0` / verified `o200k_base` asset contract without runtime
  network access.
- `LLMInterfaceV1` exposes async `complete()` and the configured Extractor role,
  but it does not define a context-compression request or response schema.
- `Chunk` provides canonical text, document/version identity, page position,
  heading path, and immutable metadata. It does not guarantee a document title.

These components are reusable, but they do not resolve the semantics below.

## Genuine contradictions and missing decisions

### 1. No canonical output or Module 6.8 handoff

Neither the roadmap nor architecture defines the immutable Module 6.7 output
type. There is no contract for:

- the assembled context string;
- selected versus compressed item records;
- source-marker-to-chunk mapping;
- total and component token counts;
- tokenizer identity;
- budget accounting evidence; or
- retention of the complete `RetrievalRerankResult`.

Returning only a string would destroy the provenance required by the task and
leave Module 6.8 unable to resolve markers without reconstruction. Adding an
unapproved model would guess the 6.8 boundary.

### 2. Token-budget inputs and accounting are undefined

The formula

```text
available = context_budget - system_prompt - question - session_history
```

does not define the Module 6.7 method signature or whether inputs are raw text,
messages, or pre-counted immutable values. It also leaves undefined:

- valid/default/minimum/maximum `context_budget`;
- whether the final context markers and separators consume the available
  budget (they must be counted somehow for the “never exceeds” invariant);
- which exact system prompt is counted before Module 6.8 exists;
- chat/message framing overhead;
- how session history is serialized;
- behavior when fixed overhead equals or exceeds the budget; and
- whether the query in `RetrievalRerankResult.query` must be the budgeted
  question or is supplied again.

Choosing any of these would invent public behavior.

### 3. Greedy selection and truncation are explicitly unresolved

The roadmap says to traverse `reranked_rank` order, but also states that the
“exact selection policy remains Module 6.7 work.” It does not decide:

- skip-overs versus prefix-only selection when the next candidate does not fit;
- whether a later smaller chunk may fill remaining space;
- whether one oversized candidate is omitted, truncated, or compressed;
- minimum useful chunk/compression size;
- exact-fit treatment including marker overhead;
- whether the top three are mandatory even when they cannot fit; or
- how equal-priority cases behave beyond the already deterministic input order.

The architecture separately says to preserve the top three verbatim, which can
conflict with a small caller budget. No precedence or explicit failure rule is
defined.

### 4. Compression is underspecified and conflicts with determinism

The architecture says remaining high-score chunks are summarized to
approximately 100 tokens through the Extractor LLM. It does not define:

- which candidates qualify as “remaining” or “high-score”;
- the exact prompt and input fields;
- whether compression is per chunk or combined;
- exact output schema and chunk/provenance association;
- maximum output tokens and enforcement when output exceeds the target;
- concurrency, ordering, timeout, cancellation, and retry policy;
- provider-unavailable, provider-failure, or malformed-output behavior;
- whether compressed text may be truncated after generation;
- cache semantics; or
- the determinism expectation for an LLM-generated artifact.

`LLMInterfaceV1.complete()` is sufficient as a provider boundary but does not
choose these semantics. Implementing a prompt or failure fallback would be an
architectural decision, not mechanical implementation.

### 5. Attribution-marker data is unavailable from the input contract

The required example includes document title, chapter, and page. The canonical
`Chunk` does not guarantee document title, and Module 6.7 receives no storage
dependency or document snapshot. `heading_path` and `position.page_number` may
also be empty/null.

The architecture does not decide whether Module 6.7 may resolve documents
through `StorageInterfaceV1`, whether callers supply an immutable title map, or
what deterministic marker format applies when title/chapter/page is missing.
Inventing metadata keys or using placeholders would create a second metadata
contract. Direct backend access is prohibited.

### 6. Source numbering and multi-document grouping are undefined

The architecture requires source markers and says multi-document context is
segmented by source document, but does not define:

- whether `[N]` identifies a selected context item, logical document, version,
  or source relationship;
- numbering before or after compression/selection;
- grouping by `document_id` or `(document_id, version_id)`;
- ordering of document groups versus global reranked order;
- behavior for multiple versions of one document; or
- whether repeated chunks from one document share or receive distinct markers.

Grouping can reorder candidates and therefore conflicts with strict traversal
of `reranked_rank` unless precedence is specified.

### 7. Low-relevance behavior is intentionally deferred

ADR-0042 prohibits treating `below_relevance_threshold` as factual confidence
and leaves any selection effect to the Module 6.7 contract. The roadmap and
architecture do not say whether flagged candidates are included, omitted,
compressed first, or merely annotated. Any choice would silently reinterpret
accepted score semantics.

### 8. Empty and insufficient-context outcomes are not typed

No contract defines the result for:

- empty `RetrievalRerankResult`;
- no candidate fitting the available budget;
- only low-relevance candidates;
- fixed overhead exhausting the budget;
- compression yielding no usable text; or
- all compression calls failing.

An empty string, a typed empty context, or an exception have materially
different implications for Module 6.8.

## Why implementation must stop

These are not implementation details that can be inferred from existing code.
They determine the public additive contract, LLM behavior, source numbering,
failure behavior, provenance shape, and the exact Module 6.8 input. Multiple
reasonable implementations would produce observably different contexts and
citations. Implementing one without approval would violate the instruction not
to guess architecture.

No frozen interface needs to change. The contradiction can be resolved with an
additive Phase 6 contract.

## Minimum decision required

Create and accept one focused ADR for deterministic, provenance-preserving
context construction. It must define at minimum:

1. exact `ContextBuilder` method signature and immutable output models;
2. exact Module 6.8 handoff and retained `RetrievalRerankResult` provenance;
3. budget input types, bounds, fixed-overhead serialization, tokenizer identity,
   and inclusion of marker/separator tokens;
4. exact greedy selection, skip, exact-fit, oversized-item, and truncation rules;
5. whether “top three verbatim” is mandatory and behavior when impossible;
6. compression eligibility, prompt/schema, target/hard maximum, concurrency,
   cancellation, determinism, and failure policy;
7. lawful document-title acquisition or a title-independent V1 marker format;
8. source-number identity, version semantics, and multi-document grouping order;
9. low-relevance behavior;
10. empty/insufficient-context behavior; and
11. registry/dependency ownership if Extractor LLM resolution belongs inside
    Module 6.7.

The smallest compliant direction is an additive immutable context result that
retains the exact `RetrievalRerankResult`, contains ordered context-item records
with their exact `RerankedChunkResult`, and records rendered text plus exact
token-accounting evidence. That direction is a recommendation only; it is not
approved architecture in this report.

## Scope state

- Modules 6.1–6.6: **COMPLETE**
- Module 6.7: **BLOCKED / NOT IMPLEMENTED**
- Modules 6.8–6.10: **NOT STARTED**
- M6: **NOT VERIFIED**
- Version: **0.20.1**
- Commit/push/tag/release: **NO**

## Resolution addendum — ADR-0043

Accepted ADR-0043, `Deterministic Provenance-Preserving Context Construction`,
resolves every contradiction above through an additive immutable
`ContextBuildResult` contract. It fixes exact token serialization/accounting,
the mandatory verbatim prefix, deterministic skip-over selection, sequential
Extractor compression, item-level document/version markers, low-relevance
neutrality, typed empty outcomes, and the Module 6.8 handoff without modifying
any frozen contract or adding storage coupling.

The contradiction is therefore **ARCHITECTURALLY RESOLVED**. Module 6.7
production implementation and acceptance remain **NOT STARTED**. Modules
6.8–6.10 remain **NOT STARTED**, and M6 remains **NOT VERIFIED**.
