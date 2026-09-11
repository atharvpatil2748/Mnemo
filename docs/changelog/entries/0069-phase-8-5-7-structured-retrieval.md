# Phase 8.5.7 — Structured retrieval and safe aggregation

Implemented an additive `StructuredQueryV1` execution path over immutable
`RetrievalResultSetV1` evidence. It provides conservative schema observations,
exact-version canonical table extraction, typed normalization, filtering,
sorting, grouping, distinct operations, deterministic aggregates, explicit
missing/completeness states, bounded provenance, and injection-safe execution.

SQLite schema v11 adds immutable generation-scoped table/cell projections.
Canonical chunks, V1 FTS/embeddings/retrieval/Final-QA, HTTP routes, and MCP
tools are unchanged. Multimodal Final-QA and delivery remain future work.
