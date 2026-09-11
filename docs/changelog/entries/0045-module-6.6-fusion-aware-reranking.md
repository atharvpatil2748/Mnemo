# Changelog 0045: Module 6.6 Fusion-Aware Reranking

## Status

Module 6.6 is implemented and locally validated under ADR-0042. This remains
unreleased Phase 6 work; version 0.20.1 and all existing tags are unchanged.

## Changes

- Added immutable `CrossEncoderEvidence`, `RerankedChunkResult`, and
  `RetrievalRerankResult` records while preserving every frozen Phase 1 and
  Module 6.5 contract.
- Added `FusionRerankingInterfaceV1`, `FusionRerankerCapabilities`, and the
  independent versioned `fusion_reranker/v1` registry family.
- Added `RerankingModule` with normalized original-query handling, exact
  candidate cardinality, deterministic cross-encoder ranking, and typed RRF
  fallback only when the fusion-aware capability is absent.
- Added the pinned CPU sentence-transformers provider for
  `cross-encoder/ms-marco-MiniLM-L6-v2` revision
  `233902d25c440f23af6f7d6e94d2946bac0bee0a`, with 512-token `only_second`
  truncation, batch size 16, startup validation, serialized inference, and
  additive shutdown cleanup.
- Added the optional `mnemo-core[reranking]` dependency boundary, focused
  tests, and a repository-relative real acceptance runner.

The live acceptance reused the real Module 6.5 Bhagavad Gita collection with
1,275 points, reranked ten real fused candidates twice with identical results,
preserved candidate cardinality and all fusion provenance, and independently
verified provider-unavailable fallback and registered-provider failure
propagation.

Module 6.7 remains not started, and milestone M6 is not verified.
