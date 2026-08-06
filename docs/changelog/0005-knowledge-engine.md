# Engineering Changelog 0005: Module 1.5 KnowledgeEngine

- **Completed module:** Phase 1, Module 1.5
- **Status:** Complete
- **Recorded:** 2026-08-07
- **Specification:** [ADR-0004: KnowledgeEngine Composition](../adr/ADR-0004-knowledge-engine-composition.md)
- **Previous module:** Phase 1, Module 1.4 — Configuration System
- **Next phase:** Phase 2 — Storage Layer (not started)

## Summary

Module 1.5 completes the Phase 1 core skeleton with a thin, asynchronous
composition root. `KnowledgeEngine` owns plugin discovery, registry freezing,
required-provider resolution, structural startup validation, atomic runtime
publication, lifecycle state, rollback, and in-memory shutdown. It performs no
business operations and makes no external connections.

## Public API delivered

- `KnowledgeEngine(config)` as the top-level core entrypoint.
- Canonical asynchronous `initialize()` and `shutdown()` lifecycle methods.
- Deprecated `startup()` convenience alias for `initialize()`.
- Read-only configuration, current registry, lifecycle state, and package
  version properties.
- Typed access to the resolved primary storage façade, embedding provider,
  primary reranker, and four configured LLM role providers.
- Immutable runtime capability inspection using the existing Module 1.2
  capability records.
- `EngineState` and typed engine initialization and lifecycle exceptions.

## Composition behavior

- Built-in candidates, Python entry points, and immediate configured plugin
  children are discovered in that order.
- Hidden entries, non-Python directories, and nested descendants are excluded
  from configured-directory discovery.
- The registry freezes before required providers are resolved.
- Phase 1 requires the `primary` storage, embedding, and reranker slots plus the
  planner, synthesizer, extractor, and classifier LLM slots.
- Parser, chunker, and retriever slots remain optional for their later roadmap
  phases.
- Failed initialization publishes no partial provider set, replaces the
  attempted registry, and leaves that runtime instance terminally failed.
- A stopped engine can initialize a new runtime with a fresh registry.

## Compatibility guarantees

- `initialize()` is the canonical lifecycle name for documentation and future
  integrations.
- Required slot names and lifecycle-state meanings are stable Phase 1 public
  behavior.
- The engine returns existing provider protocols and capability records rather
  than new wrapper models or concrete implementation types.
- Configuration remains the only source authority; the engine reads no files
  or environment variables directly.
- Phase 1 startup and shutdown never call provider `open()`, `close()`, or
  `health_check()` methods.

## Downstream impact

Phase 2 can supply the concrete `primary` storage façade through the frozen
plugin contracts without changing core composition. Later parser, chunker,
retriever, embedding, reranking, and LLM modules can register implementations
through the same registry slots. REST, MCP, CLI, and UI layers can own one
initialized engine without introducing transport dependencies into core.

## Phase boundary

This entry closes Phase 1. No storage implementation, provider implementation,
runtime business API, or Phase 2 initialization behavior is included.
