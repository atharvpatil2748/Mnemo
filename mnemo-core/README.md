# mnemo-core

`mnemo-core` is the provider-neutral domain and pipeline library for the Mnemo
local knowledge engine. It contains the typed ingestion, document/version/chunk
identity, storage, retrieval, reranking, evidence, provenance, ContextBuilder,
FinalQA, structured, multilingual, OCR, Vision, CLIP, processing, and delivery
contracts used by the server composition.

The current certified V2 profile uses content-addressed filesystem storage, an
immutable SQLite corpus with FTS5 and governed BGE-M3 vectors, and a separate
mutable operational SQLite store. Qdrant remains an optional V1/future
vector-scale adapter; SurrealDB remains a partial future graph adapter. Current
production reranking is BGE-reranker-v2-m3, not the historical MS-Marco
evaluation provider.

Phase 8.5 is completed/certified, Phase 8.6 is a validated evaluation-only
notebook, and Phase 8.7 is a completed MCP capability milestone. Phase 8.8 is
designed but not implemented; Phase 9 remains gated on Phase 8.8 verification.

See the [current architecture](../docs/architecture/current/mnemo_architecture_v2.md),
[engineering roadmap](../docs/architecture/current/mnemo_engineering_roadmap.md),
and [documentation index](../docs/README.md) for authoritative status and
navigation.
