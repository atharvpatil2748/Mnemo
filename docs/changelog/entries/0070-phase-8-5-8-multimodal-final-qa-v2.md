# Phase 8.5.8 — Multimodal context, citations, and Final-QA V2

Implemented additive typed multimodal candidates, bounded named-space rank
fusion and diversity, provider capability negotiation, authorization-safe
context construction, `EvidenceCitationV2`, strict ADR-0054 citation retry,
and ADR-0056-compatible immutable Final-QA V2 publication/replay.

SQLite schema v12 adds independent V2 execution, snapshot, and typed citation
tables. Canonical chunks, V1 FTS/embeddings/retrieval/Final-QA, HTTP routes, and
the six MCP tools are unchanged. Multilingual retrieval, concrete multimodal
provider profiles, and versioned HTTP/MCP V2 delivery remain future work.
