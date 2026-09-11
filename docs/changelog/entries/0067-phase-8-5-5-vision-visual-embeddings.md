# 0067 — Phase 8.5.5 Vision Analysis and Visual Embeddings

Implemented ADR-0062 on additive SQLite schema v10. The workstream adds typed
provider-neutral vision-analysis and image-embedding requests/results,
deterministic occurrence-scoped derivation and cache identities, immutable
structured observations and vectors, strict dimension/metric/normalization
validation, and independent generation-aware visual-vector projections.

Both operations reuse ADR-0060 durable workers, authorization, consent,
budgets, resource admission, cancellation, bounded retry, cost accounting, and
crash-safe cache replay. Image content and provider output remain untrusted;
SVG, malformed provenance, oversized media/results, invalid vectors, and
cross-notebook cache access are rejected. No provider is silently selected,
Qdrant remains optional, and canonical chunks, FTS, text embeddings, retrieval,
Final QA, HTTP, and MCP V1 contracts are unchanged. Multimodal retrieval and
delivery remain later workstreams.
