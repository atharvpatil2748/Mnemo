# 0078 — Phase 8.5 WP-08 Structured Query Exposure

Composed the existing structured projection and typed execution core into the
production runtime. Added authorized exact-version dataset/schema discovery, a
strict public DTO-to-`StructuredQueryV1` compiler, compatible union and explicit
typed equality join, signed bounded continuation, row/cell provenance, hard
scan/group/field/evidence/byte/time limits, `POST /v2/retrieval/structured`, and
MCP `query_structured`. The runtime activates execution only for a complete
active generation. No raw SQL, V1 retrieval change, schema migration, corpus
mutation, or future multimodal/Final-QA orchestration was introduced.
