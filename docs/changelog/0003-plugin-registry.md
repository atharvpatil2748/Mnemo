# Engineering Changelog 0003: Module 1.2 Core Contracts Complete

- **Completed module:** Phase 1, Module 1.2
- **Status:** Complete
- **Recorded:** 2026-08-07
- **Specification:** [ADR-0002: Core Interface Contracts](../adr/ADR-0002-core-interface-contracts.md)
- **Next module:** Phase 1, Module 1.3 — Plugin Registry System

## Summary

Module 1.2 establishes the typed, transport-independent contracts that later
Mnemo implementations and plugin registrations must satisfy. It contains no
parser, chunker, embedding, retrieval, language-model, or storage behavior.

## Public API delivered

- Explicit V1 protocols and current-version aliases for `ParserInterface`,
  `ChunkerInterface`, `EmbeddingProvider`, `RetrieverInterface`,
  `RerankerInterface`, `LLMInterface`, and `StorageInterface`.
- Per-contract V1 constants for runtime compatibility checks.
- Immutable capability descriptions for every implemented provider contract.
- Immutable records for file metadata, chunking options, embedding batches,
  provider health, language-model messages and completions, and repository
  pages.
- The shared interface exception taxonomy with stable error codes,
  retryability, and immutable details.
- PEP 561 package metadata declaring that `mnemo-core` ships inline typing.

## Architectural decisions carried forward

- `StorageInterface` is the single atomic facade over all storage capabilities;
  infrastructure repositories are not exposed as public properties.
- Provider capability discovery is descriptive, immutable, and side-effect
  free. Extension metadata requires namespaced keys.
- `EmbeddingProvider` owns vector generation; later `EmbedderInterface`
  orchestration owns batching, caching, and provider selection.
- Structural protocol conformance permits plugins without mandatory
  inheritance.
- Cancellation remains in the future public execution design but Module 1.2
  exposes no cancellation primitive.
- Contract signatures contain no transport, framework, database, or concrete
  provider types.

## Compatibility guarantees

- Version 1 contracts use explicit `*V1` names; unversioned names resolve to the
  current V1 contract.
- A breaking contract change requires a new version, with the prior version
  supported for at least two minor releases.
- Capability extensions are additive and namespaced; unknown namespaced keys
  can be ignored safely.
- Exceptions cross core boundaries through Mnemo contract types rather than
  vendor-specific failures.

## Downstream impact

Module 1.3 can validate and order plugin registrations against the V1 contract
surface. Later storage, parser, chunker, embedding, retrieval, server, MCP, and
plugin-ecosystem modules depend on these contracts without importing their
implementations into `mnemo-core`.
