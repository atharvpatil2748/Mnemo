# ADR-0014: Ingestion Canonicalization Bridge

**Status:** Accepted
**Date:** 2026-08-11
**Decision owners:** Mnemo maintainers
**Approval:** Granted

## Context

ADR-0011 correctly separates pure parsers from canonical domain models. ADR-0012
places cleaning on `ParseResult`, and ADR-0013 places deterministic
classification after cleaning. The implemented Phase 3 boundary therefore ends
with a classified `ParseResult`. The released `ChunkerInterfaceV1` accepts a
canonical `ParsedDocument`; ADR-0015 defines a V2 contract that preserves that
same canonical Phase 3.9 output while supplying registry identity separately.

At decision time, no implemented component persisted `TransientAsset` values,
resolved their parser-local identifiers to permanent `Asset` identities,
converted raw blocks, or constructed and stored the `ParsedDocument`. Phase 4
could not consume
the actual Phase 3 output until this boundary exists.

At decision time, ADR-0011 named `DocumentCanonicalizer`, but its wording
assigned both model conversion and blob-persistence coordination to a component whose only stated
responsibility is conversion. The implementation order and failure semantics
are also absent from the roadmap.

## Problem

The system needs one explicit bridge that:

- preserves parser, cleaner, and classifier purity;
- performs storage I/O only through `StorageInterfaceV1`;
- guarantees that every `RawImageBlock` resolves to a persisted `Asset`;
- constructs a valid canonical `ParsedDocument` before chunking; and
- defines behavior for deduplication and partial asset-persistence failure.

## Options considered

### 1. Make each chunker accept `ParseResult`

Rejected. It leaks parser transport models into Phase 4, duplicates asset
resolution across chunkers, and weakens `ParsedDocument` canonicality.

### 2. Put persistence and conversion inside every parser

Rejected by ADR-0011. It introduces storage I/O and permanent identity into the
pure parser boundary.

### 3. Let `DocumentCanonicalizer` perform orchestration and storage I/O

Not selected. Although close to some ADR-0011 wording, it combines workflow,
storage, and conversion responsibilities and makes the conversion itself
impossible to test as a pure deterministic transformation.

### 4. Add an internal ingestion pipeline with a pure canonicalizer

Selected. One internal orchestration component sequences existing boundaries
and owns storage interaction. `DocumentCanonicalizer` performs only deterministic
model conversion using already-resolved assets.

## Decision

Add **Phase 3, Module 3.9 — Ingestion Canonicalization Bridge** before Phase 4.
It introduces no transport API and no Phase 4 chunking behavior.

### Ingestion pipeline responsibilities

The internal ingestion pipeline:

1. invokes `ParserRouter` and honors its deduplication result;
2. applies `DocumentCleaner` to a new `ParseResult`;
3. applies the deterministic `DocumentClassifier`;
4. persists every `TransientAsset` through
   `StorageInterfaceV1.put_asset()`;
5. builds an immutable parser-local-ID-to-`Asset` resolution map;
6. invokes `DocumentCanonicalizer` with the classified result and resolution
   map;
7. persists the result with `StorageInterfaceV1.put_parsed_document()`; and
8. returns the canonical `ParsedDocument` required by Phase 4.

The caller supplies the document `version_id`. Stable `Document` and
`DocumentVersion` creation remains owned by the document registry workflow and
is not moved into the canonicalizer.

For a deduplication hit, the pipeline resolves the existing document's current
`ParsedDocument` from storage. A registry record without its corresponding
canonical document is an integrity failure, not a signal to reparse silently.

### DocumentCanonicalizer responsibilities

`DocumentCanonicalizer` is a pure, synchronous, deterministic internal
component. It:

- converts each raw block to its canonical block counterpart without changing
  ordinal, page, bounding-box, language, or namespaced metadata;
- resolves `RawImageBlock.parser_local_id` through the supplied immutable asset
  map and creates `ImageBlock(asset_id=...)`;
- preserves `DocumentMetadata`, document language, and classified `DocType`;
  and
- constructs the immutable `ParsedDocument`, allowing its domain invariants to
  validate the result.

It performs no storage, network, LLM, UUID generation, routing, cleaning, or
classification.

The implemented V1 conversion mapping is one raw block to one canonical block:
`RawTextBlock` to `TextBlock`, `RawHeadingBlock` to `HeadingBlock`,
`RawTableBlock` to `TableBlock`, `RawCodeBlock` to `CodeBlock`, `RawMathBlock`
to `EquationBlock`, and `RawImageBlock` to `ImageBlock`. Because the frozen
canonical hierarchy has no `ListBlock`, `RawListBlock` becomes one `TextBlock`
whose text is the ordered list items joined by newline characters. This
preserves item order and boundaries without adding a new public domain model.

Canonicalization also preserves approved namespaced raw-block metadata without
interpreting or rewriting it. In particular, the ADR-0011
`parser.markdown.*` correction remains parser-owned semantic data: the cleaner
may normalize typed block content but carries the immutable metadata unchanged,
and `DocumentCanonicalizer` copies the same metadata onto the corresponding
canonical block. For `RawListBlock -> TextBlock`, this is how list type,
nesting, marker information, and exact Markdown source remain available to the
later Markdown strategy. The canonicalizer does not parse Markdown, validate a
Markdown AST, derive links, or own Markdown semantics.

ADR-0016 defines an equivalent preservation rule for `parser.email.*` document
and block metadata. The cleaner and canonicalizer carry that immutable metadata
without interpreting MIME, thread relationships, headers, quotes, signatures,
or attachments. The Email parser
remains the sole owner of those source semantics. No Email-specific conversion
or storage orchestration is added to `DocumentCanonicalizer`.

### Asset identity and correlation

`StorageInterfaceV1.put_asset()` remains the sole owner of permanent asset
identity. The pipeline never mints an asset UUID. `ParseResult` requires unique
`TransientAsset.parser_local_id` values and exact correlation between extracted
assets and `RawImageBlock` references. A parser must not emit an image block for
an external reference whose bytes it did not extract; fetching remote or local
references is outside the pure parser boundary.

### Persistence and failure semantics

Asset writes are content-addressed and idempotent. The canonical document is not
published until every asset has been persisted and conversion has succeeded.
The pipeline does not compensate by deleting assets after failure because an
asset may already be shared by another document. A failed attempt may therefore
leave an unreferenced content-addressed asset eligible for later reuse or future
garbage collection, but it cannot leave a partially persisted
`ParsedDocument`.

### Optional LLM-assisted classification

Module 3.9 performs no LLM or network call. A future ingestion enhancement may
insert optional LLM-assisted classification after deterministic classification
and before asset persistence. That enhancement must preserve the
`ParseResult -> ParseResult` classifier boundary and must not be required for
Phase 4.

## Data flow

```text
bytes + filename + version_id
    -> ParserRouter
       -> existing Document -> load current ParsedDocument -> Phase 4
       -> ParseResult
          -> DocumentCleaner
          -> DocumentClassifier
          -> Ingestion pipeline persists TransientAssets via StorageInterfaceV1
          -> immutable local-ID-to-Asset map
          -> DocumentCanonicalizer
          -> ParsedDocument
          -> StorageInterfaceV1.put_parsed_document
          -> Phase 4 ChunkingContext + ChunkerInterfaceV2 (ADR-0015)
```

## Dependencies and ownership

Module 3.9 may depend on Phase 1 contracts/models, `ParserRouter`,
`DocumentCleaner`, `DocumentClassifier`, and `StorageInterfaceV1`. It must not
depend on concrete filesystem, SQLite, Qdrant, or SurrealDB classes; HTTP, MCP,
or UI code; Phase 4 chunkers; or LLM implementations.

Phase 4 depends on Module 3.9 for real ingestion flows. ADR-0015's
contract does not change Module 3.9 ownership or the canonical output type.
Chunker unit tests may
continue to construct canonical fixtures directly.

## Consequences

- Phase 3 remains pure except for the already-approved router deduplication and
  the explicitly identified ingestion orchestration boundary.
- Phase 4 receives exactly one canonical input type.
- Asset identity and persistence remain behind the atomic storage facade.
- The bridge is small but requires async orchestration because storage contracts
  are asynchronous.
- Content-addressed orphan cleanup is explicitly deferred; unsafe deletion-based
  rollback is prohibited.

## Relationship to existing ADRs

- Preserves ADR-0001 canonical domain models.
- Preserves ADR-0002 storage, parser, and chunker contracts.
- Preserves ADR-0006 router deduplication.
- Preserves ADR-0011's raw parser boundary and supersedes only its
  assignment of persistence coordination to `DocumentCanonicalizer`.
- Preserves the cleaner and classifier ordering from ADR-0012 and ADR-0013.

## Implementation status

Accepted and implemented by Module 3.9. Phase 4 has not begun.
