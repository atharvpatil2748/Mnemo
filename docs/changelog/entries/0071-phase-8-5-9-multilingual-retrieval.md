# Phase 8.5.9 — Multilingual processing and retrieval

Implemented additive BCP-47/ISO-15924 language and script observations,
uncertainty/mixed-script provenance, deterministic translation and
transliteration derivation identities, provider-neutral multilingual embedding
and reranker profiles, capability-aware same/cross-language planning, bounded
RRF, explicit completeness, and answer-language policy over Final-QA V2.

SQLite schema v13 adds immutable, authorization-scoped language observations,
derived language representations, and multilingual embedding records. Existing
canonical text, FTS, embeddings, V1 retrieval/Final-QA, HTTP routes, MCP tools,
and Qdrant configuration are unchanged. No production multilingual model is
selected or certified; profile benchmarking remains Phase 8.5.11 work.

## 2026-08-29 — WP-10 Stage 1 buildability

Added the additive Stage-1 implementation: a strict V2 language-evidence
reference, conservative EN/HI/MR detector, offline exact-revision BGE-M3 and
BGE reranker adapters, deterministic observation/derivation and embedding
generation builders, bounded authorized SQLite cosine search, and the shared
advanced-retrieval injection seam. This establishes BUILDABLE only. It neither
activates a multilingual generation nor changes the frozen multimodal database,
Golden Dataset, V1 vector space, or any certification threshold.
