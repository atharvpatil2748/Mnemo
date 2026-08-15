# Changelog 0046: Module 6.7 Context Construction

## Status

Module 6.7 is implemented and locally validated under ADR-0043. This remains
unreleased Phase 6 work; version 0.20.1 and all existing tags are unchanged.

## Changes

- Added immutable `DocumentContextLabel`, `CompressionEvidence`, `ContextItem`,
  and `ContextBuildResult` records with typed item and empty-result enums.
- Added backend-neutral `ContextBuilder` consuming the complete Module 6.6
  `RetrievalRerankResult` without retrieval, reranking, storage access,
  candidate expansion, RRF recomputation, or canonical chunk mutation.
- Implemented exact ADR-0043 fixed-envelope and rendered-context token
  accounting through the existing `TokenCounterInterfaceV1`.
- Implemented the all-or-empty top-three verbatim prefix and deterministic
  skip-over greedy traversal for all remaining reranked candidates.
- Reused the existing `llm/extractor` registry slot for sequential per-item
  structured compression with the exact 100-token target and 120-token hard
  maximum.
- Added exact version-aware attribution markers, focused contract tests, and a
  real Module 6.6 golden-handoff acceptance runner and evidence record.

Real acceptance converted ten Bhagavad Gita reranked candidates into four
bounded items: three verbatim and one controlled compressed item. The result
used exactly 1,596 available context tokens, omitted six candidates, repeated
deterministically for identical compressor outputs, and preserved the complete
selected/omitted provenance partition and canonical chunks.

Module 6.8 remains not started, and milestone M6 is not verified.
