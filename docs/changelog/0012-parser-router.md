# 0012 - Parser Router (Module 3.1)

**Date:** 2026-08-08
**Module:** 3.1 (Parser Router)
**Version:** 0.10.0

## Implementation Overview

This release completes the implementation of Module 3.1: Parser Router, fulfilling the architectural requirements for Phase 3's initial entrypoint into document parsing. The `ParserRouter` component serves as a pure orchestrator, completely decoupled from format-specific parsing logic.

## Architectural Decisions & Compliance

- **Deduplication First:** The router strictly enforces the `content_hash` deduplication gate *before* performing MIME detection, parser lookup, or execution. This eliminates unnecessary I/O and processing for duplicate documents.
- **Pure Orchestration:** `ParserRouter` contains zero format-specific knowledge (`if pdf`, `if docx`, etc. are forbidden). It routes exclusively based on `PluginRegistry` metadata and resolution.
- **Graceful MIME Detection:** `python-magic` is used for robust file type detection, with a graceful fallback to the built-in `mimetypes` library if `magic` fails. No exceptions terminate the routing flow prematurely.
- **Priority Rules:** The `PluginRegistry` precedence rules are exactly respected, allowing user plugins to override built-in parsers transparently.
- **Error Propagation:** Encountered errors are propagated cleanly without data corruption or semantic modification. Unsupported formats raise a proper `UnsupportedError`.

## Public APIs

- `ParserRouter`: The primary entry point for document routing. Exposes the `route_and_parse()` workflow which handles hashing, lookup, and dispatch.

## Tests

- Achieved >90% code coverage across the module.
- Exhaustive unit tests cover:
  - Deduplication short-circuiting.
  - MIME detection fallback and failure scenarios.
  - Correct `PluginRegistry` dispatch and precedence checking.
  - Error handling for unsupported types.

## Limitations & Future Work

- **Format Parsing:** The router currently delegates to parsers, but the concrete built-in parsers (PDF, DOCX, Markdown, etc.) are slated for Modules 3.2+ (Document Cleaner will intercept prior to actual parsing logic being fully finalized in 3.3+ if we follow the roadmap accurately, but actually Parser implementation comes next per roadmap).
- **No Cleaning Yet:** The `ParserRouter` performs no data cleaning or whitespace normalization. This is the responsibility of the Document Cleaner (Module 3.2).
