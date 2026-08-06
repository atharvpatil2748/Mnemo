# Engineering Changelog 0002: Module 1.2 Core Interface Contracts

- **Completed module:** Phase 1, Module 1.2
- **Status:** Complete
- **Recorded:** 2026-08-07
- **Specification:** [ADR-0002: Core Interface Contracts](../adr/ADR-0002-core-interface-contracts.md)
- **Previous module:** Phase 1, Module 1.1 — Domain Models
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
- A shared interface exception taxonomy with stable error codes, retryability,
  and immutable details.
- PEP 561 package metadata declaring inline typing.

## Architectural decisions carried forward

- `StorageInterface` is one atomic façade over all storage capabilities;
  infrastructure repositories are not public properties.
- `EmbeddingProvider` owns model vector generation. The later
  `EmbedderInterface` orchestration layer owns batching, caching, and provider
  selection.
- Provider capability discovery is descriptive, immutable, and side-effect
  free; extension metadata requires approved namespaces.
- Structural protocol conformance permits plugins without mandatory
  inheritance.
- Cancellation belongs to later execution modules; Module 1.2 exposes no
  cancellation primitive.
- Contract signatures contain no HTTP, framework, database, or concrete
  provider types.

## Compatibility guarantees

- Version 1 contracts use explicit `*V1` names; unversioned names resolve to
  the current V1 contract.
- Breaking contract changes require a new version and a compatibility window.
- Exceptions cross core boundaries through Mnemo contract types rather than
  vendor failures.

## Downstream impact

Module 1.3 validates plugin registrations against this surface. Later storage,
parser, chunker, embedding, retrieval, server, MCP, and plugin modules depend on
the same contracts without importing their implementations into core.
