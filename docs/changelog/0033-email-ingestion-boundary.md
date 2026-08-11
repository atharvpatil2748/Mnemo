# 0033: Email Ingestion Semantic Boundary

**Date:** 2026-08-11
**Scope:** ADR-0016 prerequisite for Phase 4, Module 4.7
**Version:** `0.17.0`
**ADR:** [ADR-0016](../adr/ADR-0016-email-ingestion-semantic-boundary.md)

## Summary

Adds the optional `email-ingestion` V1 parser plugin. It converts one supplied
`.eml` or `mbox` container into deterministic raw blocks and immutable
`parser.email.*` metadata without network, filesystem, storage, clock, UUID, or
randomness dependencies.

## Behavior

- Supports `.eml`/`message/rfc822` and `.mbox`/`application/mbox`; Outlook
  `.msg` remains explicitly unsupported.
- Preserves every source message, canonicalizes RFC message identifiers,
  resolves only unambiguous local parents, orders messages deterministically,
  and computes ADR-0016 thread correlations.
- Selects MIME bodies deterministically, preserves quoted/signature regions,
  records attachments, and emits transient assets only for supported inline
  images.
- Proves immutable Email metadata survives ParseResult through cleaning and
  canonicalization into `ParsedDocument` unchanged.

Module 4.7 `EmailChunker` is not included. The accepted ingestion boundary is
its validated prerequisite.
