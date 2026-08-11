# ADR-0017: Resume Ingestion Semantic Boundary

**Status:** Proposed
**Date:** 2026-08-11
**Decision owners:** Mnemo maintainers
**Depends on:** ADR-0001, ADR-0002, ADR-0011, ADR-0012, ADR-0013, ADR-0014, ADR-0015

## Context

Architecture section 10.3 assigns Phase 4 a Resume chunking strategy that requires deterministic isolation of canonical sections (Contact, Summary, Experience, Education, Skills, Projects, Publications) and explicit boundaries for individual roles within the Experience section. ADR-0015 requires all Phase 4 strategies to consume only a canonical `ParsedDocument` and forbids reparsing source bytes, generating UUIDs, or using LLMs.

Currently, the Phase 3 parsing boundary (PDF, DOCX, Markdown, HTML) extracts textual blocks and headings, and the `DocumentClassifier` (Module 3.8) correctly assigns `DocType.RESUME` based on heading heuristics. However, no component formally isolates the Resume sections or annotates role boundaries. The structural semantics required by Module 4.8 are completely absent from the `ParsedDocument`. 

Without a deterministic semantic boundary in Phase 3, Module 4.8 would be forced to invent structure, guess role boundaries from weak text evidence, or violate its pure chunking contract.

## Problem

Mnemo requires a deterministic Resume semantic boundary that:
- Provides Module 4.8 with sufficient structured metadata (sections, roles) via `ParsedDocument`.
- Derives deterministically from existing raw parser structures (e.g., `RawHeadingBlock`, `RawTextBlock`) without introducing a complex new `ResumeParser` plugin or external AI dependency.
- Preserves the existing `ParseResult -> DocumentCleaner -> DocumentClassifier -> DocumentCanonicalizer` pipeline.
- Assigns no UUIDs or permanent chunk identities during parsing.
- Fails closed when Resume structures are ambiguous.

## Options Considered

1. **Extend an existing Resume parser / Introduce a new plugin:** Rejected. There is currently no dedicated `ResumeParser` or `deepdoc` integration in the Phase 3 implementation. Introducing one would require major new parsing dependencies.
2. **Introduce a Resume-specific parser/cleaner stage:** Rejected. Adds a new pipeline stage, complicating orchestration.
3. **Extend existing parser metadata via the DocumentClassifier:** The `DocumentClassifier` already processes `ParseResult`, iterates over blocks, and identifies Resume-specific headings to assign `DocType.RESUME`. It is perfectly positioned to simultaneously annotate blocks with deterministic `parser.resume.*` metadata before canonicalization.

## Decision

Adopt **Option 3: Extend existing parser metadata via the DocumentClassifier**.

The `DocumentClassifier` will be extended to own the deterministic Resume semantic boundary. When it assigns `DocType.RESUME`, it will perform a second, pure, rule-based pass over the `ParseResult` blocks to assign canonical section boundaries and role boundaries. It will emit this structural information as immutable, JSON-serializable block metadata prefixed with `parser.resume.`.

The `DocumentCanonicalizer` will naturally preserve this metadata and expose it on the `ParsedDocument`, providing the Module 4.8 `ResumeChunker` with the exact semantic boundaries required.

## Resume Section and Role Semantics

### Sections
Sections are identified deterministically by encountering a `RawHeadingBlock` matching canonical patterns (e.g., "Experience", "Education"). All subsequent blocks belong to that section until a new canonical section heading is encountered. Blocks with insufficient evidence (e.g., blocks before the first canonical section heading) must be left unset/unclassified; the system must fail closed rather than guess. Unclassified blocks will be handled by chunkers as a fallback `unknown` section.

### Roles
Within the `experience` section, a new role boundary is explicitly defined as any child `RawHeadingBlock` (a heading with a deeper level than the section heading). 
If roles are formatted merely as bold text within a `RawTextBlock`, the boundary is considered ambiguous. The classifier will fail closed: it will group all ambiguous blocks under the parent experience section without inventing a local role identifier.

## Proposed Metadata Schema

### Document Metadata
| Key | Type | Meaning |
|---|---|---|
| `parser.resume.schema_version` | integer | Exactly `1`. |

### Block Metadata
| Key | Type | Meaning |
|---|---|---|
| `parser.resume.section` | string | Canonical section name (e.g., `contact`, `summary`, `experience`, `education`, `skills`, `projects`, `publications`). |
| `parser.resume.role_local_id` | string or null | Deterministic parser-local key for a role within an experience section (e.g., `role-000001`). Null if not within an explicit role. |

## Determinism and Provenance

- The `role_local_id` is a sequential, parser-local string (`role-000001`) that resets per document. It is NOT a UUID or a chunk ID.
- The metadata does not alter the canonical chunk identity formula (ADR-0001).
- The `DocumentClassifier` relies entirely on existing `ParseResult` blocks and performs no network, storage, or LLM I/O.

## Required Acceptance Tests

1. Classifier correctly assigns `parser.resume.section` based on strict heading matches.
2. Classifier detects role boundaries from nested `RawHeadingBlock` elements and assigns sequential `parser.resume.role_local_id`.
3. Classifier fails closed on ambiguous role boundaries (no `RawHeadingBlock` present).
4. Metadata is immutable, JSON-serializable, and deterministic across repeated runs.
5. Canonicalizer faithfully preserves `parser.resume.*` block metadata on the `ParsedDocument`.
6. No UUIDs, chunk IDs, or network calls are generated.

## Module 4.8 Dependency

Module 4.8 `ResumeChunker` SHALL remain unimplemented until:
- ADR-0017 is reviewed and Accepted.
- The `DocumentClassifier` is updated to emit the `parser.resume.*` schema.
- All boundary acceptance tests pass.
