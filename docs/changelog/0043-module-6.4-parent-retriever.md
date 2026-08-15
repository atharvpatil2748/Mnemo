# Changelog 0043: Module 6.4 ParentRetriever

## Status

Module 6.4 is implemented and locally validated under ADR-0040. This is
unreleased Phase 6 work; version 0.20.1 and all existing tags remain unchanged.

## Changes

- Added `ParentPromotionInterfaceV1` and immutable capability metadata.
- Added the backend-neutral, asynchronous `ParentRetriever` source-local
  transformation.
- Added the versioned `parent_promotion` PluginRegistry capability family.
- Enforced complete canonical family, exact-document/version, sibling symmetry,
  score/source, rank, ordering, single-pass, and failure semantics.
- Added focused unit tests and real `CompositeStorage`/SQLite integration tests.
- Added a repository-relative golden acceptance runner for the verified
  Bhagavad Gita corpus.

The golden BookChunker output contains 1,275 root chunks and no canonical
parent families, so golden evidence validates deterministic no-op behavior and
zero relationship lookups. Controlled canonical SQLite fixtures validate
promotion thresholds and integrity behavior without altering the corpus.

Module 6.5 and later modules remain not started, and milestone M6 is not
verified.
