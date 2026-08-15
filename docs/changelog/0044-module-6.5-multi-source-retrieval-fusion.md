# Changelog 0044: Module 6.5 Multi-Source Retrieval and Fusion

## Status

Module 6.5 is implemented and locally validated under ADR-0041. This is
unreleased Phase 6 work; version 0.20.1 and all existing tags remain unchanged.

## Changes

- Added `MultiSourceRetrievalInterfaceV1` and immutable invocation, evidence,
  fused-result, and orchestration-result models without changing frozen Phase 1
  contracts.
- Added `MultiSourceRetriever` for bounded fail-fast invocation scheduling,
  per-invocation dense embeddings, registry-based dense/sparse dispatch, and
  one source-local parent-promotion call per stream.
- Added canonical chunk-ID deduplication with conflicting-snapshot rejection,
  complete raw-evidence provenance, deterministic unweighted RRF (`k=60`),
  contiguous global ranks, and caller-supplied global truncation.
- Added focused orchestration/fusion tests and a repository-relative live
  acceptance runner using the verified Bhagavad Gita corpus, Ollama, Qdrant,
  SQLite sparse retrieval, and ParentRetriever.

The live run produced 1,275 canonical chunks and Qdrant points, four bounded
source-local streams, 24 deduplicated fusion candidates, and a deterministic
top-10 result. The corpus has no stored parent families, so the real promoter
correctly ran as a no-op; controlled family behavior remains covered by the
Module 6.4 storage fixtures and Module 6.5 focused tests.

Modules 6.6–6.10 remain not started, and milestone M6 is not verified.
