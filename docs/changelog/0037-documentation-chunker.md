# 0037: Documentation Chunker

**Date:** 2026-08-12
**Module:** Phase 4, Module 4.10
**Release:** v0.19.0
**ADRs:** ADR-0015, ADR-0037

## Summary

Module 4.10 adds the built-in V2 `DocumentationChunker` for
`DocType.DOCUMENTATION`. It consumes canonical schema-v1
`parser.documentation.*` annotations and emits deterministic task-and-topic
drafts without reparsing source.

## Behavior

- Preserves heading navigation, API topics, ToC content, atomic task blocks,
  callout roles/types, canonical asset correlations, and contiguous source
  provenance.
- Keeps atomic tables, equations, code, images, tasks, and callouts intact.
- Splits oversized ordinary prose at paragraph, sentence, then safe word
  boundaries using the supplied canonical token counter.
- Preserves unannotated content as ordinary documentation rather than silently
  discarding it.
- Registers only in the version-qualified V2 `DocType.DOCUMENTATION` slot.
