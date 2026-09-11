# 0040: Phase 5 Corrective Release

**Date:** 2026-08-12
**Release:** v0.20.1

## Summary

v0.20.1 is the immutable corrective patch release for the completed Phase 5
embedding pipeline (Modules 5.1, 5.2, and 5.3 only).

The previously published v0.20.0 tag remains immutable at its original release
commit. GitHub Actions found formatting and validation defects in that release
commit. Corrective commit `855a433836ce55bb40b724993b1438f0afa6a88b` repaired
those defects; the v0.20.1 release then repeated the complete local release
gate and passed GitHub Actions before tagging.

## Scope

- Version synchronization across the workspace, core, server, UI, and
  Email-ingestion plugin.
- Release-documentation reconciliation for the v0.20.1 corrective patch.
- No Phase 6 implementation and no Module 5.4.

## Milestone status

M5 live integration—1,000 chunks embedded through a live Ollama instance and
stored in Qdrant—is **not verified**. This release validates the implementation
and automated checks only.
