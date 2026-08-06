# Engineering Changelog 0006: Phase 1 Baseline Audit

- **Scope:** Phase 0 and Phase 1 release baseline
- **Status:** Complete
- **Recorded:** 2026-08-07
- **Release:** 0.5.1
- **Previous module:** Phase 1, Module 1.5 — KnowledgeEngine
- **Next phase:** Phase 2 — Storage Layer (not started)

## Summary

The post-Phase 1 audit reconciles the architecture, roadmap, ADRs, engineering
history, package metadata, Docker configuration, CI, and GitHub community
surface. It introduces no provider, storage, parsing, retrieval, or business
functionality.

## Baseline corrections

- Synchronized package and workspace versions with the Phase 1 release line.
- Replaced superseded architecture and roadmap shorthand with the accepted
  domain, embedding-provider, configuration, plugin-discovery, chunk-identity,
  and KnowledgeEngine terminology.
- Marked Phase 0 and Phase 1 complete while keeping all Phase 2 work pending.
- Reconciled changelog entries 0002 and 0003 with their actual Module 1.2 and
  Module 1.3 deliverables.
- Aligned Compose environment variables with ADR-0003 and removed the obsolete
  storage backend selector.
- Added release-facing project, contribution, conduct, issue, and pull-request
  documentation.
- Added CI distribution builds and manual workflow dispatch.
- Added tests that protect the package version, public exports, and core
  dependency boundary.

## Compatibility

No accepted Phase 1 public contract changed. The `startup()` alias remains
deprecated as approved; `initialize()` is canonical. Registry legacy support
for `MNEMO_PLUGINS` remains available to standalone Module 1.x callers while
KnowledgeEngine uses resolved configuration exclusively.

## Phase boundary

Phase 2 was not started. The audited baseline contains no concrete storage,
parser, chunker, retriever, embedder, reranker, or LLM implementation.
