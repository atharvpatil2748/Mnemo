# 0068 — Phase 8.5.6 Advanced Retrieval and Completeness

Implemented ADR-0058 as an additive core-only V2 retrieval boundary. The
workstream adds typed ranked and exhaustive plans/results, authorized
source/document/version and positional scopes, explicit stage budgets,
identity-aware deduplication, provenance-preserving rank fusion, bounded
parent/adjacent expansion, representation diagnostics, stable snapshot
identities, and opaque notebook/request-scoped signed cursors.

`COMPLETE` is emitted only after deterministic exhaustive termination on an
unchanged snapshot. Ranked results remain `UNKNOWN` or `PARTIAL`; unavailable
or failed representations cannot become `NO_MATCH`. Canonical SQLite
enumeration reuses existing chunks, FTS, and title projections, so no schema
migration or canonical-data rebuild was required. V1 retrieval, Final QA,
HTTP, MCP, and Qdrant optionality are unchanged. Structured aggregation,
multimodal Final QA, multilingual retrieval, and V2 delivery remain pending.
