# ADR-0062: Vision Analysis and Visual Embedding Spaces

- **Status:** Accepted
- **Implementation:** Complete for Phase 8.5.5 — provider-neutral vision and
  image-embedding contracts, immutable derivations/cache, governed execution,
  and independent SQLite visual-vector generations; concrete providers and
  retrieval integration remain intentionally pending
- **Date:** 2026-08-24
- **Extends:** ADR-0018, ADR-0059, ADR-0060
- **Supersedes:** Nothing

## Context

The text embedding contract is model/dimension guarded but cannot represent
image inputs. VLM descriptions and visual vectors have different cost,
security, and compatibility properties.

## Problem

Mnemo needs optional image understanding and retrieval without pretending that
unrelated vector spaces have comparable scores or widening frozen text V1.

## Decision

Add independent `VisionAnalysisProviderV1`, `ImageEmbeddingProviderV1`, and,
only for models proven to share a space, `MultimodalEmbeddingProviderV1`.
Vision results are versioned structured derivations with description,
observations, confidence, language, safety flags, and complete
provider/model/config provenance.

Default topology uses separate text and image collections/index generations.
A shared collection is permitted only when a pinned model contract guarantees
compatible text/image vectors, dimensions, normalization, and benchmarked
cross-modal quality. Retrieval fuses ranks across spaces; raw distances are
never compared across incompatible spaces.

Cache identity includes input asset hash, occurrence-sensitive operation when
needed, provider, model revision, preprocessing version, dimensions,
normalization, and config digest. Qdrant remains optional; derived sparse
descriptions may operate without it, but local deployments must not claim
visual vector retrieval when disabled.

## Alternatives

- Extend the text provider: rejected because it breaks V1 and hides modality.
- One universal collection: rejected without a guaranteed shared space.
- Store only VLM text: rejected because it cannot support native visual search.

## Consequences

Multiple index generations increase storage and operational complexity but
make model migration and rollback safe.

## Compatibility

Text embeddings, cache keys, Qdrant optionality, and existing collections are
unchanged. New providers and indexes are additive.

## Migration

Create side-by-side generation metadata and optional collections. Promote an
alias only after dimension, identity, and benchmark certification.

## Security implications

Image content is untrusted; provider egress needs ADR-0060 consent. Descriptions
cannot authorize access to original assets.

## Testing requirements

Test dimensions, normalization, shared-space claims, cache keys/invalidation,
missing vectors, stale generations, rank fusion, provider cancellation, and
malicious images.

## Observability

Record model-space ID, generation, vector counts, cache outcome, latency,
resource/cost usage, and typed failures without vectors or content.

## Rollback/recovery

Detach collection/index aliases and disable providers; preserve derivation
records for audit or controlled deletion.

## Future-phase impact

Phase 11 may add cross-modal reasoning, and Phase 13 benchmarks each space and
generation independently.

## Explicit non-goals

This ADR does not select a model or require Qdrant/cloud processing.
