# 0077 — Phase 8.5 WP-07 Advanced Retrieval Exposure

Composed the existing advanced retrieval core into the production runtime with
the canonical SQLite/FTS source and frozen V1 sparse/reranking providers. Added
strict bounded request/result DTOs, `POST /v2/retrieval/evidence`, and additive
MCP `search_evidence` with explicit ranked-versus-exhaustive guidance, signed
snapshot continuation, representation coverage, omissions, provenance, and
hard item/byte/character/time ceilings. Canonical text is active; unavailable
derived sources remain explicit and prevent false completeness. V1 search and
all corpus/model/database state remain unchanged.
