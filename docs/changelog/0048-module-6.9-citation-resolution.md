# Changelog 0048: Module 6.9 Citation Resolution and Persistence

## Status

Module 6.9 is implemented and locally validated under ADR-0045. This remains
unreleased Phase 6 work; version 0.20.1 and all existing tags are unchanged.

## Changes

- Added immutable `CitationResolutionStatus` and `CitationResolutionResult`
  records retaining the exact grounded-answer and assistant-turn handoff.
- Added backend-neutral `CitationEngine` with strict marker parsing, typed
  provenance resolution, exact-version title validation, deterministic UUIDv5
  identities, and one injected UTC timestamp per cited invocation.
- Preserved full canonical quotes for verbatim, compressed, and parent-promoted
  context while retaining all upstream retrieval, fusion, reranking, context,
  and generation evidence.
- Persisted fully prevalidated citations sequentially through
  `StorageInterfaceV1`; no direct backend access, batch transaction, rollback,
  retry, timeout, or partial result was introduced.
- Added 33 focused tests and a real Bhagavad Gita Modules 6.5–6.9 acceptance
  runner with isolated SQLite persistence through `CompositeStorage` and
  durable evidence.

Real acceptance resolved a repeated `[source:1]` marker to one deterministic
citation, reloaded it from SQLite, preserved its 1,768-character canonical
quote and exact document/version identity, and demonstrated convergent repeated
upsert behavior.

Module 6.10 remains not started, and milestone M6 is not verified.
