# Engineering Changelog 0002: Core Interface Contracts

- **Scope:** Phase 1, Module 1.2 architecture specification
- **Status:** Accepted
- **Accepted:** 2026-08-07
- **Specification:** [ADR-0002: Core Interface Contracts](../adr/ADR-0002-core-interface-contracts.md)

## Summary

ADR-0002 freezes Mnemo's version-one contract architecture before Module 1.2
implementation. It defines transport-independent ownership, lifecycle,
concurrency, failure, serialization, capability-discovery, and compatibility
rules for core interfaces.

The specification distinguishes contracts from their implementations. Module
1.2 is authorized to define only the roadmap's parser, chunker, embedding
provider, retriever, reranker, language-model, and atomic storage contracts plus
version markers and directly required contract records. Contracts assigned to
later roadmap phases remain specification-only.

## Contract architecture recorded

- `StorageInterface` remains the single atomic facade over blob, vector,
  keyword, metadata, and graph backends. No repository is exposed as a public
  property.
- `EmbeddingProvider` represents model-provider vector generation;
  `EmbedderInterface` represents later batching, caching, and provider-selection
  orchestration.
- Provider contracts expose immutable descriptive capability metadata without
  probing infrastructure or changing behavior.
- Protocol conformance is structural and contracts are explicitly versioned.
- I/O-facing operations are asynchronous; bounded pure transformations may be
  synchronous.
- Core signatures remain independent of HTTP, FastAPI, MCP, UI frameworks, and
  concrete database or model-provider clients.
- Operational telemetry is restricted to local no-op or in-process metrics;
  analytics and network export remain forbidden.

## Dependencies and downstream impact

The specification adds no runtime dependency. Module 1.2 contracts depend only
on Python 3.12, Module 1.1 domain models, and directly required immutable
contract records.

The accepted contracts govern later storage, parser, chunker, embedding,
retrieval, notebook, plugin, operational, and pipeline implementations. Each
later module remains responsible for implementing its assigned contracts and
must not leak infrastructure-specific types into `mnemo-core`.
