# 0062 — 15-Document Production Certification (v0.25.0)

- **Date:** 2026-08-20
- **Version:** v0.25.0
- **Scope:** Fresh heterogeneous-corpus ingestion, retrieval, Final-QA, API,
  MCP, and production lifecycle certification.

## Added

- Production XLSX parsing with read-only worksheet traversal, row-safe table
  blocks, formula preservation, and canonical sheet metadata.
- Eight additional Golden Corpus sources, expanding the reproducible
  production-ingestion corpus from seven to fifteen documents.

## Fixed

- Preserve non-table PDF spans adjacent to detected tables and prevent mixed
  heading/body blocks from losing body content.
- Use non-mutating PDF overlap calculations against the original span area.
- Preserve short root-level source-code content during structural chunking.
- Serialize nested immutable metadata safely through filesystem and HTTP
  boundaries.
- Bound sparse title candidates before fusion while retaining exact-version
  title provenance through parent promotion and reranking.
- Delete derived title rows during document cascade and use the configured
  content-addressed embedding cache in production ingestion.
- Sanitize streaming error events and honor MCP SSE host/port precedence.

## Certification

- Fresh corpus: 15 documents, 15 versions, 15 sources, 1,514 chunks, 1,514 FTS
  rows, and 1,514 title projections; zero structural orphans or duplicate chunk
  identities.
- Embeddings: 1,514/1,514 content/model cache identities at dimension 768.
- Retrieval: all fifteen representative title/content probes selected the
  intended document; Resume title-aware regression remains generic.
- Persisted Final-QA: grounded publication, canonical citation resolution,
  retry exhaustion safety, fingerprint conflict, and exact replay verified.
- HTTP, streaming, MCP stdio/SSE, all six MCP tools, frontend, Docker, Python
  quality, strict typing, package builds, and source-tree checks passed.

Qdrant remains intentionally disabled in the certified local profile. Local
retrieval is SQLite FTS/title plus cross-encoder reranking; no local
vector-backed hybrid claim is made.
