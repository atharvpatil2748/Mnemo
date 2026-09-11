# ADR-0036: Slides Ingestion Semantic Boundary

**Status:** Accepted
**Date:** 2026-08-12
**Decision owners:** Mnemo maintainers
**Depends on:** ADR-0001, ADR-0002, ADR-0011, ADR-0013, ADR-0014, ADR-0015

## Context

Architecture section 10.7 assigns Phase 4 a Slides chunking strategy that requires deterministic isolation of individual slides (one chunk per slide), including title, body text, and speaker notes. It also requires the identification of the title slide, which serves as a `SUMMARY` chunk for the presentation.

Currently, the Phase 3 parsing boundary extracts textual blocks and headings, but the `ParsedDocument` lacks presentation metadata. The parser pipeline preserves `page_number`, which corresponds to slide boundaries, but fails to structurally distinguish between slide titles, body text, and speaker notes.

Without a deterministic semantic boundary in Phase 3, Module 4.9 `SlidesChunker` would be forced to guess slide roles and title slide bounds, violating its pure chunking contract (ADR-0015).

## Problem

Mnemo requires a deterministic Slides semantic boundary that:
- Provides Module 4.9 with sufficient structured metadata (slide boundaries, title slide flag, role annotations) via `ParsedDocument`.
- Derives deterministically from existing raw parser structures (e.g., `page_number`) without inventing semantics.
- Preserves the existing `ParseResult -> DocumentCleaner -> DocumentClassifier -> DocumentCanonicalizer` pipeline.
- Fails closed when Slides structures (like speaker notes) cannot be explicitly determined.

## Decision

The `DocumentClassifier` will own the deterministic Slides semantic boundary fallback. When it assigns `DocType.SLIDES` (via `.ppt`/`.pptx` or heuristics), it will perform a pure, rule-based pass over the `ParseResult` blocks to assign canonical slide metadata.

It will emit this structural information as immutable, JSON-serializable block metadata prefixed with `parser.slide.`.

## Metadata Schema

### Document Metadata
| Key | Type | Meaning |
|---|---|---|
| `parser.slide.schema_version` | integer | Exactly `1`. |

### Block Metadata
| Key | Type | Meaning |
|---|---|---|
| `parser.slide.number` | integer | The canonical slide index, mapped from `page_number` or sequential order if `page_number` is missing. |
| `parser.slide.is_title_slide` | boolean | `True` for blocks on the first slide. |
| `parser.slide.role` | string | Identifies the semantic purpose of the block (`title`, `body`, `notes`, `section_divider`). Defaults to `body` if undetermined. |

## Fail-Closed Rules

1. **Slide Boundaries**: Grouped by `page_number`. If `page_number` is `None` across the entire document, the classifier fails closed and groups all blocks into a single slide (`parser.slide.number = 1`).
2. **Title Slide**: The first encountered `parser.slide.number` is treated as the title slide (`is_title_slide = True`).
3. **Role Identification**: The first `RawHeadingBlock` on a slide is annotated as `role = "title"`. All other text blocks default to `role = "body"` unless the upstream parser explicitly tagged them otherwise (e.g., as `notes`). The classifier will **not** guess speaker notes from generic text.

## Module 4.9 Dependency

Module 4.9 `SlidesChunker` consumes this schema to safely fulfill its architectural contract.

## Implementation status

Accepted and implemented. The classifier emits schema-v1 slide metadata, the
canonicalizer preserves it, and Module 4.9 consumes it without reparsing source
or inferring structure from chunk text.
