# ADR-0037: Documentation Ingestion Semantic Boundary

**Status:** Accepted
**Date:** 2026-08-12
**Decision owners:** Mnemo maintainers
**Depends on:** ADR-0001, ADR-0002, ADR-0011, ADR-0013, ADR-0014, ADR-0015

## Context

Architecture §10.8 requires the `DocumentationChunker` (Module 4.10) to respect
documentation navigation structure, preserve task blocks atomically, isolate
API reference topics, and preserve callouts with explicit type tags.

The Phase 3 parsers (such as `MarkdownParser`) normalize these constructs into standard `ParsedDocument` blocks (`RawTextBlock`, `RawHeadingBlock`, `RawListBlock`) without producing documentation-specific semantic metadata. Callouts are often flattened into blockquotes or text, task lists into standard lists, and API definitions into unannotated headings.

Because `ChunkerInterfaceV2` strictly prohibits chunkers from reparsing source bytes or resorting to LLM heuristics, the chunker itself cannot extract these semantics reliably.

## Decision

Following the boundaries established in ADR-0017 (Resume) and ADR-0036 (Slides), the semantic annotation of Documentation elements belongs to Phase 3.

1. **Owner:** The `DocumentClassifier` will own the deterministic annotation of documentation semantics.
2. **Trigger:** The annotation is performed strictly and only when `DocType.DOCUMENTATION` is definitively determined.
3. **Metadata Schema:** The classifier will append `parser.documentation.schema_version = 1` to the document metadata, and emit the following block-level metadata under `parser.documentation.*`:
   - `parser.documentation.role`: Can be `callout`, `api_reference`, `task_block`, or `toc`.
   - `parser.documentation.callout_type`: For callouts, values may include `note`, `warning`, `tip`, `caution`.
4. **Heuristics:** The classifier will use deterministic regex matching against `RawHeadingBlock` text, `RawTextBlock` content, and `RawListBlock` items to map these roles.
5. **No Chunker Rewrites:** The `DocumentationChunker` will consume these immutable `parser.documentation.*` annotations exactly as presented, falling closed where annotations are absent or ambiguous.

Unannotated canonical content is not discarded. It remains ordinary
documentation topic content. Missing or malformed metadata required for a
special semantic role fails closed rather than being guessed. This distinction
preserves source content while keeping special-role interpretation explicit.

## Consequences

- **Positive:** The boundary strictly preserves the V2 constraint against reparsing in the chunker layer. Semantics are uniformly presented in the immutable `ParsedDocument`.
- **Positive:** Testing the heuristics is completely isolated within the classifier's domain, leaving the chunker's logic clean.
- **Negative:** The classifier grows slightly more complex with regex-based heuristics for Callouts, Tasks, and APIs. However, this is fundamentally the classifier's responsibility.

## Implementation status

Accepted and implemented. The classifier emits schema-v1 documentation
metadata, canonicalization preserves it, and Module 4.10 consumes the metadata
without source reparsing. Task blocks and callouts remain atomic; callout types
and canonical asset correlations survive in namespaced chunk metadata.
