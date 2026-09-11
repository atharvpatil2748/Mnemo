# Engineering Changelog 0024: Phase 0–Module 3.9 Final Audit

**Release:** v0.10.8

## Summary

The final pre-Phase-4 audit reconciled implementation, contracts, ADRs,
architecture, roadmap, tests, package metadata, and release documentation
through Module 3.9.

## Engineering changes

- Clarified exact affected-key snapshot/restore semantics for composite chunk
  replacement and documented the unavoidable Qdrant process-interruption
  reconciliation limitation.
- Reconciled parser, cleaner, classifier, ingestion, canonicalization, asset
  identity, and canonical publication ownership across ADR-0011 through
  ADR-0014.
- Corrected stale architecture and roadmap descriptions without changing any
  frozen public contract.
- Added regression coverage for storage rollback and the immutable asset
  resolution boundary.
- Synchronized all workspace package versions at `0.10.8`.

## Compatibility

No Phase 4 implementation or public contract was introduced. The release
preserves the existing Phase 0–3.9 APIs while correcting storage failure
semantics and completing the documented canonical ingestion path.
