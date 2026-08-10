# Engineering Changelog 0021: Phase 0–3.8 Architecture Audit

**Date:** 2026-08-11
**Baseline audited:** 0.10.7

## Summary

The Phase 0–3.8 repository was cross-checked across implementation, contracts,
ADRs, architecture, roadmap, tests, packaging, CI, changelogs, and Git release
metadata. The audit confirmed the raw parser boundary but demonstrated that the
canonicalization bridge required before Phase 4 is not implemented.

## Corrections

- Enforced exact parser-local correlation between `RawImageBlock` and
  `TransientAsset` values.
- Prevented pure HTML and Markdown parsers from emitting unresolved external
  image references without extracted bytes.
- Registered all completed Phase 3 parsers as built-in plugin candidates and
  deprecated the obsolete no-op router registration method without breaking
  its existing call surface.
- Corrected built-in plugin descriptor names to satisfy the registry's frozen
  identifier contract; the prior dotted storage name could not be loaded.
- Removed Markdown from the plain-text parser's format claims so registry
  precedence is deterministic.
- Fixed deterministic language detection seeding in `DocumentCleaner`.
- Corrected architecture, roadmap, README, milestone, and changelog drift.
- Declared Twine in the locked development toolchain so the repository's own
  package-validation script works in a clean environment.
- Removed the duplicate, obsolete `0014-html-parser.md` entry; the authoritative
  Module 3.5 history remains `0017-html-parser.md`.

## Architectural checkpoint

ADR-0014 proposes Module 3.9 as the minimum ingestion canonicalization bridge.
It is intentionally specification-only pending review. Phase 4 remains
unstarted.
