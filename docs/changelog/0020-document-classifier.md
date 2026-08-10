# 0020: Document Classifier and Boundary Formalization

**Date:** 2026-08-08  
**Module:** 3.8  
**Version:** 0.10.7  

## Overview
Module 3.8 introduces the `DocumentClassifier`, completing the pure Phase 3 transformation sequence. The classifier determines the `DocType` of a document using a deterministic, rule-based heuristic approach. It is the final pure `ParseResult` transformation before the ingestion canonicalization bridge proposed in ADR-0014.

## Implementation Details

### Deterministic Rule-Based Classification
The `DocumentClassifier` evaluates documents in strict precedence:
1. **Extension Precedence**: E.g., `.py` or `.js` strictly assigns `DocType.CODE`, while `.md` assigns `DocType.MARKDOWN`.
2. **Heading Precedence**: Identifies structural markers like "Abstract" (`PAPER`), "Chapter" (`BOOK`), "Experience" (`RESUME`), and "API Reference" (`DOCUMENTATION`).
3. **Structural Precedence**: Computes the ratio of code blocks to total structural blocks. If code blocks exceed 80%, the document is classified as `CODE`.

### GENERIC Fallback
Documents that lack strong heuristic signals safely fall back to `DocType.GENERIC`. The classifier never speculates or hallucinates a document type when confidence is low.

### Architectural Impact and ADR-0013
- **ADR-0013** formalized the boundary of the `DocumentClassifier` as a pure, synchronous, side-effect-free component (`ParseResult -> ParseResult`).
- The roadmap originally specified an "LLM-assisted classification" for Module 3.8. To preserve the purity of Phase 3, this requirement was formally decoupled and **deferred to future orchestration layers**. Module 3.8 performs **no network I/O** and **no storage I/O**.

## Validation
- 415 tests passing cleanly across the repository.
- Module and repository test coverage securely maintained above 90% (`90.81%`).
- Strict typing and linting enforced via `mypy --strict` and `ruff`.

## Compatibility and Migration
No breaking changes. The `DocType` enumeration remains fully intact, and downstream components (which do not yet exist) will receive properly categorized `ParseResult` objects without relying on a default `GENERIC` assignment in all cases.
