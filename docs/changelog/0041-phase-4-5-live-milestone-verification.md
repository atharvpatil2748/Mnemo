# 0041: Phase 4–5 Live Milestone Verification

**Date:** 2026-08-13
**Release:** none (verification work on top of v0.20.1)

## Summary

The two roadmap acceptance milestones left open by the Phase 4 and Phase 5
releases have now executed successfully with real local data and services.

- M4: the 952-page repository Bhagavad Gita produced 1,275 deterministic
  chunks with all 18 authored chapter/title paths and zero required invariant
  violations.
- M5: 1,000 real M4 chunks were embedded by local Ollama
  `nomic-embed-text` at 768 dimensions, stored through QdrantStore, and all
  1,000 were independently read back from an isolated Qdrant collection.

The 10,000-chunk performance benchmark was not executed and remains open.

## Corrections

- Recognize word-numbered chapter headings and the corpus's clickable ToC
  syntax.
- Preserve chapter/title hierarchy across decorative images that emit no
  chunk.
- Use the installed SurrealDB 2.x asynchronous websocket lifecycle behind the
  existing HTTP(S) configuration boundary.
- Add focused regressions, an opt-in live pytest acceptance test, a repeatable
  verification runner, Markdown reports, and machine-readable evidence.

No Phase 6 functionality, Module 5.4, release, version, or tag was created.
Remote CI was not run during this local verification.
