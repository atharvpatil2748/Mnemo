# ADR-0057: Title-Aware Cross-Encoder Reranking

- **Status:** Accepted
- **Date:** 2026-08-20
- **Extends:** ADR-0042, ADR-0053
- **Supersedes:** ADR-0042 query-pair construction and deterministic ordering only

## Context

ADR-0053 adds canonical exact-version titles to sparse retrieval without
changing canonical chunk text. Runtime validation showed that ADR-0042's
chunk-text-only pair and score-exclusive ordering can discard that evidence
after fusion: an exact title match may be displaced by a semantically related
chunk from an unrelated document. Adding a title tier only in the provider
then violates ADR-0042's frozen result validator, producing a typed plugin
failure instead of a result.

## Decision

When the derived exact-version title is present on a retrieved candidate, the
cross-encoder document representation is:

```text
Document title: <canonical DocumentVersion.metadata.title>

<canonical Chunk.text>
```

The canonical chunk and its text remain unchanged. Missing title metadata uses
the ADR-0042 chunk-text representation.

For cross-encoder policy, order candidates deterministically by:

```text
(-exact_title_match, -relevance_score, fused_result.global_rank,
 fused_result.chunk.id)
```

`exact_title_match` is the generic boolean provenance emitted by the
ADR-0053 sparse projection. It is not inferred from a filename or recomputed
by the reranker. Within each title-evidence tier the ADR-0042 cross-encoder,
RRF-rank, and chunk-ID ordering remains unchanged. Raw sparse scores, RRF
scores, model logits, canonical chunks, and attribution are never overwritten.

Source diversity may be applied by later bounded context selection, but it
must not mutate the canonical `RetrievalRerankResult` ordering or its evidence.

## Consequences

The result model and built-in provider use one executable ordering contract.
Exact canonical title evidence cannot silently disappear at the reranker
boundary, while content-only queries retain the ADR-0042 behavior. Acceptance
requires synthetic heterogeneous-title tests, missing-metadata tests,
deterministic ties, parent-promotion preservation, and live sparse-only
cross-document validation.
