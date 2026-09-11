# Phase 8.5 WP-04 — Cursor and Completeness Unification

- **Date:** 2026-08-27
- **Status:** Complete
- Added the shared, domain-separated `CursorCodecV2` with canonical signed
  state, TTL, key identity, overlap-key verification, and typed restart errors.
- Migrated advanced retrieval and bounded delivery issuance to V2 cursors.
- Bound continuation to immutable snapshot, authorized request identity,
  traversal position, and effective bounds; rejected terminal/stale reuse.
- Retained a decode-only delivery-v1 compatibility path behind a fixed
  process-level overlap deadline.
- Added a lossless transport completeness/coverage mapper and production-mode
  rejection of the built-in signing secret.
- Added focused cursor, delivery, advanced-retrieval, MCP, configuration, and
  completeness regression tests. No schema migration or corpus mutation was
  performed.
